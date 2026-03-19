# YAML import: reverse-engineer ESPHome YAML into Designer project (pages, widgets, bindings).
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

# Keys that are geometry (widget root), not props/style/events.
_GEOM_KEYS = frozenset({"id", "x", "y", "width", "height", "align"})
# ESPHome uses width/height; Designer uses w/h.
_GEOM_MAP = {"width": "w", "height": "h"}


def _schemas_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "schemas" / "widgets"


def _load_widget_schema(widget_type: str) -> dict | None:
    p = _schemas_dir() / f"{widget_type}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return None


def _yaml_key_to_designer(schema: dict) -> dict[str, tuple[str, str]]:
    """Build map: yaml_key -> (section, designer_key). Sections: props, style, events."""
    out: dict[str, tuple[str, str]] = {}
    esphome = schema.get("esphome") or {}
    for section in ("props", "style", "events"):
        mapping = esphome.get(section) or {}
        for designer_key, yaml_key in mapping.items():
            if isinstance(yaml_key, str):
                out[yaml_key] = (section, designer_key)
    return out


def _root_key_to_widget_type(root_key: str, body: dict) -> str:
    """Map ESPHome LVGL root_key (and optional body hints) to Designer widget type."""
    root_key = (root_key or "").strip().lower()
    if root_key == "obj":
        return "obj"
    if root_key in ("label", "button", "arc", "slider", "bar", "dropdown", "roller", "switch",
                    "checkbox", "container", "image", "line", "spinner", "textarea", "qrcode",
                    "led", "meter", "canvas", "animimg", "buttonmatrix", "keyboard", "tabview",
                    "tileview", "msgboxes"):
        return root_key
    # Button with color_picker / white_picker pattern
    if root_key == "button":
        styles = body.get("styles") or body.get("style")
        if isinstance(styles, str) and "etd_cp_" in styles:
            return "color_picker"
        if isinstance(styles, str) and "etd_wp_" in styles:
            return "white_picker"
    return root_key or "container"


def _parse_widget_from_block(block: dict, parent_id: str | None) -> dict | None:
    """Parse a single widget block from LVGL YAML. block is single-key dict e.g. {"label": {...}}."""
    if not block or not isinstance(block, dict) or len(block) != 1:
        return None
    root_key = next(iter(block.keys()))
    body = block[root_key]
    if not isinstance(body, dict):
        return None
    wtype = _root_key_to_widget_type(root_key, body)
    schema = _load_widget_schema(wtype)
    yaml_to_designer = _yaml_key_to_designer(schema) if schema else {}

    wid = body.get("id")
    if not wid and wtype != "container" and wtype != "obj":
        wid = f"gen_{root_key}_{id(block) & 0x7FFFFFFF}"
    widget: dict = {
        "type": wtype,
        "id": wid,
        "x": int(body.get("x", 0)) if body.get("x") is not None else 0,
        "y": int(body.get("y", 0)) if body.get("y") is not None else 0,
        "w": int(body.get("width", 100)) if body.get("width") is not None else 100,
        "h": int(body.get("height", 50)) if body.get("height") is not None else 50,
        "props": {},
        "style": {},
        "events": {},
    }
    if parent_id:
        widget["parent_id"] = parent_id

    for yaml_key, value in body.items():
        if yaml_key in _GEOM_KEYS:
            if yaml_key == "id":
                widget["id"] = value
            elif yaml_key == "x":
                widget["x"] = int(value) if value is not None else 0
            elif yaml_key == "y":
                widget["y"] = int(value) if value is not None else 0
            elif yaml_key == "width":
                widget["w"] = int(value) if value is not None else 100
            elif yaml_key == "height":
                widget["h"] = int(value) if value is not None else 50
            elif yaml_key == "align":
                widget.setdefault("props", {})["align"] = value
            continue
        if yaml_key == "widgets":
            continue
        section_key = yaml_to_designer.get(yaml_key)
        if section_key:
            section, designer_key = section_key
            if section == "props":
                widget["props"][designer_key] = value
            elif section == "style":
                widget["style"][designer_key] = value
            elif section == "events":
                if isinstance(value, dict) and "then" in value:
                    widget["events"][designer_key] = _emit_then_block(value)
                elif isinstance(value, str):
                    widget["events"][designer_key] = value
                else:
                    widget["events"][designer_key] = str(value) if value is not None else ""
        else:
            if yaml_key in ("bg_color", "text_color", "radius", "border_width", "border_color",
                            "text_font", "pad_all", "pad_top", "pad_bottom", "pad_left", "pad_right",
                            "bg_opa", "text", "value", "min_value", "max_value", "start_angle", "end_angle",
                            "arc_width", "adjustable", "indicator", "knob", "arc_color", "arc_rounded",
                            "state", "checkable", "long_mode", "recolor"):
                if yaml_key in ("bg_color", "text_color", "border_color", "radius", "border_width",
                                "text_font", "pad_all", "pad_top", "pad_bottom", "pad_left", "pad_right",
                                "bg_opa", "arc_width", "arc_color", "arc_rounded"):
                    widget["style"][yaml_key] = value
                elif yaml_key in ("text", "value", "min_value", "max_value", "start_angle", "end_angle",
                                  "adjustable", "state", "checkable", "long_mode", "recolor"):
                    widget["props"][yaml_key] = value
                elif yaml_key == "indicator" and isinstance(value, dict):
                    widget["style"]["indicator"] = value
                elif yaml_key == "knob" and isinstance(value, dict):
                    widget["style"]["knob"] = value
            elif yaml_key in ("on_click", "on_release", "on_value", "on_change", "on_press", "on_long_press", "on_short_click"):
                if isinstance(value, dict) and "then" in value:
                    widget["events"][yaml_key] = _emit_then_block(value)
                elif isinstance(value, str):
                    widget["events"][yaml_key] = value
                else:
                    widget["events"][yaml_key] = str(value) if value is not None else ""

    if not widget.get("id"):
        widget["id"] = f"gen_{wtype}_{id(block) & 0x7FFFFFFF}"

    children = body.get("widgets") or []
    if children:
        child_list = []
        for c in children:
            if isinstance(c, dict):
                child_w = _parse_widget_from_block(c, parent_id=str(widget.get("id") or ""))
                if child_w:
                    child_list.append(child_w)
        if child_list:
            widget["widgets"] = child_list
    return widget


