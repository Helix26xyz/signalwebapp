"""End-to-end: the real app spawns tests/fake_signal_cli.py as its signal-cli subprocess."""

import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

FAKE = Path(__file__).parent / "fake_signal_cli.py"
ALICE = "bbbbbbbb-0000-4000-8000-000000000002"
GID = "R3JvdXAxMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Njc4OTA="
ME = "+15550000001"
A = f"/api/accounts/{ME}"  # routes for one account live under here


def wait_for(fn, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        value = fn()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("timed out")


@pytest.fixture
def env(tmp_path, monkeypatch):
    with running_app(tmp_path, monkeypatch) as e:
        yield e


@contextmanager
def running_app(tmp_path, monkeypatch):
    inject = tmp_path / "inject"
    inject.mkdir(exist_ok=True)
    log = tmp_path / "rpc.log"
    monkeypatch.setenv("FAKE_INJECT_DIR", str(inject))
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("FAKE_AUTO_LINK", "1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SIGNAL_CLI_CMD", f"{sys.executable} {FAKE}")
    app = create_app(Settings())
    counter = iter(range(10**6))

    def push(envelope: dict, account: str | None = None):
        f = inject / f"{next(counter):06d}.json"
        payload = {"envelope": envelope, **({"account": account} if account else {})}
        f.with_suffix(".tmp").write_text(json.dumps(payload))
        f.with_suffix(".tmp").rename(f)

    def calls(method=None):
        if not log.exists():
            return []
        reqs = [json.loads(line) for line in log.read_text().splitlines()]
        return [r for r in reqs if method is None or r["method"] == method]

    with TestClient(app) as client:
        yield client, push, calls


def test_link_receive_send_flow(env):
    client, push, calls = env
    assert wait_for(lambda: client.get("/api/status").json()["state"] == "unlinked")

    link = client.post("/api/link").json()
    assert link["uri"].startswith("sgnl://linkdevice") and "<svg" in link["qr_svg"]
    status = wait_for(lambda: (s := client.get("/api/status").json())["state"] == "ready" and s)
    assert [a["id"] for a in status["accounts"]] == [ME] and status["last_linked"]["account"] == ME
    assert calls("sendSyncRequest"), "should ask the phone for contacts/groups after linking"
    wait_for(lambda: any("Alice" in p["name"] for p in client.get(f"{A}/contacts").json()["people"]))

    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "status"
        push({"sourceUuid": ALICE, "sourceNumber": "+15550000002", "sourceName": "Alice P", "timestamp": 1_700_000_000_000,
              "serverReceivedTimestamp": 1_700_000_000_100,
              "dataMessage": {"timestamp": 1_700_000_000_000, "message": "hello from alice",
                              "attachments": [{"id": "pic1.jpg", "contentType": "image/jpeg", "filename": "pic.jpg", "size": 11}]}})
        event = ws.receive_json()
        while event["type"] != "message":
            event = ws.receive_json()
        assert event["message"]["body"] == "hello from alice"

    convs = client.get(f"{A}/conversations").json()
    [c] = [c for c in convs if c["id"] == f"u:{ALICE}"]
    assert c["name"] == "Alice Contact" and c["unread"] == 1

    # attachment falls back to getAttachment when the file isn't on local disk
    att = client.get(f"{A}/attachments/pic1.jpg")
    assert att.status_code == 200 and att.content == b"fake-bytes-pic1.jpg"
    assert att.headers["content-type"] == "image/jpeg"
    assert client.get(f"{A}/attachments/..%2Fetc%2Fpasswd").status_code == 404

    # sender-controlled names and types: non-ASCII filenames work, active content never renders inline
    push({"sourceUuid": ALICE, "sourceNumber": "+15550000002", "timestamp": 1_700_000_000_050,
          "dataMessage": {"timestamp": 1_700_000_000_050, "message": "",
                          "attachments": [{"id": "page1.html", "contentType": "text/html", "filename": "фото \"x\".html"}]}})
    wait_for(lambda: client.get(f"{A}/conversations/u:{ALICE}").json()["last_preview"] == "📎 Attachment")
    html = client.get(f"{A}/attachments/page1.html")
    assert html.headers["content-disposition"].startswith("attachment;")
    assert "filename*=utf-8''%D1%84%D0%BE%D1%82%D0%BE" in html.headers["content-disposition"]
    assert html.headers["x-content-type-options"] == "nosniff"
    assert client.get(f"{A}/attachments/pic1.jpg").headers["content-disposition"].startswith("inline;")

    # reading sends a read receipt (signal-cli turns it into a read-sync for our phones too)
    client.post(f"{A}/conversations/u:{ALICE}/read")
    [receipt] = calls("sendReceipt")
    assert receipt["params"]["recipient"] == ALICE and receipt["params"]["targetTimestamp"] == [1_700_000_000_000, 1_700_000_000_050]
    assert client.get(f"{A}/conversations/u:{ALICE}").json()["unread"] == 0

    # reply with quote + attachment
    incoming = client.get(f"{A}/conversations/u:{ALICE}/messages").json()[0]
    assert incoming["body"] == "hello from alice"
    sent = client.post(
        f"{A}/conversations/u:{ALICE}/messages",
        data={"text": "hi alice", "quote_id": str(incoming["id"])},
        files=[("files", ("note.txt", b"hello file", "text/plain"))],
    ).json()
    assert sent["outgoing"] and sent["status"] == "sent" and sent["quote"]["text"] == "hello from alice"
    [send] = calls("send")
    p = send["params"]
    assert p["recipient"] == [ALICE] and p["message"] == "hi alice" and p["account"] == "+15550000001"
    assert p["quoteTimestamp"] == 1_700_000_000_000 and p["quoteAuthor"] == ALICE
    assert p["attachments"][0].startswith("data:text/plain;filename=note.txt;base64,")
    local = client.get(f"{A}/attachments/{sent['attachments'][0]['id']}")
    assert local.content == b"hello file"

    # edit, react, delete for everyone
    client.post(f"{A}/conversations/u:{ALICE}/messages", data={"text": "hi Alice!", "edit_id": str(sent["id"])})
    assert calls("send")[-1]["params"]["editTimestamp"] == sent["sent_ts"]
    r = client.post(f"{A}/messages/{incoming['id']}/react", json={"emoji": "👍"})
    assert r.status_code == 200, r.text
    assert calls("sendReaction")[-1]["params"]["targetAuthor"] == ALICE
    client.post(f"{A}/messages/{sent['id']}/delete", json={"everyone": True})
    assert calls("remoteDelete")[-1]["params"]["targetTimestamp"] == sent["sent_ts"]
    msgs = {m["id"]: m for m in client.get(f"{A}/conversations/u:{ALICE}/messages").json()}
    assert msgs[sent["id"]]["deleted"] and msgs[incoming["id"]]["reactions"][0]["emoji"] == "👍"

    # a message sent from the phone shows up as ours, via sync transcript
    now = int(time.time() * 1000) + 1000
    push({"sourceUuid": "aaaaaaaa-0000-4000-8000-000000000001", "sourceNumber": "+15550000001", "timestamp": now,
          "syncMessage": {"sentMessage": {"destinationUuid": ALICE, "timestamp": now, "message": "sent on my phone"}}})
    wait_for(lambda: client.get(f"{A}/conversations/u:{ALICE}").json()["last_preview"] == "sent on my phone")

    # group: send goes to groupId
    # start chat: picking a contact sends its UUID (dashes and all); typing a number gets normalized
    r = client.post(f"{A}/conversations", json={"recipient": ALICE})
    assert r.status_code == 200 and r.json()["id"] == f"u:{ALICE}", r.text
    r = client.post(f"{A}/conversations", json={"recipient": "+1 555-000-0002"})
    assert r.json()["id"] == f"u:{ALICE}", "known number resolves to the contact's UUID"
    assert client.post(f"{A}/conversations", json={"recipient": "+1 555 abc"}).status_code == 400
    assert client.post(f"{A}/conversations", json={"recipient": "self"}).json()["id"] == "u:self"

    client.post(f"{A}/conversations", json={"group_id": GID})
    client.post(f"{A}/conversations/g:{GID}/messages", data={"text": "hi fam"})
    assert calls("send")[-1]["params"]["groupId"] == GID
    assert client.get(f"{A}/conversations/g:{GID}").json()["name"] == "Family"

    # search
    hits = client.get(f"{A}/search", params={"q": "phone"}).json()
    assert [h["body"] for h in hits] == ["sent on my phone"]

    # UI is served
    assert "Signal Web" in client.get("/").text


ME2, ME2_ACI = "+15550000009", "99999999-0000-4000-8000-000000000009"
B = f"/api/accounts/{ME2}"
DAN = "eeeeeeee-0000-4000-8000-000000000005"


def test_multiple_accounts(tmp_path, monkeypatch):
    """An existing single-account install keeps its history; a second account gets its own."""
    from app.ingest import Ingestor
    from app.store import Store

    # The layout before multi-account support: one DB in DATA_DIR, account already linked.
    data = tmp_path / "data"
    legacy = Store(data / "signal-web.db")
    legacy.set_meta("account", ME)
    legacy.set_meta("self_ids", json.dumps([ME, "aaaaaaaa-0000-4000-8000-000000000001"]))
    ing = Ingestor(legacy)
    ing.self_ids = {ME}
    ing.handle({"envelope": {"sourceUuid": ALICE, "sourceNumber": "+15550000002", "timestamp": 1000,
                             "dataMessage": {"timestamp": 1000, "message": "from before the upgrade"}}})
    legacy.close()
    (data / "signal-cli").mkdir(parents=True)
    (data / "signal-cli" / "fake-accounts.json").write_text(
        json.dumps([{"number": ME, "aci": "aaaaaaaa-0000-4000-8000-000000000001"}]))

    with running_app(tmp_path, monkeypatch) as (client, push, calls):
        status = wait_for(lambda: (s := client.get("/api/status").json())["state"] == "ready" and s)
        assert [a["id"] for a in status["accounts"]] == [ME]
        [conv] = client.get(f"{A}/conversations").json()
        assert conv["last_preview"] == "from before the upgrade"
        assert client.get("/healthz").json() == {"state": "ready"}  # open endpoint: no numbers

        # link a second account
        gen = client.post("/api/link").json()["gen"]
        status = wait_for(lambda: (s := client.get("/api/status").json())["last_linked"] and s)
        assert status["last_linked"] == {"gen": gen, "account": ME2} and not status["linking"]
        assert [a["id"] for a in status["accounts"]] == [ME, ME2]
        assert (data / "accounts" / "15550000009" / "signal-web.db").exists()
        assert (data / "signal-web.db").exists(), "legacy history stays where it was"
        assert [c["params"]["account"] for c in calls("sendSyncRequest")] == [ME2]
        names = wait_for(lambda: (n := {a["id"]: a["name"] for a in client.get("/api/accounts").json()})[ME2] and n)
        assert names == {ME: "Pat Q", ME2: "Work"}  # own profile names label the switcher

        with client.websocket_connect("/ws") as ws:
            # the same person writes to both of your numbers: two separate histories
            for acct, text in ((ME, "hi number one"), (ME2, "hi number two")):
                push({"sourceUuid": ALICE, "sourceNumber": "+15550000002", "timestamp": 2000,
                      "dataMessage": {"timestamp": 2000, "message": text}}, account=acct)
            seen = {}
            while len(seen) < 2:
                ev = ws.receive_json()
                if ev["type"] == "message":
                    seen[ev["account"]] = ev["message"]["body"]
            assert seen == {ME: "hi number one", ME2: "hi number two"}

        push({"sourceUuid": DAN, "sourceNumber": "+15550000005", "timestamp": 3000,
              "dataMessage": {"timestamp": 3000, "message": "work stuff"}}, account=ME2)
        # sent from the second account's phone: "self" means that account there, not the first one
        push({"sourceUuid": ME2_ACI, "sourceNumber": ME2, "timestamp": 3500,
              "syncMessage": {"sentMessage": {"destinationUuid": DAN, "timestamp": 3500, "message": "on it"}}},
             account=ME2)
        wait_for(lambda: any(c["last_preview"] == "on it" for c in client.get(f"{B}/conversations").json()))
        one = {c["id"]: c for c in client.get(f"{A}/conversations").json()}
        two = {c["id"]: c for c in client.get(f"{B}/conversations").json()}
        assert set(one) == {f"u:{ALICE}"} and set(two) == {f"u:{ALICE}", f"u:{DAN}"}
        assert two[f"u:{DAN}"]["name"] == "Dan Work" and two[f"u:{DAN}"]["last_author"] == "self"
        assert one[f"u:{ALICE}"]["last_preview"] == "hi number one" and one[f"u:{ALICE}"]["unread"] == 2
        assert [a["unread"] for a in client.get("/api/accounts").json()] == [2, 2]
        assert client.get(f"{A}/search", params={"q": "work"}).json() == []

        # actions go out from the account they belong to
        client.post(f"{B}/conversations/u:{DAN}/messages", data={"text": "reply from work"})
        assert calls("send")[-1]["params"]["account"] == ME2
        client.post(f"{A}/conversations/u:{ALICE}/read")
        assert calls("sendReceipt")[-1]["params"]["account"] == ME
        assert client.get(f"{B}/conversations/u:{ALICE}").json()["unread"] == 1

        assert client.get("/api/accounts/+19999999999/conversations").status_code == 404
        # the ACI works as an alias for the URL key
        assert client.get(f"/api/accounts/{ME2_ACI}/conversations").status_code == 200
