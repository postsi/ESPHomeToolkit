"""
ESPHome API Add-on: FastAPI app, API routes, static UI, WebSocket logs.
MCP server is mounted at /mcp (see mcp_server.py).
"""
# Log version first so we can confirm which build is running (stderr -> add-on log)
import sys
try:
    from app import __version__ as _v
    print(f"[ESPHome API Add-on] version {_v}", file=sys.stderr, flush=True)
except Exception:
    pass

# Starlette 0.45+ removed NotFound; fastmcp/mcp may still import it. Patch before any such import.
import starlette.exceptions as _se
if not getattr(_se, "NotFound", None):
    class _NotFound(_se.HTTPException):
        def __init__(self, detail=None):
            super().__init__(status_code=404, detail=detail or "Not Found")
    _se.NotFound = _NotFound

import asyncio
import logging
import subprocess
from pathlib import Path

# Logging to stdout so it appears in the add-on Log tab in HA
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
    force=True,
)
log = logging.getLogger("esphome_api")

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import __version__ as addon_version
from app.auth import verify_bearer_header
from app.config import get_esphome_config_dir, get_setup_complete, load_options, regenerate_token_and_save, set_setup_complete
from app.job_runner import runner
from app.mcp_server import get_mcp_app

# MCP Streamable HTTP requires the MCP app's lifespan to run so StreamableHTTPSessionManager task group is initialized.
_mcp_app = get_mcp_app()
app = FastAPI(
    title="ESPHome API Add-on",
    version=addon_version,
    lifespan=_mcp_app.lifespan,
)


