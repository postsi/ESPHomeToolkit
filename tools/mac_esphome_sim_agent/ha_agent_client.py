#!/usr/bin/env python3
"""
Connect outbound from Mac to Home Assistant WebSocket, authenticate with mac_sim_token,
receive run jobs, execute esphome run (SDL).

Usage (after install-macos.sh):
  source .venv/bin/activate
  python ha_agent_client.py --ha-url https://homeassistant.local:8123 --token-file ~/.config/esptoolkit_mac_sim_token

Use the same token as in HA: Settings → Devices & services → EspToolkit → Configure (Mac sim token).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import ssl
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import websockets

LOG = logging.getLogger("ha_mac_sim_agent")


def _ws_url_from_ha_url(ha_url: str, path: str = "/api/esptoolkit/mac_sim/agent/ws") -> str:
    p = urlparse(ha_url.strip())
    if not p.scheme or not p.netloc:
        raise ValueError(f"Invalid HA URL: {ha_url!r}")
    scheme = "wss" if p.scheme == "https" else "ws"
    return f"{scheme}://{p.netloc}{path}"


async def _run_esphome(yaml_text: str) -> int:
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(yaml_text)
        path = tmp.name
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "esphome",
            "run",
            path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=os.environ.copy(),
        )
        assert proc.stdout
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            LOG.info("%s", line.decode(errors="replace").rstrip())
        return int(await proc.wait() or 0)
    finally:
        Path(path).unlink(missing_ok=True)


async def _client_loop(uri: str, token: str, insecure_tls: bool) -> None:
    ssl_ctx: ssl.SSLContext | None = None
    if uri.startswith("wss"):
        ssl_ctx = ssl.create_default_context()
        if insecure_tls:
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

    extra_headers: list[tuple[str, str]] = []
    # Some HA setups expect a browser-like Origin for CSRF; harmless for WS.
    try:
        u = urlparse(uri.replace("wss://", "https://").replace("ws://", "http://"))
        if u.netloc:
            extra_headers.append(("Origin", f"{u.scheme}://{u.netloc}"))
    except Exception:
        pass

    while True:
        try:
            LOG.info("Connecting to %s", uri)
            async with websockets.connect(
                uri,
                ssl=ssl_ctx if uri.startswith("wss") else None,
                additional_headers=extra_headers or None,
                max_size=50 * 1024 * 1024,
            ) as ws:
                await ws.send(json.dumps({"type": "auth", "token": token}))
                raw = await ws.recv()
                msg = json.loads(raw)
                if msg.get("type") == "error":
                    LOG.error("Auth rejected: %s", msg.get("message"))
                    raise SystemExit(1)
                if msg.get("type") != "ready":
                    LOG.warning("Unexpected first message: %s", msg)

                LOG.info("Authenticated; waiting for Mac sim jobs from HA…")

                async def ping_keepalive():
                    try:
                        while True:
                            await asyncio.sleep(45)
                            await ws.send(json.dumps({"type": "ping"}))
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        pass

                ping_task = asyncio.create_task(ping_keepalive())
                try:
                    async for raw2 in ws:
                        if isinstance(raw2, bytes):
                            raw2 = raw2.decode("utf-8", errors="replace")
                        try:
                            data = json.loads(raw2)
                        except json.JSONDecodeError:
                            continue
                        mtype = data.get("type")
                        if mtype == "pong":
                            continue
                        if mtype == "run":
                            y = data.get("yaml")
                            if not isinstance(y, str) or not y.strip():
                                LOG.error("Empty yaml in run message")
                                continue
                            LOG.info("Received run job (%d bytes YAML)", len(y))
                            rc = await _run_esphome(y)
                            LOG.info("esphome run finished with code %s", rc)
                        else:
                            LOG.debug("Message: %s", data)
                finally:
                    ping_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await ping_task
        except (websockets.ConnectionClosed, OSError) as e:
            LOG.warning("Disconnected (%s); reconnecting in 5s…", e)
            await asyncio.sleep(5)


def main() -> None:
    p = argparse.ArgumentParser(description="EspToolkit Mac ↔ HA SDL agent (outbound WebSocket)")
    p.add_argument(
        "--ha-url",
        required=True,
        help="Home Assistant base URL, e.g. https://homeassistant.local:8123",
    )
    p.add_argument("--token-file", required=True, help="File containing mac_sim_token (same as HA integration options)")
    p.add_argument(
        "--insecure-tls",
        action="store_true",
        help="Disable TLS certificate verification (dev only)",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    token = Path(args.token_file).expanduser().read_text(encoding="utf-8").strip()
    if len(token) < 16:
        LOG.error("Token must be at least 16 characters (set in HA EspToolkit options).")
        raise SystemExit(1)

    uri = _ws_url_from_ha_url(args.ha_url)
    try:
        asyncio.run(_client_loop(uri, token, args.insecure_tls))
    except KeyboardInterrupt:
        LOG.info("Stopped")


if __name__ == "__main__":
    main()