def _flatten_widgets(widgets: list[dict]) -> list[dict]:
    """Flatten nested widgets into one list (Designer/compiler use parent_id)."""
    out: list[dict] = []
    for w in widgets:
        if not isinstance(w, dict):
            continue
        kids = w.pop("widgets", None) or []
        out.append(w)
        out.extend(_flatten_widgets(kids))
    return out


def _emit_then_block(then_dict: dict) -> str:
    """Convert then dict back to YAML string for event storage."""
    if not then_dict or "then" not in then_dict:
        return ""
    return yaml.safe_dump(then_dict, default_flow_style=False, allow_unicode=True, width=120).strip()


def parse_lvgl_section_to_pages(lvgl_section_str: str) -> list[dict]:
    """Parse lvgl section YAML string into list of pages with widgets (Designer format).
    lvgl_section_str can be the full 'lvgl:\\n  pages: ...' or just the body (content under lvgl:)."""
    if not (lvgl_section_str or "").strip():
        return [{"page_id": "main", "name": "Main", "widgets": []}]
    s = lvgl_section_str.strip()
    if not s.startswith("lvgl") and not s.startswith("pages"):
        s = "lvgl:\n" + lvgl_section_str
    try:
        data = yaml.safe_load(s)
    except Exception:
        return [{"page_id": "main", "name": "Main", "widgets": []}]
    if not isinstance(data, dict):
        return [{"page_id": "main", "name": "Main", "widgets": []}]
    lvgl_data = data.get("lvgl") or data
    if not isinstance(lvgl_data, dict):
        return [{"page_id": "main", "name": "Main", "widgets": []}]
    pages_data = lvgl_data.get("pages") or lvgl_data.get("page") or []
    if not isinstance(pages_data, list):
        pages_data = [pages_data] if pages_data else []
    out_pages: list[dict] = []
    for i, p in enumerate(pages_data):
        if not isinstance(p, dict):
            continue
        page_id = str(p.get("id") or p.get("page_id") or ("main" if i == 0 else f"page_{i}"))
        name = str(p.get("name") or page_id.replace("_", " ").title())
        widgets_data = p.get("widgets") or []
        root_widgets: list[dict] = []
        for w in widgets_data:
            if isinstance(w, dict):
                parsed = _parse_widget_from_block(w, parent_id=None)
                if parsed:
                    root_widgets.append(parsed)
        flat = _flatten_widgets(root_widgets)
        out_pages.append({
            "page_id": page_id,
            "name": name,
            "widgets": flat,
        })
    if not out_pages:
        return [{"page_id": "main", "name": "Main", "widgets": []}]
    return out_pages


