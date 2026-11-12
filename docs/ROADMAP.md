# Roadmap

Status as of 2026-11-12. Priorities: **P0** blocks real use · **P1** needed before exposing it
beyond localhost · **P2** feature parity · **P3** polish and tech debt.

## Where we are

Built so far: a working first version (about 4k lines), tested end to end against a **fake**
signal-cli. It has **not yet been run against a real Signal account**, and the Docker image has
**not been built** (the build sandbox had no Docker daemon and wasn't allowed to execute the
downloaded signal-cli binary).

### Done

- [x] Architecture: signal-cli `jsonRpc` child process in multi-account, manual-receive mode,
      supervised with reconnect/backoff; optional external `tcp://` daemon
- [x] Linking as a secondary device via QR code (`startLink`/`finishLink`), followed by `sendSyncRequest`
- [x] SQLite store, the single source of truth; raw envelopes kept in `raw_events`
- [x] Ingest: incoming messages, **sync transcripts of messages sent from other devices**, edits
      (incoming and from your phone), reactions, remote and admin deletes, delivery/read/viewed
      receipts, read-sync, typing, disappearing-timer changes, group updates, call notices,
      quotes, mentions, text styles, link previews, attachments; number→UUID history merge
- [x] Outgoing: text, attachments (as data URIs), replies, edits, reactions, delete for everyone,
      read receipts (which also clear the badge on your phones), typing
- [x] Contacts and group refresh, avatars (cached), attachment serving (local file or `getAttachment` fallback)
- [x] Disappearing-message expiry
- [x] UI in Google Messages style: conversation list, search (names + message text), archive, start-chat
      dialog, bubbles with grouping, day separators, reactions, ticks, edited/deleted states, lightbox,
      drag & drop / paste uploads, ↑ to edit, desktop notifications, unread count in the tab title,
      dark mode, mobile layout, linking screen
- [x] Dockerfile (native x86_64 + JVM arm64 targets), docker-compose, README
- [x] Tests: 11 ingest unit tests + 1 end-to-end flow against `tests/fake_signal_cli.py`; demo mode

## P0: prove it against real Signal

- [ ] Build both Docker targets (`native`, `jvm`) and fix whatever breaks. *`native` builds and runs
      (owner, 2026-11-12); `jvm` not yet tried*
- [ ] Link to a real account (*done by the owner 2026-11-12; 1:1 receive/send works*); confirm `finishLink` result shape, `listAccounts` → `aci`, and that
      `subscribeReceive` picks up the newly linked account without a restart
- [ ] Capture real envelopes from `raw_events` (scrub them) and add them as fixtures in
      `tests/fixtures/`, then replay them in tests. Check these field names against reality:
      `editMessage` inside `sentMessage`, `remoteDelete.targetTimestamp`, group `members` shape,
      `listContacts` `name`/`nickName` semantics, `getAttachment`/`getAvatar` result shape (`{"data": …}`)
- [ ] Verify the end-to-end sync matrix with both Molly devices:
  - a message sent from a phone appears here, and one sent here appears on both phones
  - reading a chat here clears the phones' badges, and reading on a phone clears it here
  - edits, deletes and reactions made in either direction show up on the other side
  - group messages work in both directions
- [ ] Attachments: incoming download location in the container, large videos, voice notes; outgoing
      100 MB data-URI path (memory use, `LINE_LIMIT`)
- [ ] Safety-number change with `TRUST_NEW_IDENTITIES=always`: confirm sending keeps working
- [ ] Check that bind-mount permissions for `data/` (uid 1000) are documented correctly

### Findings from the first real run (2026-11-12)

