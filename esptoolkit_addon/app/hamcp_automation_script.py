"""
Automation/script locate-and-delete (file + .storage) — ported from Vibecode ha_client patterns.
Uses /config via config_fs and HA REST/WS from callers for get/reload/remove.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Awaitable

import yaml

from app.config_fs import CONFIG_ROOT, ConfigFsError, read_config_file, write_config_file

log = logging.getLogger("esphome_api.hamcp_automation_script")


def _matches_automation(auto: dict, target_id: str) -> bool:
    auto_id = auto.get("id")
    if auto_id == target_id:
        return True
    entity_id = auto.get("entity_id", "")
    if entity_id:
        clean = entity_id.replace("automation.", "", 1) if entity_id.startswith("automation.") else entity_id
        if clean == target_id or entity_id == target_id:
            return True
    return False


def find_automation_location(automation_id: str) -> dict | None:
    """Return location dict or None."""
    # automations.yaml
    try:
        content = read_config_file("automations.yaml")
        automations = yaml.safe_load(content) or []
        if isinstance(automations, list):
            for i, auto in enumerate(automations):
                if isinstance(auto, dict) and _matches_automation(auto, automation_id):
                    return {"location": "automations.yaml", "file_path": "automations.yaml", "index": i}
    except (ConfigFsError, FileNotFoundError, OSError):
        pass
    except Exception as e:
        log.debug("find automation automations.yaml: %s", e)

    # packages
    pkg_dir = CONFIG_ROOT / "packages"
    if pkg_dir.exists():
        for yaml_file in pkg_dir.rglob("*.yaml"):
            try:
                content = yaml_file.read_text(encoding="utf-8")
                data = yaml.safe_load(content) or {}
                if not isinstance(data, dict) or "automation" not in data:
                    continue
                pkg = data["automation"]
                rel = str(yaml_file.relative_to(CONFIG_ROOT))
                if isinstance(pkg, list):
                    for i, auto in enumerate(pkg):
                        if isinstance(auto, dict) and _matches_automation(auto, automation_id):
                            return {
                                "location": "packages",
                                "file_path": rel,
                                "index": i,
                                "format": "list",
                            }
                elif isinstance(pkg, dict):
                    if automation_id in pkg:
                        return {
                            "location": "packages",
                            "file_path": rel,
                            "key": automation_id,
                            "format": "dict",
                        }
                    for key, auto in pkg.items():
                        if isinstance(auto, dict) and _matches_automation(auto, automation_id):
                            return {
                                "location": "packages",
                                "file_path": rel,
                                "key": key,
                                "format": "dict",
                            }
            except Exception:
                continue

    # automations/
    auto_dir = CONFIG_ROOT / "automations"
    if auto_dir.exists() and auto_dir.is_dir():
        for yaml_file in auto_dir.rglob("*.yaml"):
            try:
                content = yaml_file.read_text(encoding="utf-8")
                data = yaml.safe_load(content) or []
                if not isinstance(data, list):
                    continue
                rel = str(yaml_file.relative_to(CONFIG_ROOT))
                for i, auto in enumerate(data):
                    if isinstance(auto, dict) and _matches_automation(auto, automation_id):
                        return {
                            "location": "automations_dir",
                            "file_path": rel,
                            "index": i,
                            "format": "list",
                        }
            except Exception:
                continue

    # .storage/automation.storage
    storage_file = CONFIG_ROOT / ".storage" / "automation.storage"
    if storage_file.exists():
        try:
            storage_data = json.loads(storage_file.read_text(encoding="utf-8"))
            if "data" in storage_data and "automations" in storage_data["data"]:
                for i, auto in enumerate(storage_data["data"]["automations"]):
                    if isinstance(auto, dict) and _matches_automation(auto, automation_id):
                        return {
                            "location": "storage",
                            "file_path": ".storage/automation.storage",
                            "index": i,
                        }
        except Exception as e:
            log.debug("automation.storage: %s", e)
    return None


def _apply_automation_deletion(location: dict, automation_id: str) -> None:
    fp = location["file_path"]
    if location["location"] == "automations.yaml":
        content = read_config_file(fp)
        automations = yaml.safe_load(content) or []
        automations = [a for a in automations if not (isinstance(a, dict) and _matches_automation(a, automation_id))]
        write_config_file(fp, yaml.dump(automations, allow_unicode=True, default_flow_style=False, sort_keys=False))
    elif location["location"] == "packages":
        content = read_config_file(fp)
        data = yaml.safe_load(content) or {}
        pkg = data.get("automation")
        if location["format"] == "list" and isinstance(pkg, list):
            data["automation"] = [a for a in pkg if not (isinstance(a, dict) and _matches_automation(a, automation_id))]
        elif location["format"] == "dict" and isinstance(pkg, dict):
            k = location.get("key")
            if k and k in pkg:
                del pkg[k]
            else:
                for key, val in list(pkg.items()):
                    if isinstance(val, dict) and _matches_automation(val, automation_id):
                        del pkg[key]
                        break
        write_config_file(fp, yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False))
    elif location["location"] == "storage":
        content = read_config_file(fp)
        storage_data = json.loads(content)
        storage_data["data"]["automations"] = [
            a
            for a in storage_data["data"]["automations"]
            if not (isinstance(a, dict) and _matches_automation(a, automation_id))
        ]
        write_config_file(fp, json.dumps(storage_data, indent=2, ensure_ascii=False), validate_yaml_if_applicable=False)
    elif location["location"] == "automations_dir":
        content = read_config_file(fp)
        automations = yaml.safe_load(content) or []
        automations = [a for a in automations if not (isinstance(a, dict) and _matches_automation(a, automation_id))]
        write_config_file(fp, yaml.dump(automations, allow_unicode=True, default_flow_style=False, sort_keys=False))


def _matches_script(script_key: str, script_config: Any, target_id: str) -> bool:
    if script_key == target_id:
        return True
    if isinstance(script_config, dict):
        eid = script_config.get("entity_id", "")
        if eid:
            clean = eid.replace("script.", "", 1) if eid.startswith("script.") else eid
            if clean == target_id or eid == target_id:
                return True
    return False


def find_script_location(script_id: str) -> dict | None:
    try:
        content = read_config_file("scripts.yaml")
        scripts = yaml.safe_load(content) or {}
        if isinstance(scripts, dict):
            for key, cfg in scripts.items():
                if _matches_script(key, cfg, script_id):
                    return {"location": "scripts.yaml", "file_path": "scripts.yaml", "key": key}
    except (ConfigFsError, OSError):
        pass
    pkg_dir = CONFIG_ROOT / "packages"
    if pkg_dir.exists():
        for yaml_file in pkg_dir.rglob("*.yaml"):
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
                if not isinstance(data, dict) or "script" not in data:
                    continue
                pkg = data["script"]
                rel = str(yaml_file.relative_to(CONFIG_ROOT))
                if isinstance(pkg, dict):
                    for key, cfg in pkg.items():
                        if _matches_script(key, cfg, script_id):
                            return {"location": "packages", "file_path": rel, "key": key}
            except Exception:
                continue
    storage_file = CONFIG_ROOT / ".storage" / "script.storage"
    if storage_file.exists():
        try:
            storage_data = json.loads(storage_file.read_text(encoding="utf-8"))
            scripts = storage_data.get("data", {}).get("scripts", {})
            if script_id in scripts:
                return {"location": "storage", "file_path": ".storage/script.storage", "key": script_id}
        except Exception:
            pass
    scripts_sub = CONFIG_ROOT / "scripts"
    if scripts_sub.exists():
        for yaml_file in scripts_sub.rglob("*.yaml"):
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
                if not isinstance(data, dict):
                    continue
                rel = str(yaml_file.relative_to(CONFIG_ROOT))
                if script_id in data:
                    return {"location": "scripts_dir", "file_path": rel, "key": script_id}
            except Exception:
                continue
    return None


def _apply_script_deletion(location: dict, script_id: str) -> None:
    fp = location["file_path"]
    if location["location"] == "scripts.yaml":
        content = read_config_file(fp)
        scripts = yaml.safe_load(content) or {}
        if script_id in scripts:
            del scripts[script_id]
        write_config_file(fp, yaml.dump(scripts, allow_unicode=True, default_flow_style=False, sort_keys=False))
    elif location["location"] == "packages":
        content = read_config_file(fp)
        data = yaml.safe_load(content) or {}
        k = location.get("key")
        if "script" in data and isinstance(data["script"], dict) and k in data["script"]:
            del data["script"][k]
        write_config_file(fp, yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False))
    elif location["location"] == "storage":
        content = read_config_file(fp)
        storage_data = json.loads(content)
        if script_id in storage_data.get("data", {}).get("scripts", {}):
            del storage_data["data"]["scripts"][script_id]
        write_config_file(fp, json.dumps(storage_data, indent=2, ensure_ascii=False), validate_yaml_if_applicable=False)
    elif location["location"] == "scripts_dir":
        content = read_config_file(fp)
        data = yaml.safe_load(content) or {}
        if script_id in data:
            del data[script_id]
        write_config_file(fp, yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False))


async def delete_automation_full(
    automation_id: str,
    remove_registry: Callable[[str], Awaitable[Any]],
    reload_automations: Callable[[], Awaitable[Any]],
) -> dict:
    aid = automation_id.removeprefix("automation.") if automation_id.startswith("automation.") else automation_id
    loc = find_automation_location(aid)
    if not loc:
        # ghost registry cleanup
        from app.ha_ws import ha_ws_call

        reg = await ha_ws_call({"type": "config/entity_registry/list"})
        removed = []
        norm = aid.lower().replace(" ", "_").replace("-", "_")
        for ent in reg:
            eid = ent.get("entity_id", "")
            if not eid.startswith("automation."):
                continue
            name = (ent.get("name") or "").lower().replace(" ", "_").replace("-", "_")
            if eid == f"automation.{aid}" or eid.replace("automation.", "", 1) == aid or (
                name and (norm == name or norm in name or name in norm)
            ):
                try:
                    await remove_registry(eid)
                    removed.append(eid)
                except Exception:
                    pass
        if removed:
            await reload_automations()
            return {"success": True, "automation_id": aid, "removed_entities": removed}
        return {"success": False, "error": f"Automation '{aid}' not found"}

    _apply_automation_deletion(loc, aid)
    primary = f"automation.{aid}"
    try:
        await remove_registry(primary)
    except Exception:
        pass
    await reload_automations()
    return {"success": True, "automation_id": aid, "location": loc}


async def delete_script_full(
    script_id: str,
    remove_registry: Callable[[str], Awaitable[Any]],
    reload_scripts: Callable[[], Awaitable[Any]],
) -> dict:
    sid = script_id.removeprefix("script.") if script_id.startswith("script.") else script_id
    loc = find_script_location(sid)
    if not loc:
        return {"success": False, "error": f"Script '{sid}' not found"}
    _apply_script_deletion(loc, sid)
    try:
        await remove_registry(f"script.{sid}")
    except Exception:
        pass
    await reload_scripts()
    return {"success": True, "script_id": sid, "location": loc}