def extract_lvgl_section_from_full_yaml(full_yaml: str) -> str:
    """Extract the lvgl: section body from full ESPHome YAML (by top-level key split)."""
    lines = full_yaml.splitlines()
    in_lvgl = False
    indent_lvgl = 0
    out: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if re.match(r"^lvgl\s*:", line):
            in_lvgl = True
            indent_lvgl = len(line) - len(stripped)
            continue
        if in_lvgl:
            if stripped and not line.startswith(" ") and not line.startswith("\t"):
                break
            if stripped and (len(line) - len(stripped)) <= indent_lvgl and re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*\s*:", stripped):
                break
            out.append(line)
    return "\n".join(out).strip()


def _parse_section_list(section_key: str, body: str) -> list[dict]:
    """Parse a section body (content under section_key:) into a list of block dicts."""
    if not (body or "").strip():
        return []
    # Normalize line endings so CRLF or stray \\r do not break parsing
    body = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    # Section body is indented; wrap so YAML parses as one key -> list.
    wrapped = section_key + ":\n" + body
    try:
        data = yaml.safe_load(wrapped)
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    items = data.get(section_key)
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)]


def _extract_lvgl_update_from_then(then_list: list) -> list[dict]:
    """From a 'then:' list (e.g. on_value.then or on_turn_on), extract lvgl.*.update blocks as dicts with id and the update payload."""
    out: list[dict] = []
    for item in then_list or []:
        if not isinstance(item, dict):
            continue
        for key, payload in item.items():
            if key in ("lvgl.label.update", "lvgl.arc.update", "lvgl.slider.update", "lvgl.bar.update", "lvgl.widget.update", "lvgl.switch.update"):
                if isinstance(payload, dict) and payload.get("id") is not None:
                    out.append({"kind": key, "id": payload.get("id"), "payload": payload})
                break
    return out


def _action_from_lvgl_update(update: dict) -> str:
    """Map lvgl update kind to link target action (label_text, arc_value, etc.)."""
    kind = (update.get("kind") or "").strip()
    if "label" in kind:
        return "label_text"
    if "arc" in kind:
        return "arc_value"
    if "slider" in kind:
        return "slider_value"
    if "bar" in kind:
        return "bar_value"
    if "switch" in kind:
        return "widget_checked"
    return "label_text"


