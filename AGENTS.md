# AGENTS.md

Instructions for AI coding agents (and humans) working on this repository. `CLAUDE.md` imports this
file. For project status and the backlog, see [`docs/ROADMAP.md`](docs/ROADMAP.md).

## What this is

A self-hosted web client for Signal, styled like Google Messages, for one person's homelab. It runs
as a **linked device** on the owner's account (next to their Molly phones) by driving
[signal-cli](https://github.com/AsamK/signal-cli) over JSON-RPC. It stores its own history in SQLite
and pushes live updates to the browser over a WebSocket.

```
Signal servers ─► signal-cli jsonRpc (child process, --receive-mode=manual)
                    │ newline-delimited JSON-RPC over stdin/stdout (or tcp://)
                  app/rpc.py ─► app/service.py ─► app/ingest.py ─► app/store.py (SQLite)
                    │                        └─► Hub (WebSocket fan-out)
                  app/main.py (FastAPI: REST /api/*, /ws, static UI)
                    │
                  app/static/ (vanilla JS/CSS/HTML, no build step)
```

| File | Responsibility |
|---|---|
| `app/config.py` | Every setting, read from env vars (`Settings`) |
| `app/rpc.py` | Spawns and supervises signal-cli, matches request ids to responses, queues notifications to one worker so they are handled in order |
| `app/ingest.py` | **Pure envelope → DB logic.** Returns `Change` records; makes no RPC calls and does no I/O beyond `Store` |
| `app/store.py` | Schema, queries, decorating rows into API dicts. Re-entrant transactions (savepoints) |
| `app/service.py` | Linking, outgoing actions (send/react/delete/read/typing), contact and group refresh, attachments, avatars, disappearing-message expiry, `Hub` |
| `app/main.py` | FastAPI routes; request models are at module level (see Gotchas) |
| `app/static/app.js` | Whole UI: state `S`, the `h()` DOM helper, render functions, WebSocket event handling |
| `tests/fake_signal_cli.py` | Fake signal-cli speaking the same protocol; logs requests to `$FAKE_LOG` and injects envelopes from `$FAKE_INJECT_DIR` |
| `tests/demo.py` | Runs the real app against the fake with seeded conversations |

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q                 # all tests, ~1s, no network or Signal account needed
.venv/bin/python -m tests.demo                # UI at http://localhost:8080 with seeded data
DEMO_UNLINKED=1 FAKE_AUTO_LINK=0 .venv/bin/python -m tests.demo   # shows the QR linking screen
docker compose up -d --build                  # production-style run (needs a real signal-cli download)
```

Run the tests before every commit. For UI changes, run the demo and take a Playwright screenshot.
Playwright is preinstalled in Claude cloud sessions: `require('playwright')`, `chromium.launch()`.
Check desktop (1280×800), dark mode (`colorScheme: "dark"`) and mobile (390×780). Watch for
`pageerror` events.

## Core domain rules (read before touching ingest/store/service)

- **Identity.** A recipient id (`rid`) is the ACI UUID when known, otherwise the E.164 number.
  The literal `"self"` means this account. Always resolve identities through `Ingestor.rid()`, which
  also records number↔uuid mappings and merges number-keyed history into the uuid when learned.
- **Conversation ids:** `u:<rid>` for 1:1 chats (`u:self` = Note to Self), `g:<base64 groupId>` for
  groups. Group ids contain `/`, `+` and `=`, which is why routes use `{conv_id:path}` and the client
  uses `enc()`.
- **Message identity** is `(author rid, sent timestamp ms)`, with UNIQUE `(conversation_id, author, sent_ts)`.
  Reactions, edits, deletes, quotes and receipts all point at messages this way. Ingest must stay
  **idempotent**: replaying the same envelope must not create duplicates.
- **Messages you send from another device** arrive as `syncMessage.sentMessage` from your own
  account and must be stored as `author="self"`. Forgetting this is the classic bug that makes
  "half the conversation" disappear.
- **Read state.** `sendReceipt type=read` makes signal-cli send a read receipt to the author **and**
  a read-sync to our other devices (checked in signal-cli `ManagerImpl.sendReceiptMessage`).
  Incoming `syncMessage.readMessages` marks everything up to that timestamp as read.
- **Disappearing messages:** incoming ones start their timer when read (`Store.mark_read`); outgoing
  ones when sent. `_expiry_loop` deletes rows and their attachment files.
- **No loss on restart:** signal-cli runs with `--receive-mode=manual`, and we call
  `subscribeReceive` (no account param = all accounts, including ones linked later). Don't switch to
  `on-start`.
- signal-cli runs in **multi-account mode** (no `-a`); `SignalService.call()` adds `account`. Use
  `self.rpc.call` directly only for account-less methods (`listAccounts`, `startLink`, `finishLink`,
  `subscribeReceive`).
- Notification payloads come wrapped as `{"subscription": n, "result": {...}}` in manual mode;
  `_on_notification` unwraps both shapes.

### signal-cli protocol reference

Field names come from signal-cli's `src/main/java/org/asamk/signal/json/*.java` records (pinned version
in `Dockerfile`, `SIGNAL_CLI_VERSION`). Check those records rather than guessing. Fetch them with
`curl https://raw.githubusercontent.com/AsamK/signal-cli/master/src/main/java/org/asamk/signal/json/JsonDataMessage.java`.
JSON-RPC params are the CLI flags in camelCase (`--quote-timestamp` → `quoteTimestamp`); the docs are
`man/signal-cli.1.adoc` and `man/signal-cli-jsonrpc.5.adoc`. When you handle a new field, add it to
the fake and add a test that uses it.

## Conventions

- Python 3.12+, `from __future__ import annotations`, type hints, stdlib `sqlite3` (no ORM), `logging`
  via `logging.getLogger("signal-web.<module>")`.
- Keep `ingest.py` free of RPC calls and I/O. It requests follow-ups (e.g. `refresh_groups`) by returning `Change`s.
- Schema changes go in `store.SCHEMA`. There is no migration system yet (see the roadmap). Until there
  is, only add nullable columns or new tables, and note the change in the PR.
- **Frontend has no build step and no dependencies.** Plain ES2020 in one file, served as-is. Do not add
  npm, bundlers or CDN scripts. The app must work offline on a LAN.
- **XSS:** user content goes into the DOM only through `h()`/`textContent`. The only `innerHTML` is the
  server-generated QR SVG. Keep it that way.
- Icons are inline Material SVG paths in `ICONS` (app.js). Colors are CSS custom properties on `:root`,
  with dark-mode overrides. Keep the mobile breakpoint (760px) working.
- API errors: raise `HTTPException` in routes. `RpcError` → 502 and `ConnectionError` → 503 are handled
  globally.

## Gotchas

- FastAPI + `from __future__ import annotations`: Pydantic request models **must be defined at module
  level** in `main.py`. If they're defined inside `create_app`, FastAPI silently treats them as query
  params (422).
- Route order matters: `/conversations/{conv_id:path}/messages` must be declared before
  `/conversations/{conv_id:path}`.
- `rpc.call` drops `None`-valued params. Use that for optional flags (`remove=None`, `stop=None`).
- Notification handlers may call RPC methods. They run on the notification worker, not the reader
  task, so this can't deadlock. Don't move handling into `_read_loop`.
- `Store` is synchronous and called from async code. It's fine at personal scale, but don't add slow
  queries to hot paths.
- The demo/test fake is not signal-cli. Anything it doesn't exercise (real linking, attachment
  downloads, profile fetches) is unverified until tried against a real account (roadmap P0).

## Security and privacy

- `data/` holds the account's Signal identity keys and full message history. Never commit it, never
  log message bodies at INFO, and never send account data to third-party services.
- The app has **no auth by design**; the owner adds it in front. Don't add a weak built-in password
  scheme. See the roadmap for the planned auth-hook design (WebSocket Origin check, CSRF).
- Attachment ids are validated with `SAFE_ID` before touching the filesystem. Keep path handling that strict.

## Git

- Default branch `main`. Commit only when tests pass. Write commit messages in the imperative, with a
  body explaining *why*.
- Don't commit `.venv/`, `data/`, screenshots or other scratch files.
