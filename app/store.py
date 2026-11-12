"""SQLite persistence. This database is the app's source of truth for history.

Identity conventions used throughout:
  * recipient id ("rid"): the account's ACI UUID when known, otherwise the phone number.
    The literal string "self" means this account.
  * conversation id: "u:<rid>" for 1:1 chats (u:self is Note to Self), "g:<groupId>" for groups.
  * a Signal message is identified by (author rid, sent timestamp in ms).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS recipients (
    id TEXT PRIMARY KEY,
    uuid TEXT,
    number TEXT,
    username TEXT,
    contact_name TEXT,
    nick_name TEXT,
    profile_name TEXT,
    envelope_name TEXT,
    color TEXT,
    blocked INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER
);
CREATE INDEX IF NOT EXISTS recipients_number ON recipients(number);

CREATE TABLE IF NOT EXISTS groups (
    id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    members TEXT,
    is_member INTEGER NOT NULL DEFAULT 1,
    blocked INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    peer TEXT NOT NULL,
    last_ts INTEGER NOT NULL DEFAULT 0,
    last_preview TEXT,
    last_author TEXT,
    unread INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0,
    expire_timer INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS conversations_last ON conversations(last_ts DESC);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    author TEXT NOT NULL,
    sent_ts INTEGER NOT NULL,
    server_ts INTEGER,
    kind TEXT NOT NULL DEFAULT 'message',
    body TEXT,
    attachments TEXT,
    quote TEXT,
    mentions TEXT,
    text_styles TEXT,
    previews TEXT,
    sticker TEXT,
    status TEXT,
    is_read INTEGER NOT NULL DEFAULT 0,
    edited INTEGER NOT NULL DEFAULT 0,
    edit_history TEXT,
    deleted INTEGER NOT NULL DEFAULT 0,
    expires_in INTEGER NOT NULL DEFAULT 0,
    expire_at INTEGER,
    created_at INTEGER NOT NULL,
    UNIQUE(conversation_id, author, sent_ts)
);
CREATE INDEX IF NOT EXISTS messages_conv_ts ON messages(conversation_id, sent_ts);
CREATE INDEX IF NOT EXISTS messages_author_ts ON messages(author, sent_ts);
CREATE INDEX IF NOT EXISTS messages_expire ON messages(expire_at) WHERE expire_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS reactions (
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    author TEXT NOT NULL,
    emoji TEXT NOT NULL,
    ts INTEGER,
    PRIMARY KEY (message_id, author)
);

CREATE TABLE IF NOT EXISTS raw_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at INTEGER NOT NULL,
    account TEXT,
    json TEXT NOT NULL
);
"""

JSON_FIELDS = ("attachments", "quote", "mentions", "text_styles", "previews", "sticker", "edit_history")
STATUS_RANK = {"failed": 0, "sending": 1, "sent": 2, "delivered": 3, "read": 4, "viewed": 4}


def now_ms() -> int:
    return int(time.time() * 1000)


