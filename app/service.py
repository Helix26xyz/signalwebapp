"""Glue between signal-cli (RPC), the database (Store/Ingestor) and connected browsers (Hub)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import re
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import WebSocket

from .config import Settings
from .ingest import Change, Ingestor
from .rpc import RpcError, SignalRPC
from .store import Store, now_ms

log = logging.getLogger("signal-web.service")

SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,200}$")


class Hub:
    """Fan-out of live events to every connected browser tab."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def add(self, ws: WebSocket) -> None:
        self.clients.add(ws)

    def remove(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def broadcast(self, event: dict) -> None:
        if not self.clients:
            return
        data = json.dumps(event, ensure_ascii=False)
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(data)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.remove(ws)


@dataclass
class Upload:
    filename: str
    content_type: str
    data: bytes


class SignalService:
    def __init__(self, settings: Settings):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = Store(settings.db_path)
        self.ingestor = Ingestor(self.store)
        self.hub = Hub()
        self.rpc = SignalRPC(settings, self._on_notification, self._on_connected)
        self.state = "starting"  # starting | unlinked | linking | ready | disconnected
        self.account: str | None = self.store.get_meta("account")
        self.link_uri: str | None = None
        self.link_error: str | None = None
        self._link_task: asyncio.Task | None = None
        self._bg: set[asyncio.Task] = set()
        self._refresh_pending: set[str] = set()
        self._load_self_ids()

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        await self.rpc.start()
        self._spawn(self._expiry_loop())

    async def stop(self) -> None:
        for t in list(self._bg):
            t.cancel()
        if self._link_task:
            self._link_task.cancel()
        await self.rpc.stop()

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._bg.add(task)
        task.add_done_callback(self._bg.discard)
        return task

    def _load_self_ids(self) -> None:
        ids = json.loads(self.store.get_meta("self_ids") or "[]")
        self.ingestor.self_ids = {i for i in ids if i}

    def _save_self_ids(self, *ids: str | None) -> None:
        self.ingestor.self_ids |= {i for i in ids if i}
        self.store.set_meta("self_ids", json.dumps(sorted(self.ingestor.self_ids)))

    def status(self) -> dict:
        return {
            "state": self.state if self.rpc.connected or self.state == "starting" else "disconnected",
            "account": self.account,
            "link_uri": self.link_uri if self.state == "linking" else None,
            "link_error": self.link_error,
            "error": self.rpc.last_error,
            "device_name": self.settings.device_name,
        }

    async def _set_state(self, state: str) -> None:
        self.state = state
        await self.hub.broadcast({"type": "status", "status": self.status()})

    async def _on_connected(self) -> None:
        accounts = await self.rpc.call("listAccounts") or []
        # Subscribe before anything else. With no account params this covers every local
        # account, including one that gets linked later in this session.
        await self.rpc.call("subscribeReceive")
        if not accounts:
            self.account = None
            await self._set_state("unlinked")
            return
        chosen = next(
            (a for a in accounts if self.account in (a.get("number"), a.get("aci"))), accounts[0]
        )
        await self._adopt_account(chosen.get("number"), chosen.get("aci"))
        await self._set_state("ready")
        self._spawn(self.refresh_contacts())
        self._spawn(self.refresh_groups())

    async def _adopt_account(self, number: str | None, aci: str | None) -> None:
        self.account = number or aci
        self.store.set_meta("account", self.account)
        self._save_self_ids(number, aci)

    async def call(self, method: str, params: dict | None = None, timeout: float = 60) -> Any:
        """RPC call scoped to our account (signal-cli runs in multi-account mode)."""
        if not self.account:
            raise RuntimeError("No Signal account linked yet")
        return await self.rpc.call(method, {"account": self.account, **(params or {})}, timeout=timeout)

    # ------------------------------------------------------------------ linking

    async def start_link(self) -> str:
        if self._link_task and not self._link_task.done():
            self._link_task.cancel()
        self.link_error = None
        result = await self.rpc.call("startLink")
        self.link_uri = result["deviceLinkUri"]
        await self._set_state("linking")
        self._link_task = asyncio.create_task(self._finish_link(self.link_uri))
        return self.link_uri

    async def _finish_link(self, uri: str) -> None:
        try:
            result = await self.rpc.call(
                "finishLink", {"deviceLinkUri": uri, "deviceName": self.settings.device_name}, timeout=600
            )
        except (RpcError, ConnectionError, asyncio.TimeoutError) as exc:
            log.warning("linking failed: %s", exc)
            self.link_error = str(exc) or "Linking timed out"
            self.link_uri = None
            await self._set_state("unlinked")
            return
        self.link_uri = None
        await self._adopt_account(result.get("number"), result.get("aci"))
        await self._set_state("ready")
        # Ask the phone for its contact and group lists; replies arrive as sync messages.
        try:
            await self.call("sendSyncRequest")
        except Exception as exc:  # noqa: BLE001
            log.warning("sendSyncRequest failed: %s", exc)
        await self.refresh_contacts()
        await self.refresh_groups()

    # ------------------------------------------------------------------ incoming

    async def _on_notification(self, method: str, params: dict) -> None:
        if method != "receive":
            return
        payload = params.get("result") if "subscription" in params else params
        if not isinstance(payload, dict):
            return
        account = payload.get("account")
        if account and self.account and account not in self.ingestor.self_ids and account != self.account:
            return
        if payload.get("exception") or payload.get("error"):
            log.warning("signal-cli receive error: %s", payload.get("exception") or payload.get("error"))
        if self.settings.keep_raw_events:
            self.store.add_raw_event(account, payload)
        changes = self.ingestor.handle(payload)
        await self.publish(changes)

    async def publish(self, changes: list[Change]) -> None:
        seen: set[tuple] = set()
        for ch in changes:
            key = (ch.kind, ch.conversation_id, ch.message_id)
            if key in seen:
                continue
            seen.add(key)
            if ch.kind == "message" and ch.message_id is not None:
                msg = self.store.message(ch.message_id)
                if msg:
                    await self.hub.broadcast({"type": "message", "message": msg})
            elif ch.kind == "message_removed":
                await self.hub.broadcast(
                    {"type": "message_removed", "conversation_id": ch.conversation_id, "id": ch.message_id}
                )
            elif ch.kind == "conversation" and ch.conversation_id:
                conv = self.store.conversation(ch.conversation_id)
                if conv:
                    await self.hub.broadcast({"type": "conversation", "conversation": conv})
            elif ch.kind == "typing":
                await self.hub.broadcast({"type": "typing", "conversation_id": ch.conversation_id, **ch.data})
            elif ch.kind == "refresh_groups":
                self._debounced("groups", self.refresh_groups)
            elif ch.kind == "refresh_contacts":
                self._debounced("contacts", self.refresh_contacts)

    def _debounced(self, key: str, fn) -> None:
        if key in self._refresh_pending:
            return
        self._refresh_pending.add(key)

        async def run():
            await asyncio.sleep(2)
            self._refresh_pending.discard(key)
            await fn()

        self._spawn(run())

    async def refresh_contacts(self) -> None:
        try:
            contacts = await self.call("listContacts", {"allRecipients": True})
        except Exception as exc:  # noqa: BLE001
            log.warning("listContacts failed: %s", exc)
            return
        merged: list[str] = []
        for c in contacts or []:
            uuid, number = c.get("uuid"), c.get("number")
            if (uuid and uuid in self.ingestor.self_ids) or (number and number in self.ingestor.self_ids):
                self._save_self_ids(uuid, number)
                continue
            rid = uuid or number
            if not rid:
                continue
            profile = c.get("profile") or {}
            profile_name = " ".join(x for x in (profile.get("givenName"), profile.get("familyName")) if x)
            contact_name = c.get("name") or " ".join(
                x for x in (c.get("givenName"), c.get("familyName")) if x
            )
            nick = c.get("nickName") or " ".join(
                x for x in (c.get("nickGivenName"), c.get("nickFamilyName")) if x
            )
            self.store.upsert_recipient(
                rid,
                uuid=uuid,
                number=number,
                username=c.get("username"),
                contact_name=contact_name or None,
                profile_name=profile_name or None,
                nick_name=nick or None,
                color=c.get("color"),
                blocked=1 if c.get("isBlocked") else 0,
            )
            if uuid and number:
                merged += self.store.merge_number_into_uuid(number, uuid)
        for cid in set(merged):
            self.store.refresh_conversation(cid)
        await self.hub.broadcast({"type": "conversations_changed"})

    async def refresh_groups(self) -> None:
        try:
            groups = await self.call("listGroups")
        except Exception as exc:  # noqa: BLE001
            log.warning("listGroups failed: %s", exc)
            return
        for g in groups or []:
            members = []
            for m in g.get("members") or []:
                if isinstance(m, str):
                    members.append(m)
                elif isinstance(m, dict):
                    members.append(m.get("uuid") or m.get("number"))
            self.store.upsert_group(
                g["id"],
                name=g.get("name"),
                description=g.get("description"),
                members=[m for m in members if m],
                is_member=1 if g.get("isMember", True) else 0,
                blocked=1 if g.get("isBlocked") else 0,
            )
        await self.hub.broadcast({"type": "conversations_changed"})

    # ------------------------------------------------------------------ outgoing

    def _address(self, rid: str) -> str:
        if rid == "self":
            assert self.account
            return self.account
        return rid

    def _target_params(self, conv_id: str) -> dict:
        if conv_id.startswith("g:"):
            return {"groupId": conv_id[2:]}
        peer = conv_id[2:]
        if peer == "self":
            return {"noteToSelf": True}
        return {"recipient": [self._address(peer)]}

    async def send_message(
        self,
        conv_id: str,
        text: str,
        uploads: list[Upload] | None = None,
        quote_id: int | None = None,
        edit_id: int | None = None,
    ) -> dict:
        uploads = uploads or []
        params = self._target_params(conv_id)
        if text:
            params["message"] = text
        conv = self.store.conversation(conv_id)
        expires_in = (conv or {}).get("expire_timer") or 0

        local_atts: list[dict] = []
        if uploads:
            params["attachments"] = []
            self.settings.sent_attachments_dir.mkdir(parents=True, exist_ok=True)
            for up in uploads:
                ct = up.content_type or mimetypes.guess_type(up.filename)[0] or "application/octet-stream"
                safe_name = re.sub(r"[^\w.\- ]", "_", up.filename)[:120] or "file"
                params["attachments"].append(
                    f"data:{ct};filename={safe_name};base64,{base64.b64encode(up.data).decode()}"
                )
                local_id = f"local-{secrets.token_hex(12)}{Path(safe_name).suffix[:10]}"
                (self.settings.sent_attachments_dir / local_id).write_bytes(up.data)
                local_atts.append(
                    {"id": local_id, "contentType": ct, "filename": safe_name, "size": len(up.data)}
                )

        quote = None
        if quote_id:
            q = self.store.message_row(quote_id)
            if q and q["conversation_id"] == conv_id:
                params["quoteTimestamp"] = q["sent_ts"]
                params["quoteAuthor"] = self._address(q["author"])
                if q.get("body"):
                    params["quoteMessage"] = q["body"]
                quote = {"id": q["sent_ts"], "author": q["author"], "text": q.get("body"), "attachments": []}

        edit_target = self.store.message_row(edit_id) if edit_id else None
        if edit_id:
            if not edit_target or edit_target["author"] != "self" or edit_target["conversation_id"] != conv_id:
                raise ValueError("Can only edit your own messages")
            params["editTimestamp"] = edit_target["sent_ts"]

        result = await self.call("send", params, timeout=300)
        ts = int(result.get("timestamp") or now_ms())
        status = _send_status(result)

        if edit_target:
            history = json.loads(edit_target.get("edit_history") or "[]")
            history.append({"body": edit_target.get("body"), "ts": ts})
            self.store.update_message(edit_target["id"], body=text, edited=1, edit_history=history)
            mid = edit_target["id"]
        else:
            mid = self.store.upsert_message(
                conv_id,
                "self",
                ts,
                server_ts=ts,
                body=text or None,
                attachments=local_atts or None,
                quote=quote,
                status=status,
                is_read=1,
                expires_in=expires_in,
                expire_at=ts + expires_in * 1000 if expires_in else None,
            )
        self.store.refresh_conversation(conv_id)
        await self.publish([Change("message", conv_id, mid), Change("conversation", conv_id)])
        return self.store.message(mid) or {}

    async def react(self, msg_id: int, emoji: str, remove: bool = False) -> None:
        m = self.store.message_row(msg_id)
        if not m:
            raise KeyError(msg_id)
        params = self._target_params(m["conversation_id"])
        params.update(
            emoji=emoji,
            targetAuthor=self._address(m["author"]),
            targetTimestamp=m["sent_ts"],
            remove=remove or None,
        )
        await self.call("sendReaction", params)
        self.store.set_reaction(msg_id, "self", None if remove else emoji, now_ms())
        await self.publish([Change("message", m["conversation_id"], msg_id)])

    async def delete_for_everyone(self, msg_id: int) -> None:
        m = self.store.message_row(msg_id)
        if not m or m["author"] != "self":
            raise ValueError("Can only delete your own messages for everyone")
        params = self._target_params(m["conversation_id"])
        params["targetTimestamp"] = m["sent_ts"]
        await self.call("remoteDelete", params)
        self.store.update_message(msg_id, deleted=1, body=None)
        self.store.refresh_conversation(m["conversation_id"])
        await self.publish([Change("message", m["conversation_id"], msg_id), Change("conversation", m["conversation_id"])])

    async def delete_locally(self, msg_id: int) -> None:
        m = self.store.message_row(msg_id)
        if not m:
            return
        self.store.delete_message_row(msg_id)
        self.store.refresh_conversation(m["conversation_id"])
        await self.publish(
            [Change("message_removed", m["conversation_id"], msg_id), Change("conversation", m["conversation_id"])]
        )

    async def mark_read(self, conv_id: str) -> None:
        unread = self.store.unread_incoming(conv_id)
        if not unread:
            return
        self.store.mark_read([m["id"] for m in unread])
        self.store.refresh_conversation(conv_id)
        await self.publish([Change("conversation", conv_id)] + [Change("message", conv_id, m["id"]) for m in unread])
        if not self.settings.send_read_receipts:
            return
        # One receipt per original sender. signal-cli also sends a read *sync* to our other
        # devices with each receipt, which is what clears the badge on the phones.
        by_author: dict[str, list[int]] = defaultdict(list)
        for m in unread:
            by_author[m["author"]].append(m["sent_ts"])
        for author, stamps in by_author.items():
            try:
                await self.call(
                    "sendReceipt",
                    {"recipient": self._address(author), "targetTimestamp": stamps, "type": "read"},
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("sendReceipt to %s failed: %s", author, exc)

    async def send_typing(self, conv_id: str, started: bool) -> None:
        if not self.settings.send_typing or conv_id == "u:self":
            return
        params = self._target_params(conv_id)
        params["stop"] = None if started else True
        try:
            await self.call("sendTyping", params, timeout=15)
        except Exception as exc:  # noqa: BLE001
            log.debug("sendTyping failed: %s", exc)

    # ------------------------------------------------------------------ media

    async def attachment(self, att_id: str) -> tuple[bytes | Path, str] | None:
        if not SAFE_ID.match(att_id):
            return None
        meta = self.store.find_attachment(att_id) or {}
        ct = meta.get("contentType") or mimetypes.guess_type(att_id)[0] or "application/octet-stream"
        if att_id.startswith("local-"):
            path = self.settings.sent_attachments_dir / att_id
            return (path, ct) if path.is_file() else None
        path = self.settings.received_attachments_dir / att_id
        if path.is_file():
            return path, ct
        try:
            result = await self.call("getAttachment", {"id": att_id}, timeout=120)
        except Exception as exc:  # noqa: BLE001
            log.info("getAttachment %s failed: %s", att_id, exc)
            return None
        data = result.get("data") if isinstance(result, dict) else result
        if not data:
            return None
        return base64.b64decode(data), ct

    async def avatar(self, conv_id: str) -> bytes | None:
        cache_dir = self.settings.avatar_cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = re.sub(r"[^A-Za-z0-9]", "_", conv_id)[:150]
        path, miss = cache_dir / key, cache_dir / f"{key}.none"
        day = 86400
        if path.is_file() and time.time() - path.stat().st_mtime < day:
            return path.read_bytes()
        if miss.is_file() and time.time() - miss.stat().st_mtime < day:
            return None
        attempts: list[dict] = []
        if conv_id.startswith("g:"):
            attempts.append({"groupId": conv_id[2:]})
        elif conv_id != "u:self":
            addr = self._address(conv_id[2:])
            attempts += [{"contact": addr}, {"profile": addr}]
        for params in attempts:
            try:
                result = await self.call("getAvatar", params, timeout=30)
            except Exception:  # noqa: BLE001
                continue
            data = result.get("data") if isinstance(result, dict) else result
            if data:
                raw = base64.b64decode(data)
                path.write_bytes(raw)
                miss.unlink(missing_ok=True)
                return raw
        miss.touch()
        return None

    # ------------------------------------------------------------------ disappearing messages

    async def _expiry_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(5)
                expired = self.store.expired_messages()
                changes: list[Change] = []
                for m in expired:
                    for a in json.loads(m.get("attachments") or "[]"):
                        self._delete_attachment_file(a.get("id"))
                    self.store.delete_message_row(m["id"])
                    changes.append(Change("message_removed", m["conversation_id"], m["id"]))
                for cid in {m["conversation_id"] for m in expired}:
                    self.store.refresh_conversation(cid)
                    changes.append(Change("conversation", cid))
                if changes:
                    await self.publish(changes)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("expiry loop error")

    def _delete_attachment_file(self, att_id: str | None) -> None:
        if not att_id or not SAFE_ID.match(att_id):
            return
        base = self.settings.sent_attachments_dir if att_id.startswith("local-") else self.settings.received_attachments_dir
        (base / att_id).unlink(missing_ok=True)


def _send_status(result: dict) -> str:
    results = result.get("results") or []
    if not results:
        return "sent"
    ok = [r for r in results if r.get("type") == "SUCCESS"]
    return "sent" if ok else "failed"
