"""
Standard execution engines used by declarative/compat tools.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx

from app.local_http import execute_local_http


def _format_local_http_response(result: dict[str, Any]) -> str:
    if not result.get("success"):
        return f"Error: {result.get('error', 'unknown')}"
    status = result.get("status_code")
    headers = result.get("headers") or {}
    resp_body = result.get("body")
    lines = [f"Status: {status}"]
    if headers:
        lines.append("Headers: " + ", ".join(f"{k}: {v}" for k, v in list(headers.items())[:10]))
    if resp_body is not None:
        max_body = 512_000
        lines.append("Body: " + (resp_body if len(resp_body) <= max_body else resp_body[:max_body] + "\n... (truncated)"))
    return "\n".join(lines)


async def execute_ha_rest(method: str, path: str, body_obj: dict[str, Any] | list[Any] | None = None) -> str:
    body = None
    if body_obj is not None:
        body = json.dumps(body_obj, separators=(",", ":"))
    result = await execute_local_http(method=method, path=path, body=body)
    return _format_local_http_response(result)


async def execute_ha_rest_json(
    method: str, path: str, body_obj: dict[str, Any] | list[Any] | None = None
) -> Any:
    """Call HA REST and parse JSON body; raises on error status or invalid JSON."""
    body = None
    if body_obj is not None:
        body = json.dumps(body_obj, separators=(",", ":"))
    result = await execute_local_http(method=method, path=path, body=body)
    if not result.get("success"):
        raise RuntimeError(result.get("error", "request failed"))
    status = result.get("status_code")
    text = result.get("body") or ""
    if status and status >= 400:
        raise RuntimeError(f"HTTP {status}: {text[:500]}")
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON: {e}") from e


async def execute_ha_service(
    domain: str,
    service: str,
    service_data: dict[str, Any] | None = None,
    target: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {}
    if service_data:
        payload.update(service_data)
    if target:
        payload["target"] = target
    path = f"/api/services/{domain}/{service}"
    return await execute_ha_rest("POST", path, payload)


async def execute_supervisor_rest(
    method: str, path: str, body_obj: dict[str, Any] | None = None, timeout: float = 30.0
) -> str:
    token = (os.environ.get("SUPERVISOR_TOKEN") or "").strip()
    if not token:
        return "Error: SUPERVISOR_TOKEN not set (addon not running under Supervisor)"
    url = "http://supervisor" + (path if path.startswith("/") else f"/{path}")
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
    content = None
    if body_obj is not None:
        headers["Content-Type"] = "application/json"
        content = json.dumps(body_obj, separators=(",", ":")).encode("utf-8")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method.upper(), url, headers=headers, content=content)
        text = resp.text if resp.text is not None else ""
        if resp.status_code >= 400:
            return f"Error: Supervisor returned {resp.status_code}: {text[:500]}"
        return f"Status: {resp.status_code}\nBody: {text}"
    except Exception as e:
        return f"Error: {e}"


async def execute_supervisor_api_data(
    method: str,
    path: str,
    body_obj: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> Any:
    """
    Call Supervisor REST and return the JSON `data` field from {"result":"ok","data":...}.
    Raises RuntimeError on transport failure, non-2xx, or result != ok.
    """
    token = (os.environ.get("SUPERVISOR_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("SUPERVISOR_TOKEN not set (addon not running under Supervisor)")
    url = "http://supervisor" + (path if path.startswith("/") else f"/{path}")
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
    content: bytes | None = None
    if body_obj is not None:
        headers["Content-Type"] = "application/json"
        content = json.dumps(body_obj, separators=(",", ":")).encode("utf-8")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.request(method.upper(), url, headers=headers, content=content)
    text = resp.text if resp.text is not None else ""
    if resp.status_code >= 400:
        raise RuntimeError(f"Supervisor HTTP {resp.status_code}: {text[:800]}")
    if not text.strip():
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Supervisor returned non-JSON: {text[:300]}") from e
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected Supervisor JSON: {text[:300]}")
    if payload.get("result") != "ok":
        raise RuntimeError(str(payload.get("message") or payload))
    return payload.get("data")


async def execute_supervisor_raw_text(
    method: str,
    path: str,
    *,
    body_obj: dict[str, Any] | None = None,
    timeout: float = 120.0,
    max_chars: int = 512_000,
) -> str:
    """GET/POST Supervisor path and return response body as text (e.g. journal logs)."""
    token = (os.environ.get("SUPERVISOR_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("SUPERVISOR_TOKEN not set (addon not running under Supervisor)")
    url = "http://supervisor" + (path if path.startswith("/") else f"/{path}")
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
    content: bytes | None = None
    if body_obj is not None:
        headers["Content-Type"] = "application/json"
        content = json.dumps(body_obj, separators=(",", ":")).encode("utf-8")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.request(method.upper(), url, headers=headers, content=content)
    text = resp.text if resp.text is not None else ""
    if resp.status_code >= 400:
        raise RuntimeError(f"Supervisor HTTP {resp.status_code}: {text[:800]}")
    if len(text) > max_chars:
        return text[:max_chars] + "\n... (truncated)"
    return text
