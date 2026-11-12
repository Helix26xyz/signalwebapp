"""Glue between signal-cli (RPC), the databases (Store/Ingestor) and connected browsers (Hub).

One signal-cli process serves every linked account (multi-account mode). Each account gets its own
`Account`: a separate SQLite history, sent-attachment copies and avatar cache, so all the identity
rules in store/ingest ("self", u:<rid>, message identity) stay per account.

On-disk layout under DATA_DIR:
    signal-web.db            history of the account linked before multi-account support (if any)
    sent-attachments/, avatars/   ...and its files
    accounts/<id>/signal-web.db, sent-attachments/, avatars/   every account linked since
    signal-cli/              signal-cli's own data (keys for all accounts, received attachments)
"""

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
        self.hub = Hub()
        self.rpc = SignalRPC(settings, self._on_notification, self._on_connected)
        self.state = "starting"  # starting | unlinked | ready (status() reports "disconnected" too)
        self.accounts: dict[str, Account] = {}  # key (number, else ACI) -> Account, in link order
        self.link_uri: str | None = None
        self.link_error: str | None = None
        self.link_gen = 0
        self.last_linked: dict | None = None
        self._link_task: asyncio.Task | None = None
        self._bg: set[asyncio.Task] = set()
        self._discover()

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
        for acc in self.accounts.values():
            acc.store.close()

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._bg.add(task)
        task.add_done_callback(self._bg.discard)
        return task

    # ------------------------------------------------------------------ accounts

    @property
    def accounts_dir(self) -> Path:
        return self.settings.data_dir / "accounts"

    def _discover(self) -> None:
        """Open every account database on disk. Each one records which account it belongs to."""
        roots = []
        if self.settings.db_path.exists():
            roots.append(self.settings.data_dir)
        if self.accounts_dir.is_dir():
            roots += sorted(p.parent for p in self.accounts_dir.glob("*/signal-web.db"))
        for root in roots:
            store = Store(root / "signal-web.db")
            if not store.get_meta("account"):
                store.close()  # created before anything was linked; nothing to keep
                continue
            acc = Account(self, root, store)
            if self.find_account(acc.number, acc.aci):
                log.warning("ignoring %s: another database already holds this account", root)
                store.close()
                continue
            self.accounts[acc.key] = acc

    def find_account(self, number: str | None = None, aci: str | None = None) -> Account | None:
        for acc in self.accounts.values():
            if acc.matches(number, aci):
                return acc
        return None

    def account(self, key: str) -> Account | None:
        """Look up by URL key; also accepts the other identifier (ACI vs number)."""
        return self.accounts.get(key) or self.find_account(key, key)

    def _ensure_account(self, number: str | None, aci: str | None) -> Account:
        acc = self.find_account(number, aci)
        if acc is None:
            root = self._new_account_root(number, aci)
            acc = Account(self, root, Store(root / "signal-web.db"))
            log.info("added account %s", root.name)
        old_key = acc.key
        acc.adopt(number, aci)
        if old_key in self.accounts and old_key != acc.key:  # phone number changed
            self.accounts = {(acc.key if k == old_key else k): v for k, v in self.accounts.items()}
        self.accounts[acc.key] = acc
        return acc

    def _new_account_root(self, number: str | None, aci: str | None) -> Path:
        base = re.sub(r"\D", "", number or "") or re.sub(r"[^A-Za-z0-9-]", "", aci or "") or "account"
        root, n = self.accounts_dir / base, 1
        while (root / "signal-web.db").exists():
            n += 1
            root = self.accounts_dir / f"{base}-{n}"
        return root

    # ------------------------------------------------------------------ status

    def status(self) -> dict:
        return {
            "state": self.state if self.rpc.connected or self.state == "starting" else "disconnected",
            "accounts": [a.summary() for a in self.accounts.values()],
            "linking": self.link_uri is not None,
            "link_uri": self.link_uri,
            "link_error": self.link_error,
            "last_linked": self.last_linked,
            "error": self.rpc.last_error,
            "device_name": self.settings.device_name,
        }

    async def broadcast_status(self) -> None:
        await self.hub.broadcast({"type": "status", "status": self.status()})

    async def _set_state(self, state: str) -> None:
        self.state = state
        await self.broadcast_status()

    async def _on_connected(self) -> None:
        listed = await self.rpc.call("listAccounts") or []
        # Subscribe before anything else. With no account params this covers every local
        # account, including ones that get linked later in this session.
        await self.rpc.call("subscribeReceive")
        for acc in self.accounts.values():
            acc.linked = False
        ready = []
        for a in listed:
            if not (a.get("number") or a.get("aci")):
                continue
            acc = self._ensure_account(a.get("number"), a.get("aci"))
            acc.linked = True
            ready.append(acc)
        # Accounts that are no longer in signal-cli keep their history visible, read-only.
        await self._set_state("ready" if self.accounts else "unlinked")
        for acc in ready:
            self._spawn(acc.refresh_contacts())
            self._spawn(acc.refresh_groups())

    # ------------------------------------------------------------------ linking

    async def start_link(self) -> dict:
        if self._link_task and not self._link_task.done():
            self._link_task.cancel()
        self.link_error = None
        result = await self.rpc.call("startLink")
        self.link_gen += 1
        self.link_uri = result["deviceLinkUri"]
        await self.broadcast_status()
        self._link_task = asyncio.create_task(self._finish_link(self.link_uri, self.link_gen))
        return {"uri": self.link_uri, "gen": self.link_gen}

    async def cancel_link(self) -> None:
        if self._link_task and not self._link_task.done():
            self._link_task.cancel()
        self.link_uri = None
        await self.broadcast_status()

    async def _finish_link(self, uri: str, gen: int) -> None:
        try:
            result = await self.rpc.call(
                "finishLink", {"deviceLinkUri": uri, "deviceName": self.settings.device_name}, timeout=600
            )
        except (RpcError, ConnectionError, asyncio.TimeoutError) as exc:
            log.warning("linking failed: %s", exc)
            self.link_error = str(exc) or "Linking timed out"
            self.link_uri = None
            await self.broadcast_status()
            return
        self.link_uri = None
        acc = self._ensure_account(result.get("number"), result.get("aci"))
        acc.linked = True
        self.last_linked = {"gen": gen, "account": acc.key}
        await self._set_state("ready")
        # Ask the phone for its contact and group lists; replies arrive as sync messages.
        try:
            await acc.call("sendSyncRequest")
        except Exception as exc:  # noqa: BLE001
            log.warning("sendSyncRequest failed: %s", exc)
        await acc.refresh_contacts()
        await acc.refresh_groups()

    # ------------------------------------------------------------------ incoming

    async def _on_notification(self, method: str, params: dict) -> None:
        if method != "receive":
            return
        payload = params.get("result") if "subscription" in params else params
        if not isinstance(payload, dict):
            return
        acc = await self._account_for(payload.get("account"))
        if acc is None:
            log.warning("dropping envelope: can't tell which account it belongs to")
            return
        if payload.get("exception") or payload.get("error"):
            log.warning("signal-cli receive error: %s", payload.get("exception") or payload.get("error"))
        if self.settings.keep_raw_events:
            acc.store.add_raw_event(payload.get("account"), payload)
        changes = acc.ingestor.handle(payload)
        await acc.publish(changes)

    async def _account_for(self, account: str | None) -> Account | None:
        if not account:
            # Single-account daemons may omit the field.
            return next(iter(self.accounts.values())) if len(self.accounts) == 1 else None
        number, aci = (account, None) if account.startswith("+") else (None, account)
        acc = self.find_account(number, aci)
        if acc is None:
            # signal-cli knows an account we haven't seen yet (e.g. a message arrived before
            # finishLink returned). Start its history now rather than lose the envelope.
            acc = self._ensure_account(number, aci)
            acc.linked = True
            await self._set_state("ready")
        return acc

    # ------------------------------------------------------------------ disappearing messages

    async def _expiry_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(5)
                for acc in list(self.accounts.values()):
                    await acc.expire_due()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("expiry loop error")


