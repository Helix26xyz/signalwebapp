@AGENTS.md

## Claude Code notes

- Project status and backlog are in `docs/ROADMAP.md`. Pick work from there, and update it (tick items,
  add findings) in the same commit as the change.
- Cloud sessions: Chromium + Playwright are preinstalled. Use them to screenshot `python -m tests.demo`
  after UI changes, and look at the screenshots before you call a UI change done.
- Running the real signal-cli binary may be blocked in a sandbox. If so, rely on the fake and say
  clearly that the change is unverified against real Signal.
