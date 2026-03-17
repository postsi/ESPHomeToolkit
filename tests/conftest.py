"""
Pytest fixtures for HA integration tests.
Tests run against the app as it appears in HA: they call the addon via MCP (local_http)
and optionally use addon MCP tools (esphome_*). Requires ADDON_URL and ADDON_TOKEN in env.
"""
import os
import json
import pytest
import httpx

# -----------------------------------------------------------------------------
# MCP client: call addon's MCP server (tools/call) and return tool result text
# -----------------------------------------------------------------------------

def _mcp_tools_call(base_url: str, token: str, tool_name: str, arguments: dict) -> str:
    """Send MCP tools/call to addon, return the tool result as string."""
    url = base_url.rstrip("/") + "/mcp/"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    with httpx.Client(timeout=30.0) as client:
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
    if not u:
        pytest.skip("ESPTOOLKIT_ADDON_URL not set")
    return u


@pytest.fixture(scope="session")
def addon_token():
    t = os.environ.get("ESPTOOLKIT_ADDON_TOKEN", "").strip()
    if not t:
        pytest.skip("ESPTOOLKIT_ADDON_TOKEN not set")
    return t


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
