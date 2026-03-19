"""HACS install/uninstall (ZIP from GitHub) — same approach as Vibecode agent."""
from __future__ import annotations

import io
import json
import logging
import shutil
import zipfile
from pathlib import Path

import httpx

from app.tool_engines import execute_ha_service

log = logging.getLogger("esphome_api.hamcp_hacs")

HACS_GITHUB_REPO = "hacs/integration"
HACS_INSTALL_PATH = Path("/config/custom_components/hacs")


def _safe_extract_zip(zip_content: bytes, target_dir: Path) -> None:
    target_path = target_dir.resolve()
    with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
        for member in zf.namelist():
            dest = (target_path / member).resolve()
            if not str(dest).startswith(str(target_path)):
                raise ValueError(f"Path traversal in ZIP: {member}")
        zf.extractall(target_path)


async def hacs_install() -> dict:
    if HACS_INSTALL_PATH.exists():
        manifest = HACS_INSTALL_PATH / "manifest.json"
        ver = "unknown"
        if manifest.exists():
            try:
                ver = json.loads(manifest.read_text(encoding="utf-8")).get("version", "unknown")
            except Exception:
                pass
        return {"success": True, "message": "HACS already installed", "version": ver, "path": str(HACS_INSTALL_PATH)}

    url = f"https://api.github.com/repos/{HACS_GITHUB_REPO}/releases/latest"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        release = r.json()
    download_url = None
    version = release.get("tag_name", "unknown")
    for asset in release.get("assets", []):
        if asset.get("name") == "hacs.zip":
            download_url = asset.get("browser_download_url")
            break
    if not download_url:
        raise RuntimeError("hacs.zip asset not found in latest release")

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.get(download_url)
        r.raise_for_status()
        data = r.content

    HACS_INSTALL_PATH.mkdir(parents=True, exist_ok=True)
    _safe_extract_zip(data, HACS_INSTALL_PATH)
    try:
        await execute_ha_service("homeassistant", "restart")
    except Exception as e:
        log.warning("restart after HACS install: %s", e)
    return {
        "success": True,
        "message": f"HACS {version} installed; Home Assistant restart initiated",
        "version": version,
        "path": str(HACS_INSTALL_PATH),
    }


async def hacs_uninstall() -> dict:
    if not HACS_INSTALL_PATH.exists():
        return {"success": True, "message": "HACS not installed", "was_installed": False}
    shutil.rmtree(HACS_INSTALL_PATH)
    storage = Path("/config/.storage")
    if storage.exists():
        for p in storage.glob("hacs*"):
            try:
                p.unlink()
            except OSError:
                pass
    try:
        await execute_ha_service("homeassistant", "restart")
    except Exception as e:
        log.warning("restart after HACS uninstall: %s", e)
    return {"success": True, "message": "HACS removed; restart initiated", "removed_path": str(HACS_INSTALL_PATH)}


def hacs_status_dict() -> dict:
    if not HACS_INSTALL_PATH.exists():
        return {"installed": False, "path": str(HACS_INSTALL_PATH)}
    manifest = HACS_INSTALL_PATH / "manifest.json"
    ver = "unknown"
    if manifest.exists():
        try:
            ver = json.loads(manifest.read_text(encoding="utf-8")).get("version", "unknown")
        except Exception:
            pass
    return {"installed": True, "version": ver, "path": str(HACS_INSTALL_PATH)}


def hacs_list_repositories_storage(category: str | None = None) -> dict:
    path = Path("/config/.storage/hacs.repositories")
    if not path.exists():
        return {"repositories": [], "count": 0, "note": "HACS storage file missing; open HACS in UI first."}
    data = json.loads(path.read_text(encoding="utf-8"))
    inner = data.get("data") or {}
    if not isinstance(inner, dict):
        inner = {}
    out = []
    for repo_id, repo_info in inner.items():
        if not isinstance(repo_info, dict):
            continue
        cat = repo_info.get("category", "")
        if category and cat != category:
            continue
        fn = repo_info.get("full_name", "")
        name = repo_info.get("name") or (fn.split("/")[-1] if "/" in fn else fn)
        out.append(
            {
                "repository_id": str(repo_id),
                "full_name": fn,
                "name": name,
                "category": cat,
                "installed": repo_info.get("installed", False)
                or repo_info.get("version_installed") is not None,
                "installed_version": repo_info.get("version_installed") or repo_info.get("installed_version"),
                "available_version": repo_info.get("available_version") or repo_info.get("version_available"),
            }
        )
    return {"repositories": out, "count": len(out), "category": category or "all"}