@app.exception_handler(RequestValidationError)
async def log_validation_error(request: Request, exc: RequestValidationError):
    """Log Pydantic validation errors for debugging 422 responses."""
    path = request.scope.get("path", request.url.path)
    log.warning(
        "Request validation failed: path=%s errors=%s",
        path, exc.errors(),
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.middleware("http")
async def mcp_trailing_slash(request: Request, call_next):
    """Normalize /mcp to /mcp/ so the mounted MCP app (route '/') receives the request. Cursor may call either."""
    if request.scope.get("path") == "/mcp":
        request.scope["path"] = "/mcp/"
    return await call_next(request)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log request path, method and response status to add-on log for debugging."""
    try:
        response = await call_next(request)
        log.info("%s %s -> %s", request.method, request.scope.get("path", request.url.path), response.status_code)
        return response
    except Exception as e:
        log.exception("Request failed: %s %s", request.method, request.url.path)
        raise


# Optional request body for compile/config-check/run/upload
class ConfigRequest(BaseModel):
    config_source: str = Field(..., description="'file' or 'yaml'")
    filename: str | None = Field(None, description="Filename under /config/esphome (e.g. device.yaml)")
    yaml: str | None = Field(None, description="Raw YAML config when config_source is 'yaml'")


def _require_auth():
    return Depends(verify_bearer_header)

api = APIRouter(prefix="/api", dependencies=[_require_auth()])


@api.get("/version")
async def get_version():
    """Return ESPHome and add-on version."""
    try:
        result = subprocess.run(
            ["esphome", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        esphome_version = (result.stdout or result.stderr or "").strip() or "unknown"
    except Exception as e:
        esphome_version = f"error: {e}"
    return {"esphome": esphome_version, "api_addon": addon_version}


@api.post("/update-esphome")
async def update_esphome():
    """Force update ESPHome to latest. Returns output and errors."""
    result = subprocess.run(
        ["pip3", "install", "--no-cache-dir", "--break-system-packages", "-U", "esphome"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    success = result.returncode == 0
    if not success:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "ESPHome update failed",
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
            },
        )
    return {"success": True, "stdout": stdout, "stderr": stderr}


@api.post("/compile")
async def compile_config(body: ConfigRequest):
    """Compile config (file or yaml snippet)."""
    log.info("Compile request: config_source=%s filename=%s", body.config_source, body.filename)
    result = await runner.run(
        "compile",
        body.config_source,
        filename=body.filename,
        yaml_content=body.yaml,
    )
    if not result["success"]:
        raise HTTPException(
            status_code=422,
            detail={
                "error": result.get("error", "Compilation failed"),
                "exit_code": result.get("exit_code"),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
            },
        )
    return result


@api.post("/config-check")
async def config_check(body: ConfigRequest):
    """Validate config (file or yaml snippet)."""
    yaml_len = len(body.yaml) if body.yaml else 0
    log.info(
        "Config-check request: config_source=%s filename=%r yaml_len=%d",
        body.config_source, body.filename, yaml_len,
    )
    result = await runner.run(
        "config",
        body.config_source,
        filename=body.filename,
        yaml_content=body.yaml,
    )
    if not result["success"]:
        raise HTTPException(
            status_code=422,
            detail={
                "error": result.get("error", "Config check failed"),
                "exit_code": result.get("exit_code"),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
            },
        )
    return result


@api.post("/run")
async def run_config(body: ConfigRequest):
    """Run (validate + compile + upload)."""
    log.info("Run request: config_source=%s filename=%s", body.config_source, body.filename)
    result = await runner.run(
        "run",
        body.config_source,
        filename=body.filename,
        yaml_content=body.yaml,
    )
    if not result["success"]:
        raise HTTPException(
            status_code=422,
            detail={
                "error": result.get("error", "Run failed"),
                "exit_code": result.get("exit_code"),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
            },
        )
    return result


@api.post("/upload")
async def upload_config(body: ConfigRequest):
    """Upload firmware (compile if needed then upload)."""
    log.info("Upload request: config_source=%s filename=%s", body.config_source, body.filename)
    result = await runner.run(
        "upload",
        body.config_source,
        filename=body.filename,
        yaml_content=body.yaml,
    )
    if not result["success"]:
        raise HTTPException(
            status_code=422,
            detail={
                "error": result.get("error", "Upload failed"),
                "exit_code": result.get("exit_code"),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
            },
        )
    return result


@api.get("/status")
async def get_status():
    """Current job status and log tail."""
    return runner.get_status()


@api.get("/logs")
async def get_logs_tail(n: int = 500):
    """Last n log lines."""
    return {"logs": runner.get_log_tail(n)}


# WebSocket route is registered on app directly (not api router) because
# APIKeyHeader/verify_bearer_header expect HTTP Request scope; WebSocket has
# a different scope and causes TypeError. The WebSocket does its own token
# validation via query param or first message.
async def _websocket_logs_impl(websocket: WebSocket):
    """Live log stream. Client must send ?token=... or first message as {"token":"..."}."""
    await websocket.accept()
    token = None
    try:
        query = websocket.query_params.get("token")
        if query:
            token = query
        opts = load_options()
        expected = (opts.get("api_token") or "").strip()
        if not expected:
            await websocket.close(code=4503, reason="Add-on not configured")
            return
        if not token:
            msg = await websocket.receive_text()
            try:
                import json
                data = json.loads(msg)
                token = data.get("token")
            except Exception:
                await websocket.close(code=4401, reason="Invalid auth")
                return
        if token != expected:
            await websocket.close(code=4401, reason="Invalid token")
            return
        queue = runner.subscribe_logs()
        try:
            while True:
                try:
                    line = await asyncio.wait_for(queue.get(), timeout=30.0)
                    await websocket.send_text(line)
                except asyncio.TimeoutError:
                    await websocket.send_text("")
        except WebSocketDisconnect:
            pass
        finally:
            runner.unsubscribe_logs(queue)
    except Exception:
        pass


@api.get("/configs")
async def list_configs():
    """List YAML config files in /config/esphome."""
    config_dir = get_esphome_config_dir()
    files = []
    for p in config_dir.glob("*.yaml"):
        if p.name.startswith("."):
            continue
        try:
            rel = p.relative_to(config_dir)
            files.append(rel.as_posix())
        except ValueError:
            continue
    return {"configs": sorted(files)}


@api.post("/setup-complete")
async def post_setup_complete(body: dict):
    """Set setup complete (body: {"setup_complete": true|false})."""
    set_setup_complete(bool(body.get("setup_complete", False)))
    return {"setup_complete": get_setup_complete()}


@api.post("/regenerate-token")
async def regenerate_token():
    """Generate a new API token (overwrites saved token), restart the add-on, and return a warning to update Cursor."""
    import os
    import httpx
    regenerate_token_and_save()
    log.warning("API token regenerated; add-on will restart. User must update Cursor mcp.json with the new token.")
    supervisor_token = os.environ.get("SUPERVISOR_TOKEN")
    msg_after = "Refresh the Setup page and copy the new MCP config, then update your Cursor mcp.json and restart Cursor."
    if supervisor_token:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    "http://supervisor/addons/self/restart",
                    headers={"Authorization": f"Bearer {supervisor_token}"},
                )
                r.raise_for_status()
            return {"success": True, "message": f"New token saved. Add-on is restarting. {msg_after}", "restart_triggered": True}
        except Exception as e:
            log.exception("Failed to restart add-on after token regeneration: %s", e)
    return {
        "success": True,
        "message": f"New token saved. Restart the add-on manually (Settings → Add-ons → ESPHome API Add-on → Restart), then {msg_after}",
        "restart_triggered": False,
    }


def _addon_base_url(request: Request, path_suffix: str) -> str:
    """Build add-on base URL. Prefer X-Addon-Base from client (Setup page sends browser URL); else derive from request path (HA may strip path when forwarding)."""
    client_base = request.headers.get("X-Addon-Base", "").strip().rstrip("/")
    if client_base:
        return client_base
    path = request.url.path
    if path.endswith(path_suffix):
        base_path = path[: -len(path_suffix)].rstrip("/") or ""
    else:
        base_path = ""
    return f"{request.url.scheme}://{request.url.netloc}{base_path}".rstrip("/")


# Public endpoints (no auth) for UI
@app.get("/api/public/info")
async def public_info(request: Request):
    """Return add-on version. MCP URL should be built client-side from location.origin + path (ingress-safe)."""
    base = _addon_base_url(request, "/api/public/info")
    log.info("GET /api/public/info -> mcp_base_url=%s (client=%s)", base, request.client.host if request.client else "?")
    return {"mcp_base_url": base, "addon_version": addon_version}


@app.get("/api/public/mcp-config")
async def get_mcp_config(request: Request):
    """Return pre-built MCP config blocks using the current API token (single source of truth). No auth so Setup page can load it."""
    opts = load_options()
    token = (opts.get("api_token") or "").strip()
    base = _addon_base_url(request, "/api/public/mcp-config")
    if not token:
        return {"token_set": False, "message": "Set API token in Add-on Configuration and restart the add-on."}
    stdio_config = {
        "mcpServers": {
            "esptoolkit": {
                "command": "python",
                "args": ["-m", "mcp_stdio_proxy"],
                "env": {"ESPHOME_API_URL": base, "ESPHOME_API_TOKEN": token},
            }
        }
    }
    direct_config = {
        "mcpServers": {
            "esptoolkit": {
                "type": "streamableHttp",
                "url": f"{base}/mcp/",
                "headers": {"Authorization": f"Bearer {token}"},
            }
        }
    }
    return {"token_set": True, "base_url": base, "stdio_config": stdio_config, "direct_config": direct_config}


@app.get("/api/setup-complete")
async def get_setup_complete_public():
    """Whether setup is complete (for default tab). No auth so UI can decide before token is entered."""
    return {"setup_complete": get_setup_complete()}


app.include_router(api)


@app.websocket("/api/logs/ws")
async def websocket_logs(websocket: WebSocket):
    """Live log stream. Auth via ?token=... or first message {"token":"..."}."""
    await _websocket_logs_impl(websocket)


# MCP: require Bearer token for /mcp (and /mcp/)
@app.middleware("http")
async def mcp_auth_middleware(request: Request, call_next):
    path = request.scope.get("path", request.url.path)
    if path.startswith("/mcp"):
        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            log.warning("MCP request rejected: missing or invalid Authorization header (path=%s)", path)
            return JSONResponse({"detail": "Missing or invalid Authorization"}, status_code=401)
        token = auth[7:].strip()
        opts = load_options()
        expected = (opts.get("api_token") or "").strip()
        if not expected:
            log.warning("MCP request rejected: api_token not configured in add-on")
            return JSONResponse({"detail": "Add-on not configured: api_token required"}, status_code=503)
        if token != expected:
            log.warning("MCP request rejected: invalid token (path=%s)", path)
            return JSONResponse({"detail": "Invalid token"}, status_code=401)
        log.info("MCP request allowed: path=%s", path)
    response = await call_next(request)
    if path.startswith("/mcp"):
        log.info("MCP response: path=%s status=%s", path, getattr(response, "status_code", "?"))
    return response


app.mount("/mcp", _mcp_app)

# Static UI (must be last so /api and /mcp take precedence)
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def run():
    """Entry point for run.sh or s6 esphome-api service."""
    import os
    import uvicorn
    opts = load_options()
    # When behind nginx (s6), listen on internal port so nginx can bind to ingress port 8098
    port = int(os.environ.get("ESPHOME_API_LISTEN_PORT", 0)) or opts.get("port", 8098)
    has_token = bool((opts.get("api_token") or "").strip())
    config_dir = str(get_esphome_config_dir())
    log.info("Starting API server: port=%s api_token_configured=%s addon_version=%s", port, has_token, addon_version)
    log.info("ESPHome config directory: %s", config_dir)
    log.info("API ready: POST /api/compile, /api/upload, /api/run, /api/config-check | GET /api/version, /api/status, /api/configs")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    run()
