"""
MCP server exposing ESPHome API as tools. Mount at /mcp with Bearer auth.
"""
import asyncio
from typing import Any

from fastmcp import FastMCP

from app.job_runner import runner
from app.config import get_esphome_config_dir, load_options
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


@mcp.tool()
def esphome_version() -> str:
    """Return the installed ESPHome version and add-on version."""
    esphome_ver = _get_esphome_version_sync()
    return f"ESPHome: {esphome_ver}, Add-on: {addon_version}"


@mcp.tool()
def esphome_configs_list() -> str:
    """List YAML config filenames in the ESPHome config directory (/config/esphome)."""
    config_dir = get_esphome_config_dir()
    files = sorted(p.name for p in config_dir.glob("*.yaml") if not p.name.startswith("."))
    return "\n".join(files) if files else "No .yaml configs found"


@mcp.tool()
def esphome_status() -> str:
    """Return current job status: idle or running command and recent log tail."""
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


@mcp.tool()
async def esphome_config_check(config_source: str, filename: str | None = None, yaml: str | None = None) -> str:
    """Validate an ESPHome config. Use config_source 'file' with filename (e.g. device.yaml) or 'yaml' with yaml content."""
    return await _run_and_format("config", config_source, filename, yaml)


@mcp.tool()
async def esphome_compile(config_source: str, filename: str | None = None, yaml: str | None = None) -> str:
    """Compile an ESPHome config. Use config_source 'file' with filename or 'yaml' with yaml content."""
    return await _run_and_format("compile", config_source, filename, yaml)


@mcp.tool()
async def esphome_run(config_source: str, filename: str | None = None, yaml: str | None = None) -> str:
    """Run ESPHome (validate, compile, upload). Use config_source 'file' with filename or 'yaml' with yaml content."""
    return await _run_and_format("run", config_source, filename, yaml)


@mcp.tool()
async def esphome_upload(config_source: str, filename: str | None = None, yaml: str | None = None) -> str:
    """Upload firmware. Use config_source 'file' with filename or 'yaml' with yaml content."""
    return await _run_and_format("upload", config_source, filename, yaml)


@mcp.tool()
async def esphome_update() -> str:
    """Update ESPHome to the latest version (pip install -U esphome). Returns output."""
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


@mcp.tool()
async def local_http(method: str, path: str, body: str | None = None) -> str:
    """Execute an HTTP request to the local Home Assistant instance (or other allowlisted base).
    Only reachable via MCP; not exposed as REST. By default uses Supervisor proxy (http://supervisor/core) with SUPERVISOR_TOKEN.
    Optional override via ha_base_url and ha_token in add-on options.
    method: GET, POST, PUT, PATCH, or DELETE.
    path: path and optional query, e.g. /api/states or /api/config/config_entries/entry.
    body: optional request body (e.g. JSON string) for POST/PUT/PATCH.
    Returns response status, headers, and body as text."""
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
        lines.append("Body: " + (resp_body if len(resp_body) <= 8000 else resp_body[:8000] + "\n... (truncated)"))
    return "\n".join(lines)


def get_mcp_app():
    """Return the ASGI app for the MCP server (to mount at /mcp). Use path='/' so the MCP endpoint is at the mount root. json_response=True so clients get JSON bodies (not SSE); required for tests and works with Cursor."""
    return mcp.http_app(path="/", json_response=True)
