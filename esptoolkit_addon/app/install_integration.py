"""
Install or update the bundled custom integration into HA config.
Copies from /app/custom_components/esptoolkit to /config/custom_components/esptoolkit.
Adds esptoolkit to configuration.yaml so HA loads the integration at startup (required for
async_setup to run and create the config entry from the add-on config file).
Writes a small config file (URL + token) so the integration can auto-create its config entry.
If any file was updated, triggers a Home Assistant core restart so the integration loads.
"""
import filecmp
import re
import json
import logging
import os
import shutil
import sys
from pathlib import Path

import httpx

# Ensure install logs appear in add-on log (stdout) when run from run.sh before main starts
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )

SOURCE_DIR = Path("/app/custom_components/esptoolkit")
TARGET_DIR = Path("/config/custom_components/esptoolkit")
INTEGRATION_CONFIG_FILE = Path("/config/.esptoolkit_addon_config.json")
CORE_CONFIG_ENTRIES_PATH = Path("/config/.storage/core.config_entries")
CONFIGURATION_YAML = Path("/config/configuration.yaml")
MANIFEST = "manifest.json"
INTEGRATION_DOMAIN = "esptoolkit"

log = logging.getLogger("esptoolkit.install")


def _get_version(manifest_path: Path) -> str | None:
    """Read version from manifest.json if present."""
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text())
        return data.get("version")
    except Exception:
        return None


def _dir_is_newer_or_missing() -> bool:
    """
    Return True if we should copy (source is newer or target missing).
    Compare manifest version; if target missing or source version different, copy.
    """
    if not SOURCE_DIR.is_dir():
        log.warning("Bundled integration not found at %s", SOURCE_DIR)
        return False
    source_manifest = SOURCE_DIR / MANIFEST
    source_version = _get_version(source_manifest)
    if not source_version:
        log.warning("No version in bundled manifest at %s", source_manifest)
        return False
    if not TARGET_DIR.is_dir():
        log.info("Integration not installed yet; will copy (version %s)", source_version)
        return True
    target_manifest = TARGET_DIR / MANIFEST
    target_version = _get_version(target_manifest)
    if target_version != source_version:
        log.info(
            "Integration version change %s -> %s; will copy",
            target_version or "none",
            source_version,
        )
        return True
    # Same version: check if any key file differs (e.g. hotfix without version bump)
    key_files = ("__init__.py", "const.py", "manifest.json", "services.yaml", "panel.py", "storage.py")
    for name in key_files:
        src = SOURCE_DIR / name
        dst = TARGET_DIR / name
        if src.is_file() and (not dst.is_file() or not filecmp.cmp(src, dst, shallow=False)):
            log.info("File %s changed; will copy", name)
            return True
    log.info("Integration already up to date (version %s); no copy needed", source_version)
    return False


def _copy_tree() -> None:
    """Copy source dir into target, overwriting existing files."""
    log.info("Copying integration from %s to %s...", SOURCE_DIR, TARGET_DIR)
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in SOURCE_DIR.rglob("*"):
        if path.is_file():
            rel = path.relative_to(SOURCE_DIR)
            dest = TARGET_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            log.info("  Copied %s", rel)
            count += 1
    log.info("Copied %d files to %s", count, TARGET_DIR)


def _get_host_hostname() -> str | None:
    """Ask Supervisor for the host's hostname so the integration can reach this add-on."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        log.info("SUPERVISOR_TOKEN not set; cannot query Supervisor for hostname")
        return None
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(
                "http://supervisor/host/info",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            data = r.json()
            hostname = (data.get("data", {}).get("hostname") or data.get("hostname") or "").strip() or None
            if hostname:
                log.info("Got host hostname from Supervisor: %s", hostname)
            else:
                log.info("Supervisor host/info returned no hostname; will use fallback")
            return hostname
    except Exception as e:
        log.info("Could not get host hostname from Supervisor (%s); will use fallback", e)
        return None


def _write_integration_config() -> tuple[str, str] | None:
    """Write base_url and token to a file the integration reads. Returns (base_url, token) or None."""
    log.info("Writing integration config file for auto-setup...")
    try:
        from app.config import load_options
    except ImportError:
        log.warning("Could not import load_options; skipping integration config file")
        return None
    opts = load_options()
    token = (opts.get("api_token") or "").strip()
    port = int(opts.get("port") or 8098)
    if not token:
        log.info("No api_token configured; skipping integration config file")
        return None
    hostname = _get_host_hostname() or "homeassistant.local"
    if hostname == "homeassistant.local":
        log.info("Using fallback hostname: homeassistant.local (Supervisor hostname not available)")
    base_url = f"http://{hostname}:{port}"
    payload = {"base_url": base_url, "token": token}
    INTEGRATION_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    INTEGRATION_CONFIG_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info("Wrote integration config to %s (base_url=%s, token=***)", INTEGRATION_CONFIG_FILE, base_url)
    return (base_url, token)


def _patch_integration_config_entry(base_url: str, token: str) -> bool:
    """Update the esptoolkit config entry in core.config_entries. Returns True if we patched and need HA restart."""
    storage_path = CORE_CONFIG_ENTRIES_PATH
    if not storage_path.is_file():
        log.info("No core.config_entries file; nothing to patch")
        return False
    try:
        data = json.loads(storage_path.read_text(encoding="utf-8"))
        entries = (data.get("data") or {}).get("entries") or []
        base_url_clean = base_url.rstrip("/")
        for ent in entries:
            if ent.get("domain") != INTEGRATION_DOMAIN:
                continue
            d = ent.get("data") or {}
            cur_url = (d.get("base_url") or "").strip().rstrip("/")
            cur_tok = (d.get("token") or "").strip()
            if cur_url == base_url_clean and cur_tok == token:
                log.info("Integration config entry already matches; no patch needed")
                return False
            log.info(
                "Patching integration config entry: base_url %s -> %s, token (updated)",
                cur_url or "(empty)", base_url_clean,
            )
            ent["data"] = {**d, "base_url": base_url_clean, "token": token}
            storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            log.info("Integration config entry patched; HA restart needed to load new config")
            return True
        log.info("No %s config entry in storage; nothing to patch", INTEGRATION_DOMAIN)
        return False
    except Exception as e:
        log.warning("Could not patch config entries (%s)", e)
        return False


def _integration_entry_mismatch(base_url: str, token: str) -> bool:
    """Return True if the integration's config entry differs from add-on config."""
    storage_path = CORE_CONFIG_ENTRIES_PATH
    if not storage_path.is_file():
        return False
    try:
        data = json.loads(storage_path.read_text(encoding="utf-8"))
        entries = (data.get("data") or {}).get("entries") or []
        base_url_clean = base_url.rstrip("/")
        for ent in entries:
            if ent.get("domain") == INTEGRATION_DOMAIN:
                d = ent.get("data") or {}
                cur_url = (d.get("base_url") or "").strip().rstrip("/")
                cur_tok = (d.get("token") or "").strip()
                if cur_url != base_url_clean or cur_tok != token:
                    return True
                return False
        return False
    except Exception:
        return False


