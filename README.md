# Signal Web

A self-hosted web client for Signal, in the style of Google Messages. It runs as a **linked device**
on your account (just like your second Molly phone), keeps its own message history in SQLite, and
stays in sync with your other devices.

```
Signal servers
     │   per-device encrypted queue (this app is one more device)
signal-cli jsonRpc        ← child process, started with --receive-mode=manual
     │   stdin/stdout JSON-RPC
FastAPI app ──► SQLite (data/signal-web.db: the app's history store)
     │   REST + WebSocket
Browser UI (vanilla JS, no build step)
```

## How sync works (and why this design)

Your devices never talk to each other directly. When you send from your phone, the phone encrypts
one copy per recipient device **and** a "sent transcript" sync message for each of your own other
devices. Read state, contacts and groups travel the same way. Each device's queue on the server is
emptied once that device fetches it. So a client has to:

1. **Store every envelope as soon as it arrives.** signal-cli runs with `--receive-mode=manual`
   and only receives after this app subscribes. If the app is down, signal-cli is down too, and
   messages wait on the server instead of being fetched and lost.
2. **Treat `syncMessage.sentMessage` as your own outgoing messages.** This is why messages you send
   from your phone show up here.
3. **Apply edits, deletes, reactions, receipts and read-syncs** to messages it already stored.

What the app handles:

| From Signal | What it does |
|---|---|
| `dataMessage` | Incoming message: text, attachments, quotes, mentions, text styles, link previews |
| `syncMessage.sentMessage` | A message you sent from another device (also edits and reactions sent from the phone) |
| `syncMessage.readMessages` | You read it on your phone, so the unread badge clears here |
| `editMessage` / `remoteDelete` / `reaction` | Updates or removes the stored message |
| `receiptMessage` | Delivered / read ticks on your messages |
| `typingMessage` | Live typing indicator (not stored) |
| expiration timer | Disappearing messages are deleted here when the timer runs out |

What you can do from the browser:
- send messages, with or without attachments (drag and drop, or paste images)
- reply, react, edit (or press ↑ to edit your last message)
- delete for everyone, or just from this app
- mark as read: sends a read receipt, and signal-cli also sends a read-sync, so your phones clear the badge too
- typing indicators, search, archive, desktop notifications, dark mode, mobile layout

## Quick start (Docker)

```bash
mkdir -p data && sudo chown 1000:1000 data
docker compose up -d --build
```

Open http://localhost:8080, click **Show QR code**, then on your main phone go to
**Molly → Settings → Linked devices → +** and scan it. The app asks the phone for your contacts
and groups straight away. New messages start arriving from that moment on.

On arm64 (Raspberry Pi etc.), set `target: jvm` in `docker-compose.yml`. The native signal-cli
binary is x86_64 only.

## Run without Docker

You need [signal-cli](https://github.com/AsamK/signal-cli/releases) on your `PATH` (the native build,
or the JVM build with Java 25).

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
DATA_DIR=./data .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
```

## Configuration (env vars)

| Variable | Default | |
|---|---|---|
| `DATA_DIR` | `./data` (`/data` in Docker) | SQLite DB, sent-attachment copies, avatar cache |
| `SIGNAL_CLI_DATA` | `$DATA_DIR/signal-cli` | signal-cli keys and downloaded attachments |
| `SIGNAL_CLI_CMD` | `signal-cli` | Command used to spawn signal-cli |
| `SIGNAL_RPC` | *(empty)* | Set to `tcp://host:port` to use an external `signal-cli daemon --tcp --receive-mode=manual` instead of a child process |
| `DEVICE_NAME` | `Signal Web` | Name shown under Linked devices on your phone |
| `SEND_READ_RECEIPTS` | `true` | Set `false` if read receipts are off in Molly. Note: with this off, reading here won't clear unread badges on your phones |
| `SEND_TYPING` | `true` | Send typing indicators |
| `TRUST_NEW_IDENTITIES` | `always` | `always` behaves like the Signal apps (accept a changed safety number and keep going). `on-first-use` blocks until you verify the new key |
| `KEEP_RAW_EVENTS` | `true` | Keep every raw envelope in `raw_events` for debugging or re-processing |
| `MAX_UPLOAD_MB` | `100` | |

## Adding auth

There is no auth, on purpose. Everything lives under four paths:

- `/` and `/static/*`: the UI
- `/api/*`: REST
- `/ws`: live events (WebSocket)
- `/healthz`: health check, safe to leave open

With a forward-auth proxy (Authelia, Authentik, oauth2-proxy, Cloudflare Access…), protect
everything except `/healthz`, and make sure the proxy passes WebSocket upgrades on `/ws`.

To do it in-app, add a FastAPI dependency to the `api` router in `app/main.py`, plus the same check
at the top of `websocket_endpoint` and `index`.

**The `data/` directory holds your Signal identity keys and full message history.** Protect and back
it up the way you would your phone.

## Limits

- **No history from before linking.** Signal doesn't give linked devices old messages (except the
  official Desktop transfer, which signal-cli doesn't support).
- **Keep it running.** A linked device that stays offline for about 30 days is unlinked by Signal, and
  queued messages expire.
- **Calls aren't supported.** An incoming call shows up as a notice; answer it on your phone.
- **Shown as placeholders for now:** stories, polls (the question shows as text), payments, pins, stickers.

## Development

Project status and backlog: [`docs/ROADMAP.md`](docs/ROADMAP.md). Conventions for contributors and
coding agents: [`AGENTS.md`](AGENTS.md).

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q          # unit + end-to-end tests (uses a fake signal-cli)
.venv/bin/python -m tests.demo         # UI with seeded conversations at http://localhost:8080
```

`tests/fake_signal_cli.py` speaks signal-cli's JSON-RPC protocol and lets you inject envelopes, so
you can work on the UI without touching a real account.

| File | |
|---|---|
| `app/rpc.py` | JSON-RPC client; spawns and supervises signal-cli, reconnects with backoff |
| `app/ingest.py` | Envelope → database logic (the sync rules above) |
| `app/store.py` | SQLite schema and queries |
| `app/service.py` | Linking, sending, read receipts, attachments, avatars, disappearing-message timers, WebSocket fan-out |
| `app/main.py` | FastAPI routes |
| `app/static/` | UI: `index.html`, `app.css`, `app.js` |
