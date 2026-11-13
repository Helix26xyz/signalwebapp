# Signal Web

A self-hosted web client for Signal, in the style of Google Messages. It runs as a **linked device**
on your account (just like your second Molly phone), keeps its own message history in SQLite, and
stays in sync with your other devices. You can link **several Signal accounts** (say, personal and
work numbers) and switch between them.

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
- several accounts: switch from the avatar at the top right of the conversation list. A dot there means
  another account has unread messages; notifications arrive from every account

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

### Adding another account

Click your account avatar at the top right of the conversation list, choose **Link another account**,
and scan the QR code with the phone of the other account. Each account keeps a separate history.

Under `DATA_DIR`, an account you linked before multi-account support keeps its database at
`signal-web.db`. Accounts linked since then get `accounts/<number>/`. signal-cli keeps the keys for
all of them in `signal-cli/`. To stop using an account, remove Signal Web under **Linked devices** on
that phone. Its history stays readable here, marked "Not linked".

## Sending messages from webhooks

For alerts from monitoring, backups, home automation and so on. A small **webhook relay** runs as
its own process (the `signal-web-webhook` service in `docker-compose.yml`, port 8081), so your
webhook system can reach it without reaching the main app.

1. In Signal Web, open the account menu (your avatar, top right) → **Webhook sending…**, tick
   **Allow webhook sending** for the number that should send, and copy the token. Nothing can send
   as a number until you do this, and unticking it stops it immediately.
2. Point your webhook at the relay:

```bash
curl -X POST http://YOUR-HOST:8081/send \
  -H "Authorization: Bearer swh_..." \
  -H "Content-Type: application/json" \
  -d '{"recipient": "+15551234567", "message": "Backup finished"}'
```

- `recipient`: a number in international format, `"self"` (your Note to Self, handy for alerts to
  yourself), or a contact's UUID. Use `group_id` instead to send to a group.
- The token picks the sending number; each account has its own. Also accepted: `X-Webhook-Token`
  header or `?token=` (for senders that can't set headers), `to`/`text` as field names, form data,
  or a `text/plain` body with `?to=...` in the URL.
- Answers `200 {"ok": true, "message_id": …}` on success; `401` unknown token, `403` sending turned
  off for that account, `400` bad input, `502` Signal refused, `503` Signal Web unreachable. While
  the main app is unreachable (e.g. restarting) the relay keeps retrying for `WEBHOOK_RETRY_SECONDS`.
- Sent messages show up in the conversation like any other you send.

Relay settings: `WEBHOOK_HOST` (`0.0.0.0`), `WEBHOOK_PORT` (`8081`), `SIGNAL_WEB_URL` (how the relay
reaches the main app directly, default `http://127.0.0.1:8080`; `http://signal-web:8080` in compose),
`WEBHOOK_RETRY_SECONDS` (`30`). Without Docker: `python -m app.webhook`.

The token can send messages as your number: treat it like a password, and keep port 8081 off the
internet unless something like your reverse proxy restricts who can reach it.

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
| `DATA_DIR` | `./data` (`/data` in Docker) | SQLite DBs (one per account), sent-attachment copies, avatar caches |
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

There is no auth, on purpose. Everything lives under four paths (plus the webhook relay on its own
port, which checks its own tokens):

- `/` and `/static/*`: the UI
- `/api/*`: REST
- `/ws`: live events (WebSocket)
- `/healthz`: health check, safe to leave open (it reports only the state)

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
| `app/webhook.py` | Webhook relay (separate process) |
| `app/static/` | UI: `index.html`, `app.css`, `app.js` |
