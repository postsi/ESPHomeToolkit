#!/usr/bin/env python3
"""WebSocket server: receive ESPHome YAML, write a temp file, run `esphome run` (host/SDL)."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import websockets
from websockets.server import WebSocketServerProtocol

LOG = logging.getLogger("esphome_sim_agent")

_busy = False
_busy_lock = asyncio.Lock()


def _esphome_cmd(yaml_path: Path) -> list[str]:
    return [sys.executable, "-m", "esphome", "run", str(yaml_path)]


async def _pump_stream(stream: asyncio.StreamReader, ws: WebSocketServerProtocol, stream_name: str) -> None:
    while True:
        line = await stream.readline()
        if not line:
            break
        text = line.decode(errors="replace").rstrip("\n")
        await ws.send(json.dumps({"type": "log", "stream": stream_name, "line": text}))


async def _run_esphome(yaml_path: Path, ws: WebSocketServerProtocol) -> int:
    proc = await asyncio.create_subprocess_exec(
        *_esphome_cmd(yaml_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=os.environ.copy(),
    )
    assert proc.stdout and proc.stderr
    pump_out = asyncio.create_task(_pump_stream(proc.stdout, ws, "stdout"))
    pump_err = asyncio.create_task(_pump_stream(proc.stderr, ws, "stderr"))
    try:
        rc = await proc.wait()
    finally:
        pump_out.cancel()
        pump_err.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pump_out
        with contextlib.suppress(asyncio.CancelledError):
            await pump_err
    return int(rc if rc is not None else 0)


async def _handle_message(
    raw: str,
    ws: WebSocketServerProtocol,
    expected_token: str | None,
    authenticated: list[bool],
) -> None:
    global _busy
    try:
        msg: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as e:
        await ws.send(json.dumps({"type": "error", "message": f"invalid json: {e}"}))
        return

    mtype = msg.get("type")

    if mtype == "ping":
        await ws.send(json.dumps({"type": "pong"}))
        return

    if mtype == "auth":
        if not expected_token:
            await ws.send(json.dumps({"type": "error", "message": "auth not required"}))
            return
        if msg.get("token") == expected_token:
            authenticated[0] = True
            await ws.send(json.dumps({"type": "auth_ok"}))
        else:
            await ws.send(json.dumps({"type": "error", "message": "auth failed"}))
        return

    if expected_token and not authenticated[0]:
        await ws.send(json.dumps({"type": "error", "message": "auth required"}))
        return

    if mtype != "run":
        await ws.send(json.dumps({"type": "error", "message": f"unknown type: {mtype!r}"}))
        return

    yaml_text = msg.get("yaml")
    if not isinstance(yaml_text, str) or not yaml_text.strip():
        await ws.send(json.dumps({"type": "error", "message": "missing or empty yaml"}))
        return

    async with _busy_lock:
        if _busy:
            await ws.send(
                json.dumps(
                    {
                        "type": "error",
                        "message": "busy: another esphome run is in progress",
                    }
                )
            )
            return
        _busy = True

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(yaml_text)
            tmp_path = Path(tmp.name)
        await ws.send(json.dumps({"type": "started", "path": str(tmp_path)}))

        rc = await _run_esphome(tmp_path, ws)
        await ws.send(json.dumps({"type": "finished", "returncode": rc}))
    except Exception as e:
        LOG.exception("run failed")
        await ws.send(json.dumps({"type": "error", "message": str(e)}))
    finally:
        if tmp_path is not None and tmp_path.exists():
            with contextlib.suppress(OSError):
                tmp_path.unlink()
        async with _busy_lock:
            _busy = False


async def _connection_handler(ws: WebSocketServerProtocol, expected_token: str | None) -> None:
    authenticated = [not bool(expected_token)]
    try:
        async for raw in ws:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            await _handle_message(raw, ws, expected_token, authenticated)
    except websockets.ConnectionClosed:
        pass


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="EspToolkit macOS ESPHome SDL sim WebSocket agent")
    p.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8765, help="TCP port (default: 8765)")
    p.add_argument(
        "--token",
        default="",
        help="If set, client must send {\"type\":\"auth\",\"token\":\"...\"} first",
    )
    p.add_argument(
        "--token-file",
        default="",
        help="Read token from file (whitespace stripped); overrides --token if set",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    token: str | None = None
    if args.token_file:
        token = Path(args.token_file).read_text(encoding="utf-8").strip()
        if not token:
            LOG.error("token-file is empty")
            sys.exit(1)
    elif (args.token or "").strip():
        token = args.token.strip()

    if token and len(token) < 16:
        LOG.warning("token is short; use at least 16 random bytes for anything beyond local dev")

    async def handler(ws: WebSocketServerProtocol) -> None:
        await _connection_handler(ws, token)

    async def run() -> None:
        async with websockets.serve(handler, args.host, args.port):
            LOG.info(
                "Listening on ws://%s:%s (esphome via %s -m esphome)",
                args.host,
                args.port,
                sys.executable,
            )
            await asyncio.Future()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        LOG.info("Stopped")


if __name__ == "__main__":
    main()
