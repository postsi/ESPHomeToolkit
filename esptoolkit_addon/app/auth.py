"""Bearer token auth for API and MCP."""
import logging

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from app.config import load_options

_api_key_header = APIKeyHeader(name="Authorization", auto_error=False)
log = logging.getLogger("esphome_api.auth")


def get_token_from_options() -> str:
    opts = load_options()
    token = (opts.get("api_token") or "").strip()
    if not token:
        log.warning("API request rejected: api_token not configured in add-on options")
        raise HTTPException(status_code=503, detail="Add-on not configured: api_token is required")
    return token


async def verify_bearer(request: Request) -> str:
    """Verify Authorization: Bearer <token>. Raises 401 if invalid."""
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        log.warning("API request rejected: missing or invalid Authorization header")
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth[7:].strip()
    expected = get_token_from_options()
    if token != expected:
        log.warning("API request rejected: invalid token")
        raise HTTPException(status_code=401, detail="Invalid token")
    return token


def verify_bearer_header(authorization: str = Security(_api_key_header)) -> str:
    """Dependency that verifies Bearer token from header."""
    if not authorization or not authorization.startswith("Bearer "):
        log.warning("API request rejected: missing or invalid Authorization header")
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:].strip()
    expected = get_token_from_options()
    if token != expected:
        log.warning("API request rejected: invalid token")
        raise HTTPException(status_code=401, detail="Invalid token")
    return token
