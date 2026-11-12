"""Turn signal-cli envelopes into database changes.

This module only touches the Store. It returns a list of Change records telling the caller
what to push to browsers and what follow-up RPC calls to make (e.g. refresh group info).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .store import Store, now_ms

log = logging.getLogger("signal-web.ingest")


@dataclass
class Change:
    kind: str  # message | conversation | typing | refresh_groups | refresh_contacts | message_removed
    conversation_id: str | None = None
    message_id: int | None = None
    data: dict[str, Any] = field(default_factory=dict)


def format_duration(seconds: int) -> str:
    if not seconds:
        return "off"
    for unit, size in (("week", 604800), ("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= size and seconds % size == 0:
            n = seconds // size
            return f"{n} {unit}{'s' if n != 1 else ''}"
    return f"{seconds} seconds"


class Ingestor:
    def __init__(self, store: Store):
        self.store = store
        self.self_ids: set[str] = set()
        self._pending_merges: list[tuple[str, str]] = []

    # ------------------------------------------------------------------ identity

    def rid(self, uuid: str | None, number: str | None, name: str | None = None) -> str | None:
        """Resolve a (uuid, number) pair to our recipient id, recording what we learn."""
        if (uuid and uuid in self.self_ids) or (number and number in self.self_ids):
            return "self"
        if uuid:
            existing = self.store.recipient(uuid)
            self.store.upsert_recipient(uuid, uuid=uuid, number=number, envelope_name=name or None)
            if number and (existing is None or existing.get("number") != number):
                # Learned this uuid's number: fold any number-keyed history into it.
                self._pending_merges.append((number, uuid))
            return uuid
        if number:
            known = self.store.rid_for_number(number)
            if known:
                return known
            self.store.upsert_recipient(number, number=number, envelope_name=name or None)
            return number
        return None

    # ------------------------------------------------------------------ entry point

    def handle(self, payload: dict) -> list[Change]:
        """Handle one `receive` notification payload ({"envelope": ..., "account": ...})."""
        self._pending_merges: list[tuple[str, str]] = []
        changes: list[Change] = []
        env = payload.get("envelope") or {}
        if not env:
            return changes
        try:
            with self.store.transaction():
                self._handle_envelope(env, changes)
                for number, uuid in self._pending_merges:
                    for cid in self.store.merge_number_into_uuid(number, uuid):
                        changes.append(Change("conversation", cid))
                touched = {c.conversation_id for c in changes if c.conversation_id and c.kind != "typing"}
                for cid in touched:
                    if self.store.conversation(cid):
                        self.store.refresh_conversation(cid)
        except Exception:
            log.exception("failed to ingest envelope: %s", env)
            raise
        # Always follow message changes with a conversation change so lists re-sort.
        for cid in {c.conversation_id for c in changes if c.conversation_id and c.kind != "typing"}:
            changes.append(Change("conversation", cid))
        return changes

    def _handle_envelope(self, env: dict, changes: list[Change]) -> None:
        sender = self.rid(env.get("sourceUuid"), env.get("sourceNumber") or env.get("source"), env.get("sourceName"))
        server_ts = env.get("serverReceivedTimestamp") or env.get("timestamp")

        if (dm := env.get("dataMessage")) is not None and sender:
            conv = self._conv_for(dm.get("groupInfo"), sender)
            self._handle_data(conv, sender, dm, server_ts, outgoing=sender == "self", changes=changes)

        if (edit := env.get("editMessage")) is not None and sender:
            dm = edit.get("dataMessage") or {}
            conv = self._conv_for(dm.get("groupInfo"), sender)
            self._handle_edit(conv, sender, edit.get("targetSentTimestamp"), dm, changes)

        if (sync := env.get("syncMessage")) is not None:
            self._handle_sync(sync, server_ts, changes)

        if (receipt := env.get("receiptMessage")) is not None and sender:
            self._handle_receipt(receipt, changes)

        if (typing := env.get("typingMessage")) is not None and sender and sender != "self":
            gid = typing.get("groupId")
            conv = f"g:{gid}" if gid else f"u:{sender}"
            changes.append(
                Change(
                    "typing",
                    conv,
                    data={
                        "author": sender,
                        "author_name": self.store.display_name(sender),
                        "started": typing.get("action") == "STARTED",
                    },
                )
            )

        if (call := env.get("callMessage")) is not None and sender and call.get("offerMessage"):
            conv = f"u:{sender}"
            mid = self.store.upsert_message(
                conv,
                sender,
                env.get("timestamp") or now_ms(),
                kind="system",
                body="📞 Incoming Signal call — answer it on your phone",
                server_ts=server_ts,
                is_read=1,
            )
            changes.append(Change("message", conv, mid))

    # ------------------------------------------------------------------ pieces

    def _conv_for(self, group_info: dict | None, peer: str) -> str:
        if group_info and group_info.get("groupId"):
            gid = group_info["groupId"]
            if not self.store.group(gid):
                self.store.upsert_group(gid, name=group_info.get("groupName"))
            elif group_info.get("groupName"):
                self.store.upsert_group(gid, name=group_info["groupName"])
            return f"g:{gid}"
        return f"u:{peer}"

    def _handle_sync(self, sync: dict, server_ts: int | None, changes: list[Change]) -> None:
        sent = sync.get("sentMessage")
        if sent:
            dest = self.rid(sent.get("destinationUuid"), sent.get("destinationNumber") or sent.get("destination"))
            if sent.get("editMessage"):
                edit = sent["editMessage"]
                dm = edit.get("dataMessage") or {}
                conv = self._conv_for(dm.get("groupInfo"), dest or "self")
                self._handle_edit(conv, "self", edit.get("targetSentTimestamp"), dm, changes)
            elif dest or sent.get("groupInfo"):
                conv = self._conv_for(sent.get("groupInfo"), dest or "self")
                self._handle_data(conv, "self", sent, server_ts, outgoing=True, changes=changes)

        for read in sync.get("readMessages") or []:
            author = self.rid(read.get("senderUuid"), read.get("senderNumber") or read.get("sender"))
            ts = read.get("timestamp")
            if not author or not ts:
                continue
            target = self.store.find_message(author, ts)
            if not target:
                continue
            conv = target["conversation_id"]
            ids = [m["id"] for m in self.store.unread_incoming(conv, up_to_ts=ts)]
            if ids:
                self.store.mark_read(ids)
                for mid in ids:
                    changes.append(Change("message", conv, mid))
            changes.append(Change("conversation", conv))

        sync_type = sync.get("type")
        if sync_type == "CONTACTS_SYNC":
            changes.append(Change("refresh_contacts"))
        elif sync_type == "GROUPS_SYNC":
            changes.append(Change("refresh_groups"))

    def _handle_receipt(self, receipt: dict, changes: list[Change]) -> None:
        if receipt.get("isRead"):
            status = "read"
        elif receipt.get("isViewed"):
            status = "viewed"
        elif receipt.get("isDelivery"):
            status = "delivered"
        else:
            return
        for ts in receipt.get("timestamps") or []:
            m = self.store.find_message("self", ts)
            if m and self.store.bump_status(m["id"], status):
                changes.append(Change("message", m["conversation_id"], m["id"]))

    def _handle_data(
        self,
        conv: str,
        author: str,
        dm: dict,
        server_ts: int | None,
        outgoing: bool,
        changes: list[Change],
    ) -> None:
        ts = dm.get("timestamp")
        if not ts:
            return
        group_info = dm.get("groupInfo") or {}

        if (reaction := dm.get("reaction")) is not None:
            target_author = self.rid(
                reaction.get("targetAuthorUuid"), reaction.get("targetAuthorNumber") or reaction.get("targetAuthor")
            )
            target = self.store.find_message(target_author, reaction.get("targetSentTimestamp"), conv) if target_author else None
            if target:
                emoji = None if reaction.get("isRemove") else reaction.get("emoji")
                self.store.set_reaction(target["id"], author, emoji, ts)
                changes.append(Change("message", target["conversation_id"], target["id"]))
            return

        if (rd := dm.get("remoteDelete")) is not None:
            target_ts = rd.get("targetTimestamp") or rd.get("timestamp")
            target = self.store.find_message(author, target_ts, conv)
            if target:
                self.store.update_message(target["id"], deleted=1, body=None)
                changes.append(Change("message", target["conversation_id"], target["id"]))
            return

        if (ad := dm.get("adminDelete")) is not None:
            target_author = self.rid(ad.get("targetAuthorUuid"), ad.get("targetAuthorNumber") or ad.get("targetAuthor"))
            target_ts = ad.get("targetTimestamp") or ad.get("targetSentTimestamp")
            target = self.store.find_message(target_author, target_ts, conv) if target_author else None
            if target:
                self.store.update_message(target["id"], deleted=1, body=None)
                changes.append(Change("message", target["conversation_id"], target["id"]))
            return

        if dm.get("isExpirationUpdate"):
            seconds = dm.get("expiresInSeconds") or 0
            self.store.set_expire_timer(conv, seconds)
            who = "You" if outgoing else self.store.display_name(author)
            body = (
                f"{who} turned off disappearing messages"
                if not seconds
                else f"{who} set disappearing messages to {format_duration(seconds)}"
            )
            mid = self.store.upsert_message(conv, author, ts, kind="system", body=body, server_ts=server_ts, is_read=1)
            changes.append(Change("message", conv, mid))
            return

        if dm.get("groupCallUpdate") is not None:
            mid = self.store.upsert_message(
                conv, author, ts, kind="system", body="📞 Group call started", server_ts=server_ts, is_read=1
            )
            changes.append(Change("message", conv, mid))
            return

        if any(dm.get(k) for k in ("pinMessage", "unpinMessage", "pollVote", "pollTerminate", "storyContext")):
            # Not rendered in this UI (yet). Raw event is kept in raw_events.
            return

        fields = self._content_fields(dm)
        if group_info.get("type") == "UPDATE" and not fields:
            changes.append(Change("refresh_groups", conv))
            return
        if not fields:
            return  # profile key updates, end-session, empty sync etc.

        expires_in = dm.get("expiresInSeconds") or 0
        mid = self.store.upsert_message(
            conv,
            author,
            ts,
            server_ts=server_ts,
            status="sent" if outgoing else None,
            is_read=1 if outgoing else 0,
            expires_in=expires_in,
            expire_at=(ts + expires_in * 1000) if (outgoing and expires_in) else None,
            **fields,
        )
        if expires_in:
            c = self.store.conversation(conv)
            if c and c.get("expire_timer") != expires_in:
                self.store.set_expire_timer(conv, expires_in)
        changes.append(Change("message", conv, mid))

    def _content_fields(self, dm: dict) -> dict:
        fields: dict[str, Any] = {}
        body = dm.get("message")
        if (poll := dm.get("pollCreate")) is not None:
            opts = "\n".join(f"• {o}" for o in poll.get("options") or [])
            body = f"📊 {poll.get('question', 'Poll')}\n{opts}".strip()
        if dm.get("contacts"):
            body = (body + "\n" if body else "") + "👤 Shared contact"
        if dm.get("payment"):
            body = (body + "\n" if body else "") + "💸 Payment (view it on your phone)"
        if body:
            fields["body"] = body
        atts = [self._attachment(a) for a in dm.get("attachments") or []]
        if atts:
            fields["attachments"] = atts
        if dm.get("sticker"):
            fields["sticker"] = dm["sticker"]
        if dm.get("viewOnce") and atts:
            fields["body"] = "👁 View-once media (open it on your phone)"
            fields.pop("attachments", None)
        if not fields:
            return fields
        if (q := dm.get("quote")) is not None:
            fields["quote"] = {
                "id": q.get("id"),
                "author": self.rid(q.get("authorUuid"), q.get("authorNumber") or q.get("author")),
                "text": q.get("text"),
                "attachments": [
                    {"contentType": a.get("contentType"), "filename": a.get("filename")}
                    for a in q.get("attachments") or []
                ],
            }
        if dm.get("mentions"):
            fields["mentions"] = [
                {
                    "rid": self.rid(m.get("uuid"), m.get("number")),
                    "start": m.get("start", 0),
                    "length": m.get("length", 1),
                }
                for m in dm["mentions"]
            ]
        if dm.get("textStyles"):
            fields["text_styles"] = dm["textStyles"]
        if dm.get("previews"):
            fields["previews"] = [
                {
                    "url": p.get("url"),
                    "title": p.get("title"),
                    "description": p.get("description"),
                    "image": self._attachment(p["image"]) if p.get("image") else None,
                }
                for p in dm["previews"]
            ]
        return fields

    @staticmethod
    def _attachment(a: dict) -> dict:
        keep = ("id", "contentType", "filename", "size", "width", "height", "caption", "isVoiceNote")
        return {k: a.get(k) for k in keep if a.get(k) is not None}

    def _handle_edit(self, conv: str, author: str, target_ts: int | None, dm: dict, changes: list[Change]) -> None:
        if not target_ts:
            return
        target = self.store.find_message(author, target_ts, conv)
        fields = self._content_fields(dm)
        if not target:
            # Original predates this device: store the edited version as the message.
            if fields:
                mid = self.store.upsert_message(
                    conv,
                    author,
                    target_ts,
                    status="sent" if author == "self" else None,
                    is_read=1 if author == "self" else 0,
                    edited=1,
                    **fields,
                )
                changes.append(Change("message", conv, mid))
            return
        history = list(_loads(target.get("edit_history")) or [])
        history.append({"body": target.get("body"), "ts": dm.get("timestamp")})
        self.store.update_message(
            target["id"],
            body=fields.get("body"),
            attachments=fields.get("attachments") or _loads(target.get("attachments")),
            mentions=fields.get("mentions"),
            text_styles=fields.get("text_styles"),
            previews=fields.get("previews"),
            edited=1,
            edit_history=history,
        )
        changes.append(Change("message", target["conversation_id"], target["id"]))


def _loads(value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    return json.loads(value)
