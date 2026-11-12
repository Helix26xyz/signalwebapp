"""FastAPI app: REST for history/actions, a WebSocket for live events, and the static UI.

No authentication here on purpose: put it behind your reverse proxy / auth layer, or add
a dependency to `api` (and a check in `websocket_endpoint`).
"""

from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

import segno
from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import Settings
from .rpc import RpcError
from .service import SignalService, Upload

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
STATIC = Path(__file__).parent / "static"
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

    def svc(request: Request) -> SignalService:
        return request.app.state.service

    def conv_or_404(service: SignalService, conv_id: str) -> dict:
        conv = service.store.conversation(conv_id)
        if not conv:
            raise HTTPException(404, "conversation not found")
        return conv

    @app.exception_handler(RpcError)
    async def rpc_error(_: Request, exc: RpcError):
        return JSONResponse({"detail": exc.message, "code": exc.code}, status_code=502)

    @app.exception_handler(ConnectionError)
    async def conn_error(_: Request, exc: ConnectionError):
        return JSONResponse({"detail": str(exc) or "signal-cli unavailable"}, status_code=503)

    # ---------------------------------------------------------------- status / linking

    @api.get("/status")
    async def status(request: Request):
        return svc(request).status()

    @api.post("/link")
    async def link(request: Request):
        uri = await svc(request).start_link()
        qr = segno.make(uri, error="m")
        return {"uri": uri, "qr_svg": qr.svg_inline(border=2, dark="#000", light="#fff", omitsize=True)}

    # ---------------------------------------------------------------- conversations

    @api.get("/conversations")
    async def conversations(request: Request, archived: bool = False):
        return svc(request).store.list_conversations(include_archived=archived)


    @api.post("/conversations")
    async def new_conversation(body: NewConversation, request: Request):
        service = svc(request)
        if body.group_id:
            conv_id = f"g:{body.group_id}"
        elif body.recipient:
            r = normalize_number(body.recipient)
            if r.startswith("+"):
                if not re.fullmatch(r"\+\d{6,15}", r):
                    raise HTTPException(400, "Use a phone number in international format, e.g. +15551234567")
                number = r
                r = service.store.rid_for_number(number) or number
                if r == number:
                    service.store.upsert_recipient(r, number=number)
            elif r != "self" and not service.store.recipient(r):
                raise HTTPException(400, "Use a phone number in international format, e.g. +15551234567")
            conv_id = f"u:{r}"
        else:
            raise HTTPException(400, "recipient or group_id required")
        service.store.ensure_conversation(conv_id)
        return service.store.conversation(conv_id)

    @api.get("/conversations/{conv_id:path}/messages")
    async def messages(request: Request, conv_id: str, before: int | None = None, limit: int = Query(50, le=200)):
        service = svc(request)
        conv_or_404(service, conv_id)
        return service.store.messages(conv_id, before=before, limit=limit)

    @api.post("/conversations/{conv_id:path}/messages")
    async def send(
        request: Request,
        conv_id: str,
        text: str = Form(""),
        quote_id: int | None = Form(None),
        edit_id: int | None = Form(None),
        files: list[UploadFile] = File(default=[]),
    ):
        service = svc(request)
        conv = conv_or_404(service, conv_id)
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
            return await service.send_message(conv_id, text, uploads, quote_id=quote_id, edit_id=edit_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @api.post("/conversations/{conv_id:path}/read")
    async def read(request: Request, conv_id: str):
        service = svc(request)
        conv_or_404(service, conv_id)
        await service.mark_read(conv_id)
        return {"ok": True}


    @api.post("/conversations/{conv_id:path}/typing")
    async def typing(body: Typing, request: Request, conv_id: str):
        service = svc(request)
        conv_or_404(service, conv_id)
        await service.send_typing(conv_id, body.started)
        return {"ok": True}


    @api.post("/conversations/{conv_id:path}/archive")
    async def archive(body: Archive, request: Request, conv_id: str):
        service = svc(request)
        conv_or_404(service, conv_id)
        service.store.set_archived(conv_id, body.archived)
        conv = service.store.conversation(conv_id)
        await service.hub.broadcast({"type": "conversation", "conversation": conv})
        return conv

    @api.get("/conversations/{conv_id:path}")
    async def conversation(request: Request, conv_id: str):
        service = svc(request)
        conv = conv_or_404(service, conv_id)
        if conv["kind"] == "group":
            g = service.store.group(conv["peer"]) or {}
            conv["description"] = g.get("description")
            conv["members"] = [
                {"rid": m, "name": service.store.display_name(m)} for m in g.get("members") or []
            ]
        return conv

    # ---------------------------------------------------------------- messages


    @api.post("/messages/{msg_id}/react")
    async def react(body: Reaction, request: Request, msg_id: int):
        try:
            await svc(request).react(msg_id, body.emoji, body.remove)
        except KeyError as exc:
            raise HTTPException(404, "message not found") from exc
        return {"ok": True}


    @api.post("/messages/{msg_id}/delete")
    async def delete(body: Delete, request: Request, msg_id: int):
        service = svc(request)
        try:
            if body.everyone:
                await service.delete_for_everyone(msg_id)
            else:
                await service.delete_locally(msg_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True}

    @api.get("/search")
    async def search(request: Request, q: str = Query(..., min_length=2)):
        return svc(request).store.search(q)

    @api.get("/contacts")
    async def contacts(request: Request):
        service = svc(request)
        people = [
            {"rid": r["id"], "name": r["name"], "number": r.get("number")}
            for r in service.store.list_recipients()
            if r.get("contact_name") or r.get("nick_name") or r.get("profile_name")
        ]
        groups = [
            {"id": g["id"], "name": g["name"]}
            for g in (
                dict(row) for row in service.store._q("SELECT id, name FROM groups WHERE is_member=1 ORDER BY name")
            )
        ]
        return {"people": people, "groups": groups}

    # ---------------------------------------------------------------- media

    @api.get("/attachments/{att_id}")
    async def attachment(request: Request, att_id: str, download: bool = False):
        found = await svc(request).attachment(att_id)
        if not found:
            raise HTTPException(404, "attachment not available")
        content, ct = found
        meta = svc(request).store.find_attachment(att_id) or {}
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

    @api.get("/avatars/{conv_id:path}")
    async def avatar(request: Request, conv_id: str):
        data = await svc(request).avatar(conv_id)
        if not data:
            return Response(status_code=204, headers={"Cache-Control": "private, max-age=3600"})
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})

    app.include_router(api)

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
        s = svc(request).status()
        return JSONResponse(s, status_code=200 if s["state"] in ("ready", "unlinked", "linking") else 503)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
