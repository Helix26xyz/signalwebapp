"""Minimal asyncio JSON-RPC client for signal-cli.

Two transports:
  * subprocess (default): spawn `signal-cli jsonRpc` and talk over stdin/stdout.
  * tcp://host:port: connect to `signal-cli daemon --tcp`.

signal-cli is started with `--receive-mode=manual`, so nothing is pulled from the Signal
server until we call `subscribeReceive`. In subprocess mode that means: if this app is
down, signal-cli is down, and messages wait safely in the server-side queue.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .config import Settings

log = logging.getLogger("signal-web.rpc")

NotificationHandler = Callable[[str, dict], Awaitable[None]]
ConnectedHandler = Callable[[], Awaitable[None]]

LINE_LIMIT = 256 * 1024 * 1024  # getAttachment returns whole files base64-encoded on one line


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.data = data


class SignalRPC:
    def __init__(
        self,
        settings: Settings,
        on_notification: NotificationHandler,
        on_connected: ConnectedHandler,
    ):
        self.settings = settings
        self._on_notification = on_notification
        self._on_connected = on_connected
        self._ids = itertools.count(1)
        self._pending: dict[str, asyncio.Future] = {}
        self._writer: asyncio.StreamWriter | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._connected = asyncio.Event()
        self._stopping = False
        self._main_task: asyncio.Task | None = None
        self._notify_queue: asyncio.Queue = asyncio.Queue()
        self._notify_task: asyncio.Task | None = None
        self.last_error: str | None = None

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    async def start(self) -> None:
        self._notify_task = asyncio.create_task(self._notification_worker())
        self._main_task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping = True
        await self._close_transport()
        for task in (self._main_task, self._notify_task):
            if task:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    async def call(self, method: str, params: dict | None = None, timeout: float = 60.0) -> Any:
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=min(timeout, 30))
        except asyncio.TimeoutError as exc:
            raise ConnectionError("signal-cli is not connected") from exc
        req_id = str(next(self._ids))
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params:
            msg["params"] = {k: v for k, v in params.items() if v is not None}
        try:
            assert self._writer is not None
            self._writer.write(json.dumps(msg, separators=(",", ":")).encode() + b"\n")
            await self._writer.drain()
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(req_id, None)

    # ------------------------------------------------------------------ internals

    async def _run(self) -> None:
        backoff = 1.0
        while not self._stopping:
            try:
                reader = await self._open_transport()
                self.last_error = None
                backoff = 1.0
                self._connected.set()
                log.info("connected to signal-cli")
                on_conn = asyncio.create_task(self._safe_on_connected())
                await self._read_loop(reader)
                on_conn.cancel()
                if not self._stopping:
                    self.last_error = "signal-cli connection closed"
                    log.warning(self.last_error)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - keep the supervisor alive
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.error("signal-cli connection failed: %s", self.last_error)
            finally:
                self._connected.clear()
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(ConnectionError("signal-cli connection lost"))
                await self._close_transport()
            if self._stopping:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    async def _safe_on_connected(self) -> None:
        try:
            await self._on_connected()
        except Exception:  # noqa: BLE001
            log.exception("on_connected handler failed")

    async def _open_transport(self) -> asyncio.StreamReader:
        target = self.settings.signal_rpc.strip()
        if target:
            if not target.startswith("tcp://"):
                raise ValueError(f"unsupported SIGNAL_RPC {target!r}; expected tcp://host:port")
            host, _, port = target[len("tcp://"):].rpartition(":")
            reader, writer = await asyncio.open_connection(host, int(port), limit=LINE_LIMIT)
            self._writer = writer
            return reader

        self.settings.signal_cli_data.mkdir(parents=True, exist_ok=True)
        cmd = [
            *self.settings.signal_cli_cmd,
            "--config", str(self.settings.signal_cli_data),
            "--trust-new-identities", self.settings.trust_new_identities,
            "jsonRpc",
            "--receive-mode", "manual",
        ]
        log.info("starting %s", " ".join(cmd))
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=LINE_LIMIT,
        )
        asyncio.create_task(self._pipe_stderr(self._proc.stderr))
        self._writer = self._proc.stdin  # type: ignore[assignment]
        return self._proc.stdout  # type: ignore[return-value]

    async def _close_transport(self) -> None:
        writer, self._writer = self._writer, None
        if writer is not None:
            try:
                writer.close()
            except Exception:  # noqa: BLE001
                pass
        proc, self._proc = self._proc, None
        if proc is not None and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except asyncio.TimeoutError:
                proc.kill()

    async def _pipe_stderr(self, stream: asyncio.StreamReader | None) -> None:
        if stream is None:
            return
        while line := await stream.readline():
            text = line.decode(errors="replace").rstrip()
            if text:
                log.info("signal-cli: %s", text)
                if "ERROR" in text:
                    self.last_error = text

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        while True:
            line = await reader.readline()
            if not line:
                return
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                log.warning("non-JSON line from signal-cli: %r", line[:200])
                continue
            if "method" in msg and "id" not in msg:
                self._notify_queue.put_nowait((msg["method"], msg.get("params") or {}))
                continue
            fut = self._pending.get(str(msg.get("id")))
            if fut is None or fut.done():
                continue
            if "error" in msg and msg["error"] is not None:
                err = msg["error"]
                fut.set_exception(RpcError(err.get("code", -1), err.get("message", ""), err.get("data")))
            else:
                fut.set_result(msg.get("result"))

    async def _notification_worker(self) -> None:
        # Notifications are processed one at a time, in order, off the reader task: handlers
        # are allowed to make RPC calls (which need the reader to keep running).
        while True:
            method, params = await self._notify_queue.get()
            try:
                await self._on_notification(method, params)
            except Exception:  # noqa: BLE001
                log.exception("failed to handle %s notification", method)
