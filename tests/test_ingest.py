from pathlib import Path

import pytest

from app.ingest import Ingestor
from app.store import Store

ME_NUM, ME_ACI = "+15550000001", "aaaaaaaa-0000-4000-8000-000000000001"
ALICE_NUM, ALICE = "+15550000002", "bbbbbbbb-0000-4000-8000-000000000002"
BOB_NUM, BOB = "+15550000003", "cccccccc-0000-4000-8000-000000000003"
GID = "R3JvdXAxMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Njc4OTA="


@pytest.fixture
def ing(tmp_path: Path):
    i = Ingestor(Store(tmp_path / "t.db"))
    i.self_ids = {ME_NUM, ME_ACI}
    return i


def env(src_uuid=ALICE, src_num=ALICE_NUM, name="Alice", ts=1000, **body):
    return {"envelope": {"sourceUuid": src_uuid, "sourceNumber": src_num, "sourceName": name,
                         "sourceDevice": 1, "timestamp": ts, "serverReceivedTimestamp": ts + 5, **body},
            "account": ME_NUM}


def from_me(ts, **sent):
    # what a linked device sees when you send from your phone
    return env(ME_ACI, ME_NUM, "Me", ts, syncMessage={"sentMessage": {"timestamp": ts, **sent}})


def conv(ing, cid):
    return ing.store.conversation(cid)


def test_incoming_message_creates_unread_conversation(ing):
    ing.handle(env(dataMessage={"timestamp": 1000, "message": "hi there"}))
    c = conv(ing, f"u:{ALICE}")
    assert c["unread"] == 1 and c["last_preview"] == "hi there" and c["name"] == "Alice"
    [m] = ing.store.messages(f"u:{ALICE}")
    assert m["body"] == "hi there" and not m["outgoing"] and m["author"] == ALICE


def test_message_sent_from_phone_lands_in_same_thread(ing):
    ing.handle(env(dataMessage={"timestamp": 1000, "message": "hi"}))
    ing.handle(from_me(2000, destinationUuid=ALICE, destinationNumber=ALICE_NUM, message="hello back"))
    msgs = ing.store.messages(f"u:{ALICE}")
    assert [(m["body"], m["outgoing"], m["status"]) for m in msgs] == [("hi", False, None), ("hello back", True, "sent")]
    assert conv(ing, f"u:{ALICE}")["last_author"] == "self"


def test_duplicate_envelope_is_idempotent(ing):
    e = env(dataMessage={"timestamp": 1000, "message": "hi"})
    ing.handle(e)
    ing.handle(e)
    assert len(ing.store.messages(f"u:{ALICE}")) == 1


def test_edit_reaction_delete(ing):
    ing.handle(env(dataMessage={"timestamp": 1000, "message": "teh typo"}))
    ing.handle(env(ts=1100, editMessage={"targetSentTimestamp": 1000, "dataMessage": {"timestamp": 1100, "message": "the typo"}}))
    [m] = ing.store.messages(f"u:{ALICE}")
    assert m["body"] == "the typo" and m["edited"] and m["edit_history"][0]["body"] == "teh typo"

    # I react from my phone (sync), Alice reacts too
    ing.handle(from_me(1200, destinationUuid=ALICE, reaction={"emoji": "👍", "targetAuthorUuid": ALICE, "targetSentTimestamp": 1000, "isRemove": False}))
    ing.handle(env(ts=1300, dataMessage={"timestamp": 1300, "reaction": {"emoji": "❤️", "targetAuthorUuid": ALICE, "targetSentTimestamp": 1000, "isRemove": False}}))
    [m] = ing.store.messages(f"u:{ALICE}")
    assert sorted((r["author"], r["emoji"]) for r in m["reactions"]) == sorted([("self", "👍"), (ALICE, "❤️")])
    ing.handle(from_me(1400, destinationUuid=ALICE, reaction={"emoji": "👍", "targetAuthorUuid": ALICE, "targetSentTimestamp": 1000, "isRemove": True}))
    [m] = ing.store.messages(f"u:{ALICE}")
    assert [r["author"] for r in m["reactions"]] == [ALICE]

    ing.handle(env(ts=1500, dataMessage={"timestamp": 1500, "remoteDelete": {"timestamp": 1000, "targetTimestamp": 1000}}))
    [m] = ing.store.messages(f"u:{ALICE}")
    assert m["deleted"] and m["body"] is None and m["reactions"] == []


def test_edit_sent_from_phone(ing):
    ing.handle(from_me(1000, destinationUuid=ALICE, message="draft"))
    ing.handle(env(ME_ACI, ME_NUM, ts=1100, syncMessage={"sentMessage": {
        "destinationUuid": ALICE, "timestamp": 1100,
        "editMessage": {"targetSentTimestamp": 1000, "dataMessage": {"timestamp": 1100, "message": "final"}}}}))
    [m] = ing.store.messages(f"u:{ALICE}")
    assert m["body"] == "final" and m["edited"] and m["outgoing"]


