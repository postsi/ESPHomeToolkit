"""
HAMCPTools — full MCP implementations for Home Assistant (native HA + Supervisor + /config).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

from app.config_fs import delete_config_file, list_config_dir, read_config_file, write_config_file
from app.ha_ws import call_service_ws, ha_ws_call
from app.hamcp_automation_script import delete_automation_full, delete_script_full
from app.hamcp_git import (
    create_checkpoint,
    end_checkpoint,
    git_commit,
    git_diff,
    git_history,
    git_pending,
    git_rollback,
)
from app.hamcp_hacs import (
    hacs_install,
    hacs_list_repositories_storage,
    hacs_status_dict,
    hacs_uninstall,
)

from app.tool_engines import (
    execute_ha_rest,
    execute_ha_rest_json,
    execute_ha_service,
    execute_supervisor_api_data,
    execute_supervisor_raw_text,
    execute_supervisor_rest,
)

log = logging.getLogger("esphome_api.hamcp_tools_impl")


def _comma_entity_filter(val: Any) -> str:
    """Comma-separated entity ids for history/logbook query params."""
    if val is None:
        return ""
    if isinstance(val, list):
        parts = [str(x).strip() for x in val if str(x).strip()]
        return ",".join(parts)
    return str(val).strip()


HELPER_FILES: dict[str, str] = {
    "input_boolean": "input_boolean.yaml",
    "input_text": "input_text.yaml",
    "input_number": "input_number.yaml",
    "input_datetime": "input_datetime.yaml",
    "input_select": "input_select.yaml",
    "group": "groups.yaml",
    "utility_meter": "utility_meter.yaml",
}


def _j(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


async def _ws_remove_entity(entity_id: str) -> None:
    await ha_ws_call({"type": "config/entity_registry/remove", "entity_id": entity_id})


async def _resolve_automation_config_id(automation_id: str) -> str:
    aid = automation_id.removeprefix("automation.") if automation_id.startswith("automation.") else automation_id
    try:
        cfg = await execute_ha_rest_json("GET", f"/api/config/automation/config/{aid}")
        if isinstance(cfg, dict) and cfg.get("id"):
            return str(cfg["id"])
    except Exception:
        pass
    try:
        reg = await ha_ws_call({"type": "config/entity_registry/list"})
        target = f"automation.{aid}"
        for ent in reg:
            if ent.get("entity_id") == target:
                caps = ent.get("capabilities") or {}
                cid = caps.get("id")
                if cid:
                    return str(cid)
                uid = ent.get("unique_id")
                if uid:
                    return str(uid)
    except Exception:
        pass
    return aid


async def _list_automations_dict(ids_only: bool) -> dict:
    reg = await ha_ws_call({"type": "config/entity_registry/list"})
    autos = [e for e in reg if (e.get("entity_id") or "").startswith("automation.")]
    if ids_only:
        ids: list[str] = []
        for e in autos:
            caps = e.get("capabilities") or {}
            slug = e["entity_id"].split(".", 1)[1]
            cid = caps.get("id") or slug
            ids.append(str(cid))
        return {"success": True, "count": len(ids), "automation_ids": ids}
    out: list[Any] = []
    for e in autos:
        caps = e.get("capabilities") or {}
        slug = e["entity_id"].split(".", 1)[1]
        cid = caps.get("id") or slug
        try:
            cfg = await execute_ha_rest_json("GET", f"/api/config/automation/config/{cid}")
            out.append(cfg)
        except Exception:
            out.append({"id": cid, "entity_id": e.get("entity_id"), "error": "get_config_failed"})
    return {"success": True, "count": len(out), "automations": out}


async def _list_scripts_dict(ids_only: bool) -> dict:
    reg = await ha_ws_call({"type": "config/entity_registry/list"})
    scripts_ent = [e for e in reg if (e.get("entity_id") or "").startswith("script.")]
    ids: list[str] = []
    for e in scripts_ent:
        caps = e.get("capabilities") or {}
        slug = e["entity_id"].split(".", 1)[1]
        sid = caps.get("id") or slug
        ids.append(str(sid))
    if ids_only:
        return {"success": True, "count": len(ids), "script_ids": ids}
    out: dict[str, Any] = {}
    for sid in ids:
        try:
            cfg = await execute_ha_rest_json("GET", f"/api/config/script/config/{sid}")
            out[sid] = cfg
        except Exception:
            out[sid] = {"error": "get_config_failed"}
    return {"success": True, "count": len(out), "scripts": out}


def _parse_script_create_payload(args: dict) -> tuple[str, dict]:
    cfg = dict(args.get("config") or {})
    cfg.pop("commit_message", None)
    if "entity_id" in cfg:
        sid = str(cfg.pop("entity_id"))
        return sid, cfg
    if len(cfg) != 1:
        raise ValueError("config must be one script key or include entity_id")
    sid = list(cfg.keys())[0]
    return sid, cfg[sid]


async def dispatch_hamcp_full(tool_name: str, payload: dict[str, Any] | None) -> str:
    a = dict(payload or {})
    try:
        return await _dispatch(tool_name, a)
    except Exception as e:
        log.exception("HAMCP tool %s failed", tool_name)
        return _j({"success": False, "error": str(e)})


async def _dispatch(tool_name: str, a: dict[str, Any]) -> str:
    # ——— Entities / services ———
    if tool_name == "ha_call_service":
        domain = (a.get("domain") or "").strip()
        service = (a.get("service") or "").strip()
        if not domain or not service:
            return _j({"success": False, "error": "domain and service required"})
        res = await execute_ha_service(
            domain,
            service,
            a.get("service_data") if isinstance(a.get("service_data"), dict) else None,
            a.get("target") if isinstance(a.get("target"), dict) else None,
        )
        return res

    if tool_name == "ha_list_entities":
        states = await execute_ha_rest_json("GET", "/api/states")
        if not isinstance(states, list):
            return _j(states)
        domain = (a.get("domain") or "").strip()
        search = (a.get("search") or "").strip().lower()
        area_id = (a.get("area_id") or "").strip()
        filtered = states
        if domain:
            filtered = [s for s in filtered if (s.get("entity_id") or "").startswith(f"{domain}.")]
        if search:
            filtered = [
                s
                for s in filtered
                if search in (s.get("entity_id") or "").lower()
                or search in json.dumps(s.get("attributes") or {}).lower()
            ]
        if area_id:
            try:
                reg = await ha_ws_call({"type": "config/entity_registry/list"})
                allowed = {e.get("entity_id") for e in reg if e.get("area_id") == area_id}
                filtered = [s for s in filtered if s.get("entity_id") in allowed]
            except Exception:
                pass
        page = int(a.get("page") or 1)
        page_size = min(int(a.get("page_size") or 5000), 10000)
        start = (page - 1) * page_size
        chunk = filtered[start : start + page_size]
        if a.get("summary_only"):
            chunk = [
                {"entity_id": s.get("entity_id"), "state": s.get("state")} for s in chunk
            ]
        if a.get("ids_only"):
            chunk = [s.get("entity_id") for s in chunk]
        return _j(
            {
                "success": True,
                "count": len(chunk),
                "total": len(filtered),
                "entities": chunk,
            }
        )

    if tool_name == "ha_get_entity_state":
        eid = (a.get("entity_id") or "").strip()
        if not eid:
            return _j({"success": False, "error": "entity_id required"})
        data = await execute_ha_rest_json("GET", f"/api/states/{quote(eid, safe='')}")
        return _j({"success": True, **data} if isinstance(data, dict) else data)

    if tool_name == "ha_rename_entity":
        old = (a.get("old_entity_id") or "").strip()
        new = (a.get("new_entity_id") or "").strip()
        if not old or not new:
            return _j({"success": False, "error": "old_entity_id and new_entity_id required"})
        res = await ha_ws_call(
            {"type": "config/entity_registry/update", "entity_id": old, "new_entity_id": new}
        )
        return _j({"success": True, "result": res})

    # ——— Registry ———
    if tool_name == "ha_get_entity_registry":
        reg = await ha_ws_call({"type": "config/entity_registry/list"})
        return _j({"success": True, "entities": reg, "count": len(reg)})

    if tool_name == "ha_get_entity_registry_entry":
        eid = (a.get("entity_id") or "").strip()
        res = await ha_ws_call({"type": "config/entity_registry/get", "entity_id": eid})
        return _j({"success": True, "entity": res})

    if tool_name == "ha_update_entity_registry":
        eid = (a.get("entity_id") or "").strip()
        body = {k: v for k, v in a.items() if k != "entity_id"}
        res = await ha_ws_call({"type": "config/entity_registry/update", "entity_id": eid, **body})
        return _j({"success": True, "result": res})

    if tool_name == "ha_remove_entity_registry_entry":
        eid = (a.get("entity_id") or "").strip()
        await _ws_remove_entity(eid)
        return _j({"success": True, "removed": eid})

    if tool_name == "ha_find_dead_entities":
        states = await execute_ha_rest_json("GET", "/api/states")
        dead = []
        for s in states if isinstance(states, list) else []:
            st = s.get("state")
            attr = s.get("attributes") or {}
            if st in ("unavailable", "unknown", None) or attr.get("restored"):
                dead.append(
                    {
                        "entity_id": s.get("entity_id"),
                        "state": st,
                        "restored": attr.get("restored", False),
                    }
                )
        return _j({"success": True, "count": len(dead), "dead_entities": dead})

    if tool_name == "ha_get_area_registry":
        reg = await ha_ws_call({"type": "config/area_registry/list"})
        return _j({"success": True, "areas": reg})

    if tool_name == "ha_get_area_registry_entry":
        aid = (a.get("area_id") or "").strip()
        if not aid:
            return _j({"success": False, "error": "area_id required"})
        # HA Core has no stable WS "get" for areas on all versions — resolve from list.
        reg = await ha_ws_call({"type": "config/area_registry/list"})
        for ar in reg if isinstance(reg, list) else []:
            if isinstance(ar, dict) and ar.get("area_id") == aid:
                return _j({"success": True, "area": ar})
        return _j({"success": False, "error": f"area not found: {aid}"})

    if tool_name == "ha_create_area":
        msg = {"type": "config/area_registry/create", "name": a.get("name") or ""}
        if a.get("aliases"):
            msg["aliases"] = a["aliases"]
        res = await ha_ws_call(msg)
        return _j({"success": True, "result": res})

    if tool_name == "ha_update_area":
        msg: dict[str, Any] = {"type": "config/area_registry/update", "area_id": a.get("area_id") or ""}
        if a.get("name") is not None:
            msg["name"] = a["name"]
        if a.get("aliases") is not None:
            msg["aliases"] = a["aliases"]
        res = await ha_ws_call(msg)
        return _j({"success": True, "result": res})

    if tool_name == "ha_delete_area":
        aid = (a.get("area_id") or "").strip()
        res = await ha_ws_call({"type": "config/area_registry/delete", "area_id": aid})
        return _j({"success": True, "result": res})

    if tool_name == "ha_get_device_registry":
        reg = await ha_ws_call({"type": "config/device_registry/list"})
        return _j({"success": True, "devices": reg})

    if tool_name == "ha_get_device_registry_entry":
        did = (a.get("device_id") or "").strip()
        if not did:
            return _j({"success": False, "error": "device_id required"})
        reg = await ha_ws_call({"type": "config/device_registry/list"})
        device: dict[str, Any] | None = None
        for dev in reg if isinstance(reg, list) else []:
            if isinstance(dev, dict) and dev.get("id") == did:
                device = dev
                break
        if not device:
            return _j({"success": False, "error": f"device not found: {did}"})
        out: dict[str, Any] = {"success": True, "device": device}
        if a.get("include_entities"):
            ereg = await ha_ws_call({"type": "config/entity_registry/list"})
            out["entities"] = [e for e in ereg if isinstance(e, dict) and e.get("device_id") == did]
        return _j(out)

    if tool_name == "ha_update_device_registry":
        did = (a.get("device_id") or "").strip()
        body = {k: v for k, v in a.items() if k != "device_id"}
        res = await ha_ws_call({"type": "config/device_registry/update", "device_id": did, **body})
        return _j({"success": True, "result": res})

    if tool_name == "ha_remove_device_registry_entry":
        did = (a.get("device_id") or "").strip()
        res = await ha_ws_call({"type": "config/device_registry/remove", "device_id": did})
        return _j({"success": True, "result": res})

    # ——— Automations ———
    if tool_name == "ha_list_automations":
        return _j(await _list_automations_dict(bool(a.get("ids_only"))))

    if tool_name == "ha_get_automation":
        aid = (a.get("automation_id") or "").strip()
        rid = await _resolve_automation_config_id(aid)
        cfg = await execute_ha_rest_json("GET", f"/api/config/automation/config/{rid}")
        return _j({"success": True, "automation_id": aid, "config": cfg})

    if tool_name == "ha_create_automation":
        cfg = dict(a.get("config") or {})
        cfg.pop("commit_message", None)
        aid = cfg.get("id")
        if not aid:
            return _j({"success": False, "error": "config.id required"})
        if str(aid).startswith("automation."):
            cfg["id"] = str(aid).removeprefix("automation.")
        created = await execute_ha_rest_json(
            "POST", f"/api/config/automation/config/{cfg['id']}", cfg
        )
        return _j({"success": True, "data": created})

    if tool_name == "ha_update_automation":
        aid = (a.get("automation_id") or "").strip()
        cfg = dict(a.get("config") or {})
        cfg.pop("commit_message", None)
        rid = await _resolve_automation_config_id(aid)
        cfg["id"] = rid
        updated = await execute_ha_rest_json("POST", f"/api/config/automation/config/{rid}", cfg)
        return _j({"success": True, "data": updated})

    if tool_name == "ha_delete_automation":
        aid = (a.get("automation_id") or "").strip()
        res = await delete_automation_full(aid, _ws_remove_entity, lambda: call_service_ws("automation", "reload"))
        return _j(res)

    # ——— Scripts ———
    if tool_name == "ha_list_scripts":
        return _j(await _list_scripts_dict(bool(a.get("ids_only"))))

    if tool_name == "ha_get_script":
        sid = (a.get("script_id") or "").strip().removeprefix("script.")
        cfg = await execute_ha_rest_json("GET", f"/api/config/script/config/{sid}")
        return _j({"success": True, "script_id": sid, "config": cfg})

    if tool_name == "ha_create_script":
        sid, body = _parse_script_create_payload(a)
        await execute_ha_rest_json("POST", f"/api/config/script/config/{sid}", body)
        return _j({"success": True, "message": f"Script created: {sid}"})

    if tool_name == "ha_update_script":
        sid = (a.get("script_id") or "").strip().removeprefix("script.")
        cfg = dict(a.get("config") or {})
        cfg.pop("commit_message", None)
        await execute_ha_rest_json("POST", f"/api/config/script/config/{sid}", cfg)
        return _j({"success": True, "message": f"Script updated: {sid}"})

    if tool_name == "ha_delete_script":
        sid = (a.get("script_id") or "").strip().removeprefix("script.")
        res = await delete_script_full(sid, _ws_remove_entity, lambda: call_service_ws("script", "reload"))
        return _j(res)

    # ——— Helpers (YAML) ———
    if tool_name == "ha_list_helpers":
        states = await execute_ha_rest_json("GET", "/api/states")
        doms = (
            "input_boolean",
            "input_text",
            "input_number",
            "input_datetime",
            "input_select",
            "group",
            "utility_meter",
        )
        helpers = [
            s
            for s in (states or [])
            if isinstance(s, dict) and any((s.get("entity_id") or "").startswith(f"{d}.") for d in doms)
        ]
        return _j({"success": True, "count": len(helpers), "helpers": helpers})

    if tool_name == "ha_create_helper":
        htype = (a.get("type") or "").strip()
        cfg = dict(a.get("config") or {})
        if htype not in HELPER_FILES:
            return _j({"success": False, "error": f"unsupported type {htype}"})
        if "name" not in cfg:
            return _j({"success": False, "error": "config.name required"})
        fname = HELPER_FILES[htype]
        rel = fname
        try:
            raw = read_config_file(rel)
            data = yaml.safe_load(raw) or {}
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        name = cfg["name"]
        base = name.lower().replace(" ", "_").replace("-", "_")
        base = "".join(c for c in base if c.isalnum() or c == "_")
        hid = base
        n = 1
        while hid in data:
            hid = f"{base}_{n}"
            n += 1
        rest = {k: v for k, v in cfg.items()}
        data[hid] = rest
        write_config_file(rel, yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False))
        cfg_path = Path("/config/configuration.yaml")
        if cfg_path.exists():
            cur = cfg_path.read_text(encoding="utf-8")
        else:
            cur = ""
        inc = f"{htype}: !include {fname}"
        if inc not in cur:
            with cfg_path.open("a", encoding="utf-8") as f:
                f.write(f"\n{inc}\n")
        await call_service_ws(htype, "reload", {})
        return _j({"success": True, "entity_id": f"{htype}.{hid}", "data": data[hid]})

    if tool_name == "ha_delete_helper":
        eid = (a.get("entity_id") or "").strip()
        if "." not in eid:
            return _j({"success": False, "error": "entity_id required"})
        domain, hid = eid.split(".", 1)
        if domain not in HELPER_FILES:
            return _j({"success": False, "error": f"unsupported domain {domain}"})
        fname = HELPER_FILES[domain]
        try:
            data = yaml.safe_load(read_config_file(fname)) or {}
            if hid in data:
                del data[hid]
                write_config_file(fname, yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False))
                await call_service_ws(domain, "reload", {})
        except Exception:
            pass
        try:
            await _ws_remove_entity(eid)
        except Exception:
            pass
        return _j({"success": True, "message": f"Removed {eid} (best effort)"})

    # ——— System ———
    if tool_name == "ha_check_config":
        data = await execute_ha_rest_json("POST", "/api/config/core/check_config")
        errs = data.get("errors") or [] if isinstance(data, dict) else []
        return _j(
            {
                "success": len(errs) == 0,
                "message": "Configuration is valid" if not errs else "Configuration invalid",
                "data": data,
            }
        )

    if tool_name == "ha_reload_config":
        comp = (a.get("component") or "all").strip().lower()
        if comp == "automations":
            await call_service_ws("automation", "reload")
        elif comp == "scripts":
            await call_service_ws("script", "reload")
        elif comp == "templates" or comp == "template":
            await call_service_ws("template", "reload", {})
        elif comp == "themes":
            await call_service_ws("frontend", "reload_themes", {})
        else:
            await call_service_ws("homeassistant", "reload_core_config", {})
        return _j({"success": True, "reloaded": comp})

    if tool_name == "ha_restart":
        await call_service_ws("homeassistant", "restart", {})
        return _j({"success": True, "message": "Restart initiated"})

    if tool_name == "ha_get_logs":
        limit = max(1, int(a.get("limit") or 100))
        try:
            entries = await ha_ws_call({"type": "system_log/list"}, timeout=60.0)
            if isinstance(entries, list) and entries:
                tail = entries[-limit:]
                lines: list[str] = []
                for e in tail:
                    if isinstance(e, dict):
                        msg_parts = e.get("message") or []
                        line = f"{e.get('timestamp')} {e.get('level')} {e.get('name')}: {' | '.join(str(m) for m in msg_parts)}"
                        lines.append(line)
                    else:
                        lines.append(str(e))
                return _j(
                    {
                        "success": True,
                        "source": "system_log",
                        "count": len(tail),
                        "entries": tail,
                        "lines": lines,
                    }
                )
        except Exception as e_ws:
            ws_err = str(e_ws)
        else:
            ws_err = ""
        raw = await execute_ha_rest("GET", "/api/error_log")
        if "Body: " in raw:
            body = raw.split("Body: ", 1)[-1].strip()
        else:
            body = raw
        lines_out = body.splitlines()
        if not lines_out or (len(lines_out) == 1 and "404" in lines_out[0]):
            return _j(
                {
                    "success": False,
                    "error": ws_err or "error_log empty or unavailable",
                    "lines": [],
                    "count": 0,
                }
            )
        return _j(
            {
                "success": True,
                "source": "error_log",
                "lines": lines_out[-limit:],
                "count": min(len(lines_out), limit),
            }
        )

    if tool_name == "ha_logbook_entries":
        end = a.get("end_time")
        start = a.get("start_time") or datetime.now(timezone.utc).isoformat()
        path = f"/api/logbook/{quote(str(start), safe='')}"
        qs: list[str] = []
        if end:
            qs.append(f"end_time={quote(str(end), safe='')}")
        ent = _comma_entity_filter(a.get("entity_ids") or a.get("entity_id"))
        if ent:
            qs.append(f"entity={quote(ent, safe='')}")
        if a.get("period") is not None:
            qs.append(f"period={int(a['period'])}")
        if a.get("context_id"):
            qs.append(f"context_id={quote(str(a['context_id']), safe='')}")
        if qs:
            path += "?" + "&".join(qs)
        data = await execute_ha_rest_json("GET", path)
        return _j({"success": True, "entries": data})

    if tool_name == "ha_get_logbook_events":
        st = (a.get("start_time") or "").strip()
        if not st:
            return _j({"success": False, "error": "start_time required (ISO 8601)"})
        msg: dict[str, Any] = {"type": "logbook/get_events", "start_time": st}
        et = a.get("end_time")
        if et:
            msg["end_time"] = str(et).strip()
        eids = a.get("entity_ids")
        if isinstance(eids, list) and eids:
            msg["entity_ids"] = [str(x).strip() for x in eids if str(x).strip()]
        elif a.get("entity_id"):
            msg["entity_ids"] = [str(a["entity_id"]).strip()]
        dids = a.get("device_ids")
        if isinstance(dids, list) and dids:
            msg["device_ids"] = [str(x).strip() for x in dids if str(x).strip()]
        if a.get("context_id"):
            msg["context_id"] = str(a["context_id"]).strip()
        try:
            events = await ha_ws_call(msg, timeout=180.0)
        except Exception as e:
            return _j({"success": False, "error": str(e)})
        return _j({"success": True, "events": events})

    if tool_name == "ha_get_history":
        feid = _comma_entity_filter(a.get("filter_entity_id") or a.get("entity_ids") or a.get("entity_id"))
        if not feid:
            return _j(
                {
                    "success": False,
                    "error": "filter_entity_id, entity_id, or entity_ids required (recorder state history)",
                }
            )
        qs: list[str] = [f"filter_entity_id={quote(feid, safe='')}"]
        end = (a.get("end_time") or "").strip()
        if end:
            qs.append(f"end_time={quote(end, safe='')}")
        if a.get("significant_changes_only") is False:
            qs.append("significant_changes_only=0")
        if a.get("minimal_response"):
            qs.append("minimal_response")
        if a.get("no_attributes"):
            qs.append("no_attributes")
        if a.get("skip_initial_state"):
            qs.append("skip_initial_state")
        qstr = "&".join(qs)
        start = (a.get("start_time") or "").strip()
        if start:
            path = f"/api/history/period/{quote(start, safe='')}?{qstr}"
        else:
            path = f"/api/history/period?{qstr}"
        try:
            data = await execute_ha_rest_json("GET", path)
        except Exception as e:
            return _j({"success": False, "error": str(e)})
        return _j({"success": True, "history": data})

    if tool_name == "ha_list_recorder_statistic_ids":
        msg: dict[str, Any] = {"type": "recorder/list_statistic_ids"}
        st = a.get("statistic_type")
        if st in ("mean", "sum"):
            msg["statistic_type"] = st
        try:
            res = await ha_ws_call(msg, timeout=180.0)
        except Exception as e:
            return _j({"success": False, "error": str(e)})
        return _j({"success": True, "statistic_ids": res})

    if tool_name == "ha_get_recorder_statistics_metadata":
        msg: dict[str, Any] = {"type": "recorder/get_statistics_metadata"}
        ids = a.get("statistic_ids")
        if isinstance(ids, list) and ids:
            msg["statistic_ids"] = [str(x).strip() for x in ids if str(x).strip()]
        try:
            res = await ha_ws_call(msg, timeout=180.0)
        except Exception as e:
            return _j({"success": False, "error": str(e)})
        return _j({"success": True, "metadata": res})

    if tool_name == "ha_get_recorder_statistics":
        ids = a.get("statistic_ids")
        if not isinstance(ids, list) or not ids:
            return _j({"success": False, "error": "statistic_ids (non-empty list) required"})
        st = (a.get("start_time") or "").strip()
        if not st:
            return _j({"success": False, "error": "start_time required (ISO 8601)"})
        period = (a.get("period") or "hour").strip()
        if period not in ("5minute", "hour", "day", "week", "month", "year"):
            return _j(
                {
                    "success": False,
                    "error": "period must be one of: 5minute, hour, day, week, month, year",
                }
            )
        msg: dict[str, Any] = {
            "type": "recorder/statistics_during_period",
            "start_time": st,
            "statistic_ids": [str(x).strip() for x in ids if str(x).strip()],
            "period": period,
        }
        et = (a.get("end_time") or "").strip()
        if et:
            msg["end_time"] = et
        types = a.get("types")
        if isinstance(types, list) and types:
            msg["types"] = types
        units = a.get("units")
        if isinstance(units, dict) and units:
            msg["units"] = units
        try:
            res = await ha_ws_call(msg, timeout=300.0)
        except Exception as e:
            return _j({"success": False, "error": str(e)})
        return _j({"success": True, "data": res})

    if tool_name == "ha_get_recorder_statistic":
        sid = (a.get("statistic_id") or "").strip()
        if not sid:
            return _j({"success": False, "error": "statistic_id required"})
        msg: dict[str, Any] = {"type": "recorder/statistic_during_period", "statistic_id": sid}
        if a.get("start_time"):
            msg["start_time"] = str(a["start_time"]).strip()
        if a.get("end_time"):
            msg["end_time"] = str(a["end_time"]).strip()
        dur = a.get("duration")
        if isinstance(dur, dict):
            msg["duration"] = dur
        off = a.get("offset")
        if isinstance(off, dict):
            msg["offset"] = off
        types = a.get("types")
        if isinstance(types, list) and types:
            msg["types"] = types
        units = a.get("units")
        if isinstance(units, dict) and units:
            msg["units"] = units
        try:
            res = await ha_ws_call(msg, timeout=180.0)
        except Exception as e:
            return _j({"success": False, "error": str(e)})
        return _j({"success": True, "statistic_id": sid, "data": res})

    if tool_name == "ha_validate_recorder_statistics":
        try:
            issues = await ha_ws_call({"type": "recorder/validate_statistics"}, timeout=180.0)
        except Exception as e:
            return _j({"success": False, "error": str(e)})
        return _j({"success": True, "issues": issues})

    # ——— Files ———
    if tool_name == "ha_read_file":
        path = (a.get("path") or "").strip()
        content = read_config_file(path)
        return _j({"success": True, "path": path, "content": content, "size": len(content)})

    if tool_name == "ha_list_files":
        directory = (a.get("directory") or "").strip().strip("/")
        pat = (a.get("pattern") or "*.yaml").strip()
        files = list_config_dir(directory, pat)
        return _j({"success": True, "count": len(files), "files": files})

    if tool_name == "ha_write_file":
        path = (a.get("path") or "").strip()
        content = a.get("content")
        if content is None:
            return _j({"success": False, "error": "content required"})
        if not isinstance(content, str):
            content = str(content)
        write_config_file(path, content)
        if a.get("commit_message"):
            git_commit(str(a["commit_message"]))
        return _j({"success": True, "message": f"Written {path}"})

    if tool_name == "ha_delete_file":
        path = (a.get("path") or "").strip()
        delete_config_file(path)
        return _j({"success": True, "message": f"Deleted {path}"})

    # ——— Git / backup ———
    if tool_name == "ha_git_commit":
        return _j(git_commit(a.get("message")))
    if tool_name == "ha_git_pending":
        return _j(git_pending())
    if tool_name == "ha_git_history":
        return _j(git_history(int(a.get("limit") or 20)))
    if tool_name == "ha_git_diff":
        return _j(git_diff(a.get("commit1"), a.get("commit2")))
    if tool_name == "ha_git_rollback":
        return _j(git_rollback((a.get("commit_hash") or "").strip()))
    if tool_name == "ha_create_checkpoint":
        return _j(create_checkpoint((a.get("user_request") or "").strip() or "checkpoint"))
    if tool_name == "ha_end_checkpoint":
        return _j(end_checkpoint())

    # ——— Add-ons (Supervisor) ———
    if tool_name == "ha_list_store_addons":
        return await execute_supervisor_rest("GET", "/store/addons")
    if tool_name == "ha_list_addons":
        return await execute_supervisor_rest("GET", "/store/addons")
    if tool_name == "ha_list_installed_addons":
        return await execute_supervisor_rest("GET", "/addons")
    if tool_name == "ha_addon_info":
        slug = (a.get("slug") or "").strip()
        return await execute_supervisor_rest("GET", f"/addons/{slug}/info")
    if tool_name == "ha_addon_logs":
        slug = (a.get("slug") or "").strip()
        if not slug:
            return _j({"success": False, "error": "slug required"})
        lines = a.get("lines")
        enc = quote(slug, safe="")
        paths = (
            f"/addons/{enc}/logs/latest",
            f"/addons/{enc}/logs",
            f"/addons/{enc}/log",
        )
        text = ""
        last_err = ""
        for path in paths:
            try:
                text = await execute_supervisor_raw_text("GET", path, timeout=120.0)
                break
            except Exception as e:
                last_err = str(e)
                continue
        else:
            return _j({"success": False, "error": f"Could not fetch logs: {last_err}"})
        if lines:
            try:
                n = max(1, int(lines))
                text = "\n".join(text.splitlines()[-n:])
            except (TypeError, ValueError):
                pass
        return _j({"success": True, "slug": slug, "log": text})
    if tool_name == "ha_install_addon":
        slug = (a.get("slug") or "").strip()
        return await execute_supervisor_rest("POST", f"/addons/{slug}/install", None, timeout=600.0)
    if tool_name == "ha_uninstall_addon":
        slug = (a.get("slug") or "").strip()
        return await execute_supervisor_rest("POST", f"/addons/{slug}/uninstall")
    if tool_name == "ha_start_addon":
        slug = (a.get("slug") or "").strip()
        return await execute_supervisor_rest("POST", f"/addons/{slug}/start")
    if tool_name == "ha_stop_addon":
        slug = (a.get("slug") or "").strip()
        return await execute_supervisor_rest("POST", f"/addons/{slug}/stop")
    if tool_name == "ha_restart_addon":
        slug = (a.get("slug") or "").strip()
        return await execute_supervisor_rest("POST", f"/addons/{slug}/restart")
    if tool_name == "ha_update_addon":
        slug = (a.get("slug") or "").strip()
        if not slug:
            return _j({"success": False, "error": "slug required"})
        # Supervisor blocks POST /addons/{slug}/update when the caller IS that add-on
        # ("Add-on … can't update itself!"). Core's hassio.addon_update runs outside that
        # request context and succeeds for self-update.
        self_slug = ""
        try:
            self_info = await execute_supervisor_api_data("GET", "/addons/self/info")
            if isinstance(self_info, dict):
                self_slug = str(self_info.get("slug") or "").strip()
        except Exception:
            pass
        if self_slug and slug == self_slug:
            return await execute_ha_service(
                "hassio",
                "addon_update",
                {"addon": slug},
                timeout=600.0,
            )
        return await execute_supervisor_rest("POST", f"/addons/{slug}/update", None, timeout=600.0)
    if tool_name == "ha_get_addon_options":
        slug = (a.get("slug") or "").strip()
        if not slug:
            return _j({"success": False, "error": "slug required"})
        # Supervisor exposes options on GET /addons/{slug}/info (no GET /options).
        try:
            info = await execute_supervisor_api_data("GET", f"/addons/{quote(slug, safe='')}/info")
        except Exception as e:
            return _j({"success": False, "error": str(e)})
        if not isinstance(info, dict):
            return _j({"success": False, "error": "unexpected info payload"})
        return _j({"success": True, "slug": slug, "options": info.get("options")})
    if tool_name == "ha_set_addon_options":
        slug = (a.get("slug") or "").strip()
        opts = a.get("options")
        if not isinstance(opts, dict):
            return _j({"success": False, "error": "options object required"})
        return await execute_supervisor_rest("POST", f"/addons/{slug}/options", {"options": opts})
    if tool_name == "ha_addon_stats":
        slug = (a.get("slug") or "").strip()
        if not slug:
            return _j({"success": False, "error": "slug required"})
        try:
            stats = await execute_supervisor_api_data("GET", f"/addons/{quote(slug, safe='')}/stats")
        except Exception as e:
            return _j({"success": False, "error": str(e)})
        return _j({"success": True, "slug": slug, "stats": stats})

    if tool_name == "ha_list_repositories":
        return await execute_supervisor_rest("GET", "/store/repositories")
    if tool_name == "ha_add_repository":
        repo = (a.get("repository") or a.get("repository_url") or "").strip()
        return await execute_supervisor_rest("POST", "/store/repositories", {"repository": repo})

    # ——— HACS ———
    if tool_name == "ha_install_hacs":
        return _j(await hacs_install())
    if tool_name == "ha_uninstall_hacs":
        return _j(await hacs_uninstall())
    if tool_name == "ha_hacs_status":
        return _j({"success": True, **hacs_status_dict()})
    if tool_name == "ha_hacs_list_repositories":
        return _j({"success": True, **hacs_list_repositories_storage(a.get("category"))})
    if tool_name == "ha_hacs_install_repository":
        repo = (a.get("repository") or "").strip()
        _ = a.get("category")
        res = await call_service_ws("hacs", "download", {"repository": repo})
        return _j({"success": True, "websocket_result": res})
    if tool_name == "ha_hacs_search":
        q = (a.get("query") or "").lower()
        cat = a.get("category")
        states = await execute_ha_rest_json("GET", "/api/states")
        matches = []
        for s in states or []:
            if not isinstance(s, dict):
                continue
            eid = s.get("entity_id") or ""
            if not eid.startswith("sensor.hacs_"):
                continue
            attr = s.get("attributes") or {}
            if cat and attr.get("category") != cat:
                continue
            blob = json.dumps(attr).lower()
            if q in blob or q in eid.lower():
                matches.append({"entity_id": eid, "attributes": attr})
        return _j({"success": True, "count": len(matches), "repositories": matches})

    if tool_name == "ha_hacs_update_all":
        res = await call_service_ws("hacs", "update_all", {})
        return _j({"success": True, "websocket_result": res})

    if tool_name == "ha_hacs_repository_details":
        rid = str(a.get("repository_id") or "")
        states = await execute_ha_rest_json("GET", "/api/states")
        for s in states or []:
            if rid in (s.get("entity_id") or "") or rid in json.dumps(s.get("attributes") or {}):
                return _j({"success": True, "state": s})
        repos = hacs_list_repositories_storage(None).get("repositories") or []
        for r in repos:
            if rid in (r.get("repository_id") or "") or rid in (r.get("full_name") or ""):
                return _j({"success": True, "repository": r})
        return _j({"success": False, "error": f"No details for {rid}"})

    # ——— Lovelace / themes ———
    if tool_name == "ha_analyze_entities_for_dashboard":
        states = await execute_ha_rest_json("GET", "/api/states")
        by_domain: dict[str, int] = {}
        for s in states or []:
            eid = s.get("entity_id") or "unknown"
            dom = eid.split(".", 1)[0] if "." in eid else "unknown"
            by_domain[dom] = by_domain.get(dom, 0) + 1
        return _j({"success": True, "domains": dict(sorted(by_domain.items(), key=lambda x: -x[1]))})

    if tool_name == "ha_preview_dashboard":
        # Try YAML mode dashboard
        for candidate in ("ui-lovelace.yaml", "dashboards/default.yaml"):
            try:
                txt = read_config_file(candidate)
                return _j({"success": True, "source": candidate, "yaml": txt[:8000]})
            except Exception:
                continue
        return _j({"success": False, "error": "No ui-lovelace.yaml found; UI-mode dashboards live in .storage"})

    if tool_name == "ha_apply_dashboard":
        dash = a.get("dashboard_config")
        filename = (a.get("filename") or "ai-dashboard.yaml").strip()
        if isinstance(dash, dict):
            body = yaml.dump(dash, allow_unicode=True, default_flow_style=False, sort_keys=False)
        else:
            body = str(dash or "")
        path = filename if not filename.startswith("www/") else filename
        if not path.endswith((".yaml", ".yml")):
            path += ".yaml"
        write_config_file(path, body, validate_yaml_if_applicable=False)
        return _j({"success": True, "message": f"Wrote {path}; add to Lovelace resources if needed"})

    if tool_name == "ha_delete_dashboard":
        fn = (a.get("filename") or "").strip()
        delete_config_file(fn)
        return _j({"success": True, "message": f"Deleted {fn}"})

    if tool_name == "ha_list_themes":
        themes_dir = Path("/config/themes")
        if not themes_dir.is_dir():
            return _j({"success": True, "themes": []})
        return _j({"success": True, "themes": [p.name for p in themes_dir.glob("*.yaml")]})

    if tool_name == "ha_get_theme":
        name = (a.get("theme_name") or "").strip()
        path = f"themes/{name}.yaml"
        try:
            return _j({"success": True, "theme_name": name, "content": read_config_file(path)})
        except Exception as e:
            return _j({"success": False, "error": str(e)})

    if tool_name == "ha_create_theme":
        name = (a.get("theme_name") or "").strip()
        tcfg = a.get("theme_config")
        body = yaml.dump(tcfg, allow_unicode=True) if isinstance(tcfg, dict) else str(tcfg or "")
        Path("/config/themes").mkdir(parents=True, exist_ok=True)
        tpath = f"themes/{name}.yaml"
        write_config_file(tpath, body, validate_yaml_if_applicable=False)
        return _j({"success": True, "path": tpath})

    if tool_name == "ha_update_theme":
        name = (a.get("theme_name") or "").strip()
        tcfg = a.get("theme_config")
        body = yaml.dump(tcfg, allow_unicode=True) if isinstance(tcfg, dict) else str(tcfg or "")
        write_config_file(f"themes/{name}.yaml", body, validate_yaml_if_applicable=False)
        return _j({"success": True, "message": f"Updated theme {name}"})

    if tool_name == "ha_delete_theme":
        name = (a.get("theme_name") or "").strip()
        delete_config_file(f"themes/{name}.yaml")
        return _j({"success": True, "message": f"Deleted theme {name}"})

    if tool_name == "ha_reload_themes":
        await call_service_ws("frontend", "reload_themes", {})
        return _j({"success": True})

    if tool_name == "ha_check_theme_config":
        themes_dir = Path("/config/themes")
        errors = []
        if themes_dir.is_dir():
            for p in themes_dir.glob("*.yaml"):
                try:
                    yaml.safe_load(p.read_text(encoding="utf-8"))
                except Exception as e:
                    errors.append({"file": str(p.name), "error": str(e)})
        return _j({"success": len(errors) == 0, "errors": errors})

    return _j({"success": False, "error": f"unknown tool {tool_name}"})