def reverse_bindings_and_links(sections: dict[str, str], widget_ids: set[str]) -> tuple[list[dict], list[dict]]:
    """Reverse sensor/switch/climate/interval from YAML sections into project.bindings and project.links.
    widget_ids: set of widget ids from parsed pages (to avoid creating links to non-existent widgets).
    Returns (bindings, links).
    """
    bindings: list[dict] = []
    binding_keys: set[tuple[str, str, str]] = set()
    links: list[dict] = []

    def _add_ha_binding(entity_id: str, kind: str, attribute: str) -> None:
        key = (entity_id, kind, attribute)
        if key in binding_keys:
            return
        binding_keys.add(key)
        bindings.append({"entity_id": entity_id, "kind": kind, "attribute": attribute or ""})

    def _add_ha_link(entity_id: str, kind: str, attribute: str, widget_id: str, action: str, yaml_override: str | None = None, format_str: str | None = None) -> None:
        if widget_id not in widget_ids:
            return
        tgt: dict = {"widget_id": widget_id, "action": action}
        if yaml_override:
            tgt["yaml_override"] = yaml_override
        if format_str:
            tgt["format"] = format_str
        links.append({
            "source": {"entity_id": entity_id, "kind": kind, "attribute": attribute or ""},
            "target": tgt,
        })

    # --- HA sensor / text_sensor / binary_sensor -> widget links ---
    for sec_key in ("sensor", "text_sensor", "binary_sensor"):
        body = (sections.get(sec_key) or "").strip()
        if not body:
            continue
        blocks = _parse_section_list(sec_key, body)
        for blk in blocks:
            platform = str(blk.get("platform") or "").strip().lower()
            if platform != "homeassistant":
                continue
            entity_id = str(blk.get("entity_id") or "").strip()
            sid = str(blk.get("id") or "").strip()
            attribute = str(blk.get("attribute") or "").strip()
            if not entity_id or "." not in entity_id:
                continue
            if sec_key == "binary_sensor":
                kind = "binary"
            elif attribute:
                kind = "attribute_number" if attribute in ("state", "value") or "temperature" in attribute.lower() else "attribute_text"
            else:
                kind = "state"
            _add_ha_binding(entity_id, kind, attribute)
            # on_value or on_state
            for trigger in ("on_value", "on_state"):
                then_list = blk.get(trigger)
                if isinstance(then_list, dict) and "then" in then_list:
                    then_list = then_list.get("then") or []
                if not isinstance(then_list, list):
                    continue
                for upd in _extract_lvgl_update_from_then(then_list):
                    wid = str(upd.get("id") or "").strip()
                    action = _action_from_lvgl_update(upd)
                    payload = upd.get("payload") or {}
                    # Try to capture lambda/text as yaml_override for non-trivial formatting
                    yaml_override = None
                    if "text" in payload and payload.get("text") is not None:
                        try:
                            yaml_override = yaml.safe_dump([{upd.get("kind", "lvgl.label.update"): payload}], default_flow_style=False, allow_unicode=True).strip()
                        except Exception:
                            pass
                    _add_ha_link(entity_id, kind, attribute, wid, action, yaml_override=yaml_override)

    # --- Template switch -> widget (local_switch) ---
    switch_body = (sections.get("switch") or "").strip()
    if switch_body:
        switch_blocks = _parse_section_list("switch", switch_body)
        for blk in switch_blocks:
            platform = str(blk.get("platform") or "").strip().lower()
            if platform not in ("template", "output"):
                continue
            switch_id = str(blk.get("id") or "").strip()
            if not switch_id:
                continue
            for state, key in (("on", "on_turn_on"), ("off", "on_turn_off")):
                raw = blk.get(key)
                if isinstance(raw, dict) and "then" in raw:
                    then_list = raw["then"]
                elif isinstance(raw, list):
                    then_list = raw
                else:
                    continue
                for upd in _extract_lvgl_update_from_then(then_list):
                    wid = str(upd.get("id") or "").strip()
                    if wid not in widget_ids:
                        continue
                    payload = upd.get("payload") or {}
                    try:
                        yaml_override = yaml.safe_dump([{upd.get("kind", "lvgl.widget.update"): payload}], default_flow_style=False, allow_unicode=True).strip()
                    except Exception:
                        yaml_override = ""
                    links.append({
                        "source": {"type": "local_switch", "switch_id": switch_id, "state": state},
                        "target": {"widget_id": wid, "yaml_override": yaml_override},
                    })

    # --- Climate heat_action / idle_action / off_mode -> widget (local_climate) ---
    climate_body = (sections.get("climate") or "").strip()
    if climate_body:
        climate_blocks = _parse_section_list("climate", climate_body)
        for blk in climate_blocks:
            climate_id = str(blk.get("id") or "").strip()
            if not climate_id:
                continue
            for state, key in (("HEAT", "heat_action"), ("IDLE", "idle_action"), ("OFF", "off_mode")):
                raw = blk.get(key)
                if isinstance(raw, dict) and "then" in raw:
                    then_list = raw["then"]
                elif isinstance(raw, list):
                    then_list = raw
                else:
                    continue
                for upd in _extract_lvgl_update_from_then(then_list):
                    wid = str(upd.get("id") or "").strip()
                    if wid not in widget_ids:
                        continue
                    payload = upd.get("payload") or {}
                    try:
                        yaml_override = yaml.safe_dump([{upd.get("kind", "lvgl.widget.update"): payload}], default_flow_style=False, allow_unicode=True).strip()
                    except Exception:
                        yaml_override = ""
                    links.append({
                        "source": {"type": "local_climate", "climate_id": climate_id, "state": state},
                        "target": {"widget_id": wid, "yaml_override": yaml_override},
                    })

    # --- Interval -> widgets (interval links) ---
    interval_body = (sections.get("interval") or "").strip()
    if interval_body:
        # interval section can be list of blocks: - interval: 1s \n then: ...
        try:
            wrapped = "interval:\n" + interval_body
            data = yaml.safe_load(wrapped)
        except Exception:
            data = {}
        interval_blocks = data.get("interval") if isinstance(data, dict) else []
        if isinstance(interval_blocks, dict):
            interval_blocks = [interval_blocks]
        if not isinstance(interval_blocks, list):
            interval_blocks = []
        for blk in interval_blocks:
            if not isinstance(blk, dict):
                continue
            interval_sec = blk.get("interval")
            if interval_sec is None:
                continue
            # interval can be "1s" or 1
            if isinstance(interval_sec, (int, float)):
                sec = int(interval_sec)
            else:
                sec_str = str(interval_sec).strip().rstrip("s")
                try:
                    sec = int(float(sec_str))
                except ValueError:
                    sec = 1
            then_list = blk.get("then") or []
            updates: list[dict] = []
            for item in then_list or []:
                if not isinstance(item, dict):
                    continue
                for key, payload in item.items():
                    if key in ("lvgl.label.update", "lvgl.arc.update", "lvgl.slider.update", "lvgl.bar.update", "lvgl.widget.update"):
                        if isinstance(payload, dict) and payload.get("id") is not None:
                            wid = str(payload.get("id") or "").strip()
                            if wid in widget_ids:
                                # Store full update line as yaml_override so lambda is preserved
                                try:
                                    yaml_override = yaml.safe_dump([{key: payload}], default_flow_style=False, allow_unicode=True).strip()
                                except Exception:
                                    yaml_override = ""
                                updates.append({"widget_id": wid, "action": _action_from_lvgl_update({"kind": key, "payload": payload}), "yaml_override": yaml_override})
                    break
            if updates:
                links.append({
                    "source": {"type": "interval", "interval_seconds": sec, "updates": updates},
                    "target": {},
                })

    return (bindings, links)