def test_receipts_and_read_sync(ing):
    ing.handle(from_me(1000, destinationUuid=ALICE, message="ping"))
    ing.handle(env(ts=1100, receiptMessage={"when": 1100, "isDelivery": True, "isRead": False, "isViewed": False, "timestamps": [1000]}))
    assert ing.store.messages(f"u:{ALICE}")[0]["status"] == "delivered"
    ing.handle(env(ts=1200, receiptMessage={"when": 1200, "isDelivery": False, "isRead": True, "isViewed": False, "timestamps": [1000]}))
    # a late delivery receipt must not downgrade "read"
    ing.handle(env(ts=1250, receiptMessage={"when": 1250, "isDelivery": True, "isRead": False, "isViewed": False, "timestamps": [1000]}))
    assert ing.store.messages(f"u:{ALICE}")[0]["status"] == "read"

    ing.handle(env(ts=2000, dataMessage={"timestamp": 2000, "message": "one"}))
    ing.handle(env(ts=2100, dataMessage={"timestamp": 2100, "message": "two"}))
    ing.handle(env(ts=2200, dataMessage={"timestamp": 2200, "message": "three"}))
    assert conv(ing, f"u:{ALICE}")["unread"] == 3
    # read on my phone up to "two"
    ing.handle(env(ME_ACI, ME_NUM, ts=2300, syncMessage={"readMessages": [{"senderUuid": ALICE, "senderNumber": ALICE_NUM, "timestamp": 2100}]}))
    assert conv(ing, f"u:{ALICE}")["unread"] == 1


def test_group_messages_and_updates(ing):
    group = {"groupId": GID, "groupName": "Family", "revision": 3, "type": "DELIVER"}
    ing.handle(env(dataMessage={"timestamp": 1000, "message": "hi all", "groupInfo": group}))
    ing.handle(env(BOB, BOB_NUM, "Bob", 1100, dataMessage={"timestamp": 1100, "message": "yo", "groupInfo": group}))
    ing.handle(from_me(1200, message="hey", groupInfo=group))
    c = conv(ing, f"g:{GID}")
    assert c["name"] == "Family" and c["kind"] == "group" and c["unread"] == 2
    assert [m["author"] for m in ing.store.messages(f"g:{GID}")] == [ALICE, BOB, "self"]
    changes = ing.handle(env(ts=1300, dataMessage={"timestamp": 1300, "groupInfo": {**group, "type": "UPDATE"}}))
    assert any(ch.kind == "refresh_groups" for ch in changes)


def test_note_to_self_and_attachments(ing):
    ing.handle(from_me(1000, destinationUuid=ME_ACI, destinationNumber=ME_NUM, message="",
                       attachments=[{"id": "abc.jpg", "contentType": "image/jpeg", "filename": "cat.jpg", "size": 10}]))
    c = conv(ing, "u:self")
    assert c["name"] == "Note to Self" and c["last_preview"] == "📷 Photo"
    [m] = ing.store.messages("u:self")
    assert m["attachments"][0]["id"] == "abc.jpg"
    assert ing.store.find_attachment("abc.jpg")["filename"] == "cat.jpg"


def test_number_only_history_merges_when_uuid_learned(ing):
    ing.handle(env(None, BOB_NUM, "Bob", 1000, dataMessage={"timestamp": 1000, "message": "number only"}))
    assert conv(ing, f"u:{BOB_NUM}")
    ing.handle(env(BOB, BOB_NUM, "Bob", 2000, dataMessage={"timestamp": 2000, "message": "with uuid"}))
    assert conv(ing, f"u:{BOB_NUM}") is None
    assert [m["body"] for m in ing.store.messages(f"u:{BOB}")] == ["number only", "with uuid"]


def test_quote_mentions_and_disappearing(ing):
    ing.handle(from_me(1000, destinationUuid=ALICE, message="original"))
    ing.handle(env(ts=1100, dataMessage={"timestamp": 1100, "message": "￼ agreed", "mentions": [{"uuid": ME_ACI, "number": ME_NUM, "start": 0, "length": 1}],
                                         "quote": {"id": 1000, "authorUuid": ME_ACI, "authorNumber": ME_NUM, "text": "original", "attachments": []}}))
    m = ing.store.messages(f"u:{ALICE}")[-1]
    assert m["quote"]["author"] == "self" and m["quote"]["author_name"] == "You"
    assert m["mentions"][0]["rid"] == "self"

    ing.handle(env(ts=1200, dataMessage={"timestamp": 1200, "isExpirationUpdate": True, "expiresInSeconds": 3600}))
    assert conv(ing, f"u:{ALICE}")["expire_timer"] == 3600
    assert "1 hour" in ing.store.messages(f"u:{ALICE}")[-1]["body"]
    ing.handle(env(ts=1300, dataMessage={"timestamp": 1300, "message": "secret", "expiresInSeconds": 3600}))
    secret = ing.store.messages(f"u:{ALICE}")[-1]
    assert secret["expire_at"] is None  # timer starts when read
    ing.store.mark_read([secret["id"]], read_at=5000)
    assert ing.store.message(secret["id"])["expire_at"] == 5000 + 3600 * 1000


def test_typing_is_not_persisted(ing):
    changes = ing.handle(env(typingMessage={"action": "STARTED", "timestamp": 1000}))
    assert [c.kind for c in changes] == ["typing"]
    assert changes[0].data["started"] and ing.store.conversation(f"u:{ALICE}") is None