class Account:
    """One Signal account: its own history database, attachment copies and avatar cache."""

    def __init__(self, service: SignalService, root: Path, store: Store):
        self.service = service
        self.settings = service.settings
        self.rpc = service.rpc
        self.hub = service.hub
        self.root = root
        self.store = store
        self.ingestor = Ingestor(store)
        self.linked = False
        self._refresh_pending: set[str] = set()
        self.ingestor.self_ids = {i for i in json.loads(store.get_meta("self_ids") or "[]") if i}
        recorded = store.get_meta("account") or ""
        self.number: str | None = recorded if recorded.startswith("+") else None
        self.aci: str | None = (recorded or None) if not self.number else next(
            (i for i in self.ingestor.self_ids if not i.startswith("+")), None
        )

    @property
    def key(self) -> str:
        return self.number or self.aci or self.root.name

    @property
    def sent_attachments_dir(self) -> Path:
        return self.root / "sent-attachments"

    @property
    def avatar_cache_dir(self) -> Path:
        return self.root / "avatars"

    def matches(self, number: str | None, aci: str | None) -> bool:
        ids = self.ingestor.self_ids | {self.number, self.aci}
        return bool((number and number in ids) or (aci and aci in ids))

    def adopt(self, number: str | None, aci: str | None) -> None:
        self.number = number or self.number
        self.aci = aci or self.aci
        self.store.set_meta("account", self.key)
        self._save_self_ids(number, aci)

    def _save_self_ids(self, *ids: str | None) -> None:
        self.ingestor.self_ids |= {i for i in ids if i}
        self.store.set_meta("self_ids", json.dumps(sorted(self.ingestor.self_ids)))

    def summary(self) -> dict:
        return {
            "id": self.key,
            "number": self.number,
            "name": self.store.get_meta("self_name"),
            "unread": self.store.total_unread(),
            "linked": self.linked,
        }

    async def call(self, method: str, params: dict | None = None, timeout: float = 60) -> Any:
        """RPC call scoped to this account (signal-cli runs in multi-account mode)."""
        return await self.rpc.call(method, {"account": self.number or self.aci, **(params or {})}, timeout=timeout)

    async def broadcast(self, event: dict) -> None:
        await self.hub.broadcast({**event, "account": self.key})

    # ------------------------------------------------------------------ incoming

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
                    await self.broadcast({"type": "message", "message": msg})
            elif ch.kind == "message_removed":
                await self.broadcast(
                    {"type": "message_removed", "conversation_id": ch.conversation_id, "id": ch.message_id}
                )
            elif ch.kind == "conversation" and ch.conversation_id:
                conv = self.store.conversation(ch.conversation_id)
                if conv:
                    await self.broadcast({"type": "conversation", "conversation": conv})
            elif ch.kind == "typing":
                await self.broadcast({"type": "typing", "conversation_id": ch.conversation_id, **ch.data})
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

        self.service._spawn(run())

    async def refresh_contacts(self) -> None:
        try:
            contacts = await self.call("listContacts", {"allRecipients": True})
        except Exception as exc:  # noqa: BLE001
            log.warning("listContacts failed: %s", exc)
            return
        merged: list[str] = []
        for c in contacts or []:
            uuid, number = c.get("uuid"), c.get("number")
            profile = c.get("profile") or {}
            profile_name = " ".join(x for x in (profile.get("givenName"), profile.get("familyName")) if x)
            if (uuid and uuid in self.ingestor.self_ids) or (number and number in self.ingestor.self_ids):
                self._save_self_ids(uuid, number)
                if profile_name and profile_name != self.store.get_meta("self_name"):
                    self.store.set_meta("self_name", profile_name)  # labels the account switcher
                    await self.service.broadcast_status()
                continue
            rid = uuid or number
            if not rid:
                continue
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
        await self.broadcast({"type": "conversations_changed"})

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
        await self.broadcast({"type": "conversations_changed"})

    # ------------------------------------------------------------------ outgoing

    def _address(self, rid: str) -> str:
        if rid == "self":
            return self.number or self.aci or rid
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
            self.sent_attachments_dir.mkdir(parents=True, exist_ok=True)
            for up in uploads:
                ct = up.content_type or mimetypes.guess_type(up.filename)[0] or "application/octet-stream"
                safe_name = re.sub(r"[^\w.\- ]", "_", up.filename)[:120] or "file"
                params["attachments"].append(
                    f"data:{ct};filename={safe_name};base64,{base64.b64encode(up.data).decode()}"
                )
                local_id = f"local-{secrets.token_hex(12)}{Path(safe_name).suffix[:10]}"
                (self.sent_attachments_dir / local_id).write_bytes(up.data)
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
            path = self.sent_attachments_dir / att_id
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
        cache_dir = self.avatar_cache_dir
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
        else:  # u:self is this account's own profile picture (used by the account switcher)
            addr = self._address(conv_id[2:])
            attempts += [{"contact": addr}, {"profile": addr}] if conv_id != "u:self" else [{"profile": addr}]
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

    async def expire_due(self) -> None:
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

    def _delete_attachment_file(self, att_id: str | None) -> None:
        if not att_id or not SAFE_ID.match(att_id):
            return
        base = self.sent_attachments_dir if att_id.startswith("local-") else self.settings.received_attachments_dir
        (base / att_id).unlink(missing_ok=True)


def _send_status(result: dict) -> str:
    results = result.get("results") or []
    if not results:
        return "sent"
    ok = [r for r in results if r.get("type") == "SUCCESS"]
    return "sent" if ok else "failed"
