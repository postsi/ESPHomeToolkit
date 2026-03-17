"""
Pytest fixtures for HA integration tests.
Tests run against the app as it appears in HA: they call the addon via MCP (local_http)
and optionally use addon MCP tools (esphome_*). Requires ADDON_URL and ADDON_TOKEN in env.
"""
import os
import json
import pytest
import httpx
import socket
from urllib.parse import urlparse, urlunparse

# -----------------------------------------------------------------------------
# Cursor MCP config discovery (optional)
# -----------------------------------------------------------------------------

def _load_cursor_mcp_esptoolkit() -> tuple[str | None, str | None]:
    """Best-effort: read ~/.cursor/mcp.json and return (addon_base_url, addon_token)."""
    path = os.path.expanduser("~/.cursor/mcp.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None, None

    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        return None, None

    s = servers.get("esptoolkit")
    if not isinstance(s, dict):
        return None, None

    url = (s.get("url") or "").strip()
    headers = s.get("headers") or {}
    auth = (headers.get("Authorization") or headers.get("authorization") or "").strip() if isinstance(headers, dict) else ""

    if not url or not auth:
        return None, None

    # Cursor stores the full MCP endpoint, typically .../mcp/
    u = url.rstrip("/")
    if u.endswith("/mcp"):
        addon_base = u[: -len("/mcp")]
    else:
        addon_base = u

    token = auth
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return addon_base, token

# -----------------------------------------------------------------------------
# MCP client: call addon's MCP server (tools/call) and return tool result text
# -----------------------------------------------------------------------------

_MCP_SESSION_CACHE: dict[tuple[str, str], str] = {}

def _prefer_ipv4(url: str) -> str:
    """If hostname resolves to IPv4, rewrite URL to use the first IPv4 address.
    Avoids environments where IPv6 is preferred but the service only listens on IPv4."""
    try:
        u = urlparse(url)
        host = u.hostname
        if not host:
            return url
        # Already an IP literal?
        try:
            socket.inet_pton(socket.AF_INET, host)
            return url
        except Exception:
            pass
        infos = socket.getaddrinfo(host, u.port or (443 if u.scheme == "https" else 80), family=socket.AF_INET)
        if not infos:
            return url
        ip = infos[0][4][0]
        netloc = ip
        if u.port:
            netloc = f"{ip}:{u.port}"
        return urlunparse((u.scheme, netloc, u.path, u.params, u.query, u.fragment))
    except Exception:
        return url


def _mcp_initialize(base_url: str, token: str) -> str:
    """Initialize MCP session and return mcp-session-id."""
    url = _prefer_ipv4(base_url.rstrip("/") + "/mcp/")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        # Client declares supported protocol version (FastMCP uses this header for streamable HTTP sessions)
        "mcp-protocol-version": "2025-03-26",
    }
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "esptoolkit-pytest", "version": "0.1"},
        },
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.post(url, headers=headers, json=body)
        r.raise_for_status()
        sid = r.headers.get("mcp-session-id") or r.headers.get("Mcp-Session-Id")
        if not sid:
            # Some servers include it lowercased; httpx normalizes, but keep fallback
            sid = r.headers.get("mcp-session-id".lower())
        if not sid:
            # Even if server doesn't provide a session id, allow stateless mode
            return ""
        return sid