def _restart_home_assistant() -> bool:
    """Call Supervisor API to restart Home Assistant core. Return True if restart was triggered."""
    log.info("Triggering Home Assistant core restart via Supervisor API...")
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        log.warning("SUPERVISOR_TOKEN not set; cannot restart Home Assistant")
        log.warning(">>> Restart Home Assistant manually (Settings → System → Restart) so the Designer panel loads.")
        return False
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                "http://supervisor/core/restart",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
        log.info("Home Assistant core restart triggered successfully")
        return True
    except Exception as e:
        log.warning("Failed to trigger Home Assistant restart: %s", e)
        log.warning(">>> Restart Home Assistant manually (Settings → System → Restart) so the new integration and Designer panel load.")
        return False


def _ensure_integration_loaded_via_config() -> bool:
    """Ensure esptoolkit is in configuration.yaml so HA loads the integration at startup. Returns True if we modified."""
    if not CONFIGURATION_YAML.is_file():
        log.info("configuration.yaml not found at %s; cannot add %s", CONFIGURATION_YAML, INTEGRATION_DOMAIN)
        return False
    try:
        content = CONFIGURATION_YAML.read_text(encoding="utf-8")
    except Exception as e:
        log.warning("Could not read configuration.yaml: %s", e)
        return False
    if re.search(r"^\s*esptoolkit\s*:", content, re.MULTILINE):
        log.info("%s already in configuration.yaml; integration will load at startup", INTEGRATION_DOMAIN)
        return False
    addition = "\n# ESPToolkit add-on integration (auto-added so services and Designer load)\nesptoolkit:\n"
    try:
        CONFIGURATION_YAML.write_text(content.rstrip() + addition, encoding="utf-8")
        log.info("Added %s to configuration.yaml so integration loads at startup", INTEGRATION_DOMAIN)
        return True
    except Exception as e:
        log.warning("Could not write configuration.yaml: %s", e)
        return False


def install_or_update() -> bool:
    """
    Copy bundled integration to config if missing or newer; restart HA if we updated.
    Always write the integration config file (URL + token). If the integration's config entry
    no longer matches, patch and restart HA.
    Return True if we copied (and may have triggered restart).
    """
    log.info("=== ESPToolkit integration install/update started ===")
    written = _write_integration_config()
    if written:
        log.info("Integration config file written; checking if integration files need update...")
    else:
        log.info("Integration config file not written (no token); skipping config entry sync")
    updated = _dir_is_newer_or_missing()
    if updated:
        log.info("Integration files need update (missing or newer); copying...")
        _copy_tree()
    config_yaml_updated = False
    if written:
        config_yaml_updated = _ensure_integration_loaded_via_config()
    if updated or config_yaml_updated:
        restarted = _restart_home_assistant()
        changes = []
        if updated:
            changes.append("copied integration")
        if config_yaml_updated:
            changes.append("added esptoolkit to configuration.yaml")
        if restarted:
            log.info("=== Integration install/update complete: %s, restarted HA ===", ", ".join(changes))
        else:
            log.info("=== Integration install/update complete: %s. Restart HA manually (Settings → System → Restart) to load the Designer. ===", ", ".join(changes))
        return True
    if written:
        mismatch = _integration_entry_mismatch(written[0], written[1])
        if mismatch:
            _patch_integration_config_entry(written[0], written[1])
            log.info("Integration config entry out of sync; restarting HA")
            restarted = _restart_home_assistant()
            if restarted:
                log.info("=== Integration install/update complete: restarted HA for config sync ===")
            else:
                log.info("=== Integration install/update complete: config synced. Restart HA manually to apply. ===")
        else:
            log.info("=== Integration install/update complete: no changes needed ===")
    else:
        log.info("=== Integration install/update complete: no config file written ===")
    return False
