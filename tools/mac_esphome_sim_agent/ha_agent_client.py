#!/usr/bin/env python3
"""
Connect outbound from Mac to Home Assistant WebSocket, authenticate with mac_sim_token,
receive run jobs, execute esphome run (SDL).

The WebSocket receive loop stays active while ESPHome runs: HA can enqueue further jobs
without blocking on send, and a new `run` message preempts the current `esphome run` (SIGINT)
so the next job starts without waiting for the user to close SDL.

Usage (after install-macos.sh):
  source .venv/bin/activate
  # Use http:// if your browser uses http:// for HA (typical on LAN); use https:// only when HA serves TLS.
  python ha_agent_client.py --ha-url http://grimwoodha:8123 --token-file ~/.esptoolkit_mac_sim_token

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
import re
import os
import signal
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

_LOG_TAIL_MAX = 32000
_DETAIL_MAX = 4000


async def _send_job_report(
    ws,
    *,
    ok: bool,
    phase: str,
    exit_code: int | None,
    detail: str,
    log_tail: str,
) -> None:
    """Notify Home Assistant (integration stores for GET .../mac_sim/last_report)."""
    tail = log_tail[-_LOG_TAIL_MAX:] if len(log_tail) > _LOG_TAIL_MAX else log_tail
    det = (detail or "")[:_DETAIL_MAX]
    payload = {
        "type": "job_report",
        "ok": ok,
        "phase": phase,
        "exit_code": exit_code,
        "detail": det,
        "log_tail": tail,
    }
    try:
        await ws.send(json.dumps(payload))
    except Exception as exc:
        LOG.warning("job_report send failed: %s", exc)


def _screen_dims_from_esphome_yaml(yaml_text: str) -> tuple[int | None, int | None]:
    """Best-effort parse of the first display `dimensions:` width/height from MCU YAML."""
    idx = yaml_text.find("dimensions:")
    if idx < 0:
        return None, None
    chunk = yaml_text[idx : idx + 500]
    wm = re.search(r"width:\s*(\d+)", chunk)
    hm = re.search(r"height:\s*(\d+)", chunk)
    if wm and hm:
        return int(wm.group(1)), int(hm.group(1))
    return None, None


def _ws_url_from_ha_url(ha_url: str, path: str = "/api/esptoolkit/mac_sim/agent/ws") -> str:
    p = urlparse(ha_url.strip())
    if not p.scheme or not p.netloc:
        raise ValueError(f"Invalid HA URL: {ha_url!r}")
    scheme = "wss" if p.scheme == "https" else "ws"
    return f"{scheme}://{p.netloc}{path}"


async def _interrupt_esphome(proc_holder: dict) -> None:
    """Stop the current `esphome run` child so a new job can start (preemption / parity)."""
    proc = proc_holder.get("proc")
    if proc is None or proc.returncode is not None:
        return
    try:
        proc.send_signal(signal.SIGINT)
    except ProcessLookupError:
        proc_holder["proc"] = None
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=20.0)
    except asyncio.TimeoutError:
        LOG.warning("esphome did not exit after SIGINT; sending SIGKILL")
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(ProcessLookupError):
            await proc.wait()
    if proc_holder.get("proc") is proc:
        proc_holder["proc"] = None


async def _run_esphome(yaml_text: str, proc_holder: dict) -> tuple[int, str]:
    """Run ESPHome SDL in a subprocess; return (exit_code, combined stdout/stderr tail for HA)."""
    await _interrupt_esphome(proc_holder)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(yaml_text)
        path = tmp.name
    out_chunks: list[str] = []
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
        proc_holder["proc"] = proc
        assert proc.stdout
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                s = line.decode(errors="replace").rstrip()
                LOG.info("%s", s)
                out_chunks.append(s + "\n")
            rc = int(await proc.wait() or 0)
            combined = "".join(out_chunks)
            if len(combined) > _LOG_TAIL_MAX:
                combined = combined[-_LOG_TAIL_MAX:]
            return rc, combined
        finally:
            if proc_holder.get("proc") is proc:
                proc_holder["proc"] = None
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


def _transform_run_payload(data: dict) -> tuple[str | None, str | None]:
    """Build host/SDL YAML from a HA `run` WebSocket message. Returns (yaml, error_detail)."""
    source_yaml = data.get("source_yaml")
    if isinstance(source_yaml, str) and source_yaml.strip():
        try:
            sw = data.get("screen_width")
            sh = data.get("screen_height")
            try:
                swi = int(sw) if sw is not None else 0
            except (TypeError, ValueError):
                swi = 0
            try:
                shi = int(sh) if sh is not None else 0
            except (TypeError, ValueError):
                shi = 0
            if swi < 120 or shi < 120:
                yw, yh = _screen_dims_from_esphome_yaml(source_yaml)
                if yw and yh and yw >= 120 and yh >= 120:
                    swi, shi = yw, yh
            if swi < 120 or shi < 120:
                return None, "missing screen dimensions (device size required)"
            host_ip = _get_primary_ip()
            host_hostname = socket.gethostname()
            transformed_yaml, tw = transform_esphome_yaml_for_host_sdl(
                source_yaml,
                swi,
                shi,
                api_encryption_key=None,
                esphome_name=None,
                host_ip=host_ip,
                host_hostname=host_hostname,
            )
            for warn in tw:
                LOG.warning("transform warning: %s", warn)
            return transformed_yaml, None
        except Exception as exc:
            LOG.error("Mac-side transform failed: %s", exc)
            return None, str(exc)
    y = data.get("yaml")
    if isinstance(y, str) and y.strip():
        return y, None
    return None, "empty yaml in run message"


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
                # Match HA mac_sim hub queue depth so enqueue rarely blocks on send.
                job_q: asyncio.Queue[dict] = asyncio.Queue(maxsize=8)
                proc_holder: dict = {"proc": None}

                async def recv_loop() -> None:
                    """Keep reading the WebSocket while ESPHome runs (pings + new run jobs)."""
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
                                # Preempt current SDL so the executor can pick this job up without wedging HA's sender.
                                await _interrupt_esphome(proc_holder)
                                try:
                                    job_q.put_nowait(data)
                                except asyncio.QueueFull:
                                    LOG.error(
                                        "Mac sim job queue full (max %d); enqueue another after jobs drain",
                                        job_q.maxsize,
                                    )
                                continue
                            LOG.debug("Message: %s", data)
                    finally:
                        with contextlib.suppress(Exception):
                            await job_q.put({"type": "_shutdown"})

                async def exec_loop() -> None:
                    while True:
                        data = await job_q.get()
                        if data.get("type") == "_shutdown":
                            break
                        if data.get("type") != "run":
                            continue
                        ty, err = _transform_run_payload(data)
                        if err or not ty:
                            if err == "missing screen dimensions (device size required)":
                                LOG.error(
                                    "Mac sim: screen_width/screen_height missing or invalid and "
                                    "could not parse display dimensions from YAML; refusing run."
                                )
                            detail = err or "transform failed"
                            await _send_job_report(
                                ws,
                                ok=False,
                                phase="transform",
                                exit_code=None,
                                detail=detail,
                                log_tail="",
                            )
                            continue
                        transformed_yaml = ty
                        LOG.info("Received run job (%d bytes YAML)", len(transformed_yaml))
                        LOG.info("ESPHome run starting (streaming logs)…")
                        if dump_yaml:
                            _dump_yaml_to_terminal(transformed_yaml)
                        try:
                            rc, log_tail = await _run_esphome(transformed_yaml, proc_holder)
                        except Exception as exc:
                            LOG.exception("esphome run failed: %s", exc)
                            await _send_job_report(
                                ws,
                                ok=False,
                                phase="esphome_run",
                                exit_code=None,
                                detail=str(exc),
                                log_tail="",
                            )
                            continue
                        LOG.info("esphome run finished with code %s", rc)
                        await _send_job_report(
                            ws,
                            ok=(rc == 0),
                            phase="esphome_run",
                            exit_code=rc,
                            detail="" if rc == 0 else f"esphome exited with code {rc}",
                            log_tail=log_tail,
                        )

                exec_task = asyncio.create_task(exec_loop())
                try:
                    await recv_loop()
                finally:
                    await _interrupt_esphome(proc_holder)
                    await exec_task
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