- Real envelopes so far contain `dataMessage`, `receiptMessage`, `typingMessage` and
  `syncMessage.{readMessages,type,blockedNumbers,blockedGroupIds}`; field names match what ingest
  expects. Many `syncMessage` objects arrive **empty** (sync types signal-cli doesn't serialize); ingest
  ignores them correctly. No `syncMessage.sentMessage` captured yet, so "sent from phone" is still unverified.
- `syncMessage.blockedNumbers` / `blockedGroupIds` are ignored; could feed the P2 block/unblock work.

## P1: safe to put behind the owner's auth

- [ ] **WebSocket Origin check.** Once cookie auth is added, `/ws` is open to cross-site WebSocket
      hijacking. Reject upgrades whose `Origin` isn't the app's host (configurable `ALLOWED_ORIGINS`)
- [ ] **CSRF for state-changing routes.** JSON routes need a custom header or same-origin check;
      `POST /conversations/.../messages` is multipart (a "simple request"), so it needs a token or an Origin check
- [ ] Pluggable auth hook: a single FastAPI dependency (e.g. `AUTH_MODE=none|header`) that trusts a
      forward-auth header like `Remote-User` only from configured proxy IPs. Apply it to the router,
      `/ws` and `/`
- [ ] Security headers: CSP (`default-src 'self'; img-src 'self' blob:; media-src 'self' blob:`),
      `X-Content-Type-Options`, `Referrer-Policy: no-referrer` (links in messages)
- [x] Attachments: force `Content-Disposition: attachment` for HTML/SVG/unknown content types so the
      browser never renders them inline (only passive image/video/audio types are inline; `nosniff` set)
- [ ] Rate-limit and size-check uploads before reading them fully into memory

## P2: feature parity with a real chat app

- [ ] Sending @mentions in groups (composer autocomplete → `mention` param)
- [ ] Sticker rendering (`getSticker`) and sending
- [ ] Voice notes: record in the browser (MediaRecorder), send with `voiceNote`
- [ ] Message requests from unknown senders (accept/block/delete via `sendMessageRequestResponse`)
- [ ] Block/unblock contacts and groups
- [ ] Change the disappearing-messages timer per conversation
- [ ] Group management: create, rename, add/remove members, leave
- [ ] Poll voting and results; pinned messages; story replies (currently ignored)
- [ ] Contact/profile editing (nicknames, own profile name and avatar)
- [ ] Link previews when sending (fetch server-side, pass `previewUrl`/`previewTitle`)
- [ ] Unread divider and "jump to first unread"; per-conversation drafts
- [ ] Emoji picker (currently six quick reactions plus a prompt)
- [ ] PWA manifest + Web Push so notifications work when the tab is closed

## P3: robustness and tech debt

- [ ] Schema migrations (`PRAGMA user_version` + ordered migration functions)
- [ ] Move SQLite off the event loop (`asyncio.to_thread` or a dedicated writer thread); keep ingest ordering
- [ ] `Hub.broadcast`: send to clients concurrently with a timeout so one slow tab can't stall ingest
- [ ] `find_attachment` uses a `LIKE` scan over JSON. Add an `attachments` table indexed by id
- [ ] Full-text search with SQLite FTS5 instead of `LIKE`
- [ ] Prune or rotate `raw_events` (age/size limit, `KEEP_RAW_EVENTS_DAYS`)
- [ ] Re-process command: rebuild `messages` from `raw_events` after ingest bug fixes
- [ ] Handle the WebSocket reconnect catch-up incrementally (an `after` cursor) instead of full reloads
- [ ] Conversation list pagination for very large accounts
- [ ] Avatar endpoint: sniff the real content type instead of always `image/jpeg`
- [ ] `/api/contacts` uses `store._q` directly. Add a `Store.list_groups()`
- [ ] Silence the Starlette TestClient deprecation warning (pin/upgrade)
- [ ] Health check that alerts when signal-cli hasn't received anything for N days (the device is
      unlinked after about 30 days offline)
- [ ] CI: GitHub Actions running pytest + a Playwright smoke test against `tests.demo`
- [ ] Split `app.js` into ES modules once it passes ~1.5k lines (still no build step)

## Decisions made

- **FastAPI + vanilla JS rather than Streamlit**: chat needs server push and fine-grained DOM updates,
  which don't fit Streamlit's rerun model.
- **signal-cli rather than signal-cli-rest-api**: direct JSON-RPC, manual receive mode, and no extra
  container or REST layer that hides sync messages.
- **Child process by default**: if the app is down, signal-cli is down, so messages wait on Signal's
  servers rather than being fetched with nobody listening.
- **`TRUST_NEW_IDENTITIES=always` by default**: matches how the official apps treat unverified
  contacts. Configurable.
- **No built-in auth**: the owner puts their existing auth in front (see P1 for the hooks needed).
