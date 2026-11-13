"""FastAPI app: REST for history/actions, a WebSocket for live events, and the static UI.

No authentication here on purpose: put it behind your reverse proxy / auth layer, or add
a dependency to `api` (and a check in `websocket_endpoint`).

Routes about one Signal account live under /api/accounts/{acct}/..., where {acct} is the account's
phone number (or ACI if it has none). /api/status, /api/link and /ws are shared by all accounts;
WebSocket events carry an "account" field.

POST /api/hooks/send is for the webhook relay (app/webhook.py): it sends as whichever account the
bearer token belongs to, and only if webhook sending is turned on for that account in the GUI.
"""

from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

import segno
from fastapi import APIRouter, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import Settings
from .rpc import RpcError
from .service import Account, SignalService, Upload

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
STATIC = Path(__file__).parent / "static"
log = logging.getLogger("signal-web.main")
INLINE_SAFE = re.compile(r"^(image/(jpeg|png|gif|webp|avif|heic|heif|bmp)|video/[\w.+-]+|audio/[\w.+-]+)$", re.I)


def content_disposition(disposition: str, filename: str) -> str:
    """RFC 6266 header that survives non-ASCII names (headers are latin-1 on the wire)."""
    ascii_name = re.sub(r'[^\x20-\x7e]|["\\]', "_", filename) or "file"
    return f"{disposition}; filename=\"{ascii_name}\"; filename*=utf-8''{quote(filename, safe='')}"


def normalize_number(raw: str) -> str:
    return re.sub(r"[\s\-().]", "", raw.strip())


class NewConversation(BaseModel):
    recipient: str | None = None  # phone number (E.164) or recipient id
    group_id: str | None = None


class Typing(BaseModel):
    started: bool


class Archive(BaseModel):
    archived: bool


class Reaction(BaseModel):
    emoji: str
    remove: bool = False


class Delete(BaseModel):
    everyone: bool = False


class WebhookSettings(BaseModel):
    enabled: bool | None = None
    regenerate: bool = False


class HookSend(BaseModel):
    recipient: str | None = None  # E.164 number, a contact's UUID, or "self" (Note to Self)
    group_id: str | None = None
    message: str


MAX_HOOK_MESSAGE = 16_000


def resolve_conversation(store, recipient: str | None, group_id: str | None) -> str:
    """Turn what a user typed or picked into a conversation id, creating the conversation."""
    if group_id:
        conv_id = f"g:{group_id.strip()}"
    elif recipient:
        # Only phone numbers get normalized: contacts are sent as UUIDs, which contain dashes.
        r = recipient.strip()
        if r.startswith("+"):
            r = normalize_number(r)
            if not re.fullmatch(r"\+\d{6,15}", r):
                raise HTTPException(400, "Use a phone number in international format, e.g. +15551234567")
            number = r
            r = store.rid_for_number(number) or number
            if r == number:
                store.upsert_recipient(r, number=number)
        elif r != "self" and not store.recipient(r):
            raise HTTPException(400, "Use a phone number in international format, e.g. +15551234567")
        conv_id = f"u:{r}"
    else:
        raise HTTPException(400, "recipient or group_id required")
    store.ensure_conversation(conv_id)
    return conv_id


