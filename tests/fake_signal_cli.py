#!/usr/bin/env python3
"""A stand-in for `signal-cli ... jsonRpc` used by the tests and for UI development.

It speaks the same newline-delimited JSON-RPC over stdin/stdout. Extras for testing:
  * every request is appended to $FAKE_LOG (one JSON per line)
  * any *.json file dropped into $FAKE_INJECT_DIR is emitted as a `receive` notification
    (contents = the {"envelope": ...} object) and then deleted
  * FAKE_AUTO_LINK=1 makes finishLink succeed after 0.3s. Each successful link adds the next
    account from ACCOUNTS, like linking a second phone number
  * multi-account like the real thing: listContacts/listGroups answer per `account` param, and an
    injected payload's "account" field says which account received it (default: the first)
"""

import json
import os
import sys
import threading
import time
from pathlib import Path

args = sys.argv[1:]
config = Path(args[args.index("--config") + 1]) if "--config" in args else Path(".")
config.mkdir(parents=True, exist_ok=True)
accounts_file = config / "fake-accounts.json"
ACCOUNTS = [
    {"number": "+15550000001", "aci": "aaaaaaaa-0000-4000-8000-000000000001"},
    {"number": "+15550000009", "aci": "99999999-0000-4000-8000-000000000009"},
]
ACCOUNT = ACCOUNTS[0]
ALICE = {"number": "+15550000002", "uuid": "bbbbbbbb-0000-4000-8000-000000000002"}
DAN = {"number": "+15550000005", "uuid": "eeeeeeee-0000-4000-8000-000000000005"}

log_path = os.environ.get("FAKE_LOG")
inject_dir = Path(os.environ["FAKE_INJECT_DIR"]) if os.environ.get("FAKE_INJECT_DIR") else None
out_lock = threading.Lock()
subscription = {"id": None}


def write(obj):
    with out_lock:
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()


def accounts():
    return json.loads(accounts_file.read_text()) if accounts_file.exists() else []


def account_for(params):
    """Multi-account mode: account-scoped methods must say which account (like signal-cli)."""
    for a in ACCOUNTS:
        if params.get("account") in (a["number"], a["aci"]) and a in accounts():
            return a
    raise ValueError(f"unknown account {params.get('account')!r}")


def handle(method, params):
    if method == "listAccounts":
        return accounts()
    if method == "subscribeReceive":
        subscription["id"] = 0
        return 0
    if method == "startLink":
        return {"deviceLinkUri": "sgnl://linkdevice?uuid=test&pub_key=test"}
    if method == "finishLink":
        if os.environ.get("FAKE_AUTO_LINK") != "1":
            time.sleep(3600)
        time.sleep(0.3)
        linked = accounts()
        new = next((a for a in ACCOUNTS if a not in linked), None)
        if new is None:
            raise RuntimeError("all fake accounts are already linked")
        accounts_file.write_text(json.dumps(linked + [new]))
        return new
    if method not in ("listAccounts", "subscribeReceive", "startLink", "finishLink"):
        account_for(params)
    if method == "send":
        return {"timestamp": int(time.time() * 1000), "results": [{"type": "SUCCESS"}]}
    if method in ("sendReaction", "remoteDelete", "sendReceipt", "sendTyping", "sendSyncRequest"):
        return {"timestamp": int(time.time() * 1000), "results": [{"type": "SUCCESS"}]}
    if method == "listContacts":
        me = account_for(params)
        if me is ACCOUNTS[1]:
            return [
                {**DAN, "name": "Dan Work", "profile": {"givenName": "Dan"}, "isBlocked": False},
                {"number": me["number"], "uuid": me["aci"], "name": "", "profile": {"givenName": "Work"}},
            ]
        return [
            {**ALICE, "name": "Alice Contact", "profile": {"givenName": "Alice", "familyName": "P"}, "isBlocked": False},
            {"number": me["number"], "uuid": me["aci"], "name": "", "profile": {"givenName": "Pat", "familyName": "Q"}},
        ]
    if method == "listGroups":
        me = account_for(params)
        if me is ACCOUNTS[1]:
            return []
        return [{"id": "R3JvdXAxMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Njc4OTA=", "name": "Family", "isMember": True,
                 "members": [{"number": me["number"], "uuid": me["aci"]}, ALICE]}]
    if method == "getAttachment":
        import base64
        return {"data": base64.b64encode(b"fake-bytes-" + params["id"].encode()).decode()}
    if method == "getAvatar":
        raise LookupError("no avatar")
    raise NotImplementedError(method)


def injector():
    while True:
        time.sleep(0.05)
        if subscription["id"] is None or not inject_dir or not inject_dir.exists():
            continue
        for f in sorted(inject_dir.glob("*.json")):
            payload = json.loads(f.read_text())
            payload.setdefault("account", ACCOUNT["number"])
            write({"jsonrpc": "2.0", "method": "receive",
                   "params": {"subscription": subscription["id"], "result": payload}})
            f.unlink()


def serve(req):
    if log_path:
        with open(log_path, "a") as fh:
            fh.write(json.dumps(req) + "\n")
    try:
        result = handle(req["method"], req.get("params") or {})
        write({"jsonrpc": "2.0", "id": req["id"], "result": result})
    except Exception as exc:  # noqa: BLE001
        write({"jsonrpc": "2.0", "id": req["id"], "error": {"code": -1, "message": f"{type(exc).__name__}: {exc}"}})


threading.Thread(target=injector, daemon=True).start()
for line in sys.stdin:
    if line.strip():
        threading.Thread(target=serve, args=(json.loads(line),), daemon=True).start()