def _dumps(value: Any) -> str | None:
    if value is None or value == [] or value == {}:
        return None
    return json.dumps(value, ensure_ascii=False)


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)

    # ------------------------------------------------------------------ helpers

    def _q(self, sql: str, args: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.db.execute(sql, tuple(args)).fetchall()

    def _one(self, sql: str, args: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self.db.execute(sql, tuple(args)).fetchone()

    def _x(self, sql: str, args: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.db.execute(sql, tuple(args))

    def transaction(self):
        return _Tx(self)

    # ------------------------------------------------------------------ meta

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self._one("SELECT value FROM meta WHERE key=?", (key,))
        return row["value"] if row else default

    def set_meta(self, key: str, value: str | None) -> None:
        self._x(
            "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def add_raw_event(self, account: str | None, payload: dict) -> None:
        self._x(
            "INSERT INTO raw_events(received_at, account, json) VALUES(?, ?, ?)",
            (now_ms(), account, json.dumps(payload, ensure_ascii=False)),
        )

    # ------------------------------------------------------------------ recipients

    def rid_for_number(self, number: str) -> str | None:
        row = self._one(
            "SELECT id FROM recipients WHERE number=? AND uuid IS NOT NULL ORDER BY updated_at DESC LIMIT 1",
            (number,),
        )
        return row["id"] if row else None

    def upsert_recipient(self, rid: str, **fields: Any) -> None:
        """Insert/update a recipient; None values never overwrite existing data."""
        fields = {k: v for k, v in fields.items() if v is not None}
        cols = ["id", "updated_at", *fields.keys()]
        vals = [rid, now_ms(), *fields.values()]
        updates = ", ".join(f"{k}=excluded.{k}" for k in ["updated_at", *fields.keys()])
        self._x(
            f"INSERT INTO recipients({', '.join(cols)}) VALUES({', '.join('?' for _ in cols)}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            vals,
        )

    def merge_number_into_uuid(self, number: str, uuid: str) -> list[str]:
        """A recipient first seen by phone number turned out to have this UUID: move its
        history over so there is one conversation per person. Returns touched conversation ids."""
        old_conv, new_conv = f"u:{number}", f"u:{uuid}"
        touched: list[str] = []
        with self.transaction():
            if self._one("SELECT 1 FROM conversations WHERE id=?", (old_conv,)):
                if not self._one("SELECT 1 FROM conversations WHERE id=?", (new_conv,)):
                    self._x("UPDATE conversations SET id=?, peer=? WHERE id=?", (new_conv, uuid, old_conv))
                else:
                    self._x("DELETE FROM conversations WHERE id=?", (old_conv,))
                self._x(
                    "UPDATE OR IGNORE messages SET conversation_id=? WHERE conversation_id=?",
                    (new_conv, old_conv),
                )
                self._x("DELETE FROM messages WHERE conversation_id=?", (old_conv,))
                touched += [old_conv, new_conv]
            self._x("UPDATE OR IGNORE messages SET author=? WHERE author=?", (uuid, number))
            self._x("UPDATE OR IGNORE reactions SET author=? WHERE author=?", (uuid, number))
            self._x("DELETE FROM recipients WHERE id=? AND uuid IS NULL", (number,))
        return touched

    def recipient(self, rid: str) -> dict | None:
        row = self._one("SELECT * FROM recipients WHERE id=?", (rid,))
        return dict(row) if row else None

    def display_name(self, rid: str | None) -> str:
        if not rid:
            return "Unknown"
        if rid == "self":
            return "You"
        r = self.recipient(rid)
        if not r:
            return rid if rid.startswith("+") else "Unknown"
        return (
            r.get("nick_name")
            or r.get("contact_name")
            or r.get("profile_name")
            or r.get("envelope_name")
            or r.get("number")
            or (f"@{r['username']}" if r.get("username") else None)
            or "Unknown"
        )

    def list_recipients(self) -> list[dict]:
        rows = self._q("SELECT * FROM recipients WHERE blocked=0")
        out = []
        for r in rows:
            d = dict(r)
            d["name"] = self.display_name(r["id"])
            out.append(d)
        out.sort(key=lambda d: d["name"].lower())
        return out

    # ------------------------------------------------------------------ groups

    def upsert_group(self, gid: str, **fields: Any) -> None:
        fields = {k: v for k, v in fields.items() if v is not None}
        if "members" in fields and not isinstance(fields["members"], str):
            fields["members"] = json.dumps(fields["members"])
        cols = ["id", "updated_at", *fields.keys()]
        vals = [gid, now_ms(), *fields.values()]
        updates = ", ".join(f"{k}=excluded.{k}" for k in ["updated_at", *fields.keys()])
        self._x(
            f"INSERT INTO groups({', '.join(cols)}) VALUES({', '.join('?' for _ in cols)}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            vals,
        )

    def group(self, gid: str) -> dict | None:
        row = self._one("SELECT * FROM groups WHERE id=?", (gid,))
        if not row:
            return None
        d = dict(row)
        d["members"] = json.loads(d["members"]) if d.get("members") else []
        return d

    # ------------------------------------------------------------------ conversations

    def ensure_conversation(self, conv_id: str) -> None:
        kind, peer = ("group", conv_id[2:]) if conv_id.startswith("g:") else ("direct", conv_id[2:])
        self._x(
            "INSERT OR IGNORE INTO conversations(id, kind, peer) VALUES(?, ?, ?)",
            (conv_id, kind, peer),
        )

    def set_expire_timer(self, conv_id: str, seconds: int) -> None:
        self.ensure_conversation(conv_id)
        self._x("UPDATE conversations SET expire_timer=? WHERE id=?", (seconds, conv_id))

    def refresh_conversation(self, conv_id: str) -> None:
        """Recompute denormalized fields (last message, preview, unread count)."""
        last = self._one(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY sent_ts DESC, id DESC LIMIT 1",
            (conv_id,),
        )
        unread = self._one(
            "SELECT COUNT(*) AS n FROM messages WHERE conversation_id=? AND author!='self' "
            "AND is_read=0 AND deleted=0 AND kind='message'",
            (conv_id,),
        )["n"]
        if last is None:
            self._x(
                "UPDATE conversations SET last_preview=NULL, last_author=NULL, unread=? WHERE id=?",
                (unread, conv_id),
            )
            return
        self._x(
            "UPDATE conversations SET last_ts=MAX(last_ts, ?), last_preview=?, last_author=?, unread=?, "
            "archived=CASE WHEN ? > 0 THEN 0 ELSE archived END WHERE id=?",
            (last["sent_ts"], preview_for(dict(last)), last["author"], unread, unread, conv_id),
        )

    def conversation(self, conv_id: str) -> dict | None:
        row = self._one("SELECT * FROM conversations WHERE id=?", (conv_id,))
        return self._decorate_conversation(dict(row)) if row else None

    def list_conversations(self, include_archived: bool = False) -> list[dict]:
        sql = "SELECT * FROM conversations WHERE last_ts > 0"
        if not include_archived:
            sql += " AND archived=0"
        sql += " ORDER BY last_ts DESC"
        return [self._decorate_conversation(dict(r)) for r in self._q(sql)]

    def set_archived(self, conv_id: str, archived: bool) -> None:
        self._x("UPDATE conversations SET archived=? WHERE id=?", (1 if archived else 0, conv_id))

    def _decorate_conversation(self, c: dict) -> dict:
        if c["kind"] == "group":
            g = self.group(c["peer"])
            c["name"] = (g or {}).get("name") or "Unnamed group"
            c["member_count"] = len((g or {}).get("members") or [])
            c["is_member"] = bool((g or {}).get("is_member", 1))
        elif c["peer"] == "self":
            c["name"] = "Note to Self"
        else:
            c["name"] = self.display_name(c["peer"])
            r = self.recipient(c["peer"]) or {}
            c["number"] = r.get("number")
        c["last_author_name"] = (
            self.display_name(c["last_author"]) if c.get("last_author") and c["kind"] == "group" else None
        )
        c["archived"] = bool(c["archived"])
        return c

    # ------------------------------------------------------------------ messages

    def find_message(self, author: str, sent_ts: int, conv_id: str | None = None) -> dict | None:
        if conv_id:
            row = self._one(
                "SELECT * FROM messages WHERE conversation_id=? AND author=? AND sent_ts=?",
                (conv_id, author, sent_ts),
            )
            if row:
                return dict(row)
        row = self._one("SELECT * FROM messages WHERE author=? AND sent_ts=? LIMIT 1", (author, sent_ts))
        return dict(row) if row else None

    def message_row(self, msg_id: int) -> dict | None:
        row = self._one("SELECT * FROM messages WHERE id=?", (msg_id,))
        return dict(row) if row else None

    def upsert_message(self, conv_id: str, author: str, sent_ts: int, **fields: Any) -> int:
        """Insert a message, or fill in an existing one (same author + timestamp). Returns row id."""
        self.ensure_conversation(conv_id)
        for f in JSON_FIELDS:
            if f in fields:
                fields[f] = _dumps(fields[f])
        existing = self._one(
            "SELECT id FROM messages WHERE conversation_id=? AND author=? AND sent_ts=?",
            (conv_id, author, sent_ts),
        )
        if existing:
            sets = {k: v for k, v in fields.items() if v is not None and k not in ("is_read", "status")}
            if sets:
                self._x(
                    f"UPDATE messages SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?",
                    [*sets.values(), existing["id"]],
                )
            return existing["id"]
        fields.setdefault("created_at", now_ms())
        cols = ["conversation_id", "author", "sent_ts", *fields.keys()]
        cur = self._x(
            f"INSERT INTO messages({', '.join(cols)}) VALUES({', '.join('?' for _ in cols)})",
            [conv_id, author, sent_ts, *fields.values()],
        )
        return int(cur.lastrowid)

    def update_message(self, msg_id: int, **fields: Any) -> None:
        for f in JSON_FIELDS:
            if f in fields:
                fields[f] = _dumps(fields[f])
        if fields:
            self._x(
                f"UPDATE messages SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                [*fields.values(), msg_id],
            )

    def bump_status(self, msg_id: int, status: str) -> bool:
        row = self._one("SELECT status FROM messages WHERE id=?", (msg_id,))
        if not row:
            return False
        if STATUS_RANK.get(status, 0) > STATUS_RANK.get(row["status"] or "", 0):
            self._x("UPDATE messages SET status=? WHERE id=?", (status, msg_id))
            return True
        return False

    def delete_message_row(self, msg_id: int) -> None:
        self._x("DELETE FROM messages WHERE id=?", (msg_id,))

    def set_reaction(self, msg_id: int, author: str, emoji: str | None, ts: int) -> None:
        if emoji is None:
            self._x("DELETE FROM reactions WHERE message_id=? AND author=?", (msg_id, author))
        else:
            self._x(
                "INSERT INTO reactions(message_id, author, emoji, ts) VALUES(?, ?, ?, ?) "
                "ON CONFLICT(message_id, author) DO UPDATE SET emoji=excluded.emoji, ts=excluded.ts",
                (msg_id, author, emoji, ts),
            )

    def unread_incoming(self, conv_id: str, up_to_ts: int | None = None) -> list[dict]:
        sql = (
            "SELECT * FROM messages WHERE conversation_id=? AND author!='self' AND is_read=0 "
            "AND kind='message'"
        )
        args: list[Any] = [conv_id]
        if up_to_ts is not None:
            sql += " AND sent_ts<=?"
            args.append(up_to_ts)
        return [dict(r) for r in self._q(sql, args)]

    def mark_read(self, msg_ids: list[int], read_at: int | None = None) -> None:
        """Mark incoming messages read, starting disappearing-message timers."""
        read_at = read_at or now_ms()
        for mid in msg_ids:
            self._x(
                "UPDATE messages SET is_read=1, expire_at=CASE WHEN expires_in>0 AND expire_at IS NULL "
                "THEN ? + expires_in*1000 ELSE expire_at END WHERE id=?",
                (read_at, mid),
            )

    def expired_messages(self, at: int | None = None) -> list[dict]:
        return [
            dict(r)
            for r in self._q(
                "SELECT * FROM messages WHERE expire_at IS NOT NULL AND expire_at<=?", (at or now_ms(),)
            )
        ]

    def messages(self, conv_id: str, before: int | None = None, limit: int = 50) -> list[dict]:
        sql = "SELECT * FROM messages WHERE conversation_id=?"
        args: list[Any] = [conv_id]
        if before is not None:
            sql += " AND sent_ts<?"
            args.append(before)
        sql += " ORDER BY sent_ts DESC, id DESC LIMIT ?"
        args.append(limit)
        rows = [dict(r) for r in self._q(sql, args)]
        rows.reverse()
        return [self._decorate_message(r) for r in rows]

    def message(self, msg_id: int) -> dict | None:
        row = self.message_row(msg_id)
        return self._decorate_message(row) if row else None

    def search(self, text: str, limit: int = 50) -> list[dict]:
        like = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        rows = self._q(
            "SELECT * FROM messages WHERE deleted=0 AND body LIKE ? ESCAPE '\\' "
            "ORDER BY sent_ts DESC LIMIT ?",
            (like, limit),
        )
        out = []
        for r in rows:
            m = self._decorate_message(dict(r))
            conv = self.conversation(m["conversation_id"])
            m["conversation_name"] = conv["name"] if conv else ""
            out.append(m)
        return out

    def find_attachment(self, att_id: str) -> dict | None:
        like = f'%"id": "{att_id}"%'
        row = self._one("SELECT attachments FROM messages WHERE attachments LIKE ? LIMIT 1", (like,))
        if not row:
            return None
        for a in json.loads(row["attachments"]):
            if a.get("id") == att_id:
                return a
        return None

    def _decorate_message(self, m: dict) -> dict:
        for f in JSON_FIELDS:
            m[f] = json.loads(m[f]) if m.get(f) else None
        m["attachments"] = m["attachments"] or []
        m["outgoing"] = m["author"] == "self"
        m["author_name"] = self.display_name(m["author"])
        m["is_read"] = bool(m["is_read"])
        m["edited"] = bool(m["edited"])
        m["deleted"] = bool(m["deleted"])
        if m.get("quote"):
            m["quote"]["author_name"] = self.display_name(m["quote"].get("author"))
        for mention in m.get("mentions") or []:
            mention["name"] = self.display_name(mention.get("rid"))
        reactions = self._q(
            "SELECT author, emoji, ts FROM reactions WHERE message_id=? ORDER BY ts", (m["id"],)
        )
        m["reactions"] = [
            {"author": r["author"], "emoji": r["emoji"], "author_name": self.display_name(r["author"])}
            for r in reactions
        ]
        if m["deleted"]:
            m["body"] = None
            m["attachments"] = []
            m["quote"] = None
            m["previews"] = None
            m["sticker"] = None
            m["reactions"] = []
        return m


class _Tx:
    def __init__(self, store: Store):
        self.store = store

    """Re-entrant transaction: the outermost one is BEGIN/COMMIT, nested ones are savepoints."""

    def __enter__(self):
        self.store._lock.acquire()
        self.depth = getattr(self.store, "_tx_depth", 0)
        self.store._tx_depth = self.depth + 1
        self.store.db.execute("BEGIN" if self.depth == 0 else f"SAVEPOINT sp{self.depth}")
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.depth == 0:
                self.store.db.execute("ROLLBACK" if exc_type else "COMMIT")
            elif exc_type:
                self.store.db.execute(f"ROLLBACK TO sp{self.depth}")
                self.store.db.execute(f"RELEASE sp{self.depth}")
            else:
                self.store.db.execute(f"RELEASE sp{self.depth}")
        finally:
            self.store._tx_depth = self.depth
            self.store._lock.release()
        return False


def preview_for(m: dict) -> str:
    if m.get("deleted"):
        return "This message was deleted"
    if m.get("kind") == "system":
        return m.get("body") or ""
    if m.get("body"):
        return m["body"]
    atts = m.get("attachments")
    if isinstance(atts, str):
        atts = json.loads(atts)
    if atts:
        ct = (atts[0].get("contentType") or "").split("/")[0]
        label = {"image": "📷 Photo", "video": "🎥 Video", "audio": "🎤 Audio"}.get(ct, "📎 Attachment")
        return label if len(atts) == 1 else f"{label} (+{len(atts) - 1})"
    if m.get("sticker"):
        return "Sticker"
    return ""
