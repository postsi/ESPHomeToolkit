"""
Local HTTP proxy: execute requests to allowlisted bases (e.g. Home Assistant).
Used only by the MCP tool; no REST endpoint. Addon-held HA token; no client-supplied URLs.
"""
import logging
import os
from urllib.parse import urlparse

import httpx

from app.config import load_options

ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
SENSITIVE_RESPONSE_HEADERS = frozenset({"set-cookie", "authorization", "cookie"})

log = logging.getLogger("esphome_api.local_http")


def _normalize_prefix(url: str) -> str:
    """Return a normalized URL prefix: scheme://netloc[/path], no trailing slash."""
    u = urlparse(url)
    scheme = (u.scheme or "http").lower()
    netloc = (u.netloc or "").lower()
    path = (u.path or "").rstrip("/")
    return f"{scheme}://{netloc}{path}"


def _get_allowed_bases_and_token() -> tuple[list[str], str]:
    opts = load_options()
    # Tight default: use Supervisor proxy to talk to HA Core.
    # This avoids storing a separate HA long-lived token in add-on options.
    supervisor_token = (os.environ.get("SUPERVISOR_TOKEN") or "").strip()
    supervisor_base = "http://supervisor/core"

    # Optional override for advanced setups (e.g. remote HA core, custom proxy).
    override_base = (opts.get("ha_base_url") or "").strip()
    override_token = (opts.get("ha_token") or "").strip()

    base = override_base or supervisor_base
    token = override_token or supervisor_token

    bases: list[str] = []
    for b in (base, supervisor_base):
        n = _normalize_prefix(b)
        if n and n not in bases:
            bases.append(n)
    return bases, token


def _validate_path(path: str) -> str | None:
    """Path must start with / and not contain '..'. Returns error message or None."""
    if not path or not path.startswith("/"):
        return "path must start with /"
    if ".." in path:
        return "path must not contain .."
    return None


async def execute_local_http(method: str, path: str, body: str | None = None) -> dict:
    """
    Execute a single HTTP request to an allowlisted base (e.g. HA).
    method: GET, POST, PUT, PATCH, DELETE.
    path: path (and optional query) e.g. /api/states.
    body: optional string body (e.g. JSON) for POST/PUT/PATCH.
    Returns dict with success, status_code, headers, body, error.
    """
    method = (method or "GET").strip().upper()
    if method not in ALLOWED_METHODS:
        return {
            "success": False,
            "error": f"method not allowed: {method}",
            "status_code": None,
            "headers": {},
            "body": None,
        }

    path = (path or "/").strip()
    err = _validate_path(path.split("?")[0])
    if err:
        return {"success": False, "error": err, "status_code": None, "headers": {}, "body": None}

    bases, token = _get_allowed_bases_and_token()
    if not bases:
        return {
            "success": False,
            "error": "no allowed base URL configured (set ha_base_url in add-on options)",
            "status_code": None,
            "headers": {},
            "body": None,
        }

    base_prefix = bases[0]
    # When using supervisor proxy, token is required (SUPERVISOR_TOKEN); Core API rejects unauthenticated requests.
    if base_prefix == "http://supervisor/core" and not token:
        return {
            "success": False,
            "error": "SUPERVISOR_TOKEN not set; add-on may not be running under Home Assistant Supervisor, or set ha_base_url and ha_token in add-on options",
            "status_code": None,
            "headers": {},
            "body": None,
        }

    # Use first allowed base (primary HA).
    # path may include query string, e.g. /api/states?filter=...
    url = base_prefix + ("/" + path.lstrip("/") if path != "/" else "/")
    if not any(url.startswith(p + "/") or url == (p + "/") for p in bases):
        return {
            "success": False,
            "error": "url not in allowlist",
            "status_code": None,
            "headers": {},
            "body": None,
        }

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body and method in ("POST", "PUT", "PATCH"):
        headers["Content-Type"] = "application/json"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                method,
                url,
                content=body.encode("utf-8") if body else None,
                headers=headers or None,
            )
    except httpx.TimeoutException as e:
        log.warning("local_http timeout: %s %s -> %s", method, path, url)
        return {
            "success": False,
            "error": f"request timeout to {url}: {e}",
            "status_code": None,
            "headers": {},
            "body": None,
        }
    except Exception as e:
        log.exception("local_http request failed: %s %s -> %s", method, path, url)
        return {
            "success": False,
            "error": f"proxy to {url} failed: {str(e)}",
            "status_code": None,
            "headers": {},
            "body": None,
        }

    # Sanitize response headers
    out_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in SENSITIVE_RESPONSE_HEADERS
    }

    try:
        response_body = resp.text
    except Exception:
        response_body = None

    return {
        "success": True,
        "status_code": resp.status_code,
        "headers": dict(out_headers),
        "body": response_body,
    }
