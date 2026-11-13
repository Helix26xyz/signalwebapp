"""Webhook sending: GUI settings per account, POST /api/hooks/send, and the relay process in front of it."""

import json

import httpx
from fastapi.testclient import TestClient

from app.config import RelaySettings
from app.webhook import create_relay
from tests.test_app import ALICE, running_app, wait_for

ME, ME2 = "+15550000001", "+15550000009"
LINKED = [{"number": ME, "aci": "aaaaaaaa-0000-4000-8000-000000000001"},
          {"number": ME2, "aci": "99999999-0000-4000-8000-000000000009"}]


def forward_to(app_client: TestClient, fail_first: int = 0) -> httpx.MockTransport:
    """Join the relay's HTTP client straight to the app under test (optionally failing to connect first)."""
    failures = {"left": fail_first}

    def handler(request: httpx.Request) -> httpx.Response:
        if failures["left"] > 0:
            failures["left"] -= 1
            raise httpx.ConnectError("connection refused", request=request)
        keep = {k: v for k, v in request.headers.items() if k in ("authorization", "content-type")}
        r = app_client.request(request.method, request.url.path, content=request.content, headers=keep)
        return httpx.Response(r.status_code, content=r.content, headers={"content-type": r.headers["content-type"]})

    return httpx.MockTransport(handler)


def test_webhook_relay_sends_only_for_enabled_accounts(tmp_path, monkeypatch):
    (tmp_path / "data" / "signal-cli").mkdir(parents=True)
    (tmp_path / "data" / "signal-cli" / "fake-accounts.json").write_text(json.dumps(LINKED))

    with running_app(tmp_path, monkeypatch) as (app, push, calls):
        wait_for(lambda: len(app.get("/api/status").json()["accounts"]) == 2)
        wait_for(lambda: any("Alice" in p["name"] for p in app.get(f"/api/accounts/{ME}/contacts").json()["people"]))
        relay_settings = RelaySettings(signal_web_url="http://signal-web", retry_seconds=5)
        with TestClient(create_relay(relay_settings, transport=forward_to(app))) as relay:
            # nothing is allowed until the number is enabled in the GUI
            assert app.get(f"/api/accounts/{ME}/webhook").json() == {"enabled": False, "token": None}
            assert relay.post("/send", json={"to": ME, "message": "x"}).status_code == 401  # no token
            r = relay.post("/send", json={"to": ME, "message": "x"}, headers={"Authorization": "Bearer swh_nope"})
            assert r.status_code == 401 and r.json()["detail"] == "Unknown webhook token"
            assert app.post("/api/hooks/send", json={"recipient": ME, "message": "x"}).status_code == 401

            hook = app.put(f"/api/accounts/{ME}/webhook", json={"enabled": True}).json()
            assert hook["enabled"] and hook["token"].startswith("swh_")
            auth = {"Authorization": f"Bearer {hook['token']}"}

            # JSON with aliases and a sloppily typed number: goes out from this account to Alice
            r = relay.post("/send", json={"to": "+1 555-000-0002", "text": "Backup finished"}, headers=auth)
            assert r.status_code == 200, r.text
            assert r.json()["ok"] and r.json()["account"] == ME and r.json()["conversation_id"] == f"u:{ALICE}"
            send = calls("send")[-1]["params"]
            assert send["account"] == ME and send["recipient"] == [ALICE] and send["message"] == "Backup finished"
            conv = app.get(f"/api/accounts/{ME}/conversations/u:{ALICE}").json()
            assert conv["last_preview"] == "Backup finished" and conv["last_author"] == "self"

            # plain-text body, recipient and token in the query (for senders that can't set headers)
            r = relay.post(f"/send?to=self&token={hook['token']}", content=b"Disk 91% full",
                           headers={"Content-Type": "text/plain"})
            assert r.status_code == 200 and calls("send")[-1]["params"]["noteToSelf"] is True

            # bad input is rejected before anything is sent
            n = len(calls("send"))
            assert relay.post("/send", json={"message": "no recipient"}, headers=auth).status_code == 400
            assert relay.post("/send", json={"to": "+12", "message": "x"}, headers=auth).status_code == 400
            assert relay.post("/send", content=b"[1]", headers={**auth, "Content-Type": "application/json"}).status_code == 400
            assert relay.post("/send", json={"to": ME, "message": "x" * 70_000}, headers=auth).status_code == 413
            assert len(calls("send")) == n

            # each account has its own token, and it sends from that account only
            assert app.get(f"/api/accounts/{ME2}/webhook").json() == {"enabled": False, "token": None}
            hook2 = app.put(f"/api/accounts/{ME2}/webhook", json={"enabled": True}).json()
            assert hook2["token"] != hook["token"]
            r = relay.post("/send", json={"to": "self", "message": "from work"}, headers={"X-Webhook-Token": hook2["token"]})
            assert r.json()["account"] == ME2 and calls("send")[-1]["params"]["account"] == ME2

            # turning it off in the GUI stops it; regenerating invalidates the old token
            app.put(f"/api/accounts/{ME}/webhook", json={"enabled": False})
            r = relay.post("/send", json={"to": "self", "message": "x"}, headers=auth)
            assert r.status_code == 403 and "turned off" in r.json()["detail"]
            new = app.put(f"/api/accounts/{ME}/webhook", json={"enabled": True, "regenerate": True}).json()
            assert relay.post("/send", json={"to": "self", "message": "x"}, headers=auth).status_code == 401
            assert relay.post("/send", json={"to": "self", "message": "x"},
                              headers={"Authorization": f"Bearer {new['token']}"}).status_code == 200

            assert relay.get("/healthz").json() == {"relay": "ok", "signal_web": "ready"}

        # the main app restarting: the relay keeps retrying while it can't connect...
        auth = {"Authorization": f"Bearer {new['token']}"}
        with TestClient(create_relay(relay_settings, transport=forward_to(app, fail_first=2))) as relay:
            assert relay.post("/send", json={"to": "self", "message": "after restart"}, headers=auth).status_code == 200
        # ...and gives up with 503 once the retry window is over
        quick = RelaySettings(signal_web_url="http://signal-web", retry_seconds=0)
        with TestClient(create_relay(quick, transport=forward_to(app, fail_first=99))) as relay:
            r = relay.post("/send", json={"to": "self", "message": "x"}, headers=auth)
            assert r.status_code == 503 and r.json()["detail"] == "Signal Web is unreachable"
