"""
Home Assistant WebSocket API — ephemeral connections (auth + one command).
Uses the same token / base selection semantics as local_http (direct Core preferred).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any
from urllib.parse import urlparse

import websockets

from app.config import load_options

log = logging.getLogger("esphome_api.ha_ws")

_message_id = 0


def _next_id() -> int:
    global _message_id
    _message_id += 1
    return _message_id


def _ha_ws_url_and_token() -> tuple[str, str]:
    opts = load_options()
    supervisor_token = (os.environ.get("SUPERVISOR_TOKEN") or "").strip()
    direct_core_base = "http://homeassistant:8123"
    override_base = (opts.get("ha_base_url") or "").strip()
    supervisor_base = "http://supervisor/core"
    if supervisor_token and override_base in ("", "http://localhost:8123", "http://127.0.0.1:8123"):
        base = direct_core_base
    else:
        base = override_base or supervisor_base
    token = (opts.get("ha_token") or "").strip() or supervisor_token
    u = urlparse(base)
    scheme = "wss" if u.scheme == "https" else "ws"
    host = u.hostname or "homeassistant"
    port = u.port
    netloc = f"{host}:{port}" if port else host
    path = (u.path or "").rstrip("/")
    if path.endswith("/core"):
        path = path[: -len("/core")]
    origin = f"{scheme}://{netloc}{path}".rstrip("/")
    ws_url = f"{origin}/api/websocket"
    return ws_url, token


async def ha_ws_call(msg: dict[str, Any], timeout: float = 120.0) -> Any:
    """
    Connect, authenticate, send a single command (with assigned id), return command result.
    msg must NOT contain 'id'.
    """
    ws_url, token = _ha_ws_url_and_token()
    if not token:
        raise RuntimeError(
            "No HA token (SUPERVISOR_TOKEN or ha_token in add-on options)"
        )
    msg_id = _next_id()
    out = {**msg, "id": msg_id}
    async with websockets.connect(
        ws_url,
        ping_interval=20,
        ping_timeout=20,
        close_timeout=10,
        max_size=50_000_000,
    ) as ws:
        hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
        if hello.get("type") != "auth_required":
            raise RuntimeError(f"Expected auth_required, got {hello!r}")
        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        auth_ok = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
        if auth_ok.get("type") == "auth_invalid":
            raise RuntimeError(f"HA auth_invalid: {auth_ok}")
        if auth_ok.get("type") != "auth_ok":
            raise RuntimeError(f"Unexpected auth response: {auth_ok!r}")
        await ws.send(json.dumps(out))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            data = json.loads(raw)
            if data.get("type") == "result" and data.get("id") == msg_id:
                if not data.get("success", True):
                    err = data.get("error", {})
                    code = err.get("code", "?") if isinstance(err, dict) else "?"
                    message = err.get("message", err) if isinstance(err, dict) else str(err)
                    raise RuntimeError(f"HA WS error {code}: {message}")
                return data.get("result")


async def call_service_ws(
    domain: str,
    service: str,
    service_data: dict | None = None,
    target: dict | None = None,
    timeout: float = 180.0,
) -> Any:
    payload: dict[str, Any] = {
        "type": "call_service",
        "domain": domain,
        "service": service,
    }
    if service_data:
        payload["service_data"] = service_data
    if target:
        payload["target"] = target
    return await ha_ws_call(payload, timeout=timeout)