def _mcp_tools_call(base_url: str, token: str, tool_name: str, arguments: dict) -> str:
    """Send MCP tools/call to addon, return the tool result as string."""
    url = _prefer_ipv4(base_url.rstrip("/") + "/mcp/")
    cache_key = (url, token)
    sid = _MCP_SESSION_CACHE.get(cache_key)
    if sid is None:
        sid = _mcp_initialize(base_url, token)
        _MCP_SESSION_CACHE[cache_key] = sid
    # Tool-specific timeouts: compile/run/upload/update can legitimately take longer.
    timeout_s = 30.0
    if tool_name.startswith(("esphome_compile", "esphome_run", "esphome_upload", "esphome_update", "esphome_config_check")):
        timeout_s = 300.0
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "mcp-protocol-version": "2025-03-26",
    }
    if sid:
        headers["mcp-session-id"] = sid
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    with httpx.Client(timeout=timeout_s) as client:
        r = client.post(url, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
    err = data.get("error")
    if err:
        raise RuntimeError(f"MCP error: {err}")
    result = data.get("result")
    if result is None:
        raise RuntimeError("MCP response missing result")
    # fastmcp may wrap in content array
    if isinstance(result, dict) and "content" in result:
        parts = result["content"]
        if isinstance(parts, list) and parts and isinstance(parts[0], dict) and parts[0].get("type") == "text":
            return parts[0].get("text", "")
    if isinstance(result, str):
        return result
    return str(result)


# -----------------------------------------------------------------------------
# HA API client via local_http (parses Status + Body from tool result)
# -----------------------------------------------------------------------------

def _parse_local_http_result(text: str) -> tuple[int | None, str | None]:
    """Parse 'Status: 200\\nHeaders: ...\\nBody: {...}' into (status_code, body_str). Body may be multi-line."""
    status = None
    body = None
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("Status:"):
            try:
                status = int(line.split(":", 1)[1].strip())
            except (ValueError, IndexError):
                pass
        elif line.startswith("Body:"):
            first = line.split(":", 1)[1].lstrip() if ":" in line else ""
            rest = "\n".join(lines[i + 1 :]) if i + 1 < len(lines) else ""
            body = (first + ("\n" + rest if rest else "")).strip()
            break
    return status, body


class HaApiClient:
    """Calls HA integration API via addon's local_http MCP tool."""

    def __init__(self, addon_url: str, addon_token: str):
        self._url = addon_url.rstrip("/")
        self._token = addon_token

    def _request(self, method: str, path: str, body: str | None = None) -> tuple[int, str]:
        raw = _mcp_tools_call(
            self._url,
            self._token,
            "local_http",
            {"method": method, "path": path, "body": body},
        )
        if raw.startswith("Error:"):
            raise RuntimeError(raw)
        status, body_str = _parse_local_http_result(raw)
        if status is None:
            raise RuntimeError(f"Could not parse local_http result: {raw[:500]}")
        return status, body_str or ""

    def get(self, path: str) -> tuple[int, str]:
        return self._request("GET", path)

    def post(self, path: str, json_body: dict) -> tuple[int, str]:
        return self._request("POST", path, json.dumps(json_body))

    def put(self, path: str, json_body: dict) -> tuple[int, str]:
        return self._request("PUT", path, json.dumps(json_body))

    def delete(self, path: str) -> tuple[int, str]:
        return self._request("DELETE", path)

    def get_json(self, path: str) -> tuple[int, dict]:
        status, body = self.get(path)
        data = {}
        if body:
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                pass
        return status, data

    def post_json(self, path: str, payload: dict) -> tuple[int, dict]:
        status, body = self.post(path, payload)
        data = {}
        if body:
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                pass
        return status, data


def _addon_call(base_url: str, token: str, tool_name: str, **kwargs) -> str:
    """Call any addon MCP tool by name."""
    return _mcp_tools_call(base_url, token, tool_name, kwargs)


# -----------------------------------------------------------------------------
# Pytest fixtures
# -----------------------------------------------------------------------------

@pytest.fixture(scope="session")
def addon_url():
    u = os.environ.get("ESPTOOLKIT_ADDON_URL", "").strip()
    if u:
        return u
    auto_url, _ = _load_cursor_mcp_esptoolkit()
    if auto_url:
        return auto_url
    pytest.skip("ESPTOOLKIT_ADDON_URL not set and ~/.cursor/mcp.json missing esptoolkit url")


@pytest.fixture(scope="session")
def addon_token():
    t = os.environ.get("ESPTOOLKIT_ADDON_TOKEN", "").strip()
    if t:
        return t
    _, auto_token = _load_cursor_mcp_esptoolkit()
    if auto_token:
        return auto_token
    pytest.skip("ESPTOOLKIT_ADDON_TOKEN not set and ~/.cursor/mcp.json missing esptoolkit token")


@pytest.fixture(scope="session")
def ha_api(addon_url, addon_token):
    """HA API client (integration + HA Core) via local_http."""
    return HaApiClient(addon_url, addon_token)


@pytest.fixture(scope="session")
def entry_id():
    """Config entry ID for integration (optional; some tests need a device)."""
    return os.environ.get("ESPTOOLKIT_ENTRY_ID", "").strip()


@pytest.fixture(scope="session")
def device_id():
    """Device ID for project tests (optional)."""
    return os.environ.get("ESPTOOLKIT_DEVICE_ID", "").strip()


def _esptoolkit_path(path: str, entry_id: str | None = None) -> str:
    p = f"/api/esptoolkit/{path.lstrip('/')}"
    if entry_id:
        sep = "&" if "?" in p else "?"
        p = f"{p}{sep}entry_id={entry_id}"
    return p


@pytest.fixture
def api_path(entry_id):
    """Helper to build integration API path with optional entry_id."""

    def _path(path: str, use_entry: bool = True) -> str:
        return _esptoolkit_path(path, entry_id if use_entry else None)

    return _path
