"""Run the UI against the fake signal-cli with some seeded conversations (no Signal account needed).

    python -m tests.demo            # then open http://localhost:8080
    DEMO_ACCOUNTS=1 python -m tests.demo   # only one linked account (default: two)
"""

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn

ME = ("aaaaaaaa-0000-4000-8000-000000000001", "+15550000001")
WORK = ("99999999-0000-4000-8000-000000000009", "+15550000009")
DAN = ("eeeeeeee-0000-4000-8000-000000000005", "+15550000005")
ALICE = ("bbbbbbbb-0000-4000-8000-000000000002", "+15550000002")
BOB = ("cccccccc-0000-4000-8000-000000000003", "+15550000003")
CARA = ("dddddddd-0000-4000-8000-000000000004", "+15550000004")
NAMES = {BOB[0]: "Bob Martin", CARA[0]: "Cara Lee"}
GID = "R3JvdXAxMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Njc4OTA="


def seed(inject: Path, accounts: int) -> None:
    n = iter(range(10**6))
    now = int(time.time() * 1000)
    group = {"groupId": GID, "groupName": "Family", "revision": 1, "type": "DELIVER"}

    def push(src, ts, account=ME, **body):
        f = inject / f"{next(n):06d}.json"
        env = {"sourceUuid": src[0], "sourceNumber": src[1], "sourceName": NAMES.get(src[0], ""), "timestamp": ts, "serverReceivedTimestamp": ts, **body}
        f.with_suffix(".tmp").write_text(json.dumps({"envelope": env, "account": account[1]}))
        f.with_suffix(".tmp").rename(f)

    def me(ts, dest=None, **msg):
        sent = {"timestamp": ts, **msg}
        if dest:
            sent.update(destinationUuid=dest[0], destinationNumber=dest[1])
        push(ME, ts, syncMessage={"sentMessage": sent})

    day = 86400000
    t = now - 2 * day
    push(ALICE, t, dataMessage={"timestamp": t, "message": "Are we still on for Saturday?"})
    me(t + 60000, ALICE, message="Yes! 10am at the trailhead 🥾")
    push(ALICE, t + 120000, dataMessage={"timestamp": t + 120000, "message": "Perfect. I'll bring coffee ☕"})
    push(ALICE, t + 125000, dataMessage={"timestamp": t + 125000, "reaction": {"emoji": "❤️", "targetAuthorUuid": ME[0], "targetSentTimestamp": t + 60000, "isRemove": False}})
    t = now - 3 * 3600000
    push(ALICE, t, dataMessage={"timestamp": t, "message": "Check this out https://example.com/trail-map"})
    me(t + 30000, ALICE, message="Whoa, that's a long one", quote={"id": t, "authorUuid": ALICE[0], "text": "Check this out https://example.com/trail-map", "attachments": []})
    push(ALICE, t + 90000, receiptMessage={"when": t + 90000, "isDelivery": False, "isRead": True, "isViewed": False, "timestamps": [t + 30000]})
    push(ALICE, now - 60000, dataMessage={"timestamp": now - 60000, "message": "👍"})

    t = now - day
    push(BOB, t, dataMessage={"timestamp": t, "message": "Hey everyone — dinner at our place Sunday?", "groupInfo": group})
    push(CARA, t + 50000, dataMessage={"timestamp": t + 50000, "message": "I'm in!", "groupInfo": group})
    me(t + 90000, message="Count us in. Bringing dessert 🍰", groupInfo=group)
    push(BOB, t + 95000, dataMessage={"timestamp": t + 95000, "reaction": {"emoji": "😂", "targetAuthorUuid": ME[0], "targetSentTimestamp": t + 90000, "isRemove": False}, "groupInfo": group})
    push(CARA, now - 20 * 60000, dataMessage={"timestamp": now - 20 * 60000, "message": "Can someone send the address again? I keep losing it 🙈", "groupInfo": group})
    push(BOB, now - 18 * 60000, dataMessage={"timestamp": now - 18 * 60000, "message": "123 Maple St — ring the side door", "groupInfo": group,
                                               "textStyles": [{"style": "BOLD", "start": 0, "length": 12}]})

    me(now - 5 * day, ME, message="Wifi password: correct-horse-battery-staple")
    push(CARA, now - 4 * day, dataMessage={"timestamp": now - 4 * day, "message": "Thanks for the book recommendation!"})

    if accounts < 2:
        return
    t = now - 5 * 3600000
    push(DAN, t, WORK, dataMessage={"timestamp": t, "message": "Can you review the Q3 deck before 3?"})
    push(WORK, t + 60000, WORK, syncMessage={"sentMessage": {"timestamp": t + 60000, "destinationUuid": DAN[0], "destinationNumber": DAN[1], "message": "On it"}})
    push(DAN, now - 7 * 60000, WORK, dataMessage={"timestamp": now - 7 * 60000, "message": "Thanks! Slide 12 still has last year's numbers"})


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="signal-web-demo-"))
    inject = tmp / "inject"
    inject.mkdir()
    os.environ.update(
        DATA_DIR=str(tmp / "data"),
        SIGNAL_CLI_CMD=f"{sys.executable} {Path(__file__).parent / 'fake_signal_cli.py'}",
        FAKE_INJECT_DIR=str(inject),
        FAKE_AUTO_LINK=os.environ.get("FAKE_AUTO_LINK", "1"),
    )
    accounts = tmp / "data" / "signal-cli"
    accounts.mkdir(parents=True)
    if os.environ.get("DEMO_UNLINKED") != "1":
        n_accounts = int(os.environ.get("DEMO_ACCOUNTS", "2"))
        linked = [{"number": a[1], "aci": a[0]} for a in (ME, WORK)[:n_accounts]]
        (accounts / "fake-accounts.json").write_text(json.dumps(linked))
        threading.Timer(2.0, seed, args=(inject, n_accounts)).start()
    from app.main import create_app

    print(f"demo data in {tmp}")
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.environ.get("PORT", "8080")), log_level="warning")


if __name__ == "__main__":
    main()
