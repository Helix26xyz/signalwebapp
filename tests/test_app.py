"""End-to-end: the real app spawns tests/fake_signal_cli.py as its signal-cli subprocess."""

import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

FAKE = Path(__file__).parent / "fake_signal_cli.py"
ALICE = "bbbbbbbb-0000-4000-8000-000000000002"
GID = "R3JvdXAxMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Njc4OTA="


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
    inject = tmp_path / "inject"
    inject.mkdir()
    log = tmp_path / "rpc.log"
    monkeypatch.setenv("FAKE_INJECT_DIR", str(inject))
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("FAKE_AUTO_LINK", "1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SIGNAL_CLI_CMD", f"{sys.executable} {FAKE}")
    app = create_app(Settings())
    counter = iter(range(10**6))

    def push(envelope: dict):
        f = inject / f"{next(counter):06d}.json"
        f.with_suffix(".tmp").write_text(json.dumps({"envelope": envelope}))
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
    assert status["account"] == "+15550000001"
    assert calls("sendSyncRequest"), "should ask the phone for contacts/groups after linking"
    wait_for(lambda: any("Alice" in p["name"] for p in client.get("/api/contacts").json()["people"]))

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

    convs = client.get("/api/conversations").json()
    [c] = [c for c in convs if c["id"] == f"u:{ALICE}"]
    assert c["name"] == "Alice Contact" and c["unread"] == 1

    # attachment falls back to getAttachment when the file isn't on local disk
    att = client.get("/api/attachments/pic1.jpg")
    assert att.status_code == 200 and att.content == b"fake-bytes-pic1.jpg"
    assert att.headers["content-type"] == "image/jpeg"
    assert client.get("/api/attachments/..%2Fetc%2Fpasswd").status_code == 404

    # reading sends a read receipt (signal-cli turns it into a read-sync for our phones too)
    client.post(f"/api/conversations/u:{ALICE}/read")
    [receipt] = calls("sendReceipt")
    assert receipt["params"]["recipient"] == ALICE and receipt["params"]["targetTimestamp"] == [1_700_000_000_000]
    assert client.get(f"/api/conversations/u:{ALICE}").json()["unread"] == 0

    # reply with quote + attachment
    incoming = client.get(f"/api/conversations/u:{ALICE}/messages").json()[0]
    sent = client.post(
        f"/api/conversations/u:{ALICE}/messages",
        data={"text": "hi alice", "quote_id": str(incoming["id"])},
        files=[("files", ("note.txt", b"hello file", "text/plain"))],
    ).json()
    assert sent["outgoing"] and sent["status"] == "sent" and sent["quote"]["text"] == "hello from alice"
    [send] = calls("send")
    p = send["params"]
    assert p["recipient"] == [ALICE] and p["message"] == "hi alice" and p["account"] == "+15550000001"
    assert p["quoteTimestamp"] == 1_700_000_000_000 and p["quoteAuthor"] == ALICE
    assert p["attachments"][0].startswith("data:text/plain;filename=note.txt;base64,")
    local = client.get(f"/api/attachments/{sent['attachments'][0]['id']}")
    assert local.content == b"hello file"

    # edit, react, delete for everyone
    client.post(f"/api/conversations/u:{ALICE}/messages", data={"text": "hi Alice!", "edit_id": str(sent["id"])})
    assert calls("send")[-1]["params"]["editTimestamp"] == sent["sent_ts"]
    r = client.post(f"/api/messages/{incoming['id']}/react", json={"emoji": "👍"})
    assert r.status_code == 200, r.text
    assert calls("sendReaction")[-1]["params"]["targetAuthor"] == ALICE
    client.post(f"/api/messages/{sent['id']}/delete", json={"everyone": True})
    assert calls("remoteDelete")[-1]["params"]["targetTimestamp"] == sent["sent_ts"]
    msgs = {m["id"]: m for m in client.get(f"/api/conversations/u:{ALICE}/messages").json()}
    assert msgs[sent["id"]]["deleted"] and msgs[incoming["id"]]["reactions"][0]["emoji"] == "👍"

    # a message sent from the phone shows up as ours, via sync transcript
    now = int(time.time() * 1000) + 1000
    push({"sourceUuid": "aaaaaaaa-0000-4000-8000-000000000001", "sourceNumber": "+15550000001", "timestamp": now,
          "syncMessage": {"sentMessage": {"destinationUuid": ALICE, "timestamp": now, "message": "sent on my phone"}}})
    wait_for(lambda: client.get(f"/api/conversations/u:{ALICE}").json()["last_preview"] == "sent on my phone")

    # group: send goes to groupId
    client.post("/api/conversations", json={"group_id": GID})
    client.post(f"/api/conversations/g:{GID}/messages", data={"text": "hi fam"})
    assert calls("send")[-1]["params"]["groupId"] == GID
    assert client.get(f"/api/conversations/g:{GID}").json()["name"] == "Family"

    # search
    hits = client.get("/api/search", params={"q": "phone"}).json()
    assert [h["body"] for h in hits] == ["sent on my phone"]

    # UI is served
    assert "Signal Web" in client.get("/").text
