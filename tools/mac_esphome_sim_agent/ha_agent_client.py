#!/usr/bin/env python3
"""
Connect outbound from Mac to Home Assistant WebSocket, authenticate with mac_sim_token,
receive run jobs, execute esphome run (SDL).

Usage (after install-macos.sh):
  source .venv/bin/activate
  # Use http:// if your browser uses http:// for HA (typical on LAN); use https:// only when HA serves TLS.
  python ha_agent_client.py --ha-url http://homeassistant.local:8123 --token-file ~/.esptoolkit_mac_sim_token

  # Debug: print the exact YAML before each esphome run (inspect line numbers from errors)
  python ha_agent_client.py ... --dump-yaml

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
import socket
from logging.handlers import RotatingFileHandler

import websockets

from esphome_transform import transform_esphome_yaml_for_host_sdl

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


def _ssl_mismatch_tip(uri: str, exc: BaseException) -> None:
    """Suggest http:// when wss:// fails with TLS errors (HA often serves plain HTTP on :8123)."""
    if not uri.lower().startswith("wss:"):
        return
    msg = str(exc).lower()
    if isinstance(exc, ssl.SSLError) or "ssl" in msg or "record layer" in msg or "tls" in msg:
        LOG.warning(
            "If Home Assistant is opened in the browser as http:// (not https://), use the same for "
            "--ha-url, e.g. http://grimwoodha:8123 — otherwise TLS talks to a non-TLS port and SSL fails."
        )


def _dump_yaml_to_terminal(yaml_text: str) -> None:
    """Print exact YAML passed to esphome (stderr, so it stays readable vs log lines)."""
    sep = "=" * 72
    print(sep, file=sys.stderr)
    print("MAC SIM YAML (next esphome run)", file=sys.stderr)
    print(sep, file=sys.stderr)
    print(yaml_text, file=sys.stderr, end="" if yaml_text.endswith("\n") else "\n")
    print(sep, file=sys.stderr)


def _get_primary_ip() -> str | None:
    """Best-effort pick of primary outbound IP (no packets sent)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


async def _client_loop(uri: str, token: str, insecure_tls: bool, *, dump_yaml: bool) -> None:
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

    retry_delay_s = 2
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
                try:
                    msg = json.loads(raw)
                except Exception:
                    LOG.warning("Received non-JSON handshake payload; reconnecting.")
                    raise ConnectionError("invalid handshake payload")
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
                            source_yaml = data.get("source_yaml")
                            transformed_yaml: str
                            if isinstance(source_yaml, str) and source_yaml.strip():
                                try:
                                    host_ip = _get_primary_ip()
                                    host_hostname = socket.gethostname()
                                    transformed_yaml, tw = transform_esphome_yaml_for_host_sdl(
                                        source_yaml,
                                        int(data.get("screen_width") or 480),
                                        int(data.get("screen_height") or 320),
                                        api_encryption_key=None,
                                        esphome_name=None,
                                        host_ip=host_ip,
                                        host_hostname=host_hostname,
                                    )
                                    for w in tw:
                                        LOG.warning("transform warning: %s", w)
                                except Exception as exc:
                                    LOG.error("Mac-side transform failed: %s", exc)
                                    continue
                            else:
                                # Backward compatibility with older HA payloads.
                                y = data.get("yaml")
                                if not isinstance(y, str) or not y.strip():
                                    LOG.error("Empty yaml in run message")
                                    continue
                                transformed_yaml = y
                            LOG.info("Received run job (%d bytes YAML)", len(transformed_yaml))
                            LOG.info("ESPHome run starting (streaming logs)…")
                            if dump_yaml:
                                _dump_yaml_to_terminal(transformed_yaml)
                            rc = await _run_esphome(transformed_yaml)
                            LOG.info("esphome run finished with code %s", rc)
                        else:
                            LOG.debug("Message: %s", data)
                finally:
                    ping_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await ping_task
                # Successful session reset the retry delay.
                retry_delay_s = 2
        except SystemExit:
            raise
        except (websockets.ConnectionClosed, OSError, TimeoutError, Exception) as e:
            _ssl_mismatch_tip(uri, e)
            LOG.warning("Disconnected (%s); reconnecting in %ss…", e, retry_delay_s)
            await asyncio.sleep(retry_delay_s)
            retry_delay_s = min(retry_delay_s * 2, 30)


def main() -> None:
    p = argparse.ArgumentParser(description="EspToolkit Mac ↔ HA SDL agent (outbound WebSocket)")
    p.add_argument(
        "--ha-url",
        required=True,
        help="HA base URL — match your browser: http://host:8123 for plain HTTP (typical LAN), https://… if HA uses TLS",
    )
    p.add_argument("--token-file", required=True, help="File containing mac_sim_token (same as HA integration options)")
    p.add_argument(
        "--insecure-tls",
        action="store_true",
        help="Disable TLS certificate verification (dev only)",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument(
        "--dump-yaml",
        action="store_true",
        help="Print the full received YAML to stderr before each esphome run (debug invalid YAML / structure)",
    )
    p.add_argument(
        "--log-file",
        default=str(Path("~/Library/Logs/esptoolkit-mac-sim-agent.log").expanduser()),
        help="Write agent + ESPHome output to this file (helps when running under launchd)",
    )
    args = p.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    root = logging.getLogger()
    root.setLevel(log_level)
    # Always log to console
    sh = logging.StreamHandler()
    sh.setLevel(log_level)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    # Also log to file (rotating)
    try:
        lf = Path(args.log_file).expanduser()
        lf.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(lf, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        fh.setLevel(log_level)
        fh.setFormatter(fmt)
        root.addHandler(fh)
        LOG.info("Logging to %s", str(lf))
    except Exception as e:
        LOG.warning("Could not set up log file: %s", e)

    token = Path(args.token_file).expanduser().read_text(encoding="utf-8").strip()
    if len(token) < 16:
        LOG.error("Token must be at least 16 characters (set in HA EspToolkit options).")
        raise SystemExit(1)

    uri = _ws_url_from_ha_url(args.ha_url)
    try:
        asyncio.run(
            _client_loop(uri, token, args.insecure_tls, dump_yaml=args.dump_yaml),
        )
    except KeyboardInterrupt:
        LOG.info("Stopped")


if __name__ == "__main__":
    main()