def bearer_token(authorization: str | None, x_webhook_token: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return (x_webhook_token or "").strip() or None


def get_account(request: Request, acct: str) -> Account:
    account = request.app.state.service.account(acct)
    if account is None:
        raise HTTPException(404, "account not found")
    return account



def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = SignalService(settings)
        app.state.service = service
        await service.start()
        try:
            yield
        finally:
            await service.stop()

    app = FastAPI(title="Signal Web", lifespan=lifespan)
    api = APIRouter(prefix="/api")
    acct_api = APIRouter(prefix="/api/accounts/{acct}")

    def svc(request: Request) -> SignalService:
        return request.app.state.service

    def conv_or_404(account: Account, conv_id: str) -> dict:
        conv = account.store.conversation(conv_id)
        if not conv:
            raise HTTPException(404, "conversation not found")
        return conv

    @app.exception_handler(RpcError)
    async def rpc_error(_: Request, exc: RpcError):
        return JSONResponse({"detail": exc.message, "code": exc.code}, status_code=502)

    @app.exception_handler(ConnectionError)
    async def conn_error(_: Request, exc: ConnectionError):
        return JSONResponse({"detail": str(exc) or "signal-cli unavailable"}, status_code=503)

    # ---------------------------------------------------------------- status / accounts / linking

    @api.get("/status")
    async def status(request: Request):
        return svc(request).status()

    @api.get("/accounts")
    async def accounts(request: Request):
        return [a.summary() for a in svc(request).accounts.values()]

    @api.post("/link")
    async def link(request: Request):
        started = await svc(request).start_link()
        qr = segno.make(started["uri"], error="m")
        return {**started, "qr_svg": qr.svg_inline(border=2, dark="#000", light="#fff", omitsize=True)}

    @api.delete("/link")
    async def cancel_link(request: Request):
        await svc(request).cancel_link()
        return {"ok": True}

    # ---------------------------------------------------------------- webhook sending

    @acct_api.get("/webhook")
    async def webhook_settings(account: Account = Depends(get_account)):
        return account.webhook()

    @acct_api.put("/webhook")
    async def update_webhook(body: WebhookSettings, account: Account = Depends(get_account)):
        return account.set_webhook(body.enabled, body.regenerate)

    @api.post("/hooks/send")
    async def hook_send(
        body: HookSend,
        request: Request,
        authorization: str | None = Header(None),
        x_webhook_token: str | None = Header(None),
    ):
        token = bearer_token(authorization, x_webhook_token)
        account, enabled = svc(request).webhook_account(token) if token else (None, False)
        if account is None:
            raise HTTPException(401, "Unknown webhook token")
        if not enabled:
            raise HTTPException(403, "Webhook sending is turned off for this account (enable it in Signal Web)")
        text = body.message.strip()
        if not text:
            raise HTTPException(400, "message is empty")
        if len(text) > MAX_HOOK_MESSAGE:
            raise HTTPException(413, f"message is longer than {MAX_HOOK_MESSAGE} characters")
        conv_id = resolve_conversation(account.store, body.recipient, body.group_id)
        conv = account.store.conversation(conv_id) or {}
        if conv.get("kind") == "group" and not conv.get("is_member", True):
            raise HTTPException(400, "This account is not a member of that group")
        msg = await account.send_message(conv_id, text)
        log.info("webhook message sent from %s to %s: %s", account.key, conv_id, msg.get("status"))
        result = {
            "ok": msg.get("status") != "failed",
            "account": account.key,
            "conversation_id": conv_id,
            "message_id": msg.get("id"),
            "sent_ts": msg.get("sent_ts"),
            "status": msg.get("status"),
        }
        return JSONResponse(result, status_code=200 if result["ok"] else 502)

    # ---------------------------------------------------------------- conversations

    @acct_api.get("/conversations")
    async def conversations(archived: bool = False, account: Account = Depends(get_account)):
        return account.store.list_conversations(include_archived=archived)

    @acct_api.post("/conversations")
    async def new_conversation(body: NewConversation, account: Account = Depends(get_account)):
        conv_id = resolve_conversation(account.store, body.recipient, body.group_id)
        return account.store.conversation(conv_id)

    @acct_api.get("/conversations/{conv_id:path}/messages")
    async def messages(
        conv_id: str, before: int | None = None, limit: int = Query(50, le=200), account: Account = Depends(get_account)
    ):
        conv_or_404(account, conv_id)
        return account.store.messages(conv_id, before=before, limit=limit)

    @acct_api.post("/conversations/{conv_id:path}/messages")
    async def send(
        conv_id: str,
        text: str = Form(""),
        quote_id: int | None = Form(None),
        edit_id: int | None = Form(None),
        files: list[UploadFile] = File(default=[]),
        account: Account = Depends(get_account),
    ):
        conv = conv_or_404(account, conv_id)
        if conv["kind"] == "group" and not conv.get("is_member", True):
            raise HTTPException(400, "You are not a member of this group")
        text = text.strip()
        uploads = []
        limit = settings.max_upload_mb * 1024 * 1024
        for f in files:
            data = await f.read()
            if len(data) > limit:
                raise HTTPException(413, f"{f.filename} is larger than {settings.max_upload_mb} MB")
            uploads.append(Upload(f.filename or "file", f.content_type or "", data))
        if not text and not uploads:
            raise HTTPException(400, "Nothing to send")
        try:
            return await account.send_message(conv_id, text, uploads, quote_id=quote_id, edit_id=edit_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @acct_api.post("/conversations/{conv_id:path}/read")
    async def read(conv_id: str, account: Account = Depends(get_account)):
        conv_or_404(account, conv_id)
        await account.mark_read(conv_id)
        return {"ok": True}

    @acct_api.post("/conversations/{conv_id:path}/typing")
    async def typing(body: Typing, conv_id: str, account: Account = Depends(get_account)):
        conv_or_404(account, conv_id)
        await account.send_typing(conv_id, body.started)
        return {"ok": True}

    @acct_api.post("/conversations/{conv_id:path}/archive")
    async def archive(body: Archive, conv_id: str, account: Account = Depends(get_account)):
        conv_or_404(account, conv_id)
        account.store.set_archived(conv_id, body.archived)
        conv = account.store.conversation(conv_id)
        await account.broadcast({"type": "conversation", "conversation": conv})
        return conv

    @acct_api.get("/conversations/{conv_id:path}")
    async def conversation(conv_id: str, account: Account = Depends(get_account)):
        conv = conv_or_404(account, conv_id)
        if conv["kind"] == "group":
            g = account.store.group(conv["peer"]) or {}
            conv["description"] = g.get("description")
            conv["members"] = [
                {"rid": m, "name": account.store.display_name(m)} for m in g.get("members") or []
            ]
        return conv

    # ---------------------------------------------------------------- messages

    @acct_api.post("/messages/{msg_id}/react")
    async def react(body: Reaction, msg_id: int, account: Account = Depends(get_account)):
        try:
            await account.react(msg_id, body.emoji, body.remove)
        except KeyError as exc:
            raise HTTPException(404, "message not found") from exc
        return {"ok": True}

    @acct_api.post("/messages/{msg_id}/delete")
    async def delete(body: Delete, msg_id: int, account: Account = Depends(get_account)):
        try:
            if body.everyone:
                await account.delete_for_everyone(msg_id)
            else:
                await account.delete_locally(msg_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True}

    @acct_api.get("/search")
    async def search(q: str = Query(..., min_length=2), account: Account = Depends(get_account)):
        return account.store.search(q)

    @acct_api.get("/contacts")
    async def contacts(account: Account = Depends(get_account)):
        people = [
            {"rid": r["id"], "name": r["name"], "number": r.get("number")}
            for r in account.store.list_recipients()
            if r.get("contact_name") or r.get("nick_name") or r.get("profile_name")
        ]
        return {"people": people, "groups": account.store.list_groups()}

    # ---------------------------------------------------------------- media

    @acct_api.get("/attachments/{att_id}")
    async def attachment(att_id: str, download: bool = False, account: Account = Depends(get_account)):
        found = await account.attachment(att_id)
        if not found:
            raise HTTPException(404, "attachment not available")
        content, ct = found
        meta = account.store.find_attachment(att_id) or {}
        filename = meta.get("filename") or att_id
        # The content type comes from the sender. Only render passive media inline; anything else
        # (HTML, SVG, PDF, unknown) is forced to download so it can't run script on our origin.
        inline_ok = bool(INLINE_SAFE.match(ct))
        disposition = "inline" if inline_ok and not download else "attachment"
        headers = {"Cache-Control": "private, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"}
        if isinstance(content, Path):
            return FileResponse(content, media_type=ct, filename=filename, content_disposition_type=disposition, headers=headers)
        headers["Content-Disposition"] = content_disposition(disposition, filename)
        return Response(content, media_type=ct, headers=headers)

    @acct_api.get("/avatars/{conv_id:path}")
    async def avatar(conv_id: str, account: Account = Depends(get_account)):
        data = await account.avatar(conv_id)
        if not data:
            return Response(status_code=204, headers={"Cache-Control": "private, max-age=3600"})
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})

    app.include_router(api)
    app.include_router(acct_api)

    # ---------------------------------------------------------------- live events

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        service: SignalService = ws.app.state.service
        await service.hub.add(ws)
        try:
            await ws.send_json({"type": "status", "status": service.status()})
            while True:
                await ws.receive_text()  # client pings; nothing else expected
        except WebSocketDisconnect:
            pass
        finally:
            service.hub.remove(ws)

    @app.get("/healthz")
    async def healthz(request: Request):
        # Left open by design (README), so it reports only the state: no numbers, names or counts.
        state = svc(request).status()["state"]
        return JSONResponse({"state": state}, status_code=200 if state in ("ready", "unlinked") else 503)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
