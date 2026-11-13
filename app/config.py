"""Runtime configuration, all from environment variables."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # Where this app keeps its own state (SQLite DB, copies of sent attachments, avatar cache).
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("DATA_DIR", "./data")))

    # How to reach signal-cli. Empty -> spawn `signal-cli jsonRpc` as a child process (default,
    # self-contained). "tcp://host:port" -> connect to an already running `signal-cli daemon --tcp`.
    signal_rpc: str = field(default_factory=lambda: os.environ.get("SIGNAL_RPC", ""))

    # Command used to start signal-cli in subprocess mode (split shell-style, so a JVM wrapper works).
    signal_cli_cmd: list[str] = field(
        default_factory=lambda: shlex.split(os.environ.get("SIGNAL_CLI_CMD", "signal-cli"))
    )

    # signal-cli's own data directory (keys, sessions, downloaded attachments).
    signal_cli_data: Path | None = field(
        default_factory=lambda: Path(p) if (p := os.environ.get("SIGNAL_CLI_DATA")) else None
    )

    # How signal-cli handles a contact's changed safety number. "always" behaves like the
    # Signal apps for unverified contacts (accept and keep going); "on-first-use" refuses
    # until you trust the new key manually.
    trust_new_identities: str = field(
        default_factory=lambda: os.environ.get("TRUST_NEW_IDENTITIES", "always")
    )

    # Name shown under Settings > Linked devices on your phone.
    device_name: str = field(default_factory=lambda: os.environ.get("DEVICE_NAME", "Signal Web"))

    # Send read receipts when you open a conversation. signal-cli also sends a read *sync*
    # with every read receipt, which is what clears unread badges on your phones.
    # If you have read receipts turned off in Molly, set this to false.
    send_read_receipts: bool = field(default_factory=lambda: _bool("SEND_READ_RECEIPTS", True))

    # Send typing indicators while you type.
    send_typing: bool = field(default_factory=lambda: _bool("SEND_TYPING", True))

    # Keep every raw envelope in the DB (handy for debugging / re-processing).
    keep_raw_events: bool = field(default_factory=lambda: _bool("KEEP_RAW_EVENTS", True))

    max_upload_mb: int = field(default_factory=lambda: int(os.environ.get("MAX_UPLOAD_MB", "100")))

    def __post_init__(self) -> None:
        self.data_dir = self.data_dir.resolve()
        if self.signal_cli_data is None:
            self.signal_cli_data = self.data_dir / "signal-cli"
        self.signal_cli_data = self.signal_cli_data.resolve()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "signal-web.db"

    @property
    def sent_attachments_dir(self) -> Path:
        return self.data_dir / "sent-attachments"

    @property
    def avatar_cache_dir(self) -> Path:
        return self.data_dir / "avatars"

    @property
    def received_attachments_dir(self) -> Path:
        # signal-cli downloads incoming attachments here (only readable in subprocess mode
        # or when the daemon's data dir is mounted; otherwise we fall back to getAttachment).
        assert self.signal_cli_data is not None
        return self.signal_cli_data / "attachments"


@dataclass
class RelaySettings:
    """Settings for the webhook relay process (`python -m app.webhook`)."""

    # Where the relay listens for webhooks. Expose this port to your webhook system, not 8080.
    host: str = field(default_factory=lambda: os.environ.get("WEBHOOK_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.environ.get("WEBHOOK_PORT", "8081")))

    # How the relay reaches the main app, directly (not through your auth proxy).
    signal_web_url: str = field(
        default_factory=lambda: os.environ.get("SIGNAL_WEB_URL", "http://127.0.0.1:8080").rstrip("/")
    )

    # Keep retrying for this long when the main app is unreachable (e.g. during a restart).
    retry_seconds: float = field(default_factory=lambda: float(os.environ.get("WEBHOOK_RETRY_SECONDS", "30")))

    max_body_bytes: int = 64 * 1024
