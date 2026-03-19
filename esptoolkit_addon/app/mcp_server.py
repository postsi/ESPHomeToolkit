"""
MCP server exposing ESPHome API as tools. Mount at /mcp with Bearer auth.
"""
from pathlib import Path

from fastmcp import FastMCP

from app.job_runner import runner
from app.config import get_esphome_config_dir
from app.declarative_tools import DeclarativeToolRegistry
from app.hamcp_tools_compat import HAMCP_TOOL_NAMES, dispatch_hamcp_tool
from app.local_http import execute_local_http
from app import __version__ as addon_version


def _get_esphome_version_sync() -> str:
    import subprocess
    try:
        r = subprocess.run(
            ["esphome", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return (r.stdout or r.stderr or "").strip() or "unknown"
    except Exception as e:
        return f"error: {e}"


mcp = FastMCP(
    "ESPHome API",
    version=addon_version,
)


def _tool_esphome_version() -> str:
    esphome_ver = _get_esphome_version_sync()
    return f"ESPHome: {esphome_ver}, Add-on: {addon_version}"


def _tool_esphome_configs_list() -> str:
    config_dir = get_esphome_config_dir()
    files = sorted(p.name for p in config_dir.glob("*.yaml") if not p.name.startswith("."))
    return "\n".join(files) if files else "No .yaml configs found"


def _tool_esphome_status() -> str:
    status = runner.get_status()
    state = status.get("state", "idle")
    if state == "running":
        cmd = status.get("command", "?")
        tail = status.get("log_tail", [])[-20:]
        return f"Running: {cmd}\n\nLast log lines:\n" + "\n".join(tail)
    tail = status.get("log_tail", [])[-10:]
    return "Idle.\n\nLast log lines:\n" + "\n".join(tail) if tail else "Idle."


async def _run_and_format(command: str, config_source: str, filename: str | None, yaml_content: str | None) -> str:
    result = await runner.run(command, config_source, filename=filename, yaml_content=yaml_content)
    if result["success"]:
        out = result.get("stdout", "").strip()
        return out or "OK"
    err = result.get("error", "Unknown error")
    stderr = result.get("stderr", "").strip()
    stdout = result.get("stdout", "").strip()
    parts = [f"Error: {err}"]
    if stderr:
        parts.append(f"stderr:\n{stderr}")
    if stdout:
        parts.append(f"stdout:\n{stdout}")
    return "\n\n".join(parts)


async def _tool_esphome_command(command: str, config_source: str, filename: str | None = None, yaml: str | None = None) -> str:
    return await _run_and_format(command, config_source, filename, yaml)


async def _tool_esphome_update() -> str:
    import subprocess
    r = subprocess.run(
        ["pip3", "install", "--no-cache-dir", "--break-system-packages", "-U", "esphome"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if r.returncode != 0:
        return f"Update failed (exit {r.returncode}):\n{r.stderr or r.stdout}"
    return r.stdout or "ESPHome updated."


async def _tool_supervisor_store_reload() -> str:
    import os
    import httpx
    token = (os.environ.get("SUPERVISOR_TOKEN") or "").strip()
    if not token:
        return "Error: SUPERVISOR_TOKEN not set (addon not running under Supervisor)"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "http://supervisor/store/reload",
                headers={"Authorization": f"Bearer {token}"},
            )
        if r.status_code == 200:
            return "OK: add-on store reloaded"
        return f"Error: Supervisor returned {r.status_code}: {r.text[:500]}"
    except Exception as e:
        return f"Error: {e}"


async def _tool_local_http(method: str, path: str, body: str | None = None) -> str:
    result = await execute_local_http(method=method, path=path, body=body)
    if not result.get("success"):
        return f"Error: {result.get('error', 'unknown')}"
    status = result.get("status_code")
    headers = result.get("headers") or {}
    resp_body = result.get("body")
    lines = [f"Status: {status}"]
    if headers:
        lines.append("Headers: " + ", ".join(f"{k}: {v}" for k, v in list(headers.items())[:10]))
    if resp_body is not None:
        # Allow large bodies (e.g. GET project ~tens of KB) so MCP clients get valid JSON
        _max_body = 512_000
        lines.append("Body: " + (resp_body if len(resp_body) <= _max_body else resp_body[:_max_body] + "\n... (truncated)"))
    return "\n".join(lines)


_REGISTRY = DeclarativeToolRegistry(
    manifest_path=Path(__file__).resolve().parent / "tool_manifests" / "esptoolkit_tools.json",
    handlers={
        "esphome_version": _tool_esphome_version,
        "esphome_configs_list": _tool_esphome_configs_list,
        "esphome_status": _tool_esphome_status,
        "esphome_command": _tool_esphome_command,
        "esphome_update": _tool_esphome_update,
        "supervisor_store_reload": _tool_supervisor_store_reload,
        "local_http": _tool_local_http,
    },
)


@mcp.tool()
def esphome_version() -> str:
    """Return the installed ESPHome version and add-on version."""
    return _REGISTRY.execute_sync("esphome_version")


@mcp.tool()
def esphome_configs_list() -> str:
    """List YAML config filenames in the ESPHome config directory (/config/esphome)."""
    return _REGISTRY.execute_sync("esphome_configs_list")


@mcp.tool()
def esphome_status() -> str:
    """Return current job status: idle or running command and recent log tail."""
    return _REGISTRY.execute_sync("esphome_status")


@mcp.tool()
async def esphome_config_check(config_source: str, filename: str | None = None, yaml: str | None = None) -> str:
    """Validate an ESPHome config. Use config_source 'file' with filename (e.g. device.yaml) or 'yaml' with yaml content."""
    return await _REGISTRY.execute("esphome_config_check", config_source=config_source, filename=filename, yaml=yaml)


@mcp.tool()
async def esphome_compile(config_source: str, filename: str | None = None, yaml: str | None = None) -> str:
    """Compile an ESPHome config. Use config_source 'file' with filename or 'yaml' with yaml content."""
    return await _REGISTRY.execute("esphome_compile", config_source=config_source, filename=filename, yaml=yaml)


@mcp.tool()
async def esphome_run(config_source: str, filename: str | None = None, yaml: str | None = None) -> str:
    """Run ESPHome (validate, compile, upload). Use config_source 'file' with filename or 'yaml' with yaml content."""
    return await _REGISTRY.execute("esphome_run", config_source=config_source, filename=filename, yaml=yaml)


@mcp.tool()
async def esphome_upload(config_source: str, filename: str | None = None, yaml: str | None = None) -> str:
    """Upload firmware. Use config_source 'file' with filename or 'yaml' with yaml content."""
    return await _REGISTRY.execute("esphome_upload", config_source=config_source, filename=filename, yaml=yaml)


@mcp.tool()
async def esphome_update() -> str:
    """Update ESPHome to the latest version (pip install -U esphome). Returns output."""
    return await _REGISTRY.execute("esphome_update")


@mcp.tool()
async def supervisor_store_reload() -> str:
    """Reload the Home Assistant add-on store so new addon versions appear (e.g. after pushing a new image).
    Calls Supervisor API POST /store/reload. Requires addon to run under Supervisor with SUPERVISOR_TOKEN.
    Returns success message or error."""
    return await _REGISTRY.execute("supervisor_store_reload")


@mcp.tool()
async def local_http(method: str, path: str, body: str | None = None) -> str:
    """Execute an HTTP request to the local Home Assistant instance (or other allowlisted base).
    Only reachable via MCP; not exposed as REST. By default uses Supervisor proxy (http://supervisor/core) with SUPERVISOR_TOKEN.
    Optional override via ha_base_url and ha_token in add-on options.
    method: GET, POST, PUT, PATCH, or DELETE.
    path: path and optional query, e.g. /api/states or /api/config/config_entries/entry.
    body: optional request body (e.g. JSON string) for POST/PUT/PATCH.
    Returns response status, headers, and body as text."""
    return await _REGISTRY.execute("local_http", method=method, path=path, body=body)


def get_mcp_app():
    """Return the ASGI app for the MCP server (to mount at /mcp). Use path='/' so the MCP endpoint is at the mount root. json_response=True so clients get JSON bodies (not SSE); required for tests and works with Cursor."""
    return mcp.http_app(path="/", json_response=True)


def _register_hamcp_tools() -> None:
    """Expose HAMCPTools (`ha_*`) tool names on this MCP server."""
    def _make_compat_handler(bound_tool_name: str):
        async def _compat_tool(payload: dict | None = None) -> str:
            return await dispatch_hamcp_tool(bound_tool_name, payload)
        _compat_tool.__name__ = f"compat_{bound_tool_name}"
        return _compat_tool

    compat_desc = (
        "HAMCPTools — Home Assistant MCP tool (full implementation in-addon). "
        "Pass all arguments as a single JSON object in `payload`."
    )
    for tool_name in HAMCP_TOOL_NAMES:
        mcp.tool(name=tool_name, description=compat_desc)(_make_compat_handler(tool_name))


_register_hamcp_tools()