def reverse_scripts(sections: dict[str, str]) -> list[dict]:
    """Parse script: section for known patterns (thermostat inc/dec) into project.scripts format.
    Returns list of { id, entity_id, step, direction } for matching scripts; others remain in sections."""
    scripts: list[dict] = []
    body = (sections.get("script") or "").strip()
    if not body:
        return scripts
    script_blocks = _parse_section_list("script", body)
    for blk in script_blocks:
        if not isinstance(blk, dict):
            continue
        sid = str(blk.get("id") or "").strip()
        then_list = blk.get("then") or []
        if not isinstance(then_list, list) or len(then_list) < 1:
            continue
        # Look for homeassistant.action with climate.set_temperature and lambda with id(ha_num_*_temperature).state +/- step
        entity_id = ""
        step = 0.5
        direction = "inc"
        for item in then_list:
            if not isinstance(item, dict):
                continue
            ha_action = item.get("homeassistant.action")
            if not isinstance(ha_action, dict):
                continue
            action = str(ha_action.get("action") or "").strip()
            if action != "climate.set_temperature":
                continue
            data = ha_action.get("data") or {}
            eid = (data.get("entity_id") or "").strip()
            if eid and "." in eid:
                entity_id = eid
            temp = data.get("temperature")
            if isinstance(temp, str):
                # Try to parse "return id(ha_num_xxx_temperature).state + 0.5f;" or " - 0.5f" (with or without !lambda in YAML)
                if "+" in temp:
                    direction = "inc"
                    m = re.search(r"\+\s*([\d.]+)f?", temp)
                    if m:
                        try:
                            step = float(m.group(1))
                        except ValueError:
                            pass
                elif "-" in temp:
                    direction = "dec"
                    m = re.search(r"-\s*([\d.]+)f?", temp)
                    if m:
                        try:
                            step = float(m.group(1))
                        except ValueError:
                            pass
            break
        if sid and entity_id:
            scripts.append({"id": sid, "entity_id": entity_id, "step": step, "direction": direction})
    return scripts
