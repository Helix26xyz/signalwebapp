"""Webhook relay: a small separate process that turns incoming webhooks into Signal messages.

    python -m app.webhook        # listens on WEBHOOK_HOST:WEBHOOK_PORT (default 0.0.0.0:8081)

Expose this port to whatever sends your webhooks, and keep the main app (8080) behind your auth.
The relay holds no secrets or account list of its own. Each request carries a token that you get
from Signal Web (account menu → Webhook sending); the main app maps the token to that account and
refuses unless webhook sending is turned on for it there.

    POST /send
    Authorization: Bearer swh_...        (or X-Webhook-Token: swh_..., or ?token=swh_...)
    {"recipient": "+15551234567", "message": "Backup finished"}

`recipient` is a phone number in international format, "self" (your Note to Self) or a contact's
UUID; use `group_id` instead for a group. Aliases: `to` for recipient, `text` for message. The
fields can also come as form data or query parameters, for senders that can't build JSON.
Responds with the main app's answer: 200 {"ok": true, "message_id": ..., ...} on success.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from urllib.parse import parse_qs

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import RelaySettings

log = logging.getLogger("signal-web.webhook")

ALIASES = {"recipient": ("recipient", "to"), "group_id": ("group_id", "groupId"), "message": ("message", "text")}


def _token(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return (request.headers.get("x-webhook-token") or request.query_params.get("token") or "").strip() or None


def _fields(raw: bytes, content_type: str, query: dict[str, str]) -> dict:
    """Accept JSON, form data or query parameters, with a few common field names."""
    data: dict = {}
    if raw:
        if "json" in content_type or raw.lstrip()[:1] in (b"{",):
            loaded = json.loads(raw)
            if not isinstance(loaded, dict):
                raise ValueError("JSON body must be an object")
            data = loaded
        elif "x-www-form-urlencoded" in content_type:
            data = {k: v[-1] for k, v in parse_qs(raw.decode()).items()}
        elif content_type.startswith("text/"):
            data = {"message": raw.decode()}  # plain-text body = the message; recipient in the query
    out = {}
    for key, names in ALIASES.items():
        for name in names:
            value = data.get(name, query.get(name))
            if value not in (None, ""):
                out[key] = str(value)
                break
    return out


def create_relay(settings: RelaySettings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    settings = settings or RelaySettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Sends wait up to 30 s for signal-cli inside the main app, so allow well beyond that.
        async with httpx.AsyncClient(base_url=settings.signal_web_url, timeout=120, transport=transport) as client:
            app.state.client = client
            yield

    app = FastAPI(title="Signal Web webhook relay", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    async def forward(client: httpx.AsyncClient, token: str, payload: dict) -> httpx.Response:
        # Retry only when the main app can't be reached at all, so a message is never sent twice.
        deadline, delay = time.monotonic() + settings.retry_seconds, 0.5
        while True:
            try:
                return await client.post("/api/hooks/send", json=payload, headers={"Authorization": f"Bearer {token}"})
            except httpx.ConnectError:
                if time.monotonic() + delay > deadline:
                    raise
                log.info("signal-web unreachable, retrying in %.1fs", delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 5)

    @app.post("/send")
    async def send(request: Request):
        token = _token(request)
        if not token:
            return JSONResponse({"detail": "Missing token (Authorization: Bearer swh_...)"}, status_code=401)
        raw = await request.body()
        if len(raw) > settings.max_body_bytes:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
        try:
            payload = _fields(raw, request.headers.get("content-type", ""), dict(request.query_params))
        except (ValueError, UnicodeDecodeError) as exc:
            return JSONResponse({"detail": f"Could not read the request: {exc}"}, status_code=400)
        if "message" not in payload or not ("recipient" in payload or "group_id" in payload):
            return JSONResponse({"detail": "Need message and recipient (or group_id)"}, status_code=400)
        try:
            resp = await forward(request.app.state.client, token, payload)
        except httpx.HTTPError as exc:
            log.warning("could not reach signal-web at %s: %s", settings.signal_web_url, exc)
            return JSONResponse({"detail": "Signal Web is unreachable"}, status_code=503)
        try:
            body = resp.json()
        except ValueError:
            body = {"detail": resp.text[:500]}
        log.info("webhook → %s", resp.status_code)  # never log message bodies
        return JSONResponse(body, status_code=resp.status_code)

    @app.get("/healthz")
    async def healthz(request: Request):
        try:
            upstream = (await request.app.state.client.get("/healthz", timeout=5)).json().get("state")
        except Exception:  # noqa: BLE001
            upstream = "unreachable"
        return JSONResponse({"relay": "ok", "signal_web": upstream}, status_code=200 if upstream == "ready" else 503)

    return app


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = RelaySettings()
    log.info("webhook relay on %s:%s → %s", settings.host, settings.port, settings.signal_web_url)
    uvicorn.run(create_relay(settings), host=settings.host, port=settings.port, log_level="warning")


if __name__ == "__main__":
    main()
