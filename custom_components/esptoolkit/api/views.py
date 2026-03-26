from __future__ import annotations

import asyncio
import colorsys
import json
import tempfile
from pathlib import Path


# --- v0.5: hardware recipes + LVGL YAML compiler ---
import base64
import math
import os
import re
import secrets

from . import yaml_import as _yaml_import

RECIPES_BUILTIN_DIR = Path(__file__).resolve().parent.parent / "recipes" / "builtin"

# Placeholder in hardware recipes for the device name; compiler replaces with device slug (YAML-quoted).
ETD_DEVICE_NAME_PLACEHOLDER = "__ETD_DEVICE_NAME__"


def _substitute_device_name_in_sections(sections_dict: dict, device_slug: str) -> None:
    """Replace __ETD_DEVICE_NAME__ with the device slug (YAML-quoted) in section content. Mutates in place."""
    if not sections_dict or not device_slug:
        return
    repl = json.dumps(device_slug)
    for key, content in list(sections_dict.items()):
        if content and ETD_DEVICE_NAME_PLACEHOLDER in content:
            sections_dict[key] = content.replace(ETD_DEVICE_NAME_PLACEHOLDER, repl)


# Section-based compile: canonical order and categories (same package as views.py's parent).
try:
    from ..esphome_sections import SECTION_ORDER, SECTION_CATEGORIES
except ImportError:
    SECTION_ORDER = ()
    SECTION_CATEGORIES = {}


def _integration_version() -> str:
    """Best-effort integration version (from manifest.json). Cached at import to avoid blocking the event loop."""
    return _integration_version_cached


def _load_integration_version() -> str:
    try:
        manifest_path = Path(__file__).resolve().parent.parent / "manifest.json"
        data = json.loads(manifest_path.read_text("utf-8"))
        return str(data.get("version") or "0.0.0")
    except Exception:
        return "0.0.0"


_integration_version_cached = "0.0.0"
_integration_version_loaded = False


async def _async_integration_version(hass: HomeAssistant) -> str:
    """Load manifest version in executor to avoid blocking the event loop."""
    global _integration_version_cached, _integration_version_loaded
    if not _integration_version_loaded:
        _integration_version_cached = await hass.async_add_executor_job(_load_integration_version)
        _integration_version_loaded = True
    return _integration_version_cached


def list_builtin_recipes() -> list[dict]:
    label_map = {
        "sunton_2432s028r_320x240": 'Sunton ESP32-2432S028R (2.8" 320x240)',
        "elecrow_dis05035h_480x320": 'Elecrow CrowPanel DIS05035H (3.5" 480x320)',
        "guition_jc3248w535_480x320": 'Guition JC3248W535 (3.5" 480x320)',
        "sunton_8048s043_800x480": 'Sunton ESP32-8048S043 (4.3" 800x480)',
        "elecrow_7inch_800x480": "Elecrow 7.0\\\" HMI 800x480",
        "guition_jc4827w543_480x272": "Guition jc4827w543 4.3\\\" IPS 480x272",
        "guition_jc8048w535_320x480": "Guition jc8048w535 3.5\\\" IPS 480x320 (320x480)",
        "guition_jc8048w550_800x480": "Guition JC8048W550 5.0\\\" 800x480",
        "guition_s3_4848s040_480x480": "Guition jc4848s040 4.0\\\" IPS 480x480",
        "jc1060p470_esp32p4_1024x600": "JC1060P470 7\\\" 1024x600 (ESP32-P4)",
        "lilygo_tdisplays3_170x320": "LilyGo T-Display S3 170x320",
        "sunton_2432s028_240x320": "Sunton 2432s028 2.8\\\" 240x320",
        "sunton_2432s028r_240x320": "Sunton 2432s028R 2.8\\\" 240x320 (Resistive)",
        "sunton_4827s032r_480x280": "Sunton 4827s032R 4.3\\\" 480x272 (Resistive) (480x280)",
        "sunton_8048s050_800x480": "Sunton 8048s050 5.0\\\" 800x480",
        "sunton_8048s070_800x480": "Sunton 8048s070 7.0\\\" 800x480",
        "waveshare_s3_touch_lcd_4.3_800x480": "Waveshare Touch LCD 4.3 4.3\\\" 800x480",
        "waveshare_s3_touch_lcd_7_800x480": "Waveshare Touch LCD 7 7.0\\\" 800x480",
        "waveshare_universal_epaper_7.5v2_800x480": "Waveshare Universal e-Paper Raw Panel Driver Board (800x480)",
    }
    out: list[dict] = []
    if not RECIPES_BUILTIN_DIR.exists():
        return out
    for p in sorted(RECIPES_BUILTIN_DIR.glob("*.yaml")):
        rid = p.stem
        out.append({"id": rid, "name": label_map.get(rid, rid.replace("_", " ")), "kind": "builtin", "path": str(p)})
    return out


# --- Section-based compile: recipe parser and YAML section splitter ---

# Top-level YAML key: line start, then key name (word chars + underscores), then colon.
_TOP_LEVEL_KEY_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:(?:\s*(?:#.*)?)?$")


def _section_full_block(key: str, body: str) -> str:
    """Form full section block for storage/display: 'key:\\n' + body (user sees header + correct indent). Preserve body leading indent."""
    return key + ":\n" + (body or "").rstrip()


def _section_body_from_value(value: str | None, key: str) -> str:
    """Extract body from stored value. If value is full block (starts with 'key:'), return lines after first (indent preserved); else return value (legacy body-only)."""
    if not value or not value.strip():
        return ""
    s = value.strip()
    if s.startswith(key + ":") or s.startswith(key + " :"):
        lines = s.splitlines()
        if len(lines) <= 1:
            return ""
        return "\n".join(lines[1:]).rstrip()
    return value


def _normalize_section_body_indent(body: str) -> str:
    """Ensure section body has at least 2-space base indent (for merging user addition into a section).
    Only add indent to lines that have fewer than 2 leading spaces, so nested lines (e.g. 4-space
    'name:' under a list item) are not over-indented (which would produce invalid YAML)."""
    if not body or not body.strip():
        return body
    lines = body.splitlines()
    if not lines:
        return body
    result = []
    for ln in lines:
        if not ln.strip():
            result.append(ln)
            continue
        leading = len(ln) - len(ln.lstrip())
        result.append(("  " + ln) if leading < 2 else ln)
    return "\n".join(result)


# Section keys that can contain `widget:` references (LVGL platform components). Used for orphan cleanup and compile warnings.
SECTION_KEYS_WITH_WIDGET_REF: tuple[str, ...] = (
    "switch",
    "light",
    "sensor",
    "number",
    "select",
    "text_sensor",
    "binary_sensor",
)

_WIDGET_REF_RE = re.compile(r"widget:\s*[\"']?([a-zA-Z0-9_]+)[\"']?")


def _collect_widget_ids_from_project(project: dict) -> set[str]:
    """Recursively collect all widget ids from project.pages[].widgets (including nested widgets)."""
    ids: set[str] = set()
    pages = project.get("pages") or []
    if not isinstance(pages, list):
        return ids

    def collect(widgets: list) -> None:
        for w in widgets or []:
            if isinstance(w, dict) and w.get("id"):
                ids.add(str(w["id"]).strip())
            if isinstance(w, dict):
                collect(w.get("widgets") or [])

    for p in pages:
        if isinstance(p, dict):
            collect(p.get("widgets") or [])
    return ids


def _iter_all_widgets(project: dict):
    """Yield every widget dict from project.pages[].widgets (flat and nested)."""
    pages = project.get("pages") or []
    if not isinstance(pages, list):
        return

    def visit(widgets: list):
        for w in widgets or []:
            if isinstance(w, dict):
                yield w
                yield from visit(w.get("widgets") or [])

    for p in pages:
        if isinstance(p, dict):
            yield from visit(p.get("widgets") or [])


def _get_screensaver_config(project: dict) -> tuple[bool, int, str]:
    """If project has a screen saver widget (id starts with 'screensaver_'), return (True, timeout_seconds, backlight_id). Else (False, 60, 'display_backlight')."""
    for w in _iter_all_widgets(project):
        wid = str(w.get("id") or "").strip()
        if wid.startswith("screensaver_"):
            props = w.get("props") or {}
            if not isinstance(props, dict):
                return (True, 60, "display_backlight")
            timeout = 60
            if props.get("timeout_seconds") is not None:
                try:
                    timeout = max(5, min(86400, int(props["timeout_seconds"])))
                except (TypeError, ValueError):
                    pass
            raw_id = str(props.get("backlight_id") or "display_backlight").strip()
            backlight_id = "".join(c for c in raw_id if c.isalnum() or c == "_") or "display_backlight"
            return (True, timeout, backlight_id)
    return (False, 60, "display_backlight")


def _compile_screensaver_globals() -> str:
    """YAML body for screen saver global (last activity time)."""
    return (
        "  - id: etd_screensaver_last_activity\n"
        "    type: uint32_t\n"
        "    restore_value: no\n"
        "    initial_value: '0'\n"
        "  - id: etd_screensaver_dimmed\n"
        "    type: bool\n"
        "    restore_value: no\n"
        "    initial_value: 'false'\n"
        "  - id: etd_screensaver_request_blank\n"
        "    type: bool\n"
        "    restore_value: no\n"
        "    initial_value: 'false'\n"
    )


def _compile_screensaver_interval(timeout_seconds: int, backlight_id: str = "display_backlight") -> str:
    """YAML body for screen saver interval: every 1s, turn off backlight if idle > timeout. Uses light.turn_off action for reliability."""
    timeout_ms = timeout_seconds * 1000
    safe_bid = "".join(c for c in backlight_id if c.isalnum() or c == "_") or "display_backlight"
    return (
        "  - interval: 1s\n"
        "    then:\n"
        "      - lambda: |-\n"
        "          if (id(etd_screensaver_last_activity) == 0) {\n"
        f"            ESP_LOGI(\"screensaver\", \"initialized (timeout={timeout_seconds}s)\");\n"
        "            id(etd_screensaver_last_activity) = millis();\n"
        "          }\n"
        f"          const uint32_t timeout_ms = {timeout_ms};\n"
        "          const uint32_t idle_ms = millis() - id(etd_screensaver_last_activity);\n"
        "          if (!id(etd_screensaver_dimmed) && idle_ms >= timeout_ms) {\n"
        f"            ESP_LOGI(\"screensaver\", \"blanking backlight (idle=%ums)\", (unsigned)idle_ms);\n"
        "            id(etd_screensaver_request_blank) = true;\n"
        "            id(etd_screensaver_dimmed) = true;\n"
        "          }\n"
        "      - if:\n"
        "          condition:\n"
        "            lambda: 'return id(etd_screensaver_request_blank);'\n"
        "          then:\n"
        "            - light.turn_off:\n"
        f"                id: {safe_bid}\n"
        "            - lambda: 'id(etd_screensaver_request_blank) = false;'\n"
    )


def _inject_screensaver_on_touch_into_body(touchscreen_body: str, backlight_id: str = "display_backlight") -> str:
    """Inject on_touch into the first touchscreen entry so touch wakes display. Returns modified body."""
    if not touchscreen_body or not touchscreen_body.strip():
        return touchscreen_body
    lines = touchscreen_body.splitlines()
    # List format: "  - id: ...\n    platform: ..." vs single-object: "  platform: ...\n  id: ..."
    wake_lambda = (
        "id(etd_screensaver_last_activity) = millis(); "
        "if (id(etd_screensaver_dimmed)) { ESP_LOGI(\"screensaver\", \"waking (touch)\"); } "
        "id(etd_screensaver_dimmed) = false;"
    )
    on_touch_lines = [
        "  on_touch:",
        "    then:",
        "    - lambda: '" + wake_lambda + "'",
        "    - light.turn_on:",
        "        id: " + backlight_id,
    ]
    if lines[0].strip().startswith("- ") or (len(lines[0]) >= 4 and lines[0][:4] == "  - "):
        # List format: inject into first entry (before next "  - " or end)
        first_entry_end = len(lines)
        for i in range(1, len(lines)):
            ln = lines[i]
            if len(ln) >= 4 and ln[:4] == "  - " and not ln.startswith("    "):
                first_entry_end = i
                break
        indent = "    "
        on_touch_block = [
            indent + "on_touch:",
            indent + "  then:",
            indent + "  - lambda: '" + wake_lambda + "'",
            indent + "  - light.turn_on:",
            indent + "      id: " + backlight_id,
        ]
        new_lines = lines[:first_entry_end] + on_touch_block + lines[first_entry_end:]
    else:
        # Single-object format: append on_touch at top level (2-space indent)
        new_lines = lines + on_touch_lines
    return "\n".join(new_lines)


def _widget_refs_in_block(block: str) -> list[str]:
    """Return list of widget ids referenced in a section block (e.g. '  - platform: lvgl\\n    widget: x')."""
    return _WIDGET_REF_RE.findall(block)


def _remove_orphaned_widget_refs_from_sections(project: dict) -> list[tuple[str, str]]:
    """Remove from project.sections any LVGL platform blocks whose widget: id is not in the project's widgets. Mutates project. Returns list of (section_key, removed_widget_id)."""
    sections = project.get("sections")
    if not sections or not isinstance(sections, dict):
        return []
    valid_ids = _collect_widget_ids_from_project(project)
    removed: list[tuple[str, str]] = []
    for section_key in SECTION_KEYS_WITH_WIDGET_REF:
        raw = sections.get(section_key)
        if not raw or not str(raw).strip():
            continue
        body = _section_body_from_value(raw, section_key)
        if not body.strip():
            continue
        # Split into list-item blocks (body is indented; items start with "  - ")
        parts = re.split(r"\n  - ", body)
        if not parts:
            continue
        # First part may be empty or "  - ..."; rest are "platform: ..." without leading "  - "
        kept_blocks: list[str] = []
        for i, block in enumerate(parts):
            if not block.strip():
                continue
            # Normalize: first block might start with "  - ", rest don't
            if i == 0 and block.strip().startswith("  - "):
                block = block.strip()[4:].lstrip()
            elif i > 0:
                block = block.strip()
            refs = _widget_refs_in_block(block)
            if not refs:
                kept_blocks.append(block)
                continue
            if all(wid in valid_ids for wid in refs):
                kept_blocks.append(block)
            else:
                for wid in refs:
                    if wid not in valid_ids:
                        removed.append((section_key, wid))
        n_original = sum(1 for p in parts if p.strip())
        if len(kept_blocks) < n_original:
            new_body = ""
            if kept_blocks:
                new_body = "  - " + kept_blocks[0]
                if len(kept_blocks) > 1:
                    new_body += "\n  - ".join(kept_blocks[1:])
            sections[section_key] = _section_full_block(section_key, new_body.rstrip())
    return removed


def _remove_orphaned_widget_refs_from_esphome_components(project: dict) -> list[tuple[str, str]]:
    """Remove from project.esphome_components any block whose widget: id is not in the project's widgets (Create-component orphans). Mutates project. Returns list of ('esphome_components', removed_widget_id)."""
    components = project.get("esphome_components")
    if not components or not isinstance(components, list):
        return []
    valid_ids = _collect_widget_ids_from_project(project)
    kept: list = []
    removed: list[tuple[str, str]] = []
    for comp in components:
        if comp is None:
            continue
        if isinstance(comp, dict):
            root_id = comp.get("_source_root_id")
            if root_id is not None:
                if str(root_id).strip() in valid_ids:
                    kept.append(comp)
                else:
                    removed.append(("esphome_components", str(root_id).strip()))
                continue
            yaml_str = str(comp.get("yaml") or "").strip()
        else:
            yaml_str = str(comp).strip()
        if not yaml_str:
            kept.append(comp)
            continue
        refs = _widget_refs_in_block(yaml_str)
        if not refs:
            kept.append(comp)
            continue
        if all(wid in valid_ids for wid in refs):
            kept.append(comp)
        else:
            for wid in refs:
                if wid not in valid_ids:
                    removed.append(("esphome_components", wid))
    if len(kept) < len(components):
        project["esphome_components"] = kept
    return removed


def _compile_warnings(project: dict) -> list[dict]:
    """Return list of warnings for compile (e.g. widget: refs in project.sections that point to non-existent widgets)."""
    warnings: list[dict] = []
    valid_ids = _collect_widget_ids_from_project(project)
    sections = project.get("sections") or {}
    if not isinstance(sections, dict):
        return warnings
    for section_key in SECTION_KEYS_WITH_WIDGET_REF:
        raw = sections.get(section_key)
        if not raw or not str(raw).strip():
            continue
        body = _section_body_from_value(raw, section_key)
        if not body.strip():
            continue
        parts = re.split(r"\n  - ", body)
        for block in parts:
            if not block.strip():
                continue
            for wid in _widget_refs_in_block(block):
                if wid not in valid_ids:
                    warnings.append({"type": "orphan_widget_ref", "section": section_key, "widget_id": wid})
                    break
    return warnings


def _display_id_from_recipe(recipe_text: str) -> str | None:
    """Return the first display id from recipe (e.g. 'stub_display') so lvgl can reference it, or None."""
    if not recipe_text or "display:" not in recipe_text:
        return None
    in_display = False
    for line in recipe_text.splitlines():
        stripped = line.strip()
        if re.match(r"^display\s*:", line.lstrip()):
            in_display = True
            continue
        if in_display:
            if stripped.startswith("id:") and ":" in stripped:
                id_val = stripped.split(":", 1)[1].strip().split("#")[0].strip()
                if id_val:
                    return id_val
            if line and not line[0].isspace() and _TOP_LEVEL_KEY_RE.match(line.lstrip()):
                in_display = False
    return None


def _parse_recipe_into_sections(recipe_text: str) -> dict[str, str]:
    """Split recipe YAML into top-level key -> content (content = lines under key, indent preserved)."""
    sections: dict[str, str] = {}
    lines = recipe_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _TOP_LEVEL_KEY_RE.match(line)
        if m:
            key = m.group(1).strip().lower()
            i += 1
            content_lines: list[str] = []
            while i < len(lines):
                next_line = lines[i]
                # Next top-level key: line that starts with a word and colon (no leading space)
                if next_line and not next_line[0].isspace() and _TOP_LEVEL_KEY_RE.match(next_line):
                    break
                content_lines.append(next_line)
                i += 1
            content = "\n".join(content_lines).rstrip()
            if content:
                sections[key] = content
        else:
            i += 1
    return sections


def _yaml_str_to_section_map(yaml_str: str, merge_duplicate_keys: bool = False) -> dict[str, str]:
    """Split a multi-section YAML string (e.g. compiler output) into key -> content.
    Content is the body under each key (first line after 'key:' onward until next key).
    If merge_duplicate_keys is True, duplicate keys have their content concatenated (for prebuilt snippets).
    """
    sections: dict[str, str] = {}
    lines = yaml_str.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _TOP_LEVEL_KEY_RE.match(line)
        if m:
            key = m.group(1).strip().lower()
            i += 1
            content_lines = []
            while i < len(lines):
                next_line = lines[i]
                if next_line and not next_line[0].isspace() and _TOP_LEVEL_KEY_RE.match(next_line):
                    break
                content_lines.append(next_line)
                i += 1
            content = "\n".join(content_lines).rstrip()
            if merge_duplicate_keys and key in sections:
                sections[key] = sections[key].rstrip() + "\n\n" + content
            else:
                sections[key] = content
        else:
            i += 1
    return sections


def _trim_outer_blank_lines(s: str) -> str:
    """Remove leading/trailing blank lines only. Do not use str.strip() on section bodies — it strips indent from the first line."""
    if not s:
        return ""
    lines = s.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _sections_to_yaml(sections: dict[str, str]) -> str:
    """Build a single YAML document from section key -> body (body = content under 'key:', no header).
    Emits sections in SECTION_ORDER; only sections with non-empty content are included."""
    parts: list[str] = []
    for key in SECTION_ORDER:
        raw = _trim_outer_blank_lines(sections.get(key) or "")
        if not raw:
            continue
        body = _section_body_from_value(
            raw if (raw.startswith(key + ":") or raw.startswith(key + " :")) else _section_full_block(key, raw),
            key,
        ).rstrip()
        if body or key in ("wifi", "ota", "logger"):
            parts.append(f"{key}:\n{(body or '').rstrip()}\n")
    return "\n".join(parts).rstrip() + "\n" if parts else ""


def _stored_sections_from_project(project: dict) -> dict[str, str]:
    """Return section key -> body from the stored device YAML (Design v2).
    If project has esphome_yaml, parse it. Else fall back to legacy project.sections (body-only or full block)."""
    yaml_str = (project.get("esphome_yaml") or "").strip()
    if yaml_str:
        return _yaml_str_to_section_map(yaml_str)
    # Legacy: project.sections
    stored = (project.get("sections") or {}) if isinstance(project.get("sections"), dict) else {}
    out: dict[str, str] = {}
    for key in SECTION_ORDER:
        raw = (stored.get(key) or "").strip()
        if not raw:
            out[key] = ""
            continue
        if not (raw.startswith(key + ":") or raw.startswith(key + " :")):
            raw = _section_full_block(key, raw)
        out[key] = (_section_body_from_value(raw, key) or "").rstrip()
    return out


def _strip_section_key(block: str, key: str) -> str:
    """If block starts with 'key:\\n', return the rest (content only). Otherwise return block."""
    prefix = key + ":"
    if block.strip().startswith(prefix):
        rest = block.split("\n", 1)
        if len(rest) == 2:
            return rest[1].rstrip()
        return ""
    return block.strip()


def _merge_list_section_bodies(auto_body: str, user_body: str) -> str:
    """Merge two list-section bodies (e.g. sensor, light, switch) and deduplicate list items.

    When project.sections contains the same content as recipe/compiler (e.g. after Create Component
    sync or panel default), concatenating would emit duplicate blocks and break esphome config.
    We split each body into YAML list items (lines starting with '  - ') and emit each unique
    block once (order: auto items first, then user items not already present).
    """
    def _split_items(body: str) -> list[str]:
        if not (body or "").strip():
            return []
        b = body.strip()
        parts = b.split("\n  - ")
        if not parts:
            return []
        items = [parts[0].strip()]
        for p in parts[1:]:
            if p.strip():
                items.append("  - " + p.strip())
        return items

    def _normalize(item: str) -> str:
        return re.sub(r"\s+", " ", item.strip()) if item else ""

    auto_items = _split_items(auto_body)
    user_items = _split_items(user_body)
    seen: set[str] = set()
    out: list[str] = []
    for item in auto_items + user_items:
        norm = _normalize(item)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(item)
    return "\n\n".join(out).rstrip() if out else ""


def _compile_lvgl_pages(project: dict) -> str:
    pages = project.get("pages") or []
    if not pages:
        pages = [{"id": "main", "widgets": []}]
    page = pages[0] if isinstance(pages[0], dict) else {"id": "main", "widgets": []}
    widgets = page.get("widgets") or []

    def common(w: dict) -> str:
        # Integer pixel geometry in YAML (truncation toward zero). Designer uses layoutInt (round) for flex-derived positions; editor/snapping keeps values integral.
        x = int(w.get("x", 0))
        y = int(w.get("y", 0))
        width = int(w.get("w", 100))
        height = int(w.get("h", 50))
        wid = w.get("id") or "w"
        return f"        id: {wid}\n        x: {x}\n        y: {y}\n        width: {width}\n        height: {height}\n"

    out: list[str] = []
    out.append("  pages:\n")
    out.append(f"    - id: {_esphome_safe_page_id(page.get('id', 'main'))}\n")
    out.append("      widgets:\n")

    for w in widgets:
        if not isinstance(w, dict):
            continue
        wtype = w.get("type")
        props = w.get("props") or {}
        # Normalize Unicode minus (U+2212) / em dash (U+2014) to ASCII hyphen so device fonts render it
        def _safe_text(s: str) -> str:
            if not s:
                return s
            return str(s).replace("\u2212", "-").replace("\u2014", "-")

        if wtype == "label":
            txt = _safe_text(props.get("text", "Label") or "Label")
            out.append("        - label:\n")
            out.append(common(w))
            out.append(f"        text: {json.dumps(txt)}\n")
        elif wtype == "button":
            txt = _safe_text(props.get("text", "Button") or "Button")
            out.append("        - button:\n")
            out.append(common(w))
            out.append(f"        text: {json.dumps(txt)}\n")
        elif wtype == "arc" or wtype == "arc_labeled":
            out.append("        - arc:\n")
            out.append(common(w))
            out.append(f"        min_value: {int(props.get('min_value', 0))}\n")
            out.append(f"        max_value: {int(props.get('max_value', 100))}\n")
            out.append(f"        value: {int(props.get('value', 0))}\n")
            out.append(f"        adjustable: {str(bool(props.get('adjustable', False))).lower()}\n")
        elif wtype == "slider":
            out.append("        - slider:\n")
            out.append(common(w))
            out.append(f"        min_value: {int(props.get('min_value', 0))}\n")
            out.append(f"        max_value: {int(props.get('max_value', 100))}\n")
            out.append(f"        value: {int(props.get('value', 0))}\n")
        elif wtype == "dropdown":
            opts = props.get("options") or ["Option A", "Option B"]
            sel = int(props.get("selected_index", 0))
            out.append("        - dropdown:\n")
            out.append(common(w))
            out.append("        options:\n")
            for o in opts:
                out.append(f"          - {json.dumps(str(o))}\n")
            out.append(f"        selected_index: {sel}\n")
        elif wtype == "image":
            src = (props.get("src") or "").strip()
            out.append("        - image:\n")
            out.append(common(w))
            if src:
                out.append(f"        src: {json.dumps(str(src))}\n")

        else:
            out.append("        - container:\n")
            out.append(common(w))

    return "".join(out)

def _inject_pages_into_recipe(recipe_text: str, pages_yaml: str) -> str:
    marker = "#__LVGL_PAGES__"
    if marker not in recipe_text:
        return recipe_text.rstrip() + "\n\n" + pages_yaml
    # Replace the entire line containing the marker so our pages_yaml indentation is preserved.
    # If we only replaced the marker substring, a recipe line like "    #__LVGL_PAGES__" would become
    # "    " + "  pages:\n    - id: ...", putting "pages:" and "- id:" at the same indent and breaking YAML.
    pattern = re.compile(r"^.*" + re.escape(marker) + r".*$", re.MULTILINE)
    return pattern.sub(lambda m: pages_yaml.rstrip(), recipe_text, count=1)







def sha256(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()
def _safe_id(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", s)



def _compile_ha_bindings(project: dict) -> str:
    """Generate ESPHome homeassistant sensors for bound entities + attach live-update triggers.

    v0.9 scope:
    - Generate homeassistant platforms from project.bindings[]
    - Attach on_value/on_state triggers based on project.links[] that update LVGL widgets live.

    Link format (project.links[]):
      {
        "source": { "entity_id": "light.kitchen", "kind": "binary|state|attribute_number|attribute_text", "attribute": "brightness" },
        "target": { "widget_id": "btn1", "action": "widget_checked|slider_value|arc_value|bar_value|label_text", "format": "%.0f", "scale": 1.0 }
      }
    """
    bindings = project.get("bindings") or []
    if not isinstance(bindings, list):
        bindings = []

    links = project.get("links") or []
    if not isinstance(links, list):
        links = []

    valid_widget_ids = _project_widget_id_set(project)

    # Build a map: (kind, entity_id, attribute) -> list[link] (HA entity links only).
    # Links with source.type in ("local_switch", "local_climate", "interval") are handled elsewhere.
    link_map: dict[tuple[str, str, str], list[dict]] = {}
    for ln in links:
        if not isinstance(ln, dict):
            continue
        src = ln.get("source") or {}
        tgt = ln.get("target") or {}
        src_type = str(src.get("type") or "").strip()
        if src_type in ("local_switch", "local_climate", "interval"):
            continue
        entity_id = str(src.get("entity_id") or "").strip()
        kind = str(src.get("kind") or "state").strip()
        attr = str(src.get("attribute") or "").strip()
        wid = str(tgt.get("widget_id") or "").strip()
        action = str(tgt.get("action") or "").strip()
        if not entity_id or "." not in entity_id or not wid or not action:
            continue
        link_map.setdefault((kind, entity_id, attr), []).append(ln)

    # Widget id -> type (label, button, arc, slider, ...) for correct lvgl.*.update
    def _collect_widget_types(widgets: list, m: dict[str, str]) -> None:
        for w in widgets or []:
            if not isinstance(w, dict):
                continue
            if w.get("id"):
                m[str(w["id"])] = str(w.get("type") or "label")
            _collect_widget_types(w.get("widgets") or [], m)

    def _widget_type_map() -> dict[str, str]:
        m: dict[str, str] = {}
        for page in project.get("pages") or []:
            if isinstance(page, dict):
                _collect_widget_types(page.get("widgets") or [], m)
        return m

    # Widget id -> list of option strings (for dropdowns); used to emit selected_index lambda from text.
    def _collect_dropdown_options(widgets: list, m: dict[str, list[str]]) -> None:
        for w in widgets or []:
            if not isinstance(w, dict):
                continue
            if w.get("type") == "dropdown" and w.get("id"):
                props = w.get("props") or {}
                opts = props.get("options") or ["Option A", "Option B"]
                if isinstance(opts, str):
                    opts = [s.strip() for s in opts.replace("\\n", "\n").split("\n") if s.strip()]
                else:
                    opts = [str(o).strip() for o in opts if str(o).strip()]
                m[str(w["id"])] = opts if opts else ["(none)"]
            _collect_dropdown_options(w.get("widgets") or [], m)

    def _dropdown_options_map() -> dict[str, list[str]]:
        m: dict[str, list[str]] = {}
        for page in project.get("pages") or []:
            if isinstance(page, dict):
                _collect_dropdown_options(page.get("widgets") or [], m)
        return m

    def _collect_roller_options(widgets: list, m: dict[str, list[str]]) -> None:
        for w in widgets or []:
            if not isinstance(w, dict):
                continue
            if w.get("type") == "roller" and w.get("id"):
                props = w.get("props") or {}
                opts = props.get("options") or ["Option A", "Option B"]
                if isinstance(opts, str):
                    opts = [s.strip() for s in opts.replace("\\n", "\n").split("\n") if s.strip()]
                else:
                    opts = [str(o).strip() for o in opts if str(o).strip()]
                m[str(w["id"])] = opts if opts else ["(none)"]
            _collect_roller_options(w.get("widgets") or [], m)

    def _roller_options_map() -> dict[str, list[str]]:
        m: dict[str, list[str]] = {}
        for page in project.get("pages") or []:
            if isinstance(page, dict):
                _collect_roller_options(page.get("widgets") or [], m)
        return m

    widget_type_by_id = _widget_type_map()
    dropdown_options_by_id = _dropdown_options_map()
    roller_options_by_id = _roller_options_map()

    def _widget_props_by_id() -> dict[str, dict]:
        m: dict[str, dict] = {}
        for page in project.get("pages") or []:
            if not isinstance(page, dict):
                continue
            for w in page.get("widgets") or []:
                if isinstance(w, dict) and w.get("id"):
                    m[str(w["id"])] = dict(w.get("props") or {})
        return m

    widget_props_by_id = _widget_props_by_id()

    # Container id -> spinbox child id (legacy grouped spinbox+buttons: link targets container, we update the spinbox child)
    def _container_spinbox_child_map() -> dict[str, str]:
        out: dict[str, str] = {}
        for page in project.get("pages") or []:
            if not isinstance(page, dict):
                continue
            for w in page.get("widgets") or []:
                if not isinstance(w, dict):
                    continue
                pid = w.get("parent_id")
                if pid and str(w.get("type") or "") == "spinbox" and w.get("id"):
                    out[str(pid)] = str(w["id"])
        return out

    container_spinbox_child = _container_spinbox_child_map()

    def emit_lvgl_updates(kind: str, entity_id: str, attr: str) -> str:
        # After caller adds "  ": "- if:" at 8, condition/then at 12, lambda/- lvgl at 14, id/text at 18 (2 under lvgl key)
        i0, i1, i2, i3 = "      ", "          ", "            ", "                "  # 6,10,12,16 -> 8,12,14,18
        outs: list[str] = []
        targets = link_map.get((kind, entity_id, attr), [])
        for ln in targets:
            tgt = ln.get("target") or {}
            raw_wid = tgt.get("widget_id")
            if isinstance(raw_wid, dict) and "id" in raw_wid:
                wid = str(raw_wid.get("id") or "").strip()
            elif isinstance(raw_wid, list) and len(raw_wid):
                wid = str(raw_wid[0] if not isinstance(raw_wid[0], dict) else raw_wid[0].get("id", "") or "").strip()
            else:
                wid = str(raw_wid or "").strip()
            wid_safe = _safe_id(wid)
            action = str(tgt.get("action") or "").strip()
            scale = tgt.get("scale")
            fmt = tgt.get("format")

            # For display (label_text): if target is a container with a spinbox child, we update the child; lock id must match.
            wtype_for_target = widget_type_by_id.get(wid) or "label"
            if action == "label_text" and wtype_for_target == "container" and container_spinbox_child.get(wid):
                display_wid = container_spinbox_child[wid]
                lock_wid_safe = _safe_id(display_wid)
            else:
                display_wid = wid
                lock_wid_safe = wid_safe

            if display_wid not in valid_widget_ids:
                continue

            sid = _slugify_entity_id(entity_id)
            outs.append(f"{i0}- if:\n")
            outs.append(f"{i1}condition:\n")
            outs.append(
                f"{i2}lambda: 'return (millis() > id(etd_ui_lock_until)) && (millis() > id(etd_lock_{sid})) && (millis() > id(etd_lock_{sid}_{lock_wid_safe}));'\n"
            )
            outs.append(f"{i1}then:\n")

            yaml_override = tgt.get("yaml_override")
            if isinstance(yaml_override, str) and yaml_override.strip():
                for line in yaml_override.strip().splitlines():
                    outs.append(f"{i2}{line}\n")
                continue

            if action == "widget_checked":
                outs.append(f"{i2}- lvgl.widget.update:\n")
                outs.append(f"{i3}id: {wid}\n")
                outs.append(f"{i3}state:\n")
                outs.append(f"{i3}  checked: !lambda return x;\n")
            elif action == "slider_value":
                outs.append(f"{i2}- lvgl.slider.update:\n")
                outs.append(f"{i3}id: {wid}\n")
                if isinstance(scale, (int, float)) and float(scale) != 1.0:
                    outs.append(f"{i3}value: !lambda return (x * {float(scale)});\n")
                else:
                    outs.append(f"{i3}value: !lambda return x;\n")
            elif action == "arc_value":
                outs.append(f"{i2}- lvgl.arc.update:\n")
                outs.append(f"{i3}id: {wid}\n")
                if isinstance(scale, (int, float)) and float(scale) != 1.0:
                    outs.append(f"{i3}value: !lambda return (x * {float(scale)});\n")
                else:
                    outs.append(f"{i3}value: !lambda return x;\n")
            elif action == "bar_value":
                outs.append(f"{i2}- lvgl.bar.update:\n")
                outs.append(f"{i3}id: {wid}\n")
                if isinstance(scale, (int, float)) and float(scale) != 1.0:
                    outs.append(f"{i3}value: !lambda return (x * {float(scale)});\n")
                else:
                    outs.append(f"{i3}value: !lambda return x;\n")
            elif action == "spinbox2_value":
                if (widget_type_by_id.get(wid) or "") != "spinbox2":
                    continue
                wp = widget_props_by_id.get(wid) or {}
                try:
                    vmn = float(wp.get("min_value", 0))
                except (TypeError, ValueError):
                    vmn = 0.0
                try:
                    vmx = float(wp.get("max_value", 100))
                except (TypeError, ValueError):
                    vmx = 100.0
                vdec = int(wp.get("decimal_places", 0) or 0)
                vdec = max(0, min(6, vdec))
                vmul = float(10**vdec) if vdec > 0 else 0.0
                g_id = f"etd_sb2_{wid_safe}_val"
                lbl_id = f"{wid}_v"
                fmt_s = str(fmt or ("%.0f" if vdec == 0 else f"%.{vdec}f"))
                fmt_esc = fmt_s.replace("\\", "\\\\").replace('"', '\\"')
                outs.append(f"{i2}- lambda: |-\n")
                outs.append(f"{i3}float __v = (float)x;\n")
                if isinstance(scale, (int, float)) and float(scale) != 1.0:
                    outs.append(f"{i3}__v = __v * {float(scale)};\n")
                outs.append(f"{i3}if (__v < {vmn}f) __v = {vmn}f;\n")
                outs.append(f"{i3}if (__v > {vmx}f) __v = {vmx}f;\n")
                if vdec > 0:
                    outs.append(f"{i3}const float __mul = {vmul:.1f}f;\n")
                    outs.append(f"{i3}__v = (__mul != 0.0f) ? (roundf(__v * __mul) / __mul) : __v;\n")
                else:
                    outs.append(f"{i3}__v = roundf(__v);\n")
                outs.append(f"{i3}id({g_id}) = __v;\n")
                outs.append(f"{i2}- lvgl.label.update:\n")
                outs.append(f"{i3}id: {lbl_id}\n")
                outs.append(f"{i3}text: !lambda |-\n")
                outs.append(f"{i3}  char b[48];\n")
                outs.append(f"{i3}  snprintf(b, sizeof(b), \"{fmt_esc}\", (double) id({g_id}));\n")
                outs.append(f"{i3}  return std::string(b);\n")
            elif action == "label_text":
                wtype = widget_type_by_id.get(display_wid) or "label"
                if wtype == "button":
                    outs.append(f"{i2}- lvgl.button.update:\n")
                    outs.append(f"{i3}id: {display_wid}\n")
                    if kind in ("state", "attribute_text"):
                        outs.append(f"{i3}text: !lambda return x;\n")
                    else:
                        outs.append(f"{i3}text:\n")
                        outs.append(f"{i3}  format: {json.dumps(str(fmt or '%.0f'))}\n")
                        outs.append(f"{i3}  args: [ 'x' ]\n")
                elif wtype == "dropdown" and kind in ("state", "attribute_text"):
                    # Dropdown expects selected_index (int); HA sends text. Map text -> index from widget options.
                    opts = dropdown_options_by_id.get(display_wid) or []
                    outs.append(f"{i2}- lvgl.dropdown.update:\n")
                    outs.append(f"{i3}id: {display_wid}\n")
                    # Emit lambda that returns index of x in options (C++: escape " and \ in option strings)
                    parts = []
                    for idx, opt in enumerate(opts):
                        esc = str(opt).replace("\\", "\\\\").replace('"', '\\"')
                        parts.append(f'if (x == "{esc}") return {idx};')
                    parts.append("return 0;")
                    lambda_body = " ".join(parts)
                    outs.append(f"{i3}selected_index: !lambda '{lambda_body}'\n")
                elif wtype == "spinbox":
                    # Spinbox expects value (float). HA sends number or string; scale applied.
                    outs.append(f"{i2}- lvgl.spinbox.update:\n")
                    outs.append(f"{i3}id: {display_wid}\n")
                    if kind in ("attribute_number", "state") or (kind in ("attribute_text",) and attr):
                        if isinstance(scale, (int, float)) and float(scale) != 1.0:
                            outs.append(f"{i3}value: !lambda return (x * {float(scale)});\n")
                        else:
                            outs.append(f"{i3}value: !lambda return x;\n")
                    else:
                        outs.append(f"{i3}value: !lambda return x;\n")
                elif wtype == "bar":
                    # Bar expects value (int). HA sends number; scale applied.
                    outs.append(f"{i2}- lvgl.bar.update:\n")
                    outs.append(f"{i3}id: {display_wid}\n")
                    if isinstance(scale, (int, float)) and float(scale) != 1.0:
                        outs.append(f"{i3}value: !lambda return (x * {float(scale)});\n")
                    else:
                        outs.append(f"{i3}value: !lambda return x;\n")
                elif wtype == "roller" and kind in ("state", "attribute_text"):
                    # Roller expects selected_index (int); HA sends text. Map text -> index from widget options.
                    opts = roller_options_by_id.get(display_wid) or []
                    outs.append(f"{i2}- lvgl.roller.update:\n")
                    outs.append(f"{i3}id: {display_wid}\n")
                    parts = []
                    for idx, opt in enumerate(opts):
                        esc = str(opt).replace("\\", "\\\\").replace('"', '\\"')
                        parts.append(f'if (x == "{esc}") return {idx};')
                    parts.append("return 0;")
                    lambda_body = " ".join(parts)
                    outs.append(f"{i3}selected_index: !lambda '{lambda_body}'\n")
                elif wtype == "textarea":
                    outs.append(f"{i2}- lvgl.textarea.update:\n")
                    outs.append(f"{i3}id: {display_wid}\n")
                    if kind in ("state", "attribute_text"):
                        outs.append(f"{i3}text: !lambda return x;\n")
                    else:
                        outs.append(f"{i3}text:\n")
                        outs.append(f"{i3}  format: {json.dumps(str(fmt or '%.0f'))}\n")
                        outs.append(f"{i3}  args: [ 'x' ]\n")
                elif wtype == "qrcode":
                    outs.append(f"{i2}- lvgl.qrcode.update:\n")
                    outs.append(f"{i3}id: {display_wid}\n")
                    if kind in ("state", "attribute_text"):
                        outs.append(f"{i3}text: !lambda return x;\n")
                    else:
                        outs.append(f"{i3}text:\n")
                        outs.append(f"{i3}  format: {json.dumps(str(fmt or '%.0f'))}\n")
                        outs.append(f"{i3}  args: [ 'x' ]\n")
                elif wtype in ("container", "obj"):
                    # Container/obj have no label; skip to avoid "ID doesn't inherit from lv_label_t"
                    continue
                else:
                    outs.append(f"{i2}- lvgl.label.update:\n")
                    outs.append(f"{i3}id: {display_wid}\n")
                    if kind in ("state", "attribute_text"):
                        outs.append(f"{i3}text: !lambda return x;\n")
                    else:
                        outs.append(f"{i3}text:\n")
                        outs.append(f"{i3}  format: {json.dumps(str(fmt or '%.0f'))}\n")
                        outs.append(f"{i3}  args: [ 'x' ]\n")

            elif action == "button_bg_color":
                # HA rgb_color -> update colour picker button. Read from sensor state in lambda so we don't
                # rely on trigger var x being passed into the lvgl action (on_value may not pass x to nested actions).
                wtype = widget_type_by_id.get(wid) or "label"
                if wtype != "color_picker":
                    continue
                sensor_id = f"ha_txt_{_safe_id(entity_id)}_{_safe_id(attr or 'attr')}"
                i4 = "                  "  # 18 spaces for condition lambda / then list
                i5 = "                        "  # 24 spaces -> 26 after caller's "  "
                i6 = "                          "  # 26 spaces -> 28 after "  " for lambda body
                # HA sends rgb_color as tuple '(255, 0, 212)' or list '[255,0,0]'; accept both
                outs.append(f"{i2}- if:\n")
                outs.append(f"{i3}condition:\n")
                outs.append(
                    f'{i4}lambda: "return x.size() >= 9 && ( (x.find(\'[\') != std::string::npos && x.find(\']\') != std::string::npos) || (x.find(\'(\') != std::string::npos && x.find(\')\') != std::string::npos) );"\n'
                )
                outs.append(f"{i3}then:\n")
                outs.append(f"{i4}- lvgl.obj.update:\n")
                outs.append(f"{i5}id: {wid}\n")
                outs.append(f"{i5}bg_color: !lambda |-\n")
                outs.append(f"{i6}auto s = id({sensor_id}).state;\n")
                outs.append(f"{i6}int r=0,g=0,b=0;\n")
                outs.append(f"{i6}if (s.size() >= 5) {{\n")
                outs.append(f"{i6}  if (sscanf(s.c_str(), \"[%d,%d,%d]\", &r, &g, &b) != 3)\n")
                outs.append(f"{i6}    sscanf(s.c_str(), \"(%d, %d, %d)\", &r, &g, &b);\n")
                outs.append(f"{i6}  if (r==0 && g==0 && b==0) sscanf(s.c_str(), \"%d,%d,%d\", &r, &g, &b);\n")
                outs.append(f"{i6}}}\n")
                outs.append(f"{i6}return lv_color_hex((r<<16)|(g<<8)|b);\n")
                outs.append(f"{i4}- lvgl.widget.redraw:\n")
                outs.append(f"{i5}id: {wid}\n")

            elif action == "button_white_temp":
                # HA color_temp (mireds) -> update white picker button; x is numeric from attribute_number sensor
                wtype = widget_type_by_id.get(wid) or "label"
                if wtype != "white_picker":
                    continue
                sensor_id = f"ha_num_{_safe_id(entity_id)}_{_safe_id(attr or 'attr')}"
                i4 = "                  "
                i5 = "                        "
                i6 = "                          "
                outs.append(f"{i2}- if:\n")
                outs.append(f"{i3}condition:\n")
                outs.append(f'{i4}lambda: "return x >= 153 && x <= 500;"\n')
                outs.append(f"{i3}then:\n")
                outs.append(f"{i4}- lvgl.obj.update:\n")
                outs.append(f"{i5}id: {wid}\n")
                outs.append(f"{i5}bg_color: !lambda |-\n")
                outs.append(f"{i6}float m = id({sensor_id}).state;\n")
                outs.append(f"{i6}float t = (m - 153.0f) / (500.0f - 153.0f);\n")
                outs.append(f"{i6}if (t < 0.0f) t = 0.0f; if (t > 1.0f) t = 1.0f;\n")
                outs.append(f"{i6}int r = 255, g = (int)(255.0f - 75.0f * t), b = (int)(255.0f - 135.0f * t);\n")
                outs.append(f"{i6}return lv_color_hex((r<<16)|(g<<8)|b);\n")
                outs.append(f"{i4}- lvgl.widget.redraw:\n")
                outs.append(f"{i5}id: {wid}\n")

            elif action == "obj_hidden":
                expr = None
                try:
                    expr = (tgt.get("condition_expr") or "").strip()
                except Exception:
                    expr = ""
                outs.append(f"{i2}- lvgl.obj.update:\n")
                outs.append(f"{i3}id: {wid}\n")
                if expr:
                    outs.append(f"{i3}hidden: !lambda return !({expr});\n")
                else:
                    outs.append(f"{i3}hidden: !lambda return !(x);\n")
        return "".join(outs)

    # Collect (kind, entity_id, attr) from bindings, then add any from links that have no binding
    # so display links (e.g. friendly_name -> label) get a homeassistant sensor and the device updates.
    binding_keys: set[tuple[str, str, str]] = set()
    for b in bindings:
        if not isinstance(b, dict):
            continue
        eid = str(b.get("entity_id") or "").strip()
        if not eid or "." not in eid:
            continue
        kind = str(b.get("kind") or "state")
        attr = str(b.get("attribute") or "").strip()
        binding_keys.add((kind, eid, attr))
    for (kind, eid, attr) in link_map:
        if eid and "." in eid:
            binding_keys.add((kind, eid, attr))

    text_sensors: list[dict] = []
    sensors: list[dict] = []
    binary_sensors: list[dict] = []

    for (kind, entity_id, attr) in sorted(binding_keys, key=lambda x: (x[0], x[1], x[2])):
        base_id = _safe_id(entity_id)

        if kind == "binary":
            binary_sensors.append({"id": f"ha_bin_{base_id}", "entity_id": entity_id, "kind": "binary", "attribute": ""})
        elif kind == "attribute_number":
            sensors.append({"id": f"ha_num_{base_id}_{_safe_id(attr or 'attr')}", "entity_id": entity_id, "kind": "attribute_number", "attribute": attr})
        elif kind == "attribute_text":
            text_sensors.append({"id": f"ha_txt_{base_id}_{_safe_id(attr or 'attr')}", "entity_id": entity_id, "kind": "attribute_text", "attribute": attr})
        else:
            text_sensors.append({"id": f"ha_state_{base_id}", "entity_id": entity_id, "kind": "state", "attribute": ""})

    def emit_text_sensor(items: list[dict]) -> str:
        if not items:
            return ""
        out = ["text_sensor:\n"]
        for it in items:
            out.append("  - platform: homeassistant\n")
            out.append(f"    id: {it['id']}\n")
            out.append(f"    entity_id: {it['entity_id']}\n")
            if it.get("attribute"):
                out.append(f"    attribute: {it['attribute']}\n")
            then = emit_lvgl_updates(it["kind"], it["entity_id"], it.get("attribute",""))
            if then:
                out.append("    on_value:\n")
                out.append("      then:\n")
                out.append("".join(("  " + ln + "\n") if ln else "\n" for ln in then.splitlines()))
        return "".join(out)

    def emit_sensor(items: list[dict]) -> str:
        if not items:
            return ""
        out = ["sensor:\n"]
        for it in items:
            out.append("  - platform: homeassistant\n")
            out.append(f"    id: {it['id']}\n")
            out.append(f"    entity_id: {it['entity_id']}\n")
            if it.get("attribute"):
                out.append(f"    attribute: {it['attribute']}\n")
            then = emit_lvgl_updates(it["kind"], it["entity_id"], it.get("attribute",""))
            if then:
                out.append("    on_value:\n")
                out.append("      then:\n")
                # `then` lines already start with 12 spaces ("            - ...").
                # Add 6 spaces so it nests under `then:` (which is indented 12 spaces).
                out.append("".join(("  " + ln + "\n") if ln else "\n" for ln in then.splitlines()))
        return "".join(out)

    def emit_binary_sensor(items: list[dict]) -> str:
        if not items:
            return ""
        out = ["binary_sensor:\n"]
        for it in items:
            out.append("  - platform: homeassistant\n")
            out.append(f"    id: {it['id']}\n")
            out.append(f"    entity_id: {it['entity_id']}\n")
            out.append("    publish_initial_state: true\n")
            then = emit_lvgl_updates("binary", it["entity_id"], "")
            if then:
                out.append("    on_state:\n")
                out.append("      then:\n")
                out.append("".join(("  " + ln + "\n") if ln else "\n" for ln in then.splitlines()))
        return "".join(out)

    out = []
    out.append(emit_text_sensor(text_sensors))
    if text_sensors:
        out.append("\n")
    out.append(emit_sensor(sensors))
    if sensors:
        out.append("\n")
    out.append(emit_binary_sensor(binary_sensors))
    return "".join(out).rstrip() + "\n" if any(out) else ""


def _get_local_switch_links(project: dict) -> list[tuple[str, str, dict]]:
    """Return list of (switch_id, state, target) for links with source.type == 'local_switch'."""
    links = project.get("links") or []
    valid_wids = _project_widget_id_set(project)
    out: list[tuple[str, str, dict]] = []
    for ln in links:
        if not isinstance(ln, dict):
            continue
        src = ln.get("source") or {}
        if str(src.get("type") or "").strip() != "local_switch":
            continue
        switch_id = str(src.get("switch_id") or "").strip()
        state = str(src.get("state") or "on").strip().lower()
        if state not in ("on", "off"):
            state = "on"
        tgt = ln.get("target") or {}
        if not switch_id or not tgt:
            continue
        wid = str(tgt.get("widget_id") or "").strip()
        if wid not in valid_wids:
            continue
        out.append((switch_id, state, tgt))
    return out


def _inject_local_switch_links_into_section(switch_body: str, project: dict) -> str:
    """Append link-driven on_turn_on/on_turn_off actions into existing switch section body."""
    if not (switch_body or "").strip():
        return switch_body
    links_by_switch: dict[str, list[tuple[str, dict]]] = {}  # switch_id -> [(state, target), ...]
    for switch_id, state, tgt in _get_local_switch_links(project):
        links_by_switch.setdefault(switch_id, []).append((state, tgt))
    if not links_by_switch:
        return switch_body
    # Split into list items (each "  - platform: ..." block)
    items = re.split(r"\n(?=  - )", switch_body)
    result: list[str] = []
    for item in items:
        if not item.strip():
            result.append(item)
            continue
        # Find id: switch_id in this item
        id_m = re.search(r"\bid:\s*([a-zA-Z0-9_]+)", item)
        if not id_m:
            result.append(item)
            continue
        sid = id_m.group(1)
        link_list = links_by_switch.get(sid)
        if not link_list:
            result.append(item)
            continue
        # For each (state, target) append yaml_override to on_turn_on or on_turn_off
        for state, tgt in link_list:
            override = (tgt.get("yaml_override") or "").strip()
            if not override:
                continue
            # Indent for list under on_turn_on (6 spaces for "- ", 8 for continuation)
            def indent_action(ln: str) -> str:
                if ln.strip().startswith("-"):
                    return "      " + ln
                return "        " + ln
            action_lines = "\n".join(indent_action(ln) for ln in override.splitlines())
            key = "on_turn_on" if state == "on" else "on_turn_off"
            key_marker = f"\n    {key}:"
            if key_marker in item:
                idx = item.find(key_marker)
                start = idx + len(key_marker)
                rest = item[start:]
                # Next key at same indent (4 spaces + letter)
                match = re.search(r"\n    [a-zA-Z_]", rest)
                insert_pos = start + match.start() if match else len(item)
                item = item[:insert_pos] + "\n" + action_lines + "\n" + item[insert_pos:]
            else:
                item = item.rstrip() + f"\n    {key}:\n{action_lines}\n"
        result.append(item)
    return "\n".join(result).rstrip() + "\n" if result else switch_body


def _get_local_climate_links(project: dict) -> list[tuple[str, str, dict]]:
    """Return list of (climate_id, state, target) for links with source.type == 'local_climate'."""
    links = project.get("links") or []
    valid_wids = _project_widget_id_set(project)
    out: list[tuple[str, str, dict]] = []
    for ln in links:
        if not isinstance(ln, dict):
            continue
        src = ln.get("source") or {}
        if str(src.get("type") or "").strip() != "local_climate":
            continue
        climate_id = str(src.get("climate_id") or "").strip()
        state = str(src.get("state") or "HEAT").strip().upper()
        if state not in ("HEAT", "IDLE", "OFF"):
            continue
        tgt = ln.get("target") or {}
        if not climate_id or not tgt:
            continue
        wid = str(tgt.get("widget_id") or "").strip()
        if wid not in valid_wids:
            continue
        out.append((climate_id, state, tgt))
    return out


def _inject_local_climate_links_into_section(climate_body: str, project: dict) -> str:
    """Append link-driven heat_action/idle_action/off_mode into existing climate section body."""
    if not (climate_body or "").strip():
        return climate_body
    links_by_climate: dict[str, list[tuple[str, dict]]] = {}  # climate_id -> [(state, target), ...]
    for climate_id, state, tgt in _get_local_climate_links(project):
        links_by_climate.setdefault(climate_id, []).append((state, tgt))
    if not links_by_climate:
        return climate_body
    items = re.split(r"\n(?=  - )", climate_body)
    result: list[str] = []
    for item in items:
        if not item.strip():
            result.append(item)
            continue
        id_m = re.search(r"\bid:\s*([a-zA-Z0-9_]+)", item)
        if not id_m:
            result.append(item)
            continue
        cid = id_m.group(1)
        link_list = links_by_climate.get(cid)
        if not link_list:
            result.append(item)
            continue
        for state, tgt in link_list:
            override = (tgt.get("yaml_override") or "").strip()
            if not override:
                continue
            key = {"HEAT": "heat_action", "IDLE": "idle_action", "OFF": "off_mode"}.get(state, "heat_action")
            def indent_action(ln: str) -> str:
                if ln.strip().startswith("-"):
                    return "      " + ln
                return "        " + ln
            action_lines = "\n".join(indent_action(ln) for ln in override.splitlines())
            key_marker = f"\n    {key}:"
            if key_marker in item:
                idx = item.find(key_marker)
                start = idx + len(key_marker)
                rest = item[start:]
                match = re.search(r"\n    [a-zA-Z_]", rest)
                insert_pos = start + match.start() if match else len(item)
                item = item[:insert_pos] + "\n" + action_lines + "\n" + item[insert_pos:]
            else:
                item = item.rstrip() + f"\n    {key}:\n{action_lines}\n"
        result.append(item)
    return "\n".join(result).rstrip() + "\n" if result else climate_body


def _get_interval_links(project: dict) -> list[dict]:
    """Return list of links with source.type == 'interval'. Each has source.interval_seconds, source.updates[]."""
    links = project.get("links") or []
    out: list[dict] = []
    for ln in links:
        if not isinstance(ln, dict):
            continue
        src = ln.get("source") or {}
        if str(src.get("type") or "").strip() != "interval":
            continue
        out.append(ln)
    return out


def _compile_interval_links_yaml(project: dict) -> str:
    """Emit interval section body from project.links with source.type == 'interval'."""
    interval_links = _get_interval_links(project)
    if not interval_links:
        return ""
    valid_wids = _project_widget_id_set(project)
    out: list[str] = []
    for ln in interval_links:
        src = ln.get("source") or {}
        sec = int(src.get("interval_seconds") or 1)
        updates = src.get("updates") or []
        if not updates:
            continue
        filtered_updates: list[dict] = []
        for u in updates:
            if not isinstance(u, dict):
                continue
            wid_u = str(u.get("widget_id") or "").strip()
            if wid_u and wid_u not in valid_wids:
                continue
            filtered_updates.append(u)
        if not filtered_updates:
            continue
        out.append(f"  - interval: {sec}s")
        out.append("    then:")
        for u in filtered_updates:
            yaml_override = (u.get("yaml_override") or "").strip()
            if yaml_override:
                for line in yaml_override.splitlines():
                    out.append("      " + line)
            else:
                wid = str(u.get("widget_id") or "").strip()
                action = str(u.get("action") or "label_text").strip()
                local_id = str(u.get("local_id") or "").strip()
                if wid and local_id:
                    out.append(f"      - lvgl.label.update:")
                    out.append(f"          id: {wid}")
                    out.append(f"          text: !lambda return id({local_id}).state;")
        out.append("")
    return "\n".join(out).rstrip()


def _compile_scripts(project: dict) -> str:
    """Emit ESPHome script: block for project.scripts (e.g. thermostat +/- setpoint inc/dec).

    Each script: { "id": "th_inc_xxx", "entity_id": "climate.xxx", "step": 0.5, "direction": "inc"|"dec" }.
    Uses the homeassistant sensor id ha_num_<slug>_temperature for current setpoint.
    """
    scripts = project.get("scripts") or []
    if not isinstance(scripts, list) or not scripts:
        return ""
    out = ["script:\n"]
    for s in scripts:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("id") or "").strip()
        entity_id = str(s.get("entity_id") or "").strip()
        direction = str(s.get("direction") or "inc").strip().lower()
        step = float(s.get("step") if s.get("step") is not None else 0.5)
        if not sid or "." not in entity_id:
            continue
        slug = _safe_id(entity_id)
        sensor_id = f"ha_num_{slug}_temperature"
        if direction == "inc":
            expr = f"id({sensor_id}).state + {step}f"
        else:
            expr = f"id({sensor_id}).state - {step}f"
        out.append(f"  - id: {sid}\n")
        out.append("    then:\n")
        out.append("      - homeassistant.action:\n")
        out.append("          action: climate.set_temperature\n")
        out.append("          data:\n")
        out.append(f"            entity_id: {json.dumps(entity_id)}\n")
        out.append(f"            temperature: !lambda 'return {expr};'\n")
    return "".join(out).rstrip() + "\n" if len(out) > 1 else ""


def _split_esphome_block(recipe_text: str) -> tuple[str, str]:
    """Split recipe into (esphome_block, rest). esphome_block starts with 'esphome:' and runs to the next top-level key.
    Accepts a line that is optional BOM/whitespace + 'esphome:' + optional rest (whitespace, comment, or more)."""
    lines = recipe_text.splitlines()
    start_idx: int | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Block start: optional BOM, optional leading space, then "esphome:" (rest of line can be anything)
        if re.match(r"^(?:\ufeff)?\s*esphome:", line):
            start_idx = i
            break
    if start_idx is None:
        return "", recipe_text
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        if not line.strip():
            continue
        if line.strip().startswith("#"):
            continue
        # Next top-level key: no leading indent
        if (len(line) - len(line.lstrip())) == 0 and ":" in line:
            end_idx = i
            break
    esphome_block = "\n".join(lines[start_idx:end_idx])
    rest = "\n".join(lines[end_idx:]).strip()
    return esphome_block, rest


def _default_wifi_yaml() -> str:
    """Default wifi section when recipe does not include one."""
    return """wifi:
  networks:
    - ssid: !secret wifi_ssid
      password: !secret wifi_password
  ap:
    ssid: "Fallback"
    password: "12345678"
"""


def _default_ota_yaml() -> str:
    """Default ota section when recipe does not include one."""
    return """ota:
  - platform: esphome
"""


def _apply_ota_password(yaml_text: str, ota_password: str | None) -> str:
    """Set/insert OTA password into top-level ota block when provided."""
    password = (ota_password or "").strip()
    if not password:
        return yaml_text

    line = f"password: {json.dumps(password)}"
    lines = yaml_text.splitlines()
    ota_start = next((i for i, ln in enumerate(lines) if re.match(r"^\s*ota:\s*$", ln)), -1)

    # If no ota block exists, append a minimal one.
    if ota_start < 0:
        out = yaml_text.rstrip() + "\n\nota:\n  - platform: esphome\n    " + line + "\n"
        return out

    # Locate the end of the top-level ota block.
    ota_end = len(lines)
    for i in range(ota_start + 1, len(lines)):
        ln = lines[i]
        if ln and not ln.startswith(" ") and not ln.startswith("\t"):
            ota_end = i
            break

    block = lines[ota_start:ota_end]
    for i, ln in enumerate(block):
        if re.match(r"^\s*password\s*:", ln):
            indent = re.match(r"^(\s*)", ln).group(1) if re.match(r"^(\s*)", ln) else "  "
            block[i] = f"{indent}{line}"
            lines[ota_start:ota_end] = block
            return "\n".join(lines)

    # No password found; inject under first list item when possible.
    inserted = False
    for i, ln in enumerate(block):
        if re.match(r"^\s*-\s+", ln):
            indent = re.match(r"^(\s*)", ln).group(1) if re.match(r"^(\s*)", ln) else "  "
            block.insert(i + 1, f"{indent}  {line}")
            inserted = True
            break
    if not inserted:
        block.insert(1, f"  {line}")

    lines[ota_start:ota_end] = block
    return "\n".join(lines)


def _apply_wifi_settings(yaml_text: str, device_settings: dict | None) -> str:
    """Set/insert wifi network ssid/password from device settings.

    device_settings keys:
    - wifi_ssid (optional): blank -> !secret wifi_ssid
    - wifi_password (optional): blank -> !secret wifi_password
    """
    settings = device_settings if isinstance(device_settings, dict) else {}
    ssid_raw = str(settings.get("wifi_ssid") or "").strip()
    pwd_raw = str(settings.get("wifi_password") or "").strip()
    # If nothing is provided, keep existing YAML unchanged.
    if not ssid_raw and not pwd_raw:
        return yaml_text

    ssid_val = json.dumps(ssid_raw) if ssid_raw else "!secret wifi_ssid"
    pwd_val = json.dumps(pwd_raw) if pwd_raw else "!secret wifi_password"

    lines = yaml_text.splitlines()
    wifi_start = next((i for i, ln in enumerate(lines) if re.match(r"^\s*wifi:\s*$", ln)), -1)
    if wifi_start < 0:
        out = yaml_text.rstrip() + "\n\n" + _default_wifi_yaml().rstrip() + "\n"
        lines = out.splitlines()
        wifi_start = next((i for i, ln in enumerate(lines) if re.match(r"^\s*wifi:\s*$", ln)), -1)
        if wifi_start < 0:
            return out

    wifi_end = len(lines)
    for i in range(wifi_start + 1, len(lines)):
        ln = lines[i]
        if ln and not ln.startswith(" ") and not ln.startswith("\t"):
            wifi_end = i
            break

    block = lines[wifi_start:wifi_end]
    networks_idx = next((i for i, ln in enumerate(block) if re.match(r"^\s*networks\s*:\s*$", ln)), -1)
    if networks_idx < 0:
        # Add a minimal networks list under wifi:
        block.insert(1, "  networks:")
        block.insert(2, "    - ssid: " + ssid_val)
        block.insert(3, "      password: " + pwd_val)
        lines[wifi_start:wifi_end] = block
        return "\n".join(lines)

    net_indent = len(block[networks_idx]) - len(block[networks_idx].lstrip())
    item_idx = -1
    for i in range(networks_idx + 1, len(block)):
        ln = block[i]
        if not ln.strip():
            continue
        indent = len(ln) - len(ln.lstrip())
        if indent <= net_indent:
            break
        if re.match(r"^\s*-\s+", ln):
            item_idx = i
            break
    if item_idx < 0:
        item_idx = networks_idx + 1
        block.insert(item_idx, "    - ssid: " + ssid_val)
        block.insert(item_idx + 1, "      password: " + pwd_val)
        lines[wifi_start:wifi_end] = block
        return "\n".join(lines)

    item_indent = len(block[item_idx]) - len(block[item_idx].lstrip())
    item_end = len(block)
    for i in range(item_idx + 1, len(block)):
        ln = block[i]
        if not ln.strip():
            continue
        indent = len(ln) - len(ln.lstrip())
        if indent <= net_indent:
            item_end = i
            break
        if indent == item_indent and re.match(r"^\s*-\s+", ln):
            item_end = i
            break

    ssid_set = False
    pwd_set = False
    for i in range(item_idx, item_end):
        ln = block[i]
        if re.match(r"^\s*-\s*ssid\s*:", ln):
            prefix = re.match(r"^(\s*-\s*ssid\s*:\s*)", ln)
            block[i] = (prefix.group(1) if prefix else "    - ssid: ") + ssid_val
            ssid_set = True
        elif re.match(r"^\s*ssid\s*:", ln):
            prefix = re.match(r"^(\s*ssid\s*:\s*)", ln)
            block[i] = (prefix.group(1) if prefix else "      ssid: ") + ssid_val
            ssid_set = True
        elif re.match(r"^\s*password\s*:", ln):
            prefix = re.match(r"^(\s*password\s*:\s*)", ln)
            block[i] = (prefix.group(1) if prefix else "      password: ") + pwd_val
            pwd_set = True

    insert_idx = item_idx + 1
    if not ssid_set:
        block.insert(insert_idx, "      ssid: " + ssid_val)
        insert_idx += 1
        item_end += 1
    if not pwd_set:
        block.insert(insert_idx, "      password: " + pwd_val)

    lines[wifi_start:wifi_end] = block
    return "\n".join(lines)


def _default_logger_yaml() -> str:
    """Default logger section when recipe does not include one. ESPHome requires logger to be configured."""
    return """logger:
"""


def _merge_scripts_into_rest(rest: str, scripts_yaml: str) -> str:
    """Merge compiler-generated script entries into rest's existing script: block to avoid duplicate top-level key.
    Returns rest with our script list items appended inside the recipe's script block; scripts_yaml is the
    full 'script:\\n  - id: ...' block from _compile_scripts."""
    if not (rest and scripts_yaml and scripts_yaml.strip()):
        return rest
    # Top-level key: line at column 0 with key:
    top_level_re = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:")
    lines = rest.splitlines(keepends=True)
    if not lines:
        return rest
    script_start: int | None = None
    for i, ln in enumerate(lines):
        m = top_level_re.match(ln.lstrip("\ufeff"))
        if m and m.group(1) == "script":
            script_start = i
            break
    if script_start is None:
        return rest
    # Find next top-level key after script
    next_top = len(lines)
    for i in range(script_start + 1, len(lines)):
        ln = lines[i]
        if not ln.strip():
            continue
        m = top_level_re.match(ln.lstrip("\ufeff"))
        if m:
            next_top = i
            break
    # Extract our script list items (strip "script:\n" from scripts_yaml)
    script_body = scripts_yaml.strip()
    if script_body.lower().startswith("script:"):
        script_body = script_body[7:].lstrip("\n")
    if not script_body.strip():
        return rest
    # Insert our items before the next top-level key (at end of script block)
    insert_at = next_top
    new_lines = lines[:insert_at] + [script_body.rstrip() + "\n", "\n"] + lines[insert_at:]
    return "".join(new_lines)


def _all_widgets_flat(project: dict) -> list[dict]:
    """Return a flat list of all widgets from pages and top_layer, each with '_parent_id' set."""
    out: list[dict] = []

    def collect(widgets: list, parent_id: str = "") -> None:
        for w in widgets or []:
            if not isinstance(w, dict):
                continue
            w_copy = dict(w)
            w_copy["_parent_id"] = parent_id
            out.append(w_copy)
            collect(w.get("widgets") or [], w.get("id") or "")

    for page in project.get("pages") or []:
        if isinstance(page, dict):
            collect(page.get("widgets") or [], "")
    top_layer = (project.get("lvgl_config") or {}).get("top_layer") or {}
    collect(top_layer.get("widgets") or [], "")

    return out


def _project_widget_id_set(project: dict) -> set[str]:
    """All LVGL widget ids on pages and top_layer (for skipping import-orphan / stale links at compile)."""
    return {str(w["id"]) for w in _all_widgets_flat(project) if w.get("id")}


def _compile_wifi_prebuilt_intervals(project: dict) -> str:
    """Generate interval YAML for WiFi bar and WiFi fan from current project widget IDs.
    Avoids stale IDs when stored esphome_components had intervals from an older widget set.
    """
    widgets = _all_widgets_flat(project)
    by_parent: dict[str, list[dict]] = {}
    for w in widgets:
        pid = str(w.get("_parent_id") or "")
        by_parent.setdefault(pid, []).append(w)

    lines: list[str] = []
    # Bar order: left-to-right by x (and y) so first bar = leftmost = first threshold
    WIFI_BAR_THRESHOLDS = (-90, -75, -65, -55)
    for pid, group in by_parent.items():
        bars = [w for w in group if w.get("type") == "bar" and (w.get("id") or "").startswith("wifi_bar_")]
        if len(bars) != 4:
            continue
        bars.sort(key=lambda w: (int(w.get("x", 0)), int(w.get("y", 0))))
        for i, w in enumerate(bars):
            wid = w.get("id") or ""
            thresh = WIFI_BAR_THRESHOLDS[i]
            lines.append(f"      - lvgl.bar.update:")
            lines.append(f"          id: {wid}")
            lines.append(f"          value: !lambda 'return id(etd_wifi_signal).state > {thresh} ? 100 : 0;'")

    # Arc order: innermost to outermost by size (w/h) so first arc = smallest = first threshold
    WIFI_FAN_THRESHOLDS = (-90, -80, -70, -65, -55)
    for pid, group in by_parent.items():
        arcs = [w for w in group if w.get("type") == "arc" and (w.get("id") or "").startswith("wifi_fan_arc_")]
        if len(arcs) != 5:
            continue
        arcs.sort(key=lambda w: (int(w.get("w", 0)), int(w.get("h", 0))))
        for i, w in enumerate(arcs):
            wid = w.get("id") or ""
            thresh = WIFI_FAN_THRESHOLDS[i]
            lines.append(f"      - lvgl.arc.update:")
            lines.append(f"          id: {wid}")
            lines.append(f"          value: !lambda 'return id(etd_wifi_signal).state > {thresh} ? 100 : 0;'")

    if not lines:
        return ""
    return "interval:\n  - interval: 5s\n    then:\n" + "\n".join(lines) + "\n"


def _is_wifi_bar_fan_interval_block(yaml_str: str) -> bool:
    """True if this block is a WiFi bar or WiFi fan interval (skip; use compiler-generated IDs)."""
    s = yaml_str.strip()
    if "etd_wifi_signal" not in s:
        return False
    if "lvgl.bar.update" in s and "wifi_bar_" in s:
        return True
    if "lvgl.arc.update" in s and "wifi_fan_arc_" in s:
        return True
    return False


def _compile_prebuilt_components(project: dict, include_user_components: bool = True) -> str:
    """Compile ESPHome components from prebuilt widgets (sensors, intervals, etc.).

    project.esphome_components is an array of raw YAML strings (or dicts with 'yaml' key).
    We deduplicate by checking for duplicate 'id:' lines to avoid emitting duplicate
    sensors/intervals when multiple prebuilts use the same shared component.
    WiFi bar/fan intervals are generated from current widget IDs (not stored) to avoid stale IDs.

    When include_user_components is False (section-based compile), only prebuilt blocks are emitted.
    v0.70.136: added for prebuilt widget native functionality.
    """
    components = project.get("esphome_components") or []
    if not isinstance(components, list):
        components = []

    seen_ids: set[str] = set()
    out_blocks: list[str] = []

    for comp in components:
        if not comp:
            continue
        # Support both raw YAML string and dict with 'yaml' key
        if isinstance(comp, dict):
            yaml_str = str(comp.get("yaml") or "")
        else:
            yaml_str = str(comp)
        yaml_str = yaml_str.strip()
        if not yaml_str:
            continue

        # Skip WiFi bar/fan interval blocks; we generate these from current widget IDs below
        if _is_wifi_bar_fan_interval_block(yaml_str):
            continue

        # Extract all 'id: xxx' from the block for deduplication
        id_matches = re.findall(r"^\s*id:\s*(\S+)\s*$", yaml_str, re.MULTILINE)
        # Skip if ALL ids in this block are already seen (avoid duplicate sensors)
        if id_matches and all(mid in seen_ids for mid in id_matches):
            continue
        for mid in id_matches:
            seen_ids.add(mid)

        out_blocks.append(yaml_str)

    # Generate WiFi bar/fan intervals from current project widgets so IDs always match
    wifi_interval_yaml = _compile_wifi_prebuilt_intervals(project)
    if wifi_interval_yaml.strip():
        out_blocks.append(wifi_interval_yaml.strip())

    auto_header = ""
    if out_blocks:
        auto_header = "# Prebuilt widget components (auto-generated)\n" + "\n\n".join(out_blocks) + "\n"

    if not include_user_components:
        return auto_header

    # v0.70.138: Merge user_components into output (legacy path; section-based uses section_overrides)
    user_components = project.get("user_components") or {}
    user_blocks: list[str] = []
    for section in ["sensor", "text_sensor", "binary_sensor", "interval", "time", "script"]:
        items = user_components.get(section) or []
        if not isinstance(items, list) or not items:
            continue
        # Each item is a raw YAML string (list items under the section key)
        section_yaml = f"{section}:\n"
        for item in items:
            item_str = str(item).strip()
            if not item_str:
                continue
            # Check for id collision with auto-generated
            item_ids = re.findall(r"^\s*id:\s*(\S+)\s*$", item_str, re.MULTILINE)
            for iid in item_ids:
                seen_ids.add(iid)
            # Indent each line of the item by 2 spaces (under section key)
            indented = "\n".join("  " + ln if ln.strip() else ln for ln in item_str.split("\n"))
            section_yaml += indented + "\n"
        if len(section_yaml) > len(f"{section}:\n"):
            user_blocks.append(section_yaml.rstrip())

    user_header = ""
    if user_blocks:
        user_header = "\n# User-defined components\n" + "\n\n".join(user_blocks) + "\n"

    return auto_header + user_header


def _build_compiler_sections(project: dict, device: object | None = None) -> dict[str, str]:
    """Build the section map that the compiler produces (sensor, text_sensor, lvgl, script, etc.).
    Used by section-based compile and by GET sections/defaults. device is optional (for api key).
    """
    # Font rewrite (same as full compile) so lvgl/widget refs are correct
    project = dict(project)
    fonts_yaml, font_id_map = _compile_fonts_from_project(project)
    if font_id_map:
        project = _rewrite_widget_font_references(project, font_id_map)

    out: dict[str, str] = {}

    # HA bindings -> sensor, text_sensor, binary_sensor (content only)
    ha_yaml = _compile_ha_bindings(project)
    if ha_yaml.strip():
        for k, v in _yaml_str_to_section_map(ha_yaml).items():
            out[k] = v

    # Prebuilt components (no user_components; section_overrides handle user edits)
    prebuilt_str = _compile_prebuilt_components(project, include_user_components=False)
    if prebuilt_str.strip():
        prebuilt_map = _yaml_str_to_section_map(prebuilt_str, merge_duplicate_keys=True)
        for k, v in prebuilt_map.items():
            if k in out:
                out[k] = out[k].rstrip() + "\n\n" + v
            else:
                out[k] = v

    # Globals (lock vars + color picker + white picker)
    locks_yaml = _compile_ui_lock_globals(project)
    cpicker_defaults = _collect_color_picker_defaults(project)
    wpicker_defaults = _collect_white_picker_defaults(project)
    cpicker_globals_yaml = _compile_color_picker_globals(cpicker_defaults)
    wpicker_globals_yaml = _compile_white_picker_globals(wpicker_defaults)
    spinbox2_globals_yaml = _compile_spinbox2_globals(project)
    if locks_yaml.strip() or cpicker_globals_yaml.strip() or wpicker_globals_yaml.strip() or spinbox2_globals_yaml.strip():
        combined = (_strip_section_key(locks_yaml, "globals") or "").rstrip()
        if cpicker_globals_yaml.strip():
            cpicker_part = _strip_section_key(cpicker_globals_yaml, "globals").rstrip()
            combined = (combined + "\n" + cpicker_part).rstrip() if combined else cpicker_part
        if wpicker_globals_yaml.strip():
            wpicker_part = _strip_section_key(wpicker_globals_yaml, "globals").rstrip()
            combined = (combined + "\n" + wpicker_part).rstrip() if combined else wpicker_part
        if spinbox2_globals_yaml.strip():
            sb2_part = _strip_section_key(spinbox2_globals_yaml, "globals").rstrip()
            combined = (combined + "\n" + sb2_part).rstrip() if combined else sb2_part
        out["globals"] = combined

    # Script (project scripts + color picker + white picker scripts)
    scripts_yaml = _compile_scripts(project)
    cpicker_scripts_yaml = _compile_color_picker_scripts(cpicker_defaults, project)
    wpicker_scripts_yaml = _compile_white_picker_scripts(wpicker_defaults, project)
    if scripts_yaml.strip() or cpicker_scripts_yaml.strip() or wpicker_scripts_yaml.strip():
        combined = (_strip_section_key(scripts_yaml, "script") or "").rstrip()
        if cpicker_scripts_yaml.strip():
            cpicker_part = _strip_section_key(cpicker_scripts_yaml, "script").rstrip()
            combined = (combined + "\n" + cpicker_part).rstrip() if combined else cpicker_part
        if wpicker_scripts_yaml.strip():
            wpicker_part = _strip_section_key(wpicker_scripts_yaml, "script").rstrip()
            combined = (combined + "\n" + wpicker_part).rstrip() if combined else wpicker_part
        out["script"] = combined

    # Interval: colour picker + white picker HA sync
    cpicker_interval_yaml = _compile_color_picker_sync_interval(project, cpicker_defaults)
    wpicker_interval_yaml = _compile_white_picker_sync_interval(project, wpicker_defaults)
    for interval_yaml in (cpicker_interval_yaml, wpicker_interval_yaml):
        if interval_yaml.strip():
            interval_body = _strip_section_key(interval_yaml, "interval").rstrip()
            if interval_body:
                if "interval" in out:
                    out["interval"] = out["interval"].rstrip() + "\n\n" + interval_body
                else:
                    out["interval"] = interval_body

    # Screen saver: globals + interval when screen saver widget is present
    has_screensaver, screensaver_timeout, screensaver_backlight_id = _get_screensaver_config(project)
    if has_screensaver:
        ss_globals = _compile_screensaver_globals()
        if ss_globals.strip():
            if "globals" in out:
                out["globals"] = out["globals"].rstrip() + "\n\n" + ss_globals.rstrip()
            else:
                out["globals"] = ss_globals.rstrip()
        ss_interval = _compile_screensaver_interval(screensaver_timeout, screensaver_backlight_id)
        if ss_interval.strip():
            if "interval" in out:
                out["interval"] = out["interval"].rstrip() + "\n\n" + ss_interval.rstrip()
            else:
                out["interval"] = ss_interval.rstrip()

    # LVGL (full body: config + pages); keep leading indent (rstrip only).
    pages_yaml = _compile_lvgl_pages_schema_driven(
        project, cpicker_defaults=cpicker_defaults, wpicker_defaults=wpicker_defaults
    )
    if pages_yaml.strip():
        out["lvgl"] = pages_yaml.rstrip()

    # Font, image
    if fonts_yaml.strip():
        out["font"] = _strip_section_key(fonts_yaml, "font")
    assets_yaml = _compile_assets(project)
    if assets_yaml.strip():
        out["image"] = _strip_section_key(assets_yaml, "image")

    # API encryption (when device has api_key)
    if device is not None and getattr(device, "api_key", None) and str(getattr(device, "api_key", "") or "").strip():
        key = (getattr(device, "api_key", "") or "").strip()
        out["api"] = "  encryption:\n    key: " + json.dumps(key) + "\n"

    return out


def _apply_user_injection(recipe_text: str, project: dict) -> str:
    adv = project.get("advanced") or {}
    pre = str(adv.get("yaml_pre", "") or "")
    post = str(adv.get("yaml_post", "") or "")
    markers = adv.get("markers") or {}

    def repl(text: str, marker: str, payload: str) -> str:
        token = f"#__{marker}__"
        if token in text:
            return text.replace(token, payload.rstrip())
        return text

    # Standard markers
    if pre:
        recipe_text = repl(recipe_text, "USER_YAML_PRE", pre)
        if "#__USER_YAML_PRE__" not in recipe_text:
            recipe_text = pre.rstrip() + "\n\n" + recipe_text
    else:
        recipe_text = recipe_text.replace("#__USER_YAML_PRE__", "")

    if post:
        recipe_text = repl(recipe_text, "USER_YAML_POST", post)
        if "#__USER_YAML_POST__" not in recipe_text:
            recipe_text = recipe_text.rstrip() + "\n\n" + post.rstrip() + "\n"
    else:
        recipe_text = recipe_text.replace("#__USER_YAML_POST__", "")

    # Arbitrary marker replacements (marker_name -> yaml)
    if isinstance(markers, dict):
        for k, v in markers.items():
            if not k:
                continue
            recipe_text = repl(recipe_text, str(k), str(v or ""))

    return recipe_text

def _compile_assets(project: dict) -> str:
    """Compile assets referenced by the project.

    v0.27 scope:
    - Supports image assets referenced as `props.src: "asset:<filename>"`
    - Emits an `image:` section with file references (expects files to exist under
      `/config/esptoolkit_assets/<filename>` on the HA host).
    """
    pages = project.get("pages") or []
    assets: dict[str,str] = {}  # id -> filename
    for pg in pages if isinstance(pages, list) else []:
        for w in (pg.get("widgets") or []):
            if not isinstance(w, dict): 
                continue
            if str(w.get("type") or "") != "image":
                continue
            props = w.get("props") or {}
            src = str(props.get("src") or "").strip()
            if src.startswith("asset:"):
                fn = src.split(":",1)[1].strip()
                if fn:
                    aid = "asset_" + _safe_id(fn)
                    assets[aid]=fn
    if not assets:
        return ""
    out=["image:\n"]
    for aid in sorted(assets.keys()):
        fn = assets[aid]
        out.append(f"  - file: /config/{ASSETS_DIR}/{fn}\n")
        out.append(f"    id: {aid}\n")
    return "".join(out)


def _slugify_entity_id(entity_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", entity_id.strip().lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "entity"

def _compile_ui_lock_globals(project: dict) -> str:
    """Emit globals used for loop-avoidance (UI-originated actions vs HA→UI updates).

    v0.49:
    - Always emit a global lock timestamp `etd_ui_lock_until` (ms).
    - Emit per-entity locks for every bound entity_id: `etd_lock_<slug>`.
    - Emit per-link (entity + widget) locks for every project link target:
      `etd_lock_<slug>_<widget_id>`.
    """
    bindings = project.get("bindings") or []
    entity_ids: list[str] = []
    if isinstance(bindings, list):
        for b in sorted(bindings, key=lambda x: (str(x.get('kind') or 'state'), str(x.get('entity_id') or ''), str(x.get('attribute') or '')) ):
            if isinstance(b, dict):
                eid = str(b.get("entity_id") or "").strip()
                if eid and "." in eid:
                    entity_ids.append(eid)
    entity_ids = sorted(set(entity_ids))

    # Per-link locks are keyed by (entity_id, widget_id) so that UI-originated
    # service calls can suppress only the specific widget updates that would
    # otherwise “rubber-band”.
    # Container -> spinbox child (legacy grouped layout: display link may target container; lock is for the spinbox)
    def _container_spinbox_child_map() -> dict[str, str]:
        out: dict[str, str] = {}
        for page in project.get("pages") or []:
            if not isinstance(page, dict):
                continue
            for w in page.get("widgets") or []:
                if not isinstance(w, dict):
                    continue
                pid = w.get("parent_id")
                if pid and str(w.get("type") or "") == "spinbox" and w.get("id"):
                    out[str(pid)] = str(w["id"])
        return out

    def _widget_type_map_flat() -> dict[str, str]:
        m: dict[str, str] = {}
        for page in project.get("pages") or []:
            if not isinstance(page, dict):
                continue
            for w in page.get("widgets") or []:
                if isinstance(w, dict) and w.get("id"):
                    m[str(w["id"])] = str(w.get("type") or "label")
        return m

    container_spinbox_child = _container_spinbox_child_map()
    widget_type_by_id = _widget_type_map_flat()

    link_pairs: set[tuple[str, str]] = set()
    links = project.get("links") or []
    if isinstance(links, list):
        for ln in links:
            if not isinstance(ln, dict):
                continue
            src = ln.get("source") or {}
            tgt = ln.get("target") or {}
            eid = str(src.get("entity_id") or "").strip()
            raw_wid = tgt.get("widget_id")
            if isinstance(raw_wid, dict) and "id" in raw_wid:
                wid = str(raw_wid.get("id") or "").strip()
            elif isinstance(raw_wid, list) and raw_wid:
                first = raw_wid[0]
                wid = str(first.get("id", "") or "").strip() if isinstance(first, dict) else str(first or "").strip()
            else:
                wid = str(raw_wid or "").strip()
            if not eid or "." not in eid or not wid:
                continue
            action = str(tgt.get("action") or "").strip()
            if action == "label_text" and (widget_type_by_id.get(wid) or "label") == "container" and container_spinbox_child.get(wid):
                lock_wid = _safe_id(container_spinbox_child[wid])
            else:
                lock_wid = _safe_id(wid)
            link_pairs.add((eid, lock_wid))

    out: list[str] = []
    out.append("globals:\n")
    out.append("  - id: etd_ui_lock_until\n")
    out.append("    type: uint32_t\n")
    out.append("    restore_value: no\n")
    out.append("    initial_value: '0'\n")
    for eid in entity_ids:
        sid = _slugify_entity_id(eid)
        out.append(f"  - id: etd_lock_{sid}\n")
        out.append("    type: uint32_t\n")
        out.append("    restore_value: no\n")
        out.append("    initial_value: '0'\n")

    for eid, wid in sorted(link_pairs):
        sid = _slugify_entity_id(eid)
        out.append(f"  - id: etd_lock_{sid}_{wid}\n")
        out.append("    type: uint32_t\n")
        out.append("    restore_value: no\n")
        out.append("    initial_value: '0'\n")
    out.append("\n")
    return "".join(out)


# Design v2: section state for Components panel (empty | auto | edited)
SECTION_STATE_EMPTY = "empty"
SECTION_STATE_AUTO = "auto"
SECTION_STATE_EDITED = "edited"
COMPILER_OWNED_SECTIONS = frozenset({"lvgl"})

_LVGL_PAGES_MARKER = "#__LVGL_PAGES__"


def _replace_lvgl_pages_marker(section_body: str, compiler_lvgl: str) -> str:
    """Replace the entire line containing #__LVGL_PAGES__ with compiler output.

    Substring-only replace keeps the marker line's leading spaces, so the first injected line
    becomes doubly indented (e.g. ``buffer_size`` appears under ``touchscreens:`` and breaks YAML).
    """
    body = section_body or ""
    inj = (compiler_lvgl or "").rstrip()
    if _LVGL_PAGES_MARKER not in body:
        return body
    pattern = re.compile(r"^.*" + re.escape(_LVGL_PAGES_MARKER) + r".*$", re.MULTILINE)
    return pattern.sub(inj, body, count=1)


def _merge_lvgl_recipe_compiler(recipe_body: str | None, compiler_body: str | None) -> str:
    """Merge hardware recipe `lvgl` body with compiler-generated LVGL (config + pages + top_layer).

    Recipe files use `#__LVGL_PAGES__` as a placeholder; it is replaced by the full compiler
    emission so recipe keys (displays, byte_order, touchscreens, etc.) stay in the output.

    If the recipe omits the marker, compiler output wins when present (legacy behavior).
    """
    r = (recipe_body or "").rstrip()
    c = (compiler_body or "").rstrip()
    if not c:
        return r
    if _LVGL_PAGES_MARKER in r:
        return _replace_lvgl_pages_marker(r, c)
    return c


def _build_recipe_default_sections(recipe_text: str, device: object | None) -> dict[str, str]:
    """Build section key -> body from current recipe only (with substitutions). Used for Reset and for default_sections in panel v2."""
    recipe_sections = _parse_recipe_into_sections(recipe_text)
    pieces: dict[str, str] = {}
    for key in SECTION_ORDER:
        content = recipe_sections.get(key)
        if key == "esphome" and content and ETD_DEVICE_NAME_PLACEHOLDER not in content:
            if re.search(r"^\s*name\s*:", content, re.MULTILINE):
                content = re.sub(r"^(\s*name\s*:\s*).*$", r"\1" + ETD_DEVICE_NAME_PLACEHOLDER, content, count=1, flags=re.MULTILINE)
            else:
                content = "  name: " + ETD_DEVICE_NAME_PLACEHOLDER + "\n" + (content or "").lstrip()
        if not (content and str(content).strip()):
            if key == "wifi":
                content = _strip_section_key(_default_wifi_yaml(), "wifi")
            elif key == "ota":
                content = _strip_section_key(_default_ota_yaml(), "ota")
            elif key == "logger":
                content = _strip_section_key(_default_logger_yaml(), "logger")
        if content is not None and (key in ("wifi", "ota", "logger") or (content and str(content).strip())):
            pieces[key] = _section_full_block(key, (content or "").rstrip())
    if device is not None and getattr(device, "slug", None):
        _substitute_device_name_in_sections(pieces, device.slug)
    return {k: (_section_body_from_value(v, k) or "").rstrip() for k, v in pieces.items()}


def _build_default_section_pieces(
    project: dict,
    device: object | None,
    recipe_text: str,
) -> dict[str, str]:
    """Build section content from recipe + compiler only (no user edits). Used for Reset and initial populate."""
    recipe_sections = _parse_recipe_into_sections(recipe_text)
    compiler_sections = _build_compiler_sections(project, device)
    if "manage_run_and_sleep" in recipe_text and "id: manage_run_and_sleep" not in (compiler_sections.get("script") or "") and "id: manage_run_and_sleep" not in recipe_text:
        stub = "  - id: manage_run_and_sleep\n    then:\n      - delay: 1ms\n"
        current = (compiler_sections.get("script") or "").rstrip()
        compiler_sections["script"] = (current + "\n" + stub.rstrip() + "\n") if current else (stub.rstrip() + "\n")
    pieces: dict[str, str] = {}
    for key in SECTION_ORDER:
        if key == "lvgl":
            content = _merge_lvgl_recipe_compiler(
                recipe_sections.get(key), compiler_sections.get(key)
            )
        else:
            content = compiler_sections.get(key) or recipe_sections.get(key)
        if key == "esphome" and content and ETD_DEVICE_NAME_PLACEHOLDER not in content:
            if re.search(r"^\s*name\s*:", content, re.MULTILINE):
                content = re.sub(r"^(\s*name\s*:\s*).*$", r"\1" + ETD_DEVICE_NAME_PLACEHOLDER, content, count=1, flags=re.MULTILINE)
            else:
                content = "  name: " + ETD_DEVICE_NAME_PLACEHOLDER + "\n" + content.lstrip()
        if not (content and str(content).strip()):
            if key == "wifi":
                content = _strip_section_key(_default_wifi_yaml(), "wifi")
            elif key == "ota":
                content = _strip_section_key(_default_ota_yaml(), "ota")
            elif key == "logger":
                content = _strip_section_key(_default_logger_yaml(), "logger")
        if content is not None and (key in ("wifi", "ota", "logger") or (content and str(content).strip())):
            pieces[key] = _section_full_block(key, (content or "").rstrip())
    if device is not None and getattr(device, "slug", None):
        _substitute_device_name_in_sections(pieces, device.slug)
    return pieces


def _ensure_project_sections(project: dict, device: object | None, recipe_text: str) -> None:
    """Ensure project has 'sections' (full section YAML). Mutates project in place.
    Uses stored project.sections for keys that have content; fills missing/empty keys
    from compiler (esphome_components, HA bindings) and recipe. This ensures
    compiler-generated sections (e.g. interval, time from prebuilts) appear in the
    Components panel even when project.sections was previously saved without them.

    Legacy project.section_overrides is no longer used; all manual edits live in
    project.sections keyed by top-level section name.
    """
    stored = (project.get("sections") or {}) if isinstance(project.get("sections"), dict) else {}
    recipe_sections = _parse_recipe_into_sections(recipe_text)
    compiler_sections = _build_compiler_sections(project, device)
    if "manage_run_and_sleep" in recipe_text and "id: manage_run_and_sleep" not in (compiler_sections.get("script") or "") and "id: manage_run_and_sleep" not in recipe_text:
        stub = "  - id: manage_run_and_sleep\n    then:\n      - delay: 1ms\n"
        current = (compiler_sections.get("script") or "").rstrip()
        compiler_sections["script"] = (current + "\n" + stub.rstrip() + "\n") if current else (stub.rstrip() + "\n")
    pieces: dict[str, str] = {}
    for key in SECTION_ORDER:
        # Prefer stored (saved in Components) when present; otherwise fall back to compiler (prebuilts, HA bindings), then recipe.
        stored_body = _section_body_from_value(stored.get(key), key) if stored.get(key) else None
        if key == "lvgl":
            compiler_lvgl = compiler_sections.get(key) or ""
            recipe_lvgl = recipe_sections.get(key) or ""
            if (stored_body or "").strip():
                content = stored_body
                if _LVGL_PAGES_MARKER in content and compiler_lvgl.strip():
                    content = _replace_lvgl_pages_marker(content, compiler_lvgl)
            else:
                content = _merge_lvgl_recipe_compiler(recipe_lvgl, compiler_lvgl)
        else:
            content = (stored_body if (stored_body or "").strip() else None) or compiler_sections.get(key) or recipe_sections.get(key)
        if key == "esphome" and content and ETD_DEVICE_NAME_PLACEHOLDER not in content:
            if re.search(r"^\s*name\s*:", content, re.MULTILINE):
                content = re.sub(r"^(\s*name\s*:\s*).*$", r"\1" + ETD_DEVICE_NAME_PLACEHOLDER, content, count=1, flags=re.MULTILINE)
            else:
                content = "  name: " + ETD_DEVICE_NAME_PLACEHOLDER + "\n" + content.lstrip()
        if not (content and str(content).strip()):
            if key == "wifi":
                content = _strip_section_key(_default_wifi_yaml(), "wifi")
            elif key == "ota":
                content = _strip_section_key(_default_ota_yaml(), "ota")
            elif key == "logger":
                content = _strip_section_key(_default_logger_yaml(), "logger")
        if content is not None and (key in ("wifi", "ota", "logger") or (content and str(content).strip())):
            pieces[key] = _section_full_block(key, (content or "").rstrip())
    project["sections"] = pieces
    if device is not None and getattr(device, "slug", None):
        _substitute_device_name_in_sections(project["sections"], device.slug)


def _build_section_engine_pieces(
    project: dict,
    device: object | None,
    recipe_text: str,
) -> tuple[dict[str, str], set[str]]:
    """Engine: produce the final content for each section (recipe + compiler + sections).
    Returns (section_key -> content, set of keys that have user-added content in project.sections).

    Legacy: used by SectionsDefaultsView. New code should prefer project.sections +
    compiler merge in the main compile path.
    """
    stored = (project.get("sections") or {}) if isinstance(project.get("sections"), dict) else {}
    user_edited: set[str] = set(stored.keys())
    recipe_sections = _parse_recipe_into_sections(recipe_text)
    compiler_sections = _build_compiler_sections(project, device)

    if "manage_run_and_sleep" in recipe_text and "id: manage_run_and_sleep" not in (compiler_sections.get("script") or "") and "id: manage_run_and_sleep" not in recipe_text:
        stub = "  - id: manage_run_and_sleep\n    then:\n      - delay: 1ms\n"
        current = (compiler_sections.get("script") or "").rstrip()
        compiler_sections["script"] = (current + "\n" + stub.rstrip() + "\n") if current else (stub.rstrip() + "\n")

    pieces: dict[str, str] = {}
    for key in SECTION_ORDER:
        if key == "lvgl":
            compiler_lvgl = compiler_sections.get(key) or ""
            recipe_lvgl = recipe_sections.get(key) or ""
            stored_raw = stored.get(key)
            if stored_raw:
                content = _section_body_from_value(stored_raw, key) or ""
                if not (content or "").strip():
                    content = _merge_lvgl_recipe_compiler(recipe_lvgl, compiler_lvgl)
                elif _LVGL_PAGES_MARKER in content and compiler_lvgl.strip():
                    content = _replace_lvgl_pages_marker(content, compiler_lvgl)
            else:
                content = _merge_lvgl_recipe_compiler(recipe_lvgl, compiler_lvgl)
        else:
            raw = stored.get(key) or compiler_sections.get(key) or recipe_sections.get(key)
            content = _section_body_from_value(raw, key) if raw else (raw or "")
        if key == "esphome" and content and ETD_DEVICE_NAME_PLACEHOLDER not in content:
            if re.search(r"^\s*name\s*:", content, re.MULTILINE):
                content = re.sub(r"^(\s*name\s*:\s*).*$", r"\1" + ETD_DEVICE_NAME_PLACEHOLDER, content, count=1, flags=re.MULTILINE)
            else:
                content = "  name: " + ETD_DEVICE_NAME_PLACEHOLDER + "\n" + content.lstrip()
        if not (content and str(content).strip()):
            if key == "wifi":
                content = _strip_section_key(_default_wifi_yaml(), "wifi")
            elif key == "ota":
                content = _strip_section_key(_default_ota_yaml(), "ota")
            elif key == "logger":
                content = _strip_section_key(_default_logger_yaml(), "logger")
        if content is not None and (key in ("wifi", "ota", "logger") or (content and str(content).strip())):
            pieces[key] = _section_full_block(key, (content or "").rstrip())
            if key not in stored:
                user_edited.discard(key)
    return pieces, user_edited


def _sanitize_esphome_yaml_lvgl(yaml_text: str) -> str:
    """Final pass: ensure LVGL-related YAML is valid for ESPHome (works even if older code path produced it).
    - Quote buffer_size values that contain % (e.g. 100% -> \"100%\").
    - Normalize Python-style booleans to lowercase (True/False -> true/false) so ESPHome accepts them.
    """
    if not yaml_text or not yaml_text.strip():
        return yaml_text
    # buffer_size: 100% or buffer_size: 25% -> quoted when unquoted
    def _quote_buffer(m):
        val = m.group(2).rstrip()
        if "%" in val and not (val.startswith('"') and val.endswith('"')):
            return f"{m.group(1)} \"{val}\"\n"
        return m.group(0)
    yaml_text = re.sub(r"^(\s*buffer_size:)\s*(.*)$", _quote_buffer, yaml_text, flags=re.MULTILINE)
    # Python bools -> YAML lowercase (ESPHome rejects True/False)
    yaml_text = re.sub(r":\s*False\b", ": false", yaml_text)
    yaml_text = re.sub(r":\s*True\b", ": true", yaml_text)
    return yaml_text


def _compile_to_esphome_yaml_section_based(device: DeviceProject, recipe_text: str) -> str:
    """Compiler: Design v2 when project.esphome_yaml is set (stored YAML + compiler lvgl/list merge).
    Legacy: recipe + compiler + project.sections."""
    project = dict(device.project or {})
    use_stored_yaml = bool((project.get("esphome_yaml") or "").strip())
    stored_sections: dict[str, str] | None = _stored_sections_from_project(project) if use_stored_yaml else None
    stored_additions = (project.get("sections") or {}) if isinstance(project.get("sections"), dict) else {}
    auto_pieces = _build_default_section_pieces(project, device, recipe_text)
    # Script stub if recipe or user esphome references manage_run_and_sleep but script doesn't define it
    script_block = auto_pieces.get("script") or ""
    script_body = _section_body_from_value(script_block, "script") if script_block else ""
    esphome_body = _section_body_from_value(auto_pieces.get("esphome"), "esphome") or ""
    user_esphome_raw = (stored_sections.get("esphome") if stored_sections else stored_additions.get("esphome") or "").strip()
    if not user_esphome_raw and stored_additions:
        user_esphome_raw = (stored_additions.get("esphome") or "").strip()
    needs_stub = (
        "manage_run_and_sleep" in (esphome_body + user_esphome_raw + recipe_text)
        and "id: manage_run_and_sleep" not in (script_body or "")
    )
    if needs_stub:
        stub = "  - id: manage_run_and_sleep\n    then:\n      - delay: 1ms\n"
        script_body = (script_body.rstrip() + "\n" + stub.rstrip()) if script_body else stub.rstrip()
        auto_pieces["script"] = _section_full_block("script", script_body)

    LIST_SECTIONS: set[str] = {
        "sensor", "text_sensor", "binary_sensor", "switch", "number", "select", "light",
    }
    pieces: dict[str, str] = {}
    for key in SECTION_ORDER:
        auto_block = auto_pieces.get(key) or ""
        auto_body = (_section_body_from_value(auto_block, key) or "").rstrip() if auto_block else ""
        if stored_sections is not None:
            user_body = (stored_sections.get(key) or "").rstrip()
            if key == "lvgl":
                merged_body = auto_body
            elif key in LIST_SECTIONS:
                if user_body:
                    user_body = _normalize_section_body_indent(user_body).rstrip()
                if auto_body and user_body:
                    merged_body = _merge_list_section_bodies(auto_body, user_body)
                else:
                    merged_body = user_body or auto_body
            else:
                merged_body = user_body if user_body else auto_body
        else:
            user_raw = stored_additions.get(key) or ""
            user_body = (_section_body_from_value(user_raw, key) or "").rstrip() if user_raw else ""
            if user_body and key in LIST_SECTIONS:
                user_body = _normalize_section_body_indent(user_body).rstrip()
            if key in LIST_SECTIONS:
                if auto_body and user_body:
                    merged_body = _merge_list_section_bodies(auto_body, user_body)
                else:
                    merged_body = user_body or auto_body
            else:
                merged_body = user_body if user_body else auto_body
        if key == "interval":
            interval_from_links = _compile_interval_links_yaml(project)
            if interval_from_links:
                merged_body = ((merged_body or "").rstrip() + "\n\n" + interval_from_links).strip() if merged_body else interval_from_links
        if merged_body or key in ("wifi", "ota", "logger"):
            merged_body = (merged_body or "").lstrip("\n\r").rstrip()
            pieces[key] = _section_full_block(key, merged_body)
    header = (
        "---\n"
        f"# Generated by {DOMAIN} v{_integration_version()}\n"
        f"# device_id: {device.device_id}\n"
        f"# slug: {device.slug}\n"
        "\n"
    )
    display_id = _display_id_from_recipe(recipe_text)
    out_parts = [header]
    for key in SECTION_ORDER:
        if key not in pieces:
            continue
        block = pieces[key]
        content = _section_body_from_value(block, key)
        if key == "switch" and content:
            content = _inject_local_switch_links_into_section(content, project)
        if key == "climate" and content:
            content = _inject_local_climate_links_into_section(content, project)
        # Screen saver: inject on_touch into first touchscreen entry so touch wakes display
        if key == "touchscreen" and content:
            _has_ss, _ss_to, ss_backlight_id = _get_screensaver_config(project)
            if _has_ss:
                content = _inject_screensaver_on_touch_into_body(content, ss_backlight_id)
        # Minimal stub recipe uses id stub_display; lvgl body has no displays key, so prepend for "esphome config" to pass
        if key == "lvgl" and content and display_id == "stub_display" and "  displays:" not in content:
            content = "  displays:\n  - " + display_id + "\n" + content
        if key == "esphome" and content and ETD_DEVICE_NAME_PLACEHOLDER not in content:
            if re.search(r"^\s*name\s*:", content, re.MULTILINE):
                content = re.sub(r"^(\s*name\s*:\s*).*$", r"\1" + ETD_DEVICE_NAME_PLACEHOLDER, content, count=1, flags=re.MULTILINE)
            else:
                content = "  name: " + ETD_DEVICE_NAME_PLACEHOLDER + "\n" + content.lstrip()
        # Normalize globals/script indent: if body is over-indented (first list item at 4 spaces), strip 2 spaces from every line so ESPHome sees list at 2, keys at 4 (avoids "mapping values are not allowed")
        if key in ("globals", "script") and content and "\n" in content:
            first_line = content.splitlines()[0] if content.splitlines() else ""
            if first_line.startswith("    ") and not first_line.startswith("      "):
                content = "\n".join(ln[2:] if len(ln) >= 2 and ln.startswith("  ") else ln for ln in content.splitlines())
        # Ensure section body has at least 2-space base indent. Only add indent to lines with < 2
        # leading spaces (avoids over-indenting lines that already have correct indent, which would
        # produce invalid YAML like "  name: x\n    min_version: y" instead of "  name: x\n  min_version: y").
        if content and not content.startswith("  ") and "\n" in content:
            def _ensure_base_indent(ln: str) -> str:
                if not ln.strip():
                    return ln
                leading = len(ln) - len(ln.lstrip())
                return ("  " + ln) if leading < 2 else ln
            content = "\n".join(_ensure_base_indent(ln) for ln in content.splitlines())
        elif content and not content.startswith("  "):
            content = "  " + content
        out_parts.append(f"{key}:\n{content.rstrip()}\n\n")
    out = "".join(out_parts).rstrip() + "\n"
    out = out.replace(ETD_DEVICE_NAME_PLACEHOLDER, json.dumps(device.slug or "device"))
    out = _apply_wifi_settings(out, getattr(device, "device_settings", None))
    out = _apply_ota_password(out, getattr(device, "ota_password", None))
    out = _sanitize_esphome_yaml_lvgl(out)
    return out


def _sync_compile_device_yaml(
    hass: HomeAssistant,
    device: DeviceProject,
    project_override: dict | None = None,
    recipe_override: str | None = None,
) -> tuple[str, list]:
    """Sync helper: load recipe and compile device YAML. Run in executor to avoid blocking the event loop.
    Returns (yaml_text, warnings)."""
    recipe_text = _get_recipe_text_for_device(hass, device)
    if project_override is not None or recipe_override is not None:
        import copy
        device = copy.deepcopy(device)
        if project_override is not None:
            device.project = project_override
        if recipe_override is not None:
            device.hardware_recipe_id = recipe_override
        recipe_text = _get_recipe_text_for_device(hass, device)
    yaml_text = compile_to_esphome_yaml(device, recipe_text=recipe_text)
    yaml_text = yaml_text.replace(ETD_DEVICE_NAME_PLACEHOLDER, json.dumps(device.slug or "device"))
    warnings = _compile_warnings(device.project or {})
    return yaml_text, warnings


def compile_to_esphome_yaml(device: DeviceProject, recipe_text: str | None = None) -> str:
    """Compile a device project into a full ESPHome YAML document.

    Uses section-based compile when SECTION_ORDER is available: recipe is parsed into sections,
    merged with compiler output and project.sections (manual edits), then emitted in canonical order.
    """
    project = device.project or {}
    recipe_id = (
        (project.get("hardware") or {}).get("recipe_id")
        or device.hardware_recipe_id
        or "sunton_2432s028r_320x240"
    )
    if recipe_text is None:
        recipe_path = RECIPES_BUILTIN_DIR / f"{recipe_id}.yaml"
        recipe_text = recipe_path.read_text("utf-8") if recipe_path.exists() else ""

    recipe_text = _apply_user_injection(recipe_text, project)

    if SECTION_ORDER:
        return _compile_to_esphome_yaml_section_based(device, recipe_text)

    # Fallback when esphome_sections not available (legacy path)
    assets_yaml = _compile_assets(project)
    ha_bindings_yaml = _compile_ha_bindings(project)
    scripts_yaml = _compile_scripts(project)
    prebuilt_components_yaml = _compile_prebuilt_components(project)
    fonts_yaml, font_id_map = _compile_fonts_from_project(project)
    if font_id_map:
        project = _rewrite_widget_font_references(project, font_id_map)
    pages_yaml = _compile_lvgl_pages_schema_driven(project)
    locks_yaml = _compile_ui_lock_globals(project)
    if "#__HA_BINDINGS__" in recipe_text:
        recipe_text = recipe_text.replace("#__HA_BINDINGS__", ha_bindings_yaml.rstrip())
    elif ha_bindings_yaml.strip():
        recipe_text = recipe_text.rstrip() + "\n\n" + ha_bindings_yaml.rstrip() + "\n"
    merged = _inject_pages_into_recipe(recipe_text, pages_yaml)
    if "manage_run_and_sleep" in merged and "id: manage_run_and_sleep" not in scripts_yaml and "id: manage_run_and_sleep" not in merged:
        stub = "  - id: manage_run_and_sleep\n    then:\n      - delay: 1ms\n"
        scripts_yaml = scripts_yaml.rstrip() + "\n" + stub.rstrip() + "\n" if scripts_yaml.strip() else "script:\n" + stub
    esphome_block, rest = _split_esphome_block(merged)
    name_placeholder_line = "  name: " + ETD_DEVICE_NAME_PLACEHOLDER
    if not esphome_block.strip() and "esphome:" not in rest:
        esphome_block = "esphome:\n" + name_placeholder_line + "\n"
    elif not esphome_block.strip() and "esphome:" in rest:
        rest = re.sub(r"(?m)^((?:\ufeff)?\s*esphome:\s*(?:#.*)?)\r?\n", r"\1\n" + name_placeholder_line + r"\n", rest, count=1)
    else:
        lines = esphome_block.splitlines()
        if not lines:
            esphome_block = "esphome:\n" + name_placeholder_line + "\n"
        else:
            rest_lines = [ln for ln in lines[1:] if not re.match(r"^  name\s*:", ln)]
            first_line = lines[0].lstrip("\ufeff \t") or "esphome:"
            if first_line.startswith("esphome:"):
                first_line = "esphome:"
            esphome_block = first_line + "\n" + name_placeholder_line + "\n" + "\n".join(rest_lines) + ("\n" if rest_lines else "")
    def has_top_level_key(text: str, key: str) -> bool:
        t = "\n" + text
        return f"\n{key}:" in t or text.strip().startswith(f"{key}:")
    wifi_yaml = _default_wifi_yaml() if not has_top_level_key(rest, "wifi") else ""
    ota_yaml = _default_ota_yaml() if not has_top_level_key(rest, "ota") else ""
    logger_yaml = _default_logger_yaml() if not has_top_level_key(rest, "logger") else ""
    header = "---\n" + f"# Generated by {DOMAIN} v{_integration_version()}\n" + f"# device_id: {device.device_id}\n" + f"# slug: {device.slug}\n" + "\n"
    out = header
    if esphome_block.strip():
        out += esphome_block.rstrip() + "\n\n"
    if device.api_key and str(device.api_key).strip():
        out += "api:\n  encryption:\n    key: " + json.dumps(device.api_key.strip()) + "\n\n"
    if wifi_yaml:
        out += wifi_yaml.rstrip() + "\n\n"
    if ota_yaml:
        out += ota_yaml.rstrip() + "\n\n"
    if logger_yaml:
        out += logger_yaml.rstrip() + "\n\n"
    if has_top_level_key(rest, "script") and scripts_yaml.strip():
        rest = _merge_scripts_into_rest(rest, scripts_yaml)
        scripts_yaml = ""
    out += rest + "\n\n"
    if locks_yaml.strip():
        out += locks_yaml.rstrip() + "\n\n"
    if scripts_yaml.strip():
        out += scripts_yaml.rstrip() + "\n\n"
    if fonts_yaml.strip():
        out += fonts_yaml.rstrip() + "\n\n"
    if prebuilt_components_yaml.strip():
        out += prebuilt_components_yaml.rstrip() + "\n\n"
    if assets_yaml.strip():
        out += assets_yaml.rstrip() + "\n"
    out = out.replace(ETD_DEVICE_NAME_PLACEHOLDER, json.dumps(device.slug or "device"))
    out = _sanitize_esphome_yaml_lvgl(out)
    return out


def _compile_fonts_from_project(project: dict) -> tuple[str, dict[str, str]]:
    """Return (fonts_yaml, font_id_map).

    We support a lightweight descriptor format used in widget props:
      - font: "asset:MyFont.ttf:24"  -> emits an ESPHome `font:` entry and rewrites to generated id.

    Files are expected to be uploaded via the integration Assets API and stored under:
      /config/esptoolkit_assets
    """

    used: dict[tuple[str, int], str] = {}

    def scan_widget(w: dict):
        props = w.get("props") or {}
        f = props.get("font")
        if not isinstance(f, str):
            return
        f = f.strip()
        if not f.startswith("asset:"):
            return
        # asset:<filename>:<size>
        try:
            _, rest = f.split("asset:", 1)
            filename, size_s = rest.rsplit(":", 1)
            filename = filename.strip()
            size = int(size_s.strip())
            if not filename or size <= 0:
                return
            used.setdefault((filename, size), "")
        except Exception:
            return

    for page in (project.get("pages") or []):
        for w in (page.get("widgets") or []):
            scan_widget(w)

    if not used:
        return "", {}

    # Generate stable ids.
    font_id_map: dict[str, str] = {}
    lines = ["font:\n"]
    idx = 1
    for (filename, size) in sorted(used.keys()):
        safe = re.sub(r"[^a-zA-Z0-9_]+", "_", Path(filename).stem)
        fid = f"font_{safe}_{size}_{idx}"
        idx += 1
        used[(filename, size)] = fid
        font_id_map[f"asset:{filename}:{size}"] = fid
        lines.append(f"  - file: /config/{ASSETS_DIR}/{filename}\n")
        lines.append(f"    id: {fid}\n")
        lines.append(f"    size: {size}\n")

    return "".join(lines), font_id_map


def _rewrite_widget_font_references(project: dict, font_id_map: dict[str, str]) -> dict:
    # Deep copy with minimal overhead.
    p = json.loads(json.dumps(project))
    for page in (p.get("pages") or []):
        for w in (page.get("widgets") or []):
            props = w.get("props") or {}
            f = props.get("font")
            if isinstance(f, str):
                key = f.strip()
                if key in font_id_map:
                    props["font"] = font_id_map[key]
                    w["props"] = props
    return p

from aiohttp import web
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.http import HomeAssistantView

from ..const import (
    ASSETS_DIR,
    CONF_BASE_URL,
    CONF_TOKEN,
    CONFIG_DIR,
    DOMAIN,
    PLUGINS_DIR,
)
from ..storage import DeviceProject, _default_project


def _active_entry_id(hass: HomeAssistant) -> str | None:
    data = hass.data.get(DOMAIN, {})
    eid = data.get("active_entry_id")
    if eid and eid in data:
        return eid
    # Fallback: use first config entry (e.g. after unload/reload left active_entry_id cleared)
    for k, v in data.items():
        if k != "active_entry_id" and isinstance(v, dict) and "storage" in v:
            return k
    return None


def _get_storage(hass: HomeAssistant, entry_id: str):
    """Return storage for entry_id, or None if entry not loaded (e.g. stale or not yet set up)."""
    if not entry_id or entry_id not in hass.data.get(DOMAIN, {}):
        return None
    return hass.data[DOMAIN][entry_id].get("storage")


def _get_addon_connection(hass: HomeAssistant, entry_id: str | None = None) -> tuple[str, str] | None:
    """Return (base_url, token) from the active config entry (add-on writes these)."""
    eid = entry_id or _active_entry_id(hass)
    if not eid or eid not in hass.data.get(DOMAIN, {}):
        return None
    entry = hass.data[DOMAIN][eid].get("entry")
    if not entry or not entry.data:
        return None
    base_url = (entry.data.get(CONF_BASE_URL) or "").strip().rstrip("/")
    token = (entry.data.get(CONF_TOKEN) or "").strip()
    if base_url and token:
        return (base_url, token)
    return None


def _get_recipe_text_for_device(hass: HomeAssistant, device: DeviceProject) -> str:
    """Load recipe YAML text for a device (builtin or user recipe)."""
    proj = device.project or {}
    recipe_id = (
        device.hardware_recipe_id
        or (proj.get("device") or {}).get("hardware_recipe_id")
        or (proj.get("hardware") or {}).get("recipe_id")
        or ""
    )
    recipe_path = _find_recipe_path_by_id(hass, recipe_id) if recipe_id else None
    if not recipe_path or not recipe_path.exists():
        recipe_path = RECIPES_BUILTIN_DIR / f"{recipe_id}.yaml" if recipe_id else None
    return recipe_path.read_text("utf-8") if recipe_path and recipe_path.exists() else ""


async def _esphome_addon_request(
    hass: HomeAssistant,
    base_url: str,
    path: str,
    payload: dict,
    token: str | None = None,
) -> tuple[bool, str]:
    """Call ESPHome add-on HTTP API. Returns (ok, result_text). Path should be e.g. api/run, api/config-check."""
    import aiohttp
    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    headers = {"Content-Type": "application/json"}
    if token and token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"
    try:
        timeout = aiohttp.ClientTimeout(total=300)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=timeout) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    msg = text[:500]
                    if "application/json" in (resp.content_type or ""):
                        try:
                            import json as _json
                            data = _json.loads(text)
                            if isinstance(data, dict):
                                msg = (
                                    data.get("detail")
                                    or data.get("message")
                                    or data.get("error")
                                    or msg
                                )
                                if isinstance(msg, (list, dict)):
                                    msg = _json.dumps(msg)[:500]
                                else:
                                    msg = str(msg)[:500]
                        except Exception:
                            pass
                    return False, f"HTTP {resp.status}: {msg}"
                if "application/json" in (resp.content_type or ""):
                    try:
                        import json as _json
                        data = _json.loads(text)
                        result = data.get("result") if isinstance(data, dict) else text
                    except Exception:
                        result = text
                else:
                    result = text
                return True, str(result) if result is not None else text
    except asyncio.TimeoutError:
        return False, "Request timed out"
    except Exception as e:
        return False, str(e)


async def _esphome_addon_get(
    hass: HomeAssistant,
    base_url: str,
    path: str,
    token: str | None = None,
) -> tuple[bool, dict]:
    """Call ESPHome add-on HTTP API (GET JSON). Returns (ok, data)."""
    import aiohttp
    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    headers = {}
    if token and token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=timeout) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    return False, {"error": f"HTTP {resp.status}", "detail": text[:500]}
                try:
                    return True, await resp.json()
                except Exception:
                    return False, {"error": "invalid_json", "detail": text[:500]}
    except asyncio.TimeoutError:
        return False, {"error": "timeout", "detail": "Request timed out"}
    except Exception as e:
        return False, {"error": "request_failed", "detail": str(e)}


def _schemas_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "schemas" / "widgets"


# Widget types that exist in ESPHome LVGL (esphome/components/lvgl/widgets/*.py).
# Only these are shown in the Std LVGL palette.
PALETTE_WIDGET_TYPES = frozenset({
    "animimg", "arc", "bar", "button", "buttonmatrix", "canvas", "checkbox",
    "container", "dropdown", "image", "keyboard", "label", "led", "line", "meter", "msgboxes",
    "obj", "qrcode", "roller", "slider", "spinbox", "spinner", "switch", "tabview", "textarea",
    "tileview",
})
# Widget types we compile and edit but do not show in Std LVGL palette (e.g. designer-only widgets).
EXTRA_WIDGET_TYPES = frozenset({"arc_labeled", "color_picker", "white_picker", "spinbox2"})
COMPILABLE_WIDGET_TYPES = PALETTE_WIDGET_TYPES | EXTRA_WIDGET_TYPES
# Shown only via designer "Widgets" prebuilts, not Std LVGL schema list (/schemas/widgets).
WIDGETS_PANE_ONLY_SCHEMA_TYPES = frozenset({"spinbox2"})


def _common_extras_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "schemas"


# Widget types that do not display text (no label/caption); skip text-related style extras for these.
_WIDGET_TYPES_WITHOUT_TEXT = frozenset({
    "arc", "bar", "slider", "led", "line", "image", "animimg", "canvas", "spinner", "qrcode",
})
# Style keys that only affect text rendering; do not add to no-text widgets.
_TEXT_STYLE_KEYS = frozenset({
    "text_align", "text_decor", "text_letter_space", "text_line_space", "text_opa",
})


def _load_common_extras() -> dict:
    p = _common_extras_dir() / "common_extras.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return {}


def _merge_common_extras(schema: dict, widget_type: str | None = None) -> dict:
    """Merge common_extras (extra props/style/groups) into a widget schema.
    When widget_type is in _WIDGET_TYPES_WITHOUT_TEXT, text-related style extras and the
    'Text Style' group are not added, so the Properties panel only shows relevant fields."""
    extras = _load_common_extras()
    if not extras:
        return schema
    schema = dict(schema)
    skip_text_style = widget_type and widget_type.lower() in _WIDGET_TYPES_WITHOUT_TEXT
    # Merge props
    for k, v in (extras.get("props_extras") or {}).items():
        if k not in (schema.get("props") or {}):
            schema.setdefault("props", {})[k] = v
    # Merge style (skip text-related keys for widgets that don't display text)
    for k, v in (extras.get("style_extras") or {}).items():
        if skip_text_style and k in _TEXT_STYLE_KEYS:
            continue
        if k not in (schema.get("style") or {}):
            schema.setdefault("style", {})[k] = v
    # Merge state (state-based styling)
    for k, v in (extras.get("state_extras") or {}).items():
        if k not in (schema.get("state") or {}):
            schema.setdefault("state", {})[k] = v
    # Merge parts (e.g. scrollbar for scrollable widgets)
    for part_name, part_fields in (extras.get("parts_extras") or {}).items():
        for fk, fv in part_fields.items():
            if fk not in (schema.get(part_name) or {}):
                schema.setdefault(part_name, {})[fk] = fv
    # Merge esphome props mapping
    esphome = schema.get("esphome") or {}
    esphome = dict(esphome)
    for k, v in (extras.get("esphome_props_extras") or {}).items():
        if k not in (esphome.get("props") or {}):
            esphome.setdefault("props", {})[k] = v
    for k, v in (extras.get("esphome_style_extras") or {}).items():
        if skip_text_style and k in _TEXT_STYLE_KEYS:
            continue
        if k not in (esphome.get("style") or {}):
            esphome.setdefault("style", {})[k] = v
    schema["esphome"] = esphome
    # Merge groups (append new groups, don't overwrite; skip "Text Style" for no-text widgets)
    for name, grp in (extras.get("groups_extras") or {}).items():
        if skip_text_style and name == "Text Style":
            continue
        if name not in (schema.get("groups") or {}):
            schema.setdefault("groups", {})[name] = grp
    return schema


# --- v0.6: schema-driven widget emission ---
def _load_widget_schema(widget_type: str) -> dict | None:
    p = _schemas_dir() / f"{widget_type}.json"
    if not p.exists():
        return None
    schema = json.loads(p.read_text("utf-8"))
    return _merge_common_extras(schema, widget_type)


def _yaml_quote(v) -> str:
    # Use JSON quoting for strings to keep YAML safe (ESPHome accepts it)
    if isinstance(v, str):
        return json.dumps(v)
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None:
        return "null"
    return str(v)


# ESPHome event/action keys that expect a dict (then: / actions), not a literal string.
_ESPHOME_ACTION_KEYS = frozenset({"on_click", "on_press", "on_release", "on_value", "on_change", "on_focus", "on_defocus"})


def _color_value_for_esphome(key: str, value) -> str | int | None:
    """Convert CSS hex color (#rrggbb etc.) to integer for ESPHome LVGL (expects integer or 0x hex)."""
    if key != "color" and not (isinstance(key, str) and key.endswith("_color")):
        return value
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s.startswith("#"):
        return value  # CSS name or theme ref, leave as-is
    if re.match(r"^#[0-9A-Fa-f]{6}$", s):
        return int(s[1:7], 16)
    if re.match(r"^#[0-9A-Fa-f]{8}$", s):
        return int(s[1:7], 16)  # use RGB, ignore alpha
    if re.match(r"^#[0-9A-Fa-f]{3}$", s):
        # #rgb -> 0xRRGGBB
        r, g, b = int(s[1], 16) * 17, int(s[2], 16) * 17, int(s[3], 16) * 17
        return r << 16 | g << 8 | b
    return value


def _emit_kv(indent: str, key: str, value) -> str:
    """Emit a YAML key/value fragment.

    Notes:
      - We omit None/null values by default.
      - For action keys (on_release, etc.) with multiline values, emit as embedded YAML so
        ESPHome parses a dict (then: ...), not a literal string.
      - Other multiline strings use block scalar (|-).
      - For dropdown/roller "options", string values are normalized to a list (split by newline or \\n).
    """
    if value is None:
        return ""

    # ESPHome dropdown/roller expect options as a list; frontend may store as "a\\nb\\nc" or "a\nb\nc".
    if key == "options" and isinstance(value, str):
        raw = value.replace("\\n", "\n").replace("\\r", "")
        value = [s.strip() for s in raw.split("\n") if s.strip()]
        if not value:
            value = ["Option 1"]

    # LVGL line widget: points must be a list of "x, y" (two numbers per line); ESPHome does not accept quoted "0,0".
    if key == "points" and isinstance(value, list):
        out = [f"{indent}{key}:\n"]
        for item in value:
            if isinstance(item, str) and "," in item:
                parts = [p.strip() for p in item.split(",", 1)]
                if len(parts) == 2:
                    out.append(f"{indent}  - {parts[0]}, {parts[1]}\n")
                    continue
            out.append(f"{indent}  - {_yaml_quote(item)}\n")
        return "".join(out)

    if isinstance(value, list):
        out = [f"{indent}{key}:\n"]
        for item in value:
            out.append(f"{indent}  - {_yaml_quote(item)}\n")
        return "".join(out)

    if isinstance(value, dict):
        out = [f"{indent}{key}:\n"]
        for k, v in value.items():
            v = _color_value_for_esphome(k, v)
            out.append(f"{indent}  {k}: {_yaml_quote(v)}\n")
        return "".join(out)

    if isinstance(value, str) and "\n" in value:
        # Action keys must be a dict (then: ...); emit as embedded YAML, not literal.
        if key in _ESPHOME_ACTION_KEYS:
            out = [f"{indent}{key}:\n"]
            for ln in value.splitlines():
                out.append(f"{indent}  {ln}\n")
            return "".join(out)
        out = [f"{indent}{key}: |-\n"]
        for ln in value.splitlines():
            out.append(f"{indent}  {ln}\n")
        return "".join(out)

    value = _color_value_for_esphome(key, value)
    # LVGL/ESPHome expect some style enums in lowercase (e.g. text_align: center not CENTER)
    if key == "text_align" and isinstance(value, str):
        value = value.strip().lower()
    # LVGL led widget: brightness is a percentage; ESPHome expects e.g. "70%" (see esphome.io/components/lvgl/widgets).
    if key == "brightness" and isinstance(value, (int, float)):
        return f"{indent}{key}: {int(value)}%\n"
    # LVGL spinner: spin_time and arc_length use ESPHome time/angle format (e.g. "2s", "60deg").
    if key == "spin_time" and isinstance(value, (int, float)):
        return f"{indent}{key}: {int(value)}ms\n"
    if key == "arc_length" and isinstance(value, (int, float)):
        return f"{indent}{key}: {int(value)}deg\n"
    return f"{indent}{key}: {_yaml_quote(value)}\n"


# Sentinel in action_binding data: compiler replaces with lambda mapping selected index x -> option text (for dropdown/roller).
SELECT_OPTION_TEXT_SENTINEL = "!lambda SELECT_OPTION_TEXT"


def _action_binding_call_to_yaml(
    call: dict,
    widget_id: str | None = None,
    wtype: str | None = None,
    option_maps: dict[str, list[str]] | None = None,
) -> str:
    """Generate ESPHome YAML for homeassistant.action from action_binding call (domain, service, entity_id, data).
    If option_maps and widget_id are set, data values equal to SELECT_OPTION_TEXT_SENTINEL are expanded
    to a lambda that maps selected index x to the option string (for dropdown/roller -> set_hvac_mode etc).
    """
    if not isinstance(call, dict):
        return ""
    domain = str(call.get("domain") or "").strip()
    service = str(call.get("service") or "").strip()
    if not domain or not service:
        return ""
    # entity_id can be at call root (UI stores it there) or inside call.data
    data = call.get("data") or {}
    entity_id = call.get("entity_id") or data.get("entity_id")
    if entity_id is not None:
        entity_id = str(entity_id).strip() or None
    opts = []
    if option_maps and widget_id:
        opts = option_maps.get(widget_id) or []
    lines = [
        "then:",
        "  - homeassistant.action:",
        f"      action: {domain}.{service}",
        "      data:",
    ]
    # Always emit entity_id first so the service call targets the specific entity (e.g. climate.living_rm)
    if entity_id:
        lines.append(f"        entity_id: {json.dumps(str(entity_id))}")
    for k, v in data.items():
        if v is None:
            continue
        if k == "entity_id" and entity_id:
            continue  # already emitted above
        vstr = str(v).strip()
        if vstr == SELECT_OPTION_TEXT_SENTINEL and opts:
            # Map selected index x to option string for dropdown/roller
            parts = []
            for idx, opt in enumerate(opts):
                esc = str(opt).replace("\\", "\\\\").replace('"', '\\"')
                parts.append(f'if (x == {idx}) return "{esc}";')
            parts.append('return "";')
            lambda_body = " ".join(parts)
            lines.append(f"        {k}: !lambda '{lambda_body}'")
        elif vstr.startswith("!lambda"):
            lines.append(f"        {k}: {vstr}")
        else:
            lines.append(f"        {k}: {json.dumps(v)}")
    if not entity_id and not data:
        lines.append("        {}")
    return "\n".join(lines)


def _emit_widget_from_schema(
    widget: dict,
    schema: dict,
    action_bindings_for_widget: list | None = None,
    parent_w: int | None = None,
    parent_h: int | None = None,
    option_maps: dict[str, list[str]] | None = None,
    event_snippets_out: dict | None = None,
) -> str:
    wtype = widget.get("type") or schema.get("type")
    esphome = schema.get("esphome", {})
    root_key = esphome.get("root_key") or wtype  # e.g. "label", "button"
    # ESPHome animimg requires non-empty src; when missing/empty emit a container instead.
    # ESPHome buttonmatrix requires rows; when missing/empty emit a container instead.
    emit_container_only = False
    if root_key == "animimg":
        src = (widget.get("props") or {}).get("src")
        if not src or (isinstance(src, list) and len(src) == 0):
            root_key = "container"
            emit_container_only = True
    elif root_key == "buttonmatrix":
        rows = (widget.get("props") or {}).get("rows")
        if not rows or (isinstance(rows, list) and len(rows) == 0):
            root_key = "container"
            emit_container_only = True
    elif root_key == "image":
        src = (widget.get("props") or {}).get("src")
        if not src or (isinstance(src, str) and not src.strip()):
            root_key = "container"
            emit_container_only = True

    # Widget list item: "- type:" then properties indented 2 more (YAML: value of single key for ESPHome)
    body_indent = "            "  # 12 spaces: value under "- container:" so parser sees one key per list item
    out: list[str] = []
    out.append(f"        - {root_key}:\n")

    # geometry: x, y may need conversion when align is not TOP_LEFT
    # LVGL: "If specifying align, x and y can be used as an offset to the calculated position"
    # We store top-left coords; with CENTER LVGL expects offset from parent center.
    wid = widget.get("id") or "w"
    out.append(f"{body_indent}id: {wid}\n")
    x_val = int(widget.get("x", 0))
    y_val = int(widget.get("y", 0))
    w_val = int(widget.get("w", 100))
    h_val = int(widget.get("h", 50))
    align = str((widget.get("props") or {}).get("align", "TOP_LEFT") or "TOP_LEFT").strip().upper()
    if align and align != "TOP_LEFT" and parent_w is not None and parent_h is not None:
        # Convert top-left coords to LVGL's expected offset for non-default align
        pw2, ph2 = parent_w // 2, parent_h // 2
        if align == "CENTER":
            x_val = x_val + w_val // 2 - pw2
            y_val = y_val + h_val // 2 - ph2
        elif align == "TOP_MID":
            x_val = x_val + w_val // 2 - pw2
        elif align == "TOP_RIGHT":
            x_val = x_val + w_val - parent_w
        elif align == "LEFT_MID":
            y_val = y_val + h_val // 2 - ph2
        elif align == "RIGHT_MID":
            x_val = x_val + w_val - parent_w
            y_val = y_val + h_val // 2 - ph2
        elif align == "BOTTOM_LEFT":
            y_val = y_val + h_val - parent_h
        elif align == "BOTTOM_MID":
            x_val = x_val + w_val // 2 - pw2
            y_val = y_val + h_val - parent_h
        elif align == "BOTTOM_RIGHT":
            x_val = x_val + w_val - parent_w
            y_val = y_val + h_val - parent_h
    props_geom = widget.get("props") or {}
    w_emit = props_geom.get("width_override") or w_val
    h_emit = props_geom.get("height_override") or h_val
    for geom_key, yaml_key, val in [("x", "x", x_val), ("y", "y", y_val), ("w", "width", w_emit), ("h", "height", h_emit)]:
        if geom_key not in widget and yaml_key not in ("width", "height"):
            continue
        if yaml_key == "width" and not props_geom.get("width_override") and geom_key not in widget:
            continue
        if yaml_key == "height" and not props_geom.get("height_override") and geom_key not in widget:
            continue
        if yaml_key in ("width", "height") and isinstance(val, str):
            out.append(f'{body_indent}{yaml_key}: "{val}"\n')
        else:
            out.append(f"{body_indent}{yaml_key}: {int(val)}\n")

    if emit_container_only:
        return "\n".join(out)

    action_by_event = {}
    if action_bindings_for_widget:
        for ab in action_bindings_for_widget:
            if isinstance(ab, dict) and ab.get("event"):
                action_by_event[str(ab["event"])] = ab

    def _maybe_harden_event(yaml_key: str, v):
        # v0.37: best-effort runtime hardening for high-frequency controls.
        # Many HA controls (sliders) can spam service calls while dragging.
        # We don't have full bidirectional loop-avoidance yet, but a small
        # delay helps collapse bursts when combined with ESPHome's internal
        # action queue.
        if section != "events":
            return v
        if not isinstance(v, str):
            return v
        if yaml_key not in ("on_value", "on_press", "on_release"):
            return v
        if "homeassistant.action" not in v:
            return v
        if "delay" in v:
            return v
        # v0.47: add lightweight loop-avoidance + delay after `then:` if present.
        # If we can extract an entity_id from the YAML snippet, also set a per-entity lock.
        m_eid = re.search(r"^\s*entity_id:\s*([A-Za-z0-9_]+\.[A-Za-z0-9_]+)\s*$", v, re.M)
        lock_lines = []
        # Always set the global lock.
        lock_lines.append("  - lambda: id(etd_ui_lock_until) = millis() + 500;")
        if m_eid:
            sid = _slugify_entity_id(m_eid.group(1))
            lock_lines.append(f"  - lambda: id(etd_lock_{sid}) = millis() + 500;")
            # v0.49: also set a per-link (entity+widget) lock if this widget has
            # HA links, so HA→UI updates for the same entity/widget are paused.
            wid_safe = _safe_id(str(wid))
            lock_lines.append(f"  - lambda: id(etd_lock_{sid}_{wid_safe}) = millis() + 500;")

        lines = v.splitlines()
        out = []
        inserted = False
        for ln in lines:
            out.append(ln)
            if not inserted and ln.strip() == "then:":
                # Insert lock(s) first, then a small delay to reduce burst spam.
                out.extend(lock_lines)
                out.append("  - delay: 150ms")
                inserted = True
        return "\n".join(out)

    for section in ("props", "style", "events"):
        mapping = (esphome.get(section) or {})
        fields = schema.get(section) or {}
        values = dict(widget.get(section) or {})
        # ESPHome animimg requires duration when src is present; default when missing.
        if section == "props" and root_key == "animimg":
            if not values.get("duration") and "duration" not in values:
                values["duration"] = "1000ms"
        # For events: prefer action_binding for this widget (yaml_override or generated from call).
        event_source: dict[str, str] = {}  # event_key -> "auto" | "edited"
        if section == "events" and action_by_event:
            for event_key, ab in action_by_event.items():
                if ab.get("yaml_override"):
                    values[event_key] = ab.get("yaml_override")
                    event_source[event_key] = "edited"
                elif ab.get("call"):
                    values[event_key] = _action_binding_call_to_yaml(
                        ab["call"], widget_id=wid, wtype=wtype, option_maps=option_maps
                    )
                    event_source[event_key] = "auto"
                # else keep widget.events[event_key] if present
        for k, field_def in fields.items():
            if k in ("align_to_id", "align_to_align", "align_to_x", "align_to_y", "width_override", "height_override"):
                continue  # align_to -> block below; width/height_override -> used in geometry
            # Designer-only keys for arc/arc_labeled: never emit (ESPHome arc has no such options).
            if section == "style" and root_key == "arc" and k in ("tick_color", "tick_width", "tick_length", "label_text_color", "label_text_font", "label_font_size", "tick_interval", "label_interval"):
                continue
            # Only emit props/style keys that are in the esphome mapping (designer-only keys are omitted).
            if section in ("props", "style") and k not in mapping:
                continue
            yaml_key = mapping.get(k, k)
            if k in values and values[k] not in (None, ""):
                v = values[k]
                if section == "props" and isinstance(field_def, dict) and field_def.get("type") == "yaml_block" and isinstance(v, str) and "\n" in v:
                    out.append(f"{body_indent}{yaml_key}:\n")
                    for line in v.strip().split("\n"):
                        out.append(f"{body_indent}  {line}\n")
                else:
                    emitted_val = _maybe_harden_event(yaml_key, v) if section == "events" else v
                    # LVGL switch widget: state must be a dict { checked: bool }, not a bare bool (ESPHome expects a dictionary).
                    if section == "props" and yaml_key == "state" and isinstance(emitted_val, bool) and wtype == "switch":
                        emitted_val = {"checked": emitted_val}
                    out.append(_emit_kv(body_indent, yaml_key, emitted_val))
                    if section == "events" and event_snippets_out is not None:
                        event_snippets_out[k] = {"yaml": (emitted_val if isinstance(emitted_val, str) else str(emitted_val)), "source": event_source.get(k, "edited")}
            else:
                if field_def.get("compiler_emit_default", False) and "default" in field_def:
                    default_val = field_def.get("default")
                    if section == "props" and yaml_key == "state" and isinstance(default_val, bool) and wtype == "switch":
                        default_val = {"checked": default_val}
                    # yaml_block defaults (e.g. meter scales) must be embedded YAML (dict), not a literal block (|-).
                    if section == "props" and field_def.get("type") == "yaml_block" and isinstance(default_val, str) and default_val.strip():
                        out.append(f"{body_indent}{yaml_key}:\n")
                        for line in default_val.strip().split("\n"):
                            out.append(f"{body_indent}  {line}\n")
                    else:
                        out.append(_emit_kv(body_indent, yaml_key, default_val))
        # Emit action_binding events that are not in schema (e.g. arc on_release when schema has events: {}).
        if section == "events" and action_by_event:
            for event_key, ab in action_by_event.items():
                if event_key in fields:
                    continue  # already emitted above
                yaml_key = (esphome.get("events") or {}).get(event_key) or event_key
                if ab.get("yaml_override"):
                    emitted_val = _maybe_harden_event(yaml_key, ab["yaml_override"])
                    out.append(_emit_kv(body_indent, yaml_key, emitted_val))
                    if event_snippets_out is not None:
                        event_snippets_out[event_key] = {"yaml": emitted_val, "source": "edited"}
                elif ab.get("call"):
                    emitted_val = _maybe_harden_event(yaml_key, _action_binding_call_to_yaml(
                        ab["call"], widget_id=wid, wtype=wtype, option_maps=option_maps
                    ))
                    out.append(_emit_kv(body_indent, yaml_key, emitted_val))
                    if event_snippets_out is not None:
                        event_snippets_out[event_key] = {"yaml": emitted_val, "source": "auto"}
        # v0.70.138: Emit custom_events from widget (user-defined native YAML events)
        if section == "events":
            custom_events = widget.get("custom_events") or {}
            for event_key, event_yaml in custom_events.items():
                if not event_yaml or not str(event_yaml).strip():
                    continue
                # Skip if already emitted from action_bindings or schema
                if event_key in (values or {}) or event_key in action_by_event:
                    continue
                yaml_key = (esphome.get("events") or {}).get(event_key) or event_key
                emitted_val = str(event_yaml).strip()
                out.append(_emit_kv(body_indent, yaml_key, emitted_val))
                if event_snippets_out is not None:
                    event_snippets_out[event_key] = {"yaml": emitted_val, "source": "edited"}
            # Fill empty for any event key we consider but did not emit
            if event_snippets_out is not None:
                all_event_keys = set(fields.keys()) | set(action_by_event.keys()) | set(custom_events.keys())
                for ev in all_event_keys:
                    if ev not in event_snippets_out:
                        event_snippets_out[ev] = {"yaml": "", "source": "empty"}

    # align_to: position relative to another widget (from props align_to_*)
    props = widget.get("props") or {}
    if props.get("align_to_id"):
        out.append(f"{body_indent}align_to:\n")
        out.append(f"{body_indent}  - id: {props.get('align_to_id')}\n")
        out.append(f"{body_indent}    align: {props.get('align_to_align') or 'OUT_TOP_LEFT'}\n")
        out.append(f"{body_indent}    x: {props.get('align_to_x', 0)}\n")
        out.append(f"{body_indent}    y: {props.get('align_to_y', 0)}\n")

    # Style parts and nested blocks: any schema section that is a dict of field defs (not props/style/events)
    _skip = {"props", "style", "events", "type", "title", "esphome", "groups"}
    for part_section, part_fields in (schema or {}).items():
        if part_section in _skip or not isinstance(part_fields, dict):
            continue
        def _is_field_def(d):
            return isinstance(d, dict) and ("type" in d or "default" in d)

        def _has_field_defs(v):
            if _is_field_def(v):
                return True
            if isinstance(v, dict):
                return any(_is_field_def(x) or _has_field_defs(x) for x in v.values())
            return False

        if not part_fields or not any(_has_field_defs(v) for v in part_fields.values()):
            continue
        values = widget.get(part_section) or {}
        if not values:
            continue
        # state section with _yaml: emit raw YAML block (pressed/checked/etc.)
        if part_section == "state" and isinstance(values.get("_yaml"), str) and values.get("_yaml").strip():
            out.append(f"{body_indent}state:\n")
            for line in values["_yaml"].strip().split("\n"):
                out.append(f"{body_indent}  {line}\n")
            continue
        out.append(f"{body_indent}{part_section}:\n")
        for k, field_def in part_fields.items():
            v = values.get(k)
            if v is None or v == "":
                continue
            out.append(_emit_kv(body_indent + "  ", k, v))

    return "".join(out)


def _esphome_safe_page_id(pid: str) -> str:
    """Return an ESPHome-safe page id for emitted YAML. ESPHome generates C++ from page ids;
    'main' is reserved (C++ entry point), so we emit 'main_page' instead."""
    s = (pid or "").strip()
    return "main_page" if s == "main" else (s or "main_page")


def _hex_color_for_yaml(v) -> str | int | None:
    """Convert #rrggbb or #rgb to 0xRRGGBB integer for LVGL YAML."""
    if not isinstance(v, str):
        return v
    s = v.strip()
    if s.startswith("#") and re.match(r"^#[0-9A-Fa-f]{6}$", s):
        return int(s[1:7], 16)
    if s.startswith("#") and re.match(r"^#[0-9A-Fa-f]{3}$", s):
        r, g, b = int(s[1], 16) * 17, int(s[2], 16) * 17, int(s[3], 16) * 17
        return r << 16 | g << 8 | b
    return v


def _value_to_angle_deg(
    rotation: float,
    start_angle: float,
    end_angle: float,
    mode: str,
    min_val: float,
    max_val: float,
    value: float,
) -> float:
    """Map value to world angle (degrees [0, 360)) for tick/label placement. Matches frontend valueToAngle."""
    sweep_cw = (end_angle - start_angle + 360) % 360 or 360
    t = (value - min_val) / (max_val - min_val) if max_val > min_val else 0.5
    clamped_t = max(0.0, min(1.0, t))
    if mode == "REVERSE":
        arc_deg = start_angle + (1 - clamped_t) * sweep_cw
    elif mode == "SYMMETRICAL":
        mid = start_angle + sweep_cw / 2
        arc_deg = mid + clamped_t * (sweep_cw / 2)
    else:
        arc_deg = start_angle + clamped_t * sweep_cw
    return (rotation + arc_deg + 720) % 360


def _emit_style_dict(indent: str, d: dict, key_filter: set | None = None) -> str:
    """Emit a flat or nested style dict as YAML. Color-like keys get 0xRRGGBB."""
    out: list[str] = []
    for k, v in (d or {}).items():
        if key_filter is not None and k not in key_filter:
            continue
        if v is None or v == "":
            continue
        if isinstance(v, dict) and not isinstance(v.get("_raw"), str):
            out.append(f"{indent}{k}:\n")
            out.append(_emit_style_dict(indent + "  ", v))
            continue
        if k.endswith("_color") or k == "color":
            v = _hex_color_for_yaml(v) if isinstance(v, str) else v
        if isinstance(v, str) and "\n" in v:
            out.append(f"{indent}{k}: |-\n")
            for line in v.splitlines():
                out.append(f"{indent}  {line}\n")
        else:
            out.append(f"{indent}{k}: {v}\n")
    return "".join(out)


def _collect_color_picker_defaults(project: dict) -> list[tuple[str, str, int]]:
    """Collect (wid, wid_safe, initial_color) for color_picker widgets that have no action binding for on_click.
    These get the overlay (open script) on tap; we ignore legacy custom_events.on_click so overlay always wins."""
    pages = project.get("pages") or []
    action_bindings_by_widget: dict[str, list[dict]] = {}
    for ab in project.get("action_bindings") or []:
        if not isinstance(ab, dict):
            continue
        wid = str(ab.get("widget_id") or "").strip()
        if wid:
            action_bindings_by_widget.setdefault(wid, []).append(ab)
    has_on_click_binding: set[str] = set()
    for wid, ab_list in action_bindings_by_widget.items():
        for ab in ab_list:
            if str(ab.get("event") or "").strip().lower() == "on_click":
                has_on_click_binding.add(wid)
                break
    out: list[tuple[str, str, int]] = []

    def walk_widgets(widgets: list) -> None:
        for w in widgets or []:
            if not isinstance(w, dict):
                continue
            if str(w.get("type") or "") == "color_picker":
                wid = str(w.get("id") or "").strip()
                if not wid or wid in has_on_click_binding:
                    continue
                wid_safe = _safe_id(wid)
                props = w.get("props") or {}
                style = w.get("style") or {}
                raw = props.get("value") or style.get("bg_color") or 0x4080FF
                if isinstance(raw, str) and raw.strip().startswith("#"):
                    s = raw.strip()
                    if re.match(r"^#[0-9A-Fa-f]{6}$", s):
                        initial = int(s[1:7], 16)
                    elif re.match(r"^#[0-9A-Fa-f]{3}$", s):
                        r, g, b = int(s[1], 16) * 17, int(s[2], 16) * 17, int(s[3], 16) * 17
                        initial = r << 16 | g << 8 | b
                    else:
                        initial = 0x4080FF
                else:
                    initial = int(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else 0x4080FF
                out.append((wid, wid_safe, initial))
            walk_widgets(w.get("widgets") or [])

    for page in pages:
        if not isinstance(page, dict):
            continue
        walk_widgets(page.get("widgets") or [])
    return out


def _compile_color_picker_globals(cpicker_defaults: list[tuple[str, str, int]]) -> str:
    """Emit globals for color picker: cycle index, overlay hue/sat/result (for hue/sat picker on device)."""
    if not cpicker_defaults:
        return ""
    out: list[str] = []
    for _wid, wid_safe, _initial in cpicker_defaults:
        out.append(f"  - id: etd_cp_{wid_safe}_idx\n")
        out.append("    type: int\n")
        out.append("    restore_value: no\n")
        out.append("    initial_value: '0'\n")
        out.append(f"  - id: etd_cp_{wid_safe}_hue\n")
        out.append("    type: int\n")
        out.append("    restore_value: no\n")
        out.append("    initial_value: '210'\n")
        out.append(f"  - id: etd_cp_{wid_safe}_sat\n")
        out.append("    type: int\n")
        out.append("    restore_value: no\n")
        out.append("    initial_value: '100'\n")
        out.append(f"  - id: etd_cp_{wid_safe}_result\n")
        out.append("    type: int\n")
        out.append("    restore_value: no\n")
        out.append("    initial_value: '0'\n")
    return "globals:\n" + "".join(out).rstrip() + "\n" if out else ""


def _compile_color_picker_scripts(cpicker_defaults: list[tuple[str, str, int]], project: dict) -> str:
    """Emit script: open overlay, apply (HSV->RGB + update style + hide), cancel (hide), and legacy cycle.
    When a display link 'Set button colour' exists for a colour picker to a light entity, Apply also calls light.turn_on with rgb_color."""
    if not cpicker_defaults:
        return ""
    # Map color_picker widget_id -> entity_id for links with action button_bg_color (so Apply can send colour to HA)
    cpicker_entity_by_wid: dict[str, str] = {}
    for ln in project.get("links") or []:
        if not isinstance(ln, dict):
            continue
        tgt = ln.get("target") or {}
        if str(tgt.get("action") or "").strip() != "button_bg_color":
            continue
        raw_wid = tgt.get("widget_id")
        if isinstance(raw_wid, dict) and "id" in raw_wid:
            wid = str(raw_wid.get("id") or "").strip()
        elif isinstance(raw_wid, list) and len(raw_wid):
            wid = str(raw_wid[0] if not isinstance(raw_wid[0], dict) else raw_wid[0].get("id", "") or "").strip()
        else:
            wid = str(raw_wid or "").strip()
        if not wid:
            continue
        src = ln.get("source") or {}
        eid = str(src.get("entity_id") or "").strip()
        if eid and "." in eid:
            cpicker_entity_by_wid[wid] = eid
    colors = [0xFF0000, 0x00FF00, 0x0000FF, 0xFFFF00, 0xFF00FF, 0x00FFFF, 0xFFFFFF, 0x4080FF]
    out: list[str] = []
    for _wid, wid_safe, _initial in cpicker_defaults:
        style_id = f"etd_cp_{wid_safe}"
        overlay_id = f"etd_cp_overlay_{wid_safe}"
        slider_id = f"etd_cp_slider_{wid_safe}"
        sat_slider_id = f"etd_cp_sat_{wid_safe}"
        # Open overlay: sync hue and sat sliders from globals, then show overlay
        out.append(f"  - id: etd_cp_{wid_safe}_open\n")
        out.append("    then:\n")
        out.append(f"      - lvgl.slider.update:\n")
        out.append(f"          id: {slider_id}\n")
        out.append(f"          value: !lambda 'return id(etd_cp_{wid_safe}_hue);'\n")
        out.append(f"      - lvgl.slider.update:\n")
        out.append(f"          id: {sat_slider_id}\n")
        out.append(f"          value: !lambda 'return id(etd_cp_{wid_safe}_sat);'\n")
        out.append(f"      - lvgl.widget.show: {overlay_id}\n")
        # Apply: HSV to RGB, update style, hide overlay; optionally call light.turn_on with rgb_color
        out.append(f"  - id: etd_cp_{wid_safe}_apply\n")
        out.append("    then:\n")
        out.append("      - lambda: |-\n")
        out.append("          float h = id(etd_cp_" + wid_safe + "_hue) / 60.0f;\n")
        out.append("          float s = id(etd_cp_" + wid_safe + "_sat) / 100.0f;\n")
        out.append("          float v = 1.0f;\n")
        out.append("          float c = v * s;\n")
        out.append("          float x_ = c * (1.0f - fabs(fmod(h, 2.0f) - 1.0f));\n")
        out.append("          float m = v - c;\n")
        out.append("          float r = 0, g = 0, b = 0;\n")
        out.append("          if (h < 1.0f) { r = c; g = x_; b = 0; }\n")
        out.append("          else if (h < 2.0f) { r = x_; g = c; b = 0; }\n")
        out.append("          else if (h < 3.0f) { r = 0; g = c; b = x_; }\n")
        out.append("          else if (h < 4.0f) { r = 0; g = x_; b = c; }\n")
        out.append("          else if (h < 5.0f) { r = x_; g = 0; b = c; }\n")
        out.append("          else { r = c; g = 0; b = x_; }\n")
        out.append("          id(etd_cp_" + wid_safe + "_result) = ((int)((r+m)*255) << 16) | ((int)((g+m)*255) << 8) | (int)((b+m)*255);\n")
        out.append(f"      - lvgl.style.update:\n")
        out.append(f"          id: {style_id}\n")
        out.append(f"          bg_color: !lambda 'return lv_color_hex(id(etd_cp_{wid_safe}_result));'\n")
        out.append(f"      - lvgl.widget.hide: {overlay_id}\n")
        out.append(f"      - lvgl.widget.redraw:\n")
        out.append(f"          id: {_wid}\n")
        entity_id = cpicker_entity_by_wid.get(_wid)
        if entity_id and entity_id.startswith("light."):
            # ESPHome homeassistant.action does not accept a list for rgb_color; call our integration's service (scalars only)
            out.append("      - homeassistant.action:\n")
            out.append(f"          action: {DOMAIN}.set_light_rgb\n")
            out.append("          data:\n")
            out.append(f"            entity_id: {json.dumps(entity_id)}\n")
            out.append(f"            red: !lambda 'return (id(etd_cp_{wid_safe}_result) >> 16) & 0xFF;'\n")
            out.append(f"            green: !lambda 'return (id(etd_cp_{wid_safe}_result) >> 8) & 0xFF;'\n")
            out.append(f"            blue: !lambda 'return id(etd_cp_{wid_safe}_result) & 0xFF;'\n")
        # Cancel: hide overlay
        out.append(f"  - id: etd_cp_{wid_safe}_cancel\n")
        out.append("    then:\n")
        out.append(f"      - lvgl.widget.hide: {overlay_id}\n")
        # Legacy cycle script (optional; open is the default on_click now)
        out.append(f"  - id: etd_cp_{wid_safe}_cycle\n")
        out.append("    then:\n")
        out.append(f"      - lambda: id(etd_cp_{wid_safe}_idx) = (id(etd_cp_{wid_safe}_idx) + 1) % 8;\n")
        for i, col in enumerate(colors):
            out.append("      - if:\n")
            out.append(f"          condition:\n            lambda: 'return id(etd_cp_{wid_safe}_idx) == {i};'\n")
            out.append("          then:\n")
            out.append("            - lvgl.style.update:\n")
            out.append(f"                id: {style_id}\n")
            out.append(f"                bg_color: 0x{col:06X}\n")
        # Sync button colour from HA (in case on_value doesn't fire for attribute-only changes)
        entity_id = cpicker_entity_by_wid.get(_wid)
        if entity_id and entity_id.startswith("light."):
            sensor_id = f"ha_txt_{_safe_id(entity_id)}_rgb_color"
            out.append(f"  - id: etd_cp_{wid_safe}_sync_ha_rgb\n")
            out.append("    then:\n")
            out.append("      - if:\n")
            out.append("          condition:\n")
            out.append("            lambda: |-\n")
            out.append(f"              auto s = id({sensor_id}).state;\n")
            out.append(
                "              return s.size() >= 9 && ( (s.find('[') != std::string::npos && s.find(']') != std::string::npos) || (s.find('(') != std::string::npos && s.find(')') != std::string::npos) );\n"
            )
            out.append("          then:\n")
            out.append("            - lvgl.obj.update:\n")
            out.append(f"                id: {_wid}\n")
            out.append("                bg_color: !lambda |-\n")
            out.append(f"                  auto s = id({sensor_id}).state;\n")
            out.append("                  int r=0,g=0,b=0;\n")
            out.append("                  if (s.size() >= 5) {\n")
            out.append('                    if (sscanf(s.c_str(), "[%d,%d,%d]", &r, &g, &b) != 3)\n')
            out.append('                      sscanf(s.c_str(), "(%d, %d, %d)", &r, &g, &b);\n')
            out.append("                    if (r==0 && g==0 && b==0) sscanf(s.c_str(), \"%d,%d,%d\", &r, &g, &b);\n")
            out.append("                  }\n")
            out.append("                  return lv_color_hex((r<<16)|(g<<8)|b);\n")
            out.append("            - lvgl.widget.redraw:\n")
            out.append(f"                id: {_wid}\n")
    return "script:\n" + "".join(out).rstrip() + "\n" if out else ""


def _compile_color_picker_sync_interval(project: dict, cpicker_defaults: list[tuple[str, str, int]]) -> str:
    """Emit interval that runs HA→button sync scripts every 5s so button updates even if on_value doesn't fire for attribute-only changes."""
    cpicker_entity_by_wid: dict[str, str] = {}
    for ln in project.get("links") or []:
        if not isinstance(ln, dict):
            continue
        tgt = ln.get("target") or {}
        if str(tgt.get("action") or "").strip() != "button_bg_color":
            continue
        raw_wid = tgt.get("widget_id")
        if isinstance(raw_wid, dict) and "id" in raw_wid:
            wid = str(raw_wid.get("id") or "").strip()
        elif isinstance(raw_wid, list) and len(raw_wid):
            wid = str(raw_wid[0] if not isinstance(raw_wid[0], dict) else raw_wid[0].get("id", "") or "").strip()
        else:
            wid = str(raw_wid or "").strip()
        if not wid:
            continue
        src = ln.get("source") or {}
        eid = str(src.get("entity_id") or "").strip()
        if eid and "." in eid and eid.startswith("light."):
            cpicker_entity_by_wid[wid] = eid
    sync_scripts = []
    for _wid, wid_safe, _initial in cpicker_defaults:
        if cpicker_entity_by_wid.get(_wid):
            sync_scripts.append(f"etd_cp_{wid_safe}_sync_ha_rgb")
    if not sync_scripts:
        return ""
    lines = ["  - interval: 5s", "    then:"]
    for sid in sync_scripts:
        lines.append(f"      - script.execute: {sid}")
    return "interval:\n" + "\n".join(lines) + "\n"


# --- White picker (warm/cool white temp, mireds 153-500) ---

MIREDS_MIN, MIREDS_MAX = 153, 500


def _mireds_to_rgb_hex(mireds: int) -> int:
    """Convert mireds (153=cool, 500=warm) to approximate RGB for swatch (0xRRGGBB)."""
    t = (mireds - MIREDS_MIN) / (MIREDS_MAX - MIREDS_MIN)
    t = max(0.0, min(1.0, t))
    r, g, b = 255, int(255 - 75 * t), int(255 - 135 * t)
    return (r << 16) | (g << 8) | b


def _collect_white_picker_defaults(project: dict) -> list[tuple[str, str, int]]:
    """Collect (wid, wid_safe, initial_mireds) for white_picker widgets that have no on_click action binding."""
    pages = project.get("pages") or []
    action_bindings_by_widget = {}
    for ab in project.get("action_bindings") or []:
        if not isinstance(ab, dict):
            continue
        wid = str(ab.get("widget_id") or "").strip()
        if wid:
            action_bindings_by_widget.setdefault(wid, []).append(ab)
    has_on_click = set()
    for wid, ab_list in action_bindings_by_widget.items():
        for ab in ab_list:
            if str(ab.get("event") or "").strip().lower() == "on_click":
                has_on_click.add(wid)
                break
    out: list[tuple[str, str, int]] = []

    def walk(widgets: list) -> None:
        for w in widgets or []:
            if not isinstance(w, dict):
                continue
            if str(w.get("type") or "") == "white_picker":
                wid = str(w.get("id") or "").strip()
                if not wid or wid in has_on_click:
                    continue
                wid_safe = _safe_id(wid)
                props = w.get("props") or {}
                raw = props.get("value")
                if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                    initial = int(max(MIREDS_MIN, min(MIREDS_MAX, raw)))
                else:
                    initial = 326
                out.append((wid, wid_safe, initial))
            walk(w.get("widgets") or [])

    for page in pages:
        if isinstance(page, dict):
            walk(page.get("widgets") or [])
    return out


def _compile_white_picker_globals(wpicker_defaults: list[tuple[str, str, int]]) -> str:
    if not wpicker_defaults:
        return ""
    out = []
    for _wid, wid_safe, initial_m in wpicker_defaults:
        out.append(f"  - id: etd_wp_{wid_safe}_mireds\n")
        out.append("    type: int\n")
        out.append("    restore_value: no\n")
        out.append(f"    initial_value: '{initial_m}'\n")
    return "globals:\n" + "".join(out).rstrip() + "\n" if out else ""


def _spinbox2_rewrite_action_lambdas(yaml_text: str, g_id: str) -> str:
    if not yaml_text:
        return yaml_text
    t = yaml_text
    t = re.sub(r"!lambda return \(float\)x\s*;", f"!lambda return (float)id({g_id});", t)
    t = re.sub(r"!lambda return \(int\)x\s*;", f"!lambda return (int)id({g_id});", t)
    return t


def _spinbox2_harden_ha_then(yaml_text: str, wid_safe: str) -> str:
    if not yaml_text.strip() or "homeassistant.action" not in yaml_text:
        return yaml_text
    if "delay: 150ms" in yaml_text:
        return yaml_text
    m_eid = re.search(r"^\s*entity_id:\s*([A-Za-z0-9_]+\.[A-Za-z0-9_]+)\s*$", yaml_text, re.M)
    lock_lines = ["  - lambda: id(etd_ui_lock_until) = millis() + 500;"]
    if m_eid:
        sid = _slugify_entity_id(m_eid.group(1))
        lock_lines.append(f"  - lambda: id(etd_lock_{sid}) = millis() + 500;")
        lock_lines.append(f"  - lambda: id(etd_lock_{sid}_{wid_safe}) = millis() + 500;")
    lines = yaml_text.splitlines()
    out_ln: list[str] = []
    inserted = False
    for ln in lines:
        out_ln.append(ln)
        if not inserted and ln.strip() == "then:":
            out_ln.extend(lock_lines)
            out_ln.append("  - delay: 150ms")
            inserted = True
    return "\n".join(out_ln)


def _compile_spinbox2_globals(project: dict) -> str:
    out: list[str] = []
    for page in project.get("pages") or []:
        if not isinstance(page, dict):
            continue
        for w in page.get("widgets") or []:
            if not isinstance(w, dict):
                continue
            if str(w.get("type") or "") != "spinbox2":
                continue
            wid = str(w.get("id") or "").strip()
            if not wid:
                continue
            props = w.get("props") or {}
            try:
                val = float(props.get("value", 0))
            except (TypeError, ValueError):
                val = 0.0
            g = f"etd_sb2_{_safe_id(wid)}_val"
            out.append(f"  - id: {g}\n")
            out.append("    type: float\n")
            out.append("    restore_value: no\n")
            out.append(f"    initial_value: {val}\n")
    return "globals:\n" + "".join(out).rstrip() + "\n" if out else ""


def _emit_spinbox2_yaml(
    w: dict,
    indent: str,
    ab_list: list | None,
    parent_w: int | None,
    parent_h: int | None,
    option_maps: dict[str, list[str]] | None,
) -> str:
    """Emit container + minus/plus buttons + value label; runtime value stored in etd_sb2_<id>_val global."""
    option_maps = option_maps or {}
    ab_list = list(ab_list or [])
    wid = str(w.get("id") or "w")
    wid_safe = _safe_id(wid)
    g_id = f"etd_sb2_{wid_safe}_val"
    props = dict(w.get("props") or {})
    style = dict(w.get("style") or {})
    x_val = int(w.get("x", 0))
    y_val = int(w.get("y", 0))
    w_val = int(w.get("w", 200))
    h_val = int(w.get("h", 48))
    align = str(props.get("align", "TOP_LEFT") or "TOP_LEFT").strip().upper()
    if align and align != "TOP_LEFT" and parent_w is not None and parent_h is not None:
        pw2, ph2 = parent_w // 2, parent_h // 2
        if align == "CENTER":
            x_val = x_val + w_val // 2 - pw2
            y_val = y_val + h_val // 2 - ph2
        elif align == "TOP_MID":
            x_val = x_val + w_val // 2 - pw2
        elif align == "TOP_RIGHT":
            x_val = x_val + w_val - parent_w
        elif align == "LEFT_MID":
            y_val = y_val + h_val // 2 - ph2
        elif align == "RIGHT_MID":
            x_val = x_val + w_val - parent_w
            y_val = y_val + h_val // 2 - ph2
        elif align == "BOTTOM_LEFT":
            y_val = y_val + h_val - parent_h
        elif align == "BOTTOM_MID":
            x_val = x_val + w_val // 2 - pw2
            y_val = y_val + h_val - parent_h
        elif align == "BOTTOM_RIGHT":
            x_val = x_val + w_val - parent_w
            y_val = y_val + h_val - parent_h
    try:
        value = float(props.get("value", 0))
    except (TypeError, ValueError):
        value = 0.0
    try:
        mn = float(props.get("min_value", 0))
    except (TypeError, ValueError):
        mn = 0.0
    try:
        mx = float(props.get("max_value", 100))
    except (TypeError, ValueError):
        mx = 100.0
    try:
        step = float(props.get("step", 1))
    except (TypeError, ValueError):
        step = 1.0
    if step <= 0:
        step = 1.0
    dec = int(props.get("decimal_places", 0) or 0)
    dec = max(0, min(6, dec))
    minus_txt = json.dumps(str(props.get("minus_text", "-") or "-"))
    plus_txt = json.dumps(str(props.get("plus_text", "+") or "+"))
    btn_w = max(28, min(64, w_val // 4))
    lbl_w = max(20, w_val - 2 * btn_w)
    mul = float(10**dec) if dec > 0 else 0.0
    step_lit = f"{step:.8f}".rstrip("0").rstrip(".")
    if not step_lit or step_lit == "-":
        step_lit = "1"
    fmt_c = "%.0f" if dec == 0 else f"%.{dec}f"
    init_text = f"{value:.{dec}f}" if dec > 0 else str(int(round(value)))
    init_text_j = json.dumps(init_text)

    i1 = indent + "    "
    i2 = indent + "      "
    i3 = indent + "        "
    i4 = indent + "          "
    i5 = indent + "            "
    i6 = indent + "              "

    parts: list[str] = [
        f"{indent}- container:\n",
        f"{i1}id: {wid}\n",
        f"{i1}x: {x_val}\n",
        f"{i1}y: {y_val}\n",
        f"{i1}width: {w_val}\n",
        f"{i1}height: {h_val}\n",
    ]
    bc = style.get("bg_color")
    if bc is not None:
        hx = _hex_color_for_yaml(bc)
        if hx is not None:
            parts.append(f"{i1}bg_color: 0x{int(hx):06X}\n")
    bw = int(style.get("border_width", 1) or 0)
    if bw > 0:
        parts.append(f"{i1}border_width: {bw}\n")
        brc = style.get("border_color")
        if brc is not None:
            hx2 = _hex_color_for_yaml(brc)
            if hx2 is not None:
                parts.append(f"{i1}border_color: 0x{int(hx2):06X}\n")
    rad = int(style.get("radius", 6) or 0)
    if rad > 0:
        parts.append(f"{i1}radius: {rad}\n")
    parts.append(f"{i1}pad_all: 0\n")
    parts.append(f"{i1}widgets:\n")

    tc = style.get("text_color") or 0xE2E8F0
    tcx = _hex_color_for_yaml(tc)
    lbl_color_line = ""
    if tcx is not None:
        lbl_color_line = f"{i4}text_color: 0x{int(tcx):06X}\n"

    lbl_id = f"{wid}_v"
    btn_minus = f"{wid}_m"
    btn_plus = f"{wid}_p"

    ab_on_change = None
    for ab in ab_list:
        if isinstance(ab, dict) and str(ab.get("event") or "") == "on_change":
            ab_on_change = ab
            break

    def _lambda_lines(sign: int) -> list[str]:
        op = "-" if sign < 0 else "+"
        lines = [
            f"float st = {step_lit}f;",
            f"float v = id({g_id}) {op} st;",
            f"if (v < {mn}f) v = {mn}f;",
            f"if (v > {mx}f) v = {mx}f;",
        ]
        if dec > 0:
            lines.append(f"const float __mul = {mul:.1f}f;")
            lines.append("v = (__mul != 0.0f) ? (roundf(v * __mul) / __mul) : v;")
        else:
            lines.append("v = roundf(v);")
        lines.append(f"id({g_id}) = v;")
        return lines

    def _on_click_yaml(sign: int) -> str:
        lam_lines = _lambda_lines(sign)
        block = [f"{i4}on_click:", f"{i5}then:", f"{i6}- lambda: |-"]
        for ll in lam_lines:
            block.append(f"{i6}    {ll}")
        block.append(f"{i6}- lvgl.label.update:")
        block.append(f"{i6}    id: {lbl_id}")
        block.append(f"{i6}    text: !lambda |-")
        block.append(f"{i6}      char b[48];")
        block.append(f"{i6}      snprintf(b, sizeof(b), \"{fmt_c}\", (double) id({g_id}));")
        block.append(f"{i6}      return std::string(b);")
        if ab_on_change:
            if ab_on_change.get("yaml_override"):
                raw_ha = str(ab_on_change.get("yaml_override") or "").strip()
            elif ab_on_change.get("call"):
                raw_ha = _action_binding_call_to_yaml(
                    ab_on_change["call"], widget_id=wid, wtype="spinbox2", option_maps=option_maps
                )
            else:
                raw_ha = ""
            if raw_ha:
                raw_ha = _spinbox2_rewrite_action_lambdas(raw_ha, g_id)
                raw_ha = _spinbox2_harden_ha_then(raw_ha, wid_safe)
                ha_lines = [ln for ln in raw_ha.strip().splitlines() if ln.strip()]
                if ha_lines and ha_lines[0].strip() == "then:":
                    ha_lines = ha_lines[1:]
                if ha_lines:
                    lead0 = min(len(ln) - len(ln.lstrip(" ")) for ln in ha_lines)
                    for ln in ha_lines:
                        d = len(ln) - len(ln.lstrip(" "))
                        rest = ln.lstrip(" ")
                        block.append(i6 + (" " * max(0, d - lead0)) + rest)
        return "\n".join(block) + "\n"

    parts.append(f"{i2}- button:\n")
    parts.append(f"{i4}id: {btn_minus}\n")
    parts.append(f"{i4}x: 0\n")
    parts.append(f"{i4}y: 0\n")
    parts.append(f"{i4}width: {btn_w}\n")
    parts.append(f"{i4}height: {h_val}\n")
    parts.append(f"{i4}text: {minus_txt}\n")
    parts.append(_on_click_yaml(-1))

    parts.append(f"{i2}- label:\n")
    parts.append(f"{i4}id: {lbl_id}\n")
    parts.append(f"{i4}x: {btn_w}\n")
    parts.append(f"{i4}y: 0\n")
    parts.append(f"{i4}width: {lbl_w}\n")
    parts.append(f"{i4}height: {h_val}\n")
    parts.append(f"{i4}text: {init_text_j}\n")
    if lbl_color_line:
        parts.append(lbl_color_line)
    parts.append(f"{i4}text_align: CENTER\n")

    parts.append(f"{i2}- button:\n")
    parts.append(f"{i4}id: {btn_plus}\n")
    parts.append(f"{i4}x: {btn_w + lbl_w}\n")
    parts.append(f"{i4}y: 0\n")
    parts.append(f"{i4}width: {btn_w}\n")
    parts.append(f"{i4}height: {h_val}\n")
    parts.append(f"{i4}text: {plus_txt}\n")
    parts.append(_on_click_yaml(1))

    return "".join(parts)


def _compile_white_picker_scripts(wpicker_defaults: list[tuple[str, str, int]], project: dict) -> str:
    if not wpicker_defaults:
        return ""
    wpicker_entity_by_wid: dict[str, str] = {}
    for ln in project.get("links") or []:
        if not isinstance(ln, dict):
            continue
        tgt = ln.get("target") or {}
        if str(tgt.get("action") or "").strip() != "button_white_temp":
            continue
        raw_wid = tgt.get("widget_id")
        wid = _extract_widget_id(raw_wid)
        if not wid:
            continue
        src = ln.get("source") or {}
        eid = str(src.get("entity_id") or "").strip()
        if eid and "." in eid and eid.startswith("light."):
            wpicker_entity_by_wid[wid] = eid

    out = []
    for _wid, wid_safe, initial_mireds in wpicker_defaults:
        style_id = f"etd_wp_{wid_safe}"
        overlay_id = f"etd_wp_overlay_{wid_safe}"
        slider_id = f"etd_wp_slider_{wid_safe}"
        out.append(f"  - id: etd_wp_{wid_safe}_open\n")
        out.append("    then:\n")
        out.append(f"      - lvgl.slider.update:\n")
        out.append(f"          id: {slider_id}\n")
        out.append(f"          value: !lambda 'return id(etd_wp_{wid_safe}_mireds);'\n")
        out.append(f"      - lvgl.widget.show: {overlay_id}\n")
        out.append(f"  - id: etd_wp_{wid_safe}_apply\n")
        out.append("    then:\n")
        out.append(f"      - lvgl.style.update:\n")
        out.append(f"          id: {style_id}\n")
        out.append(f"          bg_color: !lambda |-\n")
        out.append(f"            int m = id(etd_wp_{wid_safe}_mireds);\n")
        out.append(f"            float t = (m - {MIREDS_MIN}) / (float)({MIREDS_MAX} - {MIREDS_MIN});\n")
        out.append("            if (t < 0) t = 0; if (t > 1) t = 1;\n")
        out.append("            int r = 255, g = (int)(255 - 75*t), b = (int)(255 - 135*t);\n")
        out.append("            return lv_color_hex((r<<16)|(g<<8)|b);\n")
        out.append(f"      - lvgl.widget.hide: {overlay_id}\n")
        out.append(f"      - lvgl.widget.redraw:\n")
        out.append(f"          id: {_wid}\n")
        entity_id = wpicker_entity_by_wid.get(_wid)
        if entity_id:
            out.append("      - homeassistant.action:\n")
            out.append(f"          action: {DOMAIN}.set_light_color_temp\n")
            out.append("          data:\n")
            out.append(f"            entity_id: {json.dumps(entity_id)}\n")
            out.append(f"            color_temp: !lambda 'return id(etd_wp_{wid_safe}_mireds);'\n")
        out.append(f"  - id: etd_wp_{wid_safe}_cancel\n")
        out.append("    then:\n")
        out.append(f"      - lvgl.widget.hide: {overlay_id}\n")
        entity_id = wpicker_entity_by_wid.get(_wid)
        if entity_id:
            sensor_id = f"ha_num_{_safe_id(entity_id)}_color_temp"
            out.append(f"  - id: etd_wp_{wid_safe}_sync_ha_mireds\n")
            out.append("    then:\n")
            out.append("      - if:\n")
            out.append("          condition:\n")
            out.append("            lambda: |-\n")
            out.append(f"              float m = id({sensor_id}).state;\n")
            out.append(f"              return m >= {MIREDS_MIN} && m <= {MIREDS_MAX};\n")
            out.append("          then:\n")
            out.append("            - lambda: id(etd_wp_" + wid_safe + "_mireds) = (int)id(" + sensor_id + ").state;\n")
            out.append("            - lvgl.style.update:\n")
            out.append(f"                id: {style_id}\n")
            out.append("                bg_color: !lambda |-\n")
            out.append(f"                  int m = id(etd_wp_{wid_safe}_mireds);\n")
            out.append(f"                  float t = (m - {MIREDS_MIN}) / (float)({MIREDS_MAX} - {MIREDS_MIN});\n")
            out.append("                  if (t < 0) t = 0; if (t > 1) t = 1;\n")
            out.append("                  int r = 255, g = (int)(255 - 75*t), b = (int)(255 - 135*t);\n")
            out.append("                  return lv_color_hex((r<<16)|(g<<8)|b);\n")
            out.append("            - lvgl.widget.redraw:\n")
            out.append(f"                id: {_wid}\n")
    return "script:\n" + "".join(out).rstrip() + "\n" if out else ""


def _extract_widget_id(raw_wid) -> str:
    if isinstance(raw_wid, dict) and "id" in raw_wid:
        return str(raw_wid.get("id") or "").strip()
    if isinstance(raw_wid, list) and raw_wid:
        first = raw_wid[0]
        return str(first.get("id", "") or "").strip() if isinstance(first, dict) else str(first or "").strip()
    return str(raw_wid or "").strip()


def _compile_white_picker_sync_interval(project: dict, wpicker_defaults: list[tuple[str, str, int]]) -> str:
    wpicker_entity_by_wid = {}
    for ln in project.get("links") or []:
        if not isinstance(ln, dict):
            continue
        tgt = ln.get("target") or {}
        if str(tgt.get("action") or "").strip() != "button_white_temp":
            continue
        wid = _extract_widget_id(tgt.get("widget_id"))
        if not wid:
            continue
        eid = str((ln.get("source") or {}).get("entity_id") or "").strip()
        if eid and "." in eid and eid.startswith("light."):
            wpicker_entity_by_wid[wid] = eid
    sync_scripts = [f"etd_wp_{wid_safe}_sync_ha_mireds" for _wid, wid_safe, _ in wpicker_defaults if wpicker_entity_by_wid.get(_wid)]
    if not sync_scripts:
        return ""
    lines = ["  - interval: 5s", "    then:"]
    for sid in sync_scripts:
        lines.append(f"      - script.execute: {sid}")
    return "interval:\n" + "\n".join(lines) + "\n"


def _emit_white_picker_overlay_yaml(
    wid_safe: str,
    disp_w: int,
    disp_h: int,
    btn_x: int,
    btn_y: int,
    btn_w: int,
    btn_h: int,
) -> str:
    overlay_w, overlay_h = 260, 200
    center_x = btn_x + btn_w // 2
    center_y = btn_y + btn_h // 2
    overlay_x = max(0, min(center_x - overlay_w // 2, disp_w - overlay_w))
    overlay_y = max(0, min(center_y - overlay_h // 2, disp_h - overlay_h))
    i, ii, iii, iv, v = "      ", "          ", "            ", "                ", "                    "
    swatch_id = f"etd_wp_swatch_{wid_safe}"
    slider_id = f"etd_wp_slider_{wid_safe}"
    _swatch_update = [
        f"{v}- lvgl.obj.update:\n",
        f"{v}    id: {swatch_id}\n",
        f"{v}    bg_color: !lambda |-\n",
        f"{v}      int m = id(etd_wp_{wid_safe}_mireds);\n",
        f"{v}      float t = (m - {MIREDS_MIN}.0f) / ({MIREDS_MAX} - {MIREDS_MIN});\n",
        f"{v}      if (t < 0) t = 0; if (t > 1) t = 1;\n",
        f"{v}      int r = 255, g = (int)(255 - 75*t), b = (int)(255 - 135*t);\n",
        f"{v}      return lv_color_hex((r<<16)|(g<<8)|b);\n",
    ]
    # Warm-to-cool bar: tappable segments linked to slider (like colour picker hue strip)
    strip_w, strip_h = 220, 18
    strip_segments = 20
    strip_segment_w = strip_w // strip_segments
    strip_x_start, strip_y = 20, 22
    out_lines = [
        f"{i}- container:\n",
        f"{ii}id: etd_wp_overlay_{wid_safe}\n",
        f"{ii}hidden: true\n",
        f"{ii}x: {overlay_x}\n",
        f"{ii}y: {overlay_y}\n",
        f"{ii}width: {overlay_w}\n",
        f"{ii}height: {overlay_h}\n",
        f"{ii}bg_color: 0x333333\n",
        f"{ii}bg_opa: 100%\n",
        f"{ii}widgets:\n",
        f"{iii}- label:\n",
        f"{iv}text: White temp (mireds)\n",
        f"{iv}text_color: 0xFFFFFF\n",
        f"{iv}x: 20\n",
        f"{iv}y: 4\n",
        f"{iv}width: 220\n",
        f"{iv}height: 16\n",
    ]
    for seg_i in range(strip_segments):
        mireds_val = MIREDS_MIN + round((MIREDS_MAX - MIREDS_MIN) * seg_i / max(1, strip_segments - 1))
        hex_col = _mireds_to_rgb_hex(mireds_val)
        seg_x = strip_x_start + seg_i * strip_segment_w
        out_lines.extend([
            f"{iii}- button:\n",
            f"{iv}id: etd_wp_strip_{wid_safe}_{seg_i}\n",
            f"{iv}x: {seg_x}\n",
            f"{iv}y: {strip_y}\n",
            f"{iv}width: {strip_segment_w}\n",
            f"{iv}height: {strip_h}\n",
            f"{iv}bg_color: 0x{hex_col:06X}\n",
            f"{iv}on_click:\n",
            f"{iv}  then:\n",
            f"{v}- lambda: id(etd_wp_{wid_safe}_mireds) = {mireds_val};\n",
            f"{v}- lvgl.slider.update:\n",
            f"{v}    id: {slider_id}\n",
            f"{v}    value: {mireds_val}\n",
        ])
        out_lines.extend(_swatch_update)
    out_lines.extend([
        f"{iii}- slider:\n",
        f"{iv}id: {slider_id}\n",
        f"{iv}x: 20\n",
        f"{iv}y: 48\n",
        f"{iv}width: 220\n",
        f"{iv}height: 24\n",
        f"{iv}min_value: {MIREDS_MIN}\n",
        f"{iv}max_value: {MIREDS_MAX}\n",
        f"{iv}value: 326\n",
        f"{iv}on_release:\n",
        f"{iv}  then:\n",
        f"{v}- lambda: id(etd_wp_{wid_safe}_mireds) = (int)x;\n",
    ])
    out_lines.extend(_swatch_update)
    out_lines.extend([
        f"{iii}- button:\n",
        f"{iv}id: {swatch_id}\n",
        f'{iv}text: " "\n',
        f"{iv}x: 20\n",
        f"{iv}y: 78\n",
        f"{iv}width: 40\n",
        f"{iv}height: 40\n",
        f"{iv}border_color: 0xFFFFFF\n",
        f"{iv}border_width: 2\n",
        f"{iv}bg_opa: 100%\n",
        f"{iv}bg_color: !lambda |-\n",
        f"{iv}  int m = id(etd_wp_{wid_safe}_mireds);\n",
        f"{iv}  float t = (m - {MIREDS_MIN}.0f) / ({MIREDS_MAX} - {MIREDS_MIN});\n",
        f"{iv}  if (t < 0) t = 0; if (t > 1) t = 1;\n",
        f"{iv}  int r = 255, g = (int)(255 - 75*t), b = (int)(255 - 135*t);\n",
        f"{iv}  return lv_color_hex((r<<16)|(g<<8)|b);\n",
        f"{iii}- button:\n",
        f"{iv}text: Apply\n",
        f"{iv}x: 70\n",
        f"{iv}y: 78\n",
        f"{iv}width: 100\n",
        f"{iv}height: 36\n",
        f"{iv}on_click:\n",
        f"{iv}  then:\n",
        f"{v}- script.execute: etd_wp_{wid_safe}_apply\n",
        f"{iii}- button:\n",
        f"{iv}text: Cancel\n",
        f"{iv}x: 180\n",
        f"{iv}y: 78\n",
        f"{iv}width: 80\n",
        f"{iv}height: 36\n",
        f"{iv}on_click:\n",
        f"{iv}  then:\n",
        f"{v}- script.execute: etd_wp_{wid_safe}_cancel\n",
    ])
    return "".join(out_lines)


def _widget_bounds_by_id(project: dict, widget_id: str) -> tuple[int, int, int, int]:
    """Return (x, y, width, height) for the first widget with id == widget_id in project pages. Default (0, 0, 80, 36) if not found."""
    for page in project.get("pages") or []:
        if not isinstance(page, dict):
            continue
        for w in page.get("widgets") or []:
            if not isinstance(w, dict):
                continue
            if str(w.get("id") or "").strip() == str(widget_id).strip():
                return (
                    int(w.get("x", 0)),
                    int(w.get("y", 0)),
                    int(w.get("w", 80)),
                    int(w.get("h", 36)),
                )
            # recurse into children (e.g. container widgets)
            for c in w.get("widgets") or []:
                if isinstance(c, dict) and str(c.get("id") or "").strip() == str(widget_id).strip():
                    return (
                        int(c.get("x", 0)),
                        int(c.get("y", 0)),
                        int(c.get("w", 80)),
                        int(c.get("h", 36)),
                    )
    return (0, 0, 80, 36)


def _emit_color_picker_overlay_yaml(
    wid_safe: str,
    disp_w: int,
    disp_h: int,
    btn_x: int,
    btn_y: int,
    btn_w: int,
    btn_h: int,
) -> str:
    """Emit YAML for one colour picker overlay. Matches simulator: hue gradient strip, labels, arc, bar, preview swatch, Apply/Cancel."""
    overlay_w, overlay_h = 280, 240
    center_x = btn_x + btn_w // 2
    center_y = btn_y + btn_h // 2
    overlay_x = max(0, min(center_x - overlay_w // 2, disp_w - overlay_w))
    overlay_y = max(0, min(center_y - overlay_h // 2, disp_h - overlay_h))
    i = "      "
    ii = "          "
    iii = "            "
    iv = "                "
    v = "                    "
    swatch_id = f"etd_cp_swatch_{wid_safe}"
    slider_id = f"etd_cp_slider_{wid_safe}"
    # Snippet to update swatch bg_color from current hue/sat (use lvgl.obj.update; refresh often fails on container)
    _swatch_update = [
        f"{v}- lvgl.obj.update:\n",
        f"{v}    id: {swatch_id}\n",
        f"{v}    bg_color: !lambda |-\n",
        f"{v}      float h = id(etd_cp_{wid_safe}_hue) / 360.0f;\n",
        f"{v}      float s = id(etd_cp_{wid_safe}_sat) / 100.0f;\n",
        f"{v}      float v = 1.0f;\n",
        f"{v}      float c = v * s, x_ = c * (1.0f - fabs(fmod(h * 6.0f, 2.0f) - 1.0f)), m = v - c;\n",
        f"{v}      float r = (h < 1.0f/6.0f) ? c : (h < 2.0f/6.0f) ? x_ : (h < 3.0f/6.0f) ? 0.0f : (h < 4.0f/6.0f) ? x_ : (h < 5.0f/6.0f) ? c : c;\n",
        f"{v}      float g = (h < 1.0f/6.0f) ? x_ : (h < 2.0f/6.0f) ? c : (h < 3.0f/6.0f) ? c : (h < 4.0f/6.0f) ? 0.0f : (h < 5.0f/6.0f) ? x_ : 0.0f;\n",
        f"{v}      float b = (h < 1.0f/6.0f) ? 0.0f : (h < 2.0f/6.0f) ? 0.0f : (h < 3.0f/6.0f) ? x_ : (h < 4.0f/6.0f) ? c : (h < 5.0f/6.0f) ? c : x_;\n",
        f"{v}      return lv_color_hex(((int)((r+m)*255) << 16) | ((int)((g+m)*255) << 8) | (int)((b+m)*255));\n",
    ]
    # Hue gradient strip: 36 tappable segments (like simulator's linear-gradient strip)
    strip_segment_w = 7
    strip_h = 18
    strip_y = 22
    strip_x_start = 20
    out_lines = [
        f"{i}- container:\n",
        f"{ii}id: etd_cp_overlay_{wid_safe}\n",
        f"{ii}hidden: true\n",
        f"{ii}x: {overlay_x}\n",
        f"{ii}y: {overlay_y}\n",
        f"{ii}width: {overlay_w}\n",
        f"{ii}height: {overlay_h}\n",
        f"{ii}bg_color: 0x333333\n",
        f"{ii}bg_opa: 100%\n",
        f"{ii}widgets:\n",
        # Label "Hue" above strip (match simulator); text_color so visible on dark overlay
        f"{iii}- label:\n",
        f"{iv}text: Hue\n",
        f"{iv}text_color: 0xFFFFFF\n",
        f"{iv}x: 20\n",
        f"{iv}y: 4\n",
        f"{iv}width: 240\n",
        f"{iv}height: 16\n",
    ]
    for seg_i in range(36):
        hue_deg = seg_i * 10
        r, g, b = colorsys.hsv_to_rgb(hue_deg / 360.0, 1.0, 1.0)
        hex_col = (int(r * 255) << 16) | (int(g * 255) << 8) | int(b * 255)
        seg_x = strip_x_start + seg_i * strip_segment_w
        out_lines.extend([
            f"{iii}- button:\n",
            f"{iv}id: etd_cp_strip_{wid_safe}_{seg_i}\n",
            f"{iv}x: {seg_x}\n",
            f"{iv}y: {strip_y}\n",
            f"{iv}width: {strip_segment_w}\n",
            f"{iv}height: {strip_h}\n",
            f"{iv}bg_color: 0x{hex_col:06X}\n",
            f"{iv}on_click:\n",
            f"{iv}  then:\n",
            f"{v}- lambda: id(etd_cp_{wid_safe}_hue) = {hue_deg};\n",
            f"{v}- lvgl.slider.update:\n",
            f"{v}    id: {slider_id}\n",
            f"{v}    value: {hue_deg}\n",
        ])
        out_lines.extend(_swatch_update)
    # Slider for hue (horizontal, like simulator)
    out_lines.extend([
        f"{iii}- slider:\n",
        f"{iv}id: {slider_id}\n",
        f"{iv}x: 20\n",
        f"{iv}y: 44\n",
        f"{iv}width: 240\n",
        f"{iv}height: 24\n",
        f"{iv}min_value: 0\n",
        f"{iv}max_value: 360\n",
        f"{iv}value: 210\n",
        f"{iv}on_release:\n",
        f"{iv}  then:\n",
        f"{v}- lambda: id(etd_cp_{wid_safe}_hue) = x;\n",
    ])
    out_lines.extend(_swatch_update)
    out_lines.extend([
        # Label "Sat" (visible on dark bg)
        f"{iii}- label:\n",
        f"{iv}text: Sat\n",
        f"{iv}text_color: 0xFFFFFF\n",
        f"{iv}x: 20\n",
        f"{iv}y: 72\n",
        f"{iv}width: 240\n",
        f"{iv}height: 16\n",
        # Slider for saturation (same as hue: has knob, slideable)
        f"{iii}- slider:\n",
        f"{iv}id: etd_cp_sat_{wid_safe}\n",
        f"{iv}x: 20\n",
        f"{iv}y: 90\n",
        f"{iv}width: 240\n",
        f"{iv}height: 24\n",
        f"{iv}min_value: 0\n",
        f"{iv}max_value: 100\n",
        f"{iv}value: 100\n",
        f"{iv}on_release:\n",
        f"{iv}  then:\n",
        f"{v}- lambda: id(etd_cp_{wid_safe}_sat) = x;\n",
    ])
    out_lines.extend(_swatch_update)
    out_lines.extend([
        # Preview swatch (button so lvgl.obj.update bg_color works; border, bg_opa so colour shows; no label)
        f"{iii}- button:\n",
        f"{iv}id: {swatch_id}\n",
        f'{iv}text: " "\n',  # single space to avoid LVGL showing default "text" when empty
        f"{iv}x: 20\n",
        f"{iv}y: 120\n",
        f"{iv}width: 40\n",
        f"{iv}height: 40\n",
        f"{iv}border_color: 0xFFFFFF\n",
        f"{iv}border_width: 2\n",
        f"{iv}bg_opa: 100%\n",
        f"{iv}bg_color: !lambda |-\n",
        f"{iv}  float h = id(etd_cp_{wid_safe}_hue) / 360.0f;\n",
        f"{iv}  float s = id(etd_cp_{wid_safe}_sat) / 100.0f;\n",
        f"{iv}  float v = 1.0f;\n",
        f"{iv}  float c = v * s, x_ = c * (1.0f - fabs(fmod(h * 6.0f, 2.0f) - 1.0f)), m = v - c;\n",
        f"{iv}  float r = (h < 1.0f/6.0f) ? c : (h < 2.0f/6.0f) ? x_ : (h < 3.0f/6.0f) ? 0.0f : (h < 4.0f/6.0f) ? x_ : (h < 5.0f/6.0f) ? c : c;\n",
        f"{iv}  float g = (h < 1.0f/6.0f) ? x_ : (h < 2.0f/6.0f) ? c : (h < 3.0f/6.0f) ? c : (h < 4.0f/6.0f) ? 0.0f : (h < 5.0f/6.0f) ? x_ : 0.0f;\n",
        f"{iv}  float b = (h < 1.0f/6.0f) ? 0.0f : (h < 2.0f/6.0f) ? 0.0f : (h < 3.0f/6.0f) ? x_ : (h < 4.0f/6.0f) ? c : (h < 5.0f/6.0f) ? c : x_;\n",
        f"{iv}  return lv_color_hex(((int)((r+m)*255) << 16) | ((int)((g+m)*255) << 8) | (int)((b+m)*255));\n",
        # Apply / Cancel (same row as swatch)
        f"{iii}- button:\n",
        f"{iv}text: Apply\n",
        f"{iv}x: 70\n",
        f"{iv}y: 120\n",
        f"{iv}width: 100\n",
        f"{iv}height: 36\n",
        f"{iv}on_click:\n",
        f"{iv}  then:\n",
        f"{v}- script.execute: etd_cp_{wid_safe}_apply\n",
        f"{iii}- button:\n",
        f"{iv}text: Cancel\n",
        f"{iv}x: 180\n",
        f"{iv}y: 120\n",
        f"{iv}width: 80\n",
        f"{iv}height: 36\n",
        f"{iv}on_click:\n",
        f"{iv}  then:\n",
        f"{v}- script.execute: etd_cp_{wid_safe}_cancel\n",
    ])
    return "".join(out_lines)


def _compile_lvgl_config_body(
    project: dict,
    cpicker_styles: list[dict] | None = None,
    wpicker_styles: list[dict] | None = None,
) -> str:
    """Emit LVGL main config, style_definitions, theme, gradients (no pages/top_layer)."""
    lc = project.get("lvgl_config") or {}
    main = lc.get("main") or {}
    out: list[str] = []

    # Main config: buffer_size, etc. disp_bg_color is not emitted here because some ESPHome
    # versions do not accept it in static lvgl config (only via lvgl.update at runtime).
    # Page bg_color is set below so the visible background is correct.
    buf = main.get("buffer_size")
    if buf and str(buf).strip():
        buf_str = str(buf).strip()
        # ESPHome expects percentage as quoted string (e.g. "100%") in YAML
        if "%" in buf_str and not (buf_str.startswith('"') and buf_str.endswith('"')):
            buf_str = f'"{buf_str}"'
        out.append(f"  buffer_size: {buf_str}\n")

    # style_definitions: list of { id: "...", ...style_props (nested state blocks allowed) }
    style_defs = list(lc.get("style_definitions") or [])
    if cpicker_styles:
        style_defs = style_defs + cpicker_styles
    if wpicker_styles:
        style_defs = style_defs + wpicker_styles
    if isinstance(style_defs, list) and style_defs:
        out.append("  style_definitions:\n")
        for sd in style_defs:
            if not isinstance(sd, dict):
                continue
            sid = sd.get("id") or "style"
            out.append(f"    - id: {sid}\n")
            for k, v in sd.items():
                if k == "id" or v is None or v == "":
                    continue
                if isinstance(v, dict):
                    out.append(f"      {k}:\n")
                    out.append(_emit_style_dict("        ", v))
                else:
                    if k.endswith("_color") or k == "color":
                        v = _hex_color_for_yaml(v) if isinstance(v, str) else v
                    out.append(f"      {k}: {v}\n")

    # theme: { widget_type: { ...props, pressed: {...}, checked: {...} } }
    theme = lc.get("theme") or {}
    if isinstance(theme, dict) and theme:
        out.append("  theme:\n")
        for wtype, props in theme.items():
            if not isinstance(props, dict):
                continue
            out.append(f"    {wtype}:\n")
            out.append(_emit_style_dict("      ", props))

    # gradients: list of { id, direction, stops: [ { color, position } ] }
    gradients = lc.get("gradients") or []
    if isinstance(gradients, list) and gradients:
        out.append("  gradients:\n")
        for g in gradients:
            if not isinstance(g, dict):
                continue
            gid = g.get("id") or "grad"
            out.append(f"    - id: {gid}\n")
            if g.get("direction"):
                out.append(f"      direction: {g['direction']}\n")
            stops = g.get("stops") or []
            if stops:
                out.append("      stops:\n")
                for st in stops:
                    if not isinstance(st, dict):
                        continue
                    c = st.get("color")
                    pos = st.get("position")
                    if c is None and pos is None:
                        continue
                    if c is not None:
                        c = _hex_color_for_yaml(c) if isinstance(c, str) else c
                    out.append("        -\n")
                    if c is not None:
                        out.append(f"          color: {c}\n")
                    if pos is not None:
                        out.append(f"          position: {pos}\n")

    return "".join(out)


def _preview_widget_yaml(project: dict, widget_id: str, page_index: int = 0) -> tuple[str, dict] | None:
    """Return the exact YAML fragment the compiler would emit for one widget, plus per-event snippets.

    Used by the frontend Widget YAML tab to show a complete preview including
    all props, style, and action bindings. event_snippets: { event_key: { yaml, source } }
    where source is "empty" | "auto" | "edited".
    """
    pages = project.get("pages") or []
    if not isinstance(pages, list) or not pages or page_index < 0 or page_index >= len(pages):
        return None
    page = pages[page_index]
    if not isinstance(page, dict):
        return None
    all_widgets = page.get("widgets") or []
    if not isinstance(all_widgets, list):
        all_widgets = []
    widget = None
    for w in all_widgets:
        if isinstance(w, dict) and str(w.get("id") or "") == str(widget_id):
            widget = w
            break
    if not widget or widget.get("type") not in COMPILABLE_WIDGET_TYPES:
        return None

    action_bindings_raw = project.get("action_bindings") or []
    action_bindings_by_widget: dict[str, list[dict]] = {}
    for ab in action_bindings_raw:
        if not isinstance(ab, dict):
            continue
        wid = str(ab.get("widget_id") or "").strip()
        if not wid:
            continue
        action_bindings_by_widget.setdefault(wid, []).append(ab)
    ab_list = action_bindings_by_widget.get(str(widget_id)) or []

    def _collect_options(widgets: list, m: dict[str, list[str]]) -> None:
        for w in widgets or []:
            if not isinstance(w, dict):
                continue
            t = w.get("type")
            if t in ("dropdown", "roller") and w.get("id"):
                props = w.get("props") or {}
                opts = props.get("options") or ["Option A", "Option B"]
                if isinstance(opts, str):
                    opts = [s.strip() for s in opts.replace("\\n", "\n").split("\n") if s.strip()]
                else:
                    opts = [str(o).strip() for o in opts if str(o).strip()]
                m[str(w["id"])] = opts if opts else ["(none)"]
            _collect_options(w.get("widgets") or [], m)

    option_maps: dict[str, list[str]] = {}
    for p in pages:
        if isinstance(p, dict):
            _collect_options(p.get("widgets") or [], option_maps)

    parent_w, parent_h = 100, 50
    parent_id = widget.get("parent_id")
    if parent_id:
        for w in all_widgets:
            if isinstance(w, dict) and str(w.get("id") or "") == str(parent_id):
                parent_w = int(w.get("w") or 100)
                parent_h = int(w.get("h") or 50)
                break

    wtype = widget.get("type")
    schema = _load_widget_schema(str(wtype)) if wtype else None
    if not schema:
        return None
    event_snippets: dict = {}
    raw = _emit_widget_from_schema(widget, schema, ab_list, parent_w, parent_h, option_maps, event_snippets_out=event_snippets)
    # Normalize indent for standalone preview: 8 spaces -> 2, 12 spaces -> 4
    lines = raw.splitlines()
    out_lines = []
    for ln in lines:
        if ln.startswith("            "):
            out_lines.append("    " + ln[12:])
        elif ln.startswith("        "):
            out_lines.append("  " + ln[8:])
        else:
            out_lines.append(ln)
    return "\n".join(out_lines), event_snippets


def _compile_lvgl_pages_schema_driven(
    project: dict,
    cpicker_defaults: list[tuple[str, str, int]] | None = None,
    wpicker_defaults: list[tuple[str, str, int]] | None = None,
) -> str:
    """Compile LVGL pages from the project model.

    v0.18: supports container-style parenting via `parent_id` and emits nested
    `widgets:` blocks where applicable.
    v0.71: emits lvgl_config (main, style_definitions, theme, gradients) then pages, then top_layer.
    """
    cpicker_defaults = cpicker_defaults or []
    wpicker_defaults = wpicker_defaults or []
    cpicker_by_wid = {wid: (wid_safe, initial) for (wid, wid_safe, initial) in cpicker_defaults}
    cpicker_styles = [{"id": f"etd_cp_{wid_safe}", "bg_color": initial} for (_w, wid_safe, initial) in cpicker_defaults]
    wpicker_by_wid = {wid: (wid_safe, initial_m) for (wid, wid_safe, initial_m) in wpicker_defaults}
    wpicker_styles = [
        {"id": f"etd_wp_{wid_safe}", "bg_color": _mireds_to_rgb_hex(initial_m)}
        for (_w, wid_safe, initial_m) in wpicker_defaults
    ]

    pages = project.get("pages") or []
    if not isinstance(pages, list) or not pages:
        pages = [{"page_id": "main", "name": "Main", "widgets": []}]

    action_bindings_raw = project.get("action_bindings") or []
    action_bindings_by_widget: dict[str, list[dict]] = {}
    for ab in action_bindings_raw:
        if not isinstance(ab, dict):
            continue
        wid = str(ab.get("widget_id") or "").strip()
        if not wid:
            continue
        action_bindings_by_widget.setdefault(wid, []).append(ab)

    def _collect_options(widgets: list, m: dict[str, list[str]]) -> None:
        for w in widgets or []:
            if not isinstance(w, dict):
                continue
            t = w.get("type")
            if t in ("dropdown", "roller") and w.get("id"):
                props = w.get("props") or {}
                opts = props.get("options") or ["Option A", "Option B"]
                if isinstance(opts, str):
                    opts = [s.strip() for s in opts.replace("\\n", "\n").split("\n") if s.strip()]
                else:
                    opts = [str(o).strip() for o in opts if str(o).strip()]
                m[str(w["id"])] = opts if opts else ["(none)"]
            _collect_options(w.get("widgets") or [], m)

    option_maps: dict[str, list[str]] = {}
    for page in pages:
        if isinstance(page, dict):
            _collect_options(page.get("widgets") or [], option_maps)

    def children_map(all_widgets: list[dict]) -> dict[str, list[dict]]:
        m: dict[str, list[dict]] = {}
        for w in all_widgets:
            pid = str(w.get("parent_id") or "")
            if not pid:
                continue
            m.setdefault(pid, []).append(w)
        return m

    def emit_widget(w: dict, indent: str, kids: dict[str, list[dict]], parent_w: int, parent_h: int) -> str:
        wtype = w.get("type")
        if wtype not in COMPILABLE_WIDGET_TYPES:
            return ""  # Non-ESPHome widget types are not emitted
        wid = str(w.get("id") or "")
        ab_list = action_bindings_by_widget.get(wid) or []
        schema = _load_widget_schema(str(wtype)) if wtype else None
        if schema:
            w_emit = dict(w)
            if wtype == "color_picker" and wid in cpicker_by_wid:
                # Emit button with named style + default on_click (tap opens hue/sat overlay on device)
                wid_safe, _initial = cpicker_by_wid[wid]
                x_val = int(w.get("x", 0))
                y_val = int(w.get("y", 0))
                w_val = int(w.get("w", 100))
                h_val = int(w.get("h", 50))
                align = str((w.get("props") or {}).get("align", "TOP_LEFT") or "TOP_LEFT").strip().upper()
                if align and align != "TOP_LEFT" and parent_w is not None and parent_h is not None:
                    pw2, ph2 = parent_w // 2, parent_h // 2
                    if align == "CENTER":
                        x_val = x_val + w_val // 2 - pw2
                        y_val = y_val + h_val // 2 - ph2
                    elif align == "TOP_MID":
                        x_val = x_val + w_val // 2 - pw2
                    elif align == "TOP_RIGHT":
                        x_val = x_val + w_val - parent_w
                    elif align == "LEFT_MID":
                        y_val = y_val + h_val // 2 - ph2
                    elif align == "RIGHT_MID":
                        x_val = x_val + w_val - parent_w
                        y_val = y_val + h_val // 2 - ph2
                    elif align == "BOTTOM_LEFT":
                        y_val = y_val + h_val - parent_h
                    elif align == "BOTTOM_MID":
                        x_val = x_val + w_val // 2 - pw2
                        y_val = y_val + h_val - parent_h
                    elif align == "BOTTOM_RIGHT":
                        x_val = x_val + w_val - parent_w
                        y_val = y_val + h_val - parent_h
                # Use fixed format (8/12 spaces) so post-processor applies indent correctly
                raw = (
                    "        - button:\n"
                    "            id: {wid}\n"
                    "            x: {x_val}\n"
                    "            y: {y_val}\n"
                    "            width: {w_val}\n"
                    "            height: {h_val}\n"
                    "            styles: etd_cp_{wid_safe}\n"
                    "            on_click:\n"
                    "              then:\n"
                    "                - script.execute: etd_cp_{wid_safe}_open\n"
                ).format(wid=wid, x_val=x_val, y_val=y_val, w_val=w_val, h_val=h_val, wid_safe=wid_safe)
            elif wtype == "color_picker":
                # Emit as button with bg_color from props.value (current colour). Do not emit props.value — button has no value key.
                props = w_emit.get("props") or {}
                style = w_emit.get("style") or {}
                w_emit["style"] = dict(style)
                w_emit["style"]["bg_color"] = props.get("value") or style.get("bg_color") or 0x4080FF
                w_emit["props"] = {k: v for k, v in props.items() if k != "value"}
                raw = _emit_widget_from_schema(w_emit, schema, ab_list, parent_w, parent_h, option_maps)
            elif wtype == "white_picker" and wid in wpicker_by_wid:
                wid_safe, _initial_m = wpicker_by_wid[wid]
                x_val = int(w.get("x", 0))
                y_val = int(w.get("y", 0))
                w_val = int(w.get("w", 100))
                h_val = int(w.get("h", 50))
                align = str((w.get("props") or {}).get("align", "TOP_LEFT") or "TOP_LEFT").strip().upper()
                if align and align != "TOP_LEFT" and parent_w is not None and parent_h is not None:
                    pw2, ph2 = parent_w // 2, parent_h // 2
                    if align == "CENTER":
                        x_val = x_val + w_val // 2 - pw2
                        y_val = y_val + h_val // 2 - ph2
                    elif align == "TOP_MID":
                        x_val = x_val + w_val // 2 - pw2
                    elif align == "TOP_RIGHT":
                        x_val = x_val + w_val - parent_w
                    elif align == "LEFT_MID":
                        y_val = y_val + h_val // 2 - ph2
                    elif align == "RIGHT_MID":
                        x_val = x_val + w_val - parent_w
                        y_val = y_val + h_val // 2 - ph2
                    elif align == "BOTTOM_LEFT":
                        y_val = y_val + h_val - parent_h
                    elif align == "BOTTOM_MID":
                        x_val = x_val + w_val // 2 - pw2
                        y_val = y_val + h_val - parent_h
                    elif align == "BOTTOM_RIGHT":
                        x_val = x_val + w_val - parent_w
                        y_val = y_val + h_val - parent_h
                # Use fixed format (8/12 spaces) so post-processor applies indent correctly
                raw = (
                    "        - button:\n"
                    "            id: {wid}\n"
                    "            x: {x_val}\n"
                    "            y: {y_val}\n"
                    "            width: {w_val}\n"
                    "            height: {h_val}\n"
                    "            styles: etd_wp_{wid_safe}\n"
                    "            on_click:\n"
                    "              then:\n"
                    "                - script.execute: etd_wp_{wid_safe}_open\n"
                ).format(wid=wid, x_val=x_val, y_val=y_val, w_val=w_val, h_val=h_val, wid_safe=wid_safe)
            elif wtype == "white_picker":
                props = w_emit.get("props") or {}
                style = w_emit.get("style") or {}
                initial_m = int(props.get("value", 326))
                initial_m = max(MIREDS_MIN, min(MIREDS_MAX, initial_m))
                w_emit["style"] = dict(style)
                w_emit["style"]["bg_color"] = _mireds_to_rgb_hex(initial_m)
                w_emit["props"] = {k: v for k, v in props.items() if k != "value"}
                raw = _emit_widget_from_schema(w_emit, schema, ab_list, parent_w, parent_h, option_maps)
            elif wtype == "spinbox2":
                raw = _emit_spinbox2_yaml(w, indent, ab_list, parent_w, parent_h, option_maps)
            elif wtype == "arc_labeled":
                # Emit container with arc + line widgets (ticks) + label widgets (scale numbers) so they appear on device.
                x_val = int(w.get("x", 0))
                y_val = int(w.get("y", 0))
                w_val = int(w.get("w", 100))
                h_val = int(w.get("h", 50))
                props = w.get("props") or {}
                style = w.get("style") or {}
                rot = float(props.get("rotation", 0))
                start_angle = float(props.get("start_angle", 135))
                end_angle = float(props.get("end_angle", 45))
                mode = str(props.get("mode", "NORMAL")).strip().upper()
                min_val = float(props.get("min_value", 0))
                max_val = float(props.get("max_value", 100))
                tick_interval = max(1, int(style.get("tick_interval") or props.get("tick_interval") or 1))
                label_interval = max(1, int(style.get("label_interval") or props.get("label_interval") or 2))
                label_color = style.get("label_text_color") or style.get("text_color") or 0xFFFFFF
                if isinstance(label_color, str):
                    label_color = _hex_color_for_yaml(label_color) or 0xFFFFFF
                label_color = int(label_color) & 0xFFFFFF
                tick_color = style.get("tick_color") or style.get("label_text_color") or style.get("text_color") or 0xFFFFFF
                if isinstance(tick_color, str):
                    tick_color = _hex_color_for_yaml(tick_color) or 0xFFFFFF
                tick_color = int(tick_color) & 0xFFFFFF
                label_font = (style.get("label_text_font") or "").strip() or None
                cx = w_val / 2.0
                cy = h_val / 2.0
                r = min(w_val, h_val) / 2.0
                tick_len_auto = max(2, min(6, min(w_val, h_val) / 40.0))
                tick_length_style = max(0, int(style.get("tick_length") or 0))
                tick_len = max(2, min(48, tick_length_style)) if tick_length_style > 0 else tick_len_auto
                tick_width = max(1, min(16, int(style.get("tick_width") or 0) or 3))
                label_offset = max(4, min(20, min(w_val, h_val) / 10.0))
                label_r = r + label_offset
                min_int = int(math.ceil(min_val))
                max_int = int(math.floor(max_val))
                tick_values = [v for v in range(min_int, max_int + 1) if (v - min_int) % tick_interval == 0]
                label_values = [v for v in range(min_int, max_int + 1) if (v - min_int) % label_interval == 0]
                label_font_size = max(8, min(24, int(style.get("label_font_size") or 0) or 14))
                # Compute label positions and bounding box so container can be expanded to avoid clipping
                label_boxes = []
                for i, value in enumerate(label_values):
                    angle_deg = _value_to_angle_deg(rot, start_angle, end_angle, mode, min_val, max_val, float(value))
                    angle_rad = math.radians(angle_deg)
                    lx = cx + label_r * math.cos(angle_rad)
                    ly = cy + label_r * math.sin(angle_rad)
                    text = str(value)
                    box = max(20, int(len(text) * label_font_size * 0.6) + 6)
                    half = box / 2
                    lx_int = int(round(lx - half))
                    ly_int = int(round(ly - label_font_size / 2))
                    label_boxes.append((lx_int, ly_int, box, label_font_size + 2))
                pad = 4
                min_x = 0
                max_x = w_val
                min_y = 0
                max_y = h_val
                for (lx_int, ly_int, box, lh) in label_boxes:
                    min_x = min(min_x, lx_int)
                    max_x = max(max_x, lx_int + box)
                    min_y = min(min_y, ly_int)
                    max_y = max(max_y, ly_int + lh)
                container_w = max(w_val, max_x - min_x + 2 * pad)
                container_h = max(h_val, max_y - min_y + 2 * pad)
                ox = pad - min_x
                oy = pad - min_y
                w_arc = dict(w)
                w_arc["x"] = int(round(ox))
                w_arc["y"] = int(round(oy))
                raw_arc = _emit_widget_from_schema(w_arc, schema, ab_list, parent_w, parent_h, option_maps)
                ci = indent + "    "
                ce = indent + "      "
                cb_arc = indent + "          "
                out_parts = [
                    f"{indent}- container:\n",
                    f"{ci}id: {wid}_ct\n",
                    f"{ci}x: {x_val}\n",
                    f"{ci}y: {y_val}\n",
                    f"{ci}width: {container_w}\n",
                    f"{ci}height: {container_h}\n",
                    f"{ci}widgets:\n",
                ]
                for ln in raw_arc.splitlines(True):
                    if ln.startswith("            "):
                        out_parts.append(cb_arc + ln[12:])
                    elif ln.startswith("        "):
                        out_parts.append(ce + ln[8:])
                for i, value in enumerate(tick_values):
                    angle_deg = _value_to_angle_deg(rot, start_angle, end_angle, mode, min_val, max_val, float(value))
                    angle_rad = math.radians(angle_deg)
                    c = math.cos(angle_rad)
                    s = math.sin(angle_rad)
                    x1 = cx + (r - tick_len) * c
                    y1 = cy + (r - tick_len) * s
                    x2 = cx + r * c
                    y2 = cy + r * s
                    pts = [f"{int(round(x1))},{int(round(y1))}", f"{int(round(x2))},{int(round(y2))}"]
                    line_id = f"{wid}_tick_{i}"
                    out_parts.append(f"{ce}- line:\n")
                    out_parts.append(f"{cb_arc}id: {line_id}\n")
                    out_parts.append(f"{cb_arc}x: {int(round(ox))}\n")
                    out_parts.append(f"{cb_arc}y: {int(round(oy))}\n")
                    out_parts.append(f"{cb_arc}width: {w_val}\n")
                    out_parts.append(f"{cb_arc}height: {h_val}\n")
                    out_parts.append(f"{cb_arc}points:\n")
                    out_parts.append(f"{cb_arc}  - {pts[0]}\n")
                    out_parts.append(f"{cb_arc}  - {pts[1]}\n")
                    out_parts.append(f"{cb_arc}line_width: {tick_width}\n")
                    out_parts.append(f"{cb_arc}line_color: 0x{tick_color:06X}\n")
                for i, value in enumerate(label_values):
                    lx_int, ly_int, box, lh = label_boxes[i]
                    text = str(value)
                    lbl_id = f"{wid}_lbl_{value}"
                    out_parts.append(f"{ce}- label:\n")
                    out_parts.append(f"{cb_arc}id: {lbl_id}\n")
                    out_parts.append(f"{cb_arc}x: {int(round(ox)) + lx_int}\n")
                    out_parts.append(f"{cb_arc}y: {int(round(oy)) + ly_int}\n")
                    out_parts.append(f"{cb_arc}width: {box}\n")
                    out_parts.append(f"{cb_arc}height: {lh}\n")
                    out_parts.append(f"{cb_arc}text: {json.dumps(text)}\n")
                    out_parts.append(f"{cb_arc}text_color: 0x{label_color:06X}\n")
                    if label_font:
                        out_parts.append(f"{cb_arc}text_font: {json.dumps(label_font)}\n")
                out = "".join(out_parts)
            else:
                raw = _emit_widget_from_schema(w_emit, schema, ab_list, parent_w, parent_h, option_maps)
            if wtype != "arc_labeled":
                lines = raw.splitlines(True)
                out_lines = []
                for ln in lines:
                    if ln.startswith("            "):  # body: value of single-key dict (12 spaces)
                        out_lines.append(indent + "    " + ln[12:])
                    elif ln.startswith("        "):
                        out_lines.append(indent + ln[8:])  # first line "- type:"
                    else:
                        out_lines.append(indent + ln)
                out = "".join(out_lines)
        else:
            # No schema: emit bar/arc from props (e.g. prebuilt WiFi bar/fan) or fallback to container
            wid = str(w.get("id") or "w")
            props = w.get("props") or {}
            style = w.get("style") or {}
            if wtype == "bar":
                lines = [
                    f"{indent}- bar:\n",
                    f"{indent}    id: {wid}\n",
                    f"{indent}    x: {int(w.get('x', 0))}\n",
                    f"{indent}    y: {int(w.get('y', 0))}\n",
                    f"{indent}    width: {int(w.get('w', 100))}\n",
                    f"{indent}    height: {int(w.get('h', 50))}\n",
                    f"{indent}    min_value: {int(props.get('min_value', 0))}\n",
                    f"{indent}    max_value: {int(props.get('max_value', 100))}\n",
                    f"{indent}    value: {int(props.get('value', 0))}\n",
                ]
                if style.get("bg_color") is not None:
                    bc = _hex_color_for_yaml(style["bg_color"])
                    if bc is not None:
                        lines.append(f"{indent}    bg_color: 0x{int(bc):06X}\n")
                out = "".join(lines)
            elif wtype == "arc" or wtype == "arc_labeled":
                lines = [
                    f"{indent}- arc:\n",
                    f"{indent}    id: {wid}\n",
                    f"{indent}    x: {int(w.get('x', 0))}\n",
                    f"{indent}    y: {int(w.get('y', 0))}\n",
                    f"{indent}    width: {int(w.get('w', 100))}\n",
                    f"{indent}    height: {int(w.get('h', 50))}\n",
                    f"{indent}    min_value: {int(props.get('min_value', 0))}\n",
                    f"{indent}    max_value: {int(props.get('max_value', 100))}\n",
                    f"{indent}    value: {int(props.get('value', 0))}\n",
                    f"{indent}    adjustable: {str(bool(props.get('adjustable', False))).lower()}\n",
                ]
                if props.get("start_angle") is not None:
                    lines.append(f"{indent}    start_angle: {int(props.get('start_angle', 135))}\n")
                if props.get("end_angle") is not None:
                    lines.append(f"{indent}    end_angle: {int(props.get('end_angle', 45))}\n")
                if props.get("arc_width") is not None:
                    lines.append(f"{indent}    arc_width: {int(props.get('arc_width', 4))}\n")
                if style.get("bg_color") is not None:
                    bc = _hex_color_for_yaml(style["bg_color"])
                    if bc is not None:
                        lines.append(f"{indent}    bg_color: 0x{int(bc):06X}\n")
                out = "".join(lines)
            else:
                out = "".join(
                    [
                        f"{indent}- container:\n",
                        f"{indent}    id: {wid}\n",
                        f"{indent}    x: {int(w.get('x', 0))}\n",
                        f"{indent}    y: {int(w.get('y', 0))}\n",
                        f"{indent}    width: {int(w.get('w', 100))}\n",
                        f"{indent}    height: {int(w.get('h', 50))}\n",
                    ]
                )

        # Children: nest under `widgets:`. ESPHome LVGL supports this for containers and many widgets.
        wid = str(w.get("id") or "")
        child_list = kids.get(wid) or []
        pw, ph = int(w.get("w", 100)), int(w.get("h", 50))
        if child_list:
            out += f"{indent}    widgets:\n"
            for c in child_list:
                out += emit_widget(c, indent + "      ", kids, pw, ph)  # 6 spaces: list item 2 under "widgets:"
        elif wtype == "container":
            # Empty container: emit explicit list so structure is valid
            out += f"{indent}    widgets: []\n"
        return out

    out: list[str] = []
    # Emit main config, style_definitions, theme, gradients (from lvgl_config + color picker styles)
    out.append(_compile_lvgl_config_body(project, cpicker_styles=cpicker_styles, wpicker_styles=wpicker_styles))

    disp_bg = project.get("disp_bg_color") or ((project.get("lvgl_config") or {}).get("main") or {}).get("disp_bg_color")
    disp_bg_hex: int | None = None  # 0xRRGGBB for page bg_color
    if disp_bg and isinstance(disp_bg, str):
        s = str(disp_bg).strip()
        if s.startswith("#") and re.match(r"^#[0-9A-Fa-f]{6}$", s):
            disp_bg_hex = int(s[1:7], 16)
        elif s.startswith("#") and re.match(r"^#[0-9A-Fa-f]{3}$", s):
            r, g, b = int(s[1], 16) * 17, int(s[2], 16) * 17, int(s[3], 16) * 17
            disp_bg_hex = r << 16 | g << 8 | b

    out.append("  pages:\n")
    for page in pages:
        if not isinstance(page, dict):
            continue
        raw_pid = page.get("page_id") or page.get("id") or "main"
        pid = _esphome_safe_page_id(raw_pid)
        # ESPHome LVGL pages support id, widgets, scrollable, and style (bg_color, bg_opa).
        # The visible background is the page; set page bg_color so it matches disp_bg_color
        # (otherwise the page can default to white and hide the display background).
        out.append(f"    - id: {pid}\n")
        out.append("      scrollable: false\n")
        if page.get("layout") and str(page.get("layout")).strip().upper() != "NONE":
            out.append(f"      layout: {page.get('layout')}\n")
        if page.get("skip") is True:
            out.append("      skip: true\n")
        if disp_bg_hex is not None:
            out.append(f"      bg_color: 0x{disp_bg_hex:06X}\n")
            out.append("      bg_opa: COVER\n")
        all_widgets = page.get("widgets") or []
        if not isinstance(all_widgets, list):
            all_widgets = []
        # Editor-only widgets: keep in project/canvas, but do not emit to device YAML.
        all_widgets = [
            w for w in all_widgets
            if isinstance(w, dict) and not str(w.get("id") or "").strip().startswith("screensaver_")
        ]
        kids = children_map(all_widgets)
        roots = [w for w in all_widgets if not w.get("parent_id")]
        # Display dims for align conversion: extract from recipe_id (e.g. guition_s3_4848s040_480x480)
        recipe_id = str((project.get("hardware") or {}).get("recipe_id", "") or (project.get("device") or {}).get("hardware_recipe_id", "") or "")
        m = re.search(r"(\d{3,4})x(\d{3,4})", recipe_id, re.I) if recipe_id else None
        disp_w, disp_h = (int(m.group(1)), int(m.group(2))) if m else (480, 320)
        if not roots:
            out.append("      widgets: []\n")
        else:
            out.append("      widgets:\n")
            for w in roots:
                out.append(emit_widget(w, "        ", kids, disp_w, disp_h))

    # top_layer: user widgets (from lvgl_config.top_layer.widgets) + colour picker overlays
    top_layer = (project.get("lvgl_config") or {}).get("top_layer") or {}
    tl_widgets = top_layer.get("widgets") or []
    has_tl = isinstance(tl_widgets, list) and tl_widgets
    if has_tl or cpicker_defaults or wpicker_defaults:
        recipe_id = str((project.get("hardware") or {}).get("recipe_id", "") or (project.get("device") or {}).get("hardware_recipe_id", "") or "")
        m = re.search(r"(\d{3,4})x(\d{3,4})", recipe_id, re.I) if recipe_id else None
        disp_w, disp_h = (int(m.group(1)), int(m.group(2))) if m else (480, 320)
        out.append("  top_layer:\n")
        out.append("    id: top_layer\n")
        out.append("    widgets:\n")
        if has_tl:
            tl_kids = children_map([w for w in tl_widgets if isinstance(w, dict)])
            tl_roots = [w for w in tl_widgets if isinstance(w, dict) and not w.get("parent_id")]
            for w in tl_roots:
                out.append(emit_widget(w, "      ", tl_kids, disp_w, disp_h))  # 6 spaces: 2 in from "widgets"
        for wid, wid_safe, _initial in cpicker_defaults:
            btn_x, btn_y, btn_w, btn_h = _widget_bounds_by_id(project, wid)
            out.append(_emit_color_picker_overlay_yaml(wid_safe, disp_w, disp_h, btn_x, btn_y, btn_w, btn_h))
        for wid, wid_safe, _initial_m in wpicker_defaults:
            btn_x, btn_y, btn_w, btn_h = _widget_bounds_by_id(project, wid)
            out.append(_emit_white_picker_overlay_yaml(wid_safe, disp_w, disp_h, btn_x, btn_y, btn_w, btn_h))

    return "".join(out)





# --- Hardware Recipe Loading (Builtin + User + Packs) ---

from pathlib import Path

def _collect_recipe_files(hass):
    """Return list of (name, path, source) for all recipes."""
    recipes = []

    base_dir = Path(hass.config.path(""))
    builtin_dir = Path(__file__).resolve().parent.parent / "recipes" / "builtin"
    user_dir = base_dir / CONFIG_DIR / "recipes"
    packs_dir = base_dir / CONFIG_DIR / "recipe_packs"

    # Builtin
    if builtin_dir.exists():
        for f in sorted(builtin_dir.glob("*.yaml")):
            recipes.append({
                "name": f.stem,
                "path": str(f),
                "source": "builtin",
                "label": f"Built-in • {f.stem}"
            })

    # User recipes
    if user_dir.exists():
        for f in sorted(user_dir.glob("*.yaml")):
            recipes.append({
                "name": f.stem,
                "path": str(f),
                "source": "user",
                "label": f"Custom • {f.stem}"
            })

    # Recipe packs
    if packs_dir.exists():
        for pack in sorted(packs_dir.iterdir()):
            if not pack.is_dir():
                continue
            for f in sorted(pack.glob("*.yaml")):
                recipes.append({
                    "name": f.stem,
                    "path": str(f),
                    "source": "pack",
                    "pack": pack.name,
                    "label": f"{pack.name} • {f.stem}"
                })

    return recipes

class ContextView(HomeAssistantView):
    url = f"/api/{DOMAIN}/context"
    name = f"api:{DOMAIN}:context"
    requires_auth = False  # Panel loads in iframe; context needed before session may be available

    async def get(self, request):
        hass: HomeAssistant = request.app["hass"]
        entry_id = _active_entry_id(hass) or ""
        if not entry_id:
            ensure = (hass.data.get(DOMAIN) or {}).get("_ensure_config_entry_from_file")
            if callable(ensure):
                try:
                    entry_id = await ensure(hass) or ""
                except Exception:
                    entry_id = ""
        addon_base_url = ""
        conn = _get_addon_connection(hass, entry_id or None)
        if conn:
            addon_base_url = conn[0]
        return self.json({"ok": True, "entry_id": entry_id or "", "addon_base_url": addon_base_url})


class HealthView(HomeAssistantView):
    url = f"/api/{DOMAIN}/health"
    name = f"api:{DOMAIN}:health"
    requires_auth = True

    async def get(self, request):
        hass: HomeAssistant = request.app["hass"]
        version = await _async_integration_version(hass)
        return self.json({"ok": True, "version": version})


class VersionView(HomeAssistantView):
    """Return integration and add-on versions for the Designer UI (e.g. 'Designer 1.0.24 | Add-on 1.0.24')."""

    url = f"/api/{DOMAIN}/version"
    name = f"api:{DOMAIN}:version"
    requires_auth = False

    async def get(self, request):
        hass: HomeAssistant = request.app["hass"]
        integration_version = await _async_integration_version(hass)
        entry_id = request.query.get("entry_id") or _active_entry_id(hass)
        addon_version = None
        conn = _get_addon_connection(hass, entry_id) if entry_id else None
        if conn:
            base_url, token = conn
            import aiohttp
            url = base_url.rstrip("/") + "/api/version"
            headers = {}
            if token and token.strip():
                headers["Authorization"] = f"Bearer {token.strip()}"
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, timeout=timeout) as resp:
                        if resp.status == 200:
                            data = await resp.json() if "application/json" in (resp.content_type or "") else None
                            if isinstance(data, dict) and "api_addon" in data:
                                addon_version = str(data["api_addon"]).strip() or None
            except Exception:
                pass
        return self.json({
            "integration": integration_version,
            "addon": addon_version,
        })



class DiagnosticsView(HomeAssistantView):
    """Lightweight diagnostics for troubleshooting (used by Lane A hardening)."""

    url = f"/api/{DOMAIN}/diagnostics"
    name = f"api:{DOMAIN}:diagnostics"
    requires_auth = True

    async def get(self, request):
        hass: HomeAssistant = request.app["hass"]
        entry_id = _active_entry_id(hass)
        device_count = 0
        if entry_id:
            storage = _get_storage(hass, entry_id)
            if storage is not None:
                device_count = len(storage.state.devices)
        return self.json({
            "ok": True,
            "version": _integration_version(),
            "entry_id": entry_id,
            "device_count": device_count,
        })





class SelfCheckView(HomeAssistantView):
    """Run built-in verification suite checks.

    These checks are designed for personal-use "bullet proof" confidence:
    - compile determinism (same project compiles to identical YAML twice)
    - recipe discovery (builtin + user folder visibility)
    - safe merge marker invariants (no silent corruption)

    NOTE: This does not write or deploy anything.
    """

    url = f"/api/{DOMAIN}/self_check"
    name = f"api:{DOMAIN}:self_check"
    requires_auth = False

    async def get(self, request):
        hass: HomeAssistant = request.app["hass"]
        results: list[dict] = []

        # 1) Recipe discovery
        try:
            recipes = list_all_recipes(hass)
            results.append({
                "name": "recipes_list",
                "ok": True,
                "detail": {"count": len(recipes), "first": recipes[0] if recipes else None},
            })
        except Exception as e:
            results.append({"name":"recipes_list", "ok": False, "error": str(e)})

        # 2) Compile determinism on representative mini-projects (run in executor to avoid blocking I/O)
        samples = [
            {
                "name": "sample_basic_label",
                "project": {
                    "model_version": 1,
                    "hardware": {"recipe_id": "sunton_2432s028r_320x240"},
                    "pages": [{
                        "page_id": "main",
                        "name": "Main",
                        "widgets": [{
                            "id": "lbl1",
                            "type": "label",
                            "x": 10, "y": 10, "w": 120, "h": 32,
                            "props": {"text": "Hello"},
                            "style": {},
                            "events": {},
                        }]
                    }],
                    "bindings": [],
                    "assets": {"images": [], "fonts": []},
                },
            },
            {
                "name": "sample_entity_widget_light",
                "project": {
                    "model_version": 1,
                    "hardware": {"recipe_id": "sunton_2432s028r_320x240"},
                    "pages": [{
                        "page_id": "main",
                        "name": "Main",
                        "widgets": [],
                    }],
                    "bindings": [],
                    "assets": {"images": [], "fonts": []},
                    "palette": {},
                    # A minimal card drop usually expands into widgets; for determinism we just ensure compiler runs.
                },
            },
        ]

        def _selfcheck_compile_determinism(samples_list: list) -> list:
            out = []
            for s in samples_list:
                try:
                    dev = DeviceProject(
                        device_id=f"selfcheck_{s['name']}",
                        slug=f"selfcheck_{s['name']}",
                        name=f"SelfCheck {s['name']}",
                        hardware_recipe_id=(s["project"].get("hardware") or {}).get("recipe_id"),
                        device_settings={},
                        project=s["project"],
                    )
                    y1 = compile_to_esphome_yaml(dev)
                    y2 = compile_to_esphome_yaml(dev)
                    out.append({
                        "name": f"compile_determinism:{s['name']}",
                        "ok": y1 == y2 and bool(y1.strip()),
                        "detail": {"len": len(y1), "identical": y1 == y2},
                    })
                except Exception as e:
                    out.append({"name": f"compile_determinism:{s['name']}", "ok": False, "error": str(e)})
            return out

        compile_results = await hass.async_add_executor_job(_selfcheck_compile_determinism, samples)
        results.extend(compile_results)

        # 3) Safe merge marker invariant checks (pure string-level; does not touch disk)
        try:
            begin = "# --- BEGIN ESPHOME_TOUCH_DESIGNER GENERATED ---"
            end = "# --- END ESPHOME_TOUCH_DESIGNER GENERATED ---"
            sample_generated = f"{begin}\n# generated\n{end}\n"
            # Case: insert into empty file
            merged = _safe_merge_markers("", sample_generated)
            ok_insert = begin in merged and end in merged
            # Case: duplicate markers should raise
            dup = f"{begin}\nA\n{end}\n{begin}\nB\n{end}\n"
            err_dup = None
            try:
                _safe_merge_markers(dup, sample_generated)
            except Exception as e:
                err_dup = str(e)
            results.append({
                "name": "safe_merge_markers",
                "ok": ok_insert and bool(err_dup),
                "detail": {"insert_ok": ok_insert, "duplicate_error": err_dup},
            })
        except Exception as e:
            results.append({"name":"safe_merge_markers", "ok": False, "error": str(e)})

        ok = all(r.get("ok") for r in results)
        return self.json({"ok": ok, "version": _integration_version(), "results": results})


def _safe_merge_markers(existing_text: str, generated_block: str) -> str:
    """Pure helper: merge (or insert) the generated block using the required marker lines.

    This is used by SelfCheck and mirrors the export behavior without touching disk.
    """
    begin = "# --- BEGIN ESPHOME_TOUCH_DESIGNER GENERATED ---"
    end = "# --- END ESPHOME_TOUCH_DESIGNER GENERATED ---"

    if begin not in generated_block or end not in generated_block:
        raise ValueError("generated_block_missing_markers")

    # Count markers in existing
    bcount = existing_text.count(begin)
    ecount = existing_text.count(end)

    if bcount == 0 and ecount == 0:
        # Insert at end with a blank line separator
        if existing_text and not existing_text.endswith("\n"):
            existing_text += "\n"
        if existing_text and not existing_text.endswith("\n\n"):
            existing_text += "\n"
        return existing_text + generated_block

    if bcount != 1 or ecount != 1:
        raise ValueError(f"marker_count_mismatch begin={bcount} end={ecount}")

    bidx = existing_text.find(begin)
    eidx = existing_text.find(end)
    if eidx < bidx:
        raise ValueError("marker_order_invalid")

    # Replace block content including markers
    eidx_end = eidx + len(end)
    before = existing_text[:bidx]
    after = existing_text[eidx_end:]
    # Preserve surrounding newlines
    if before and not before.endswith("\n"):
        before += "\n"
    if after and not after.startswith("\n"):
        after = "\n" + after
    return before + generated_block + after

def _read_json_path(path):  # Used in executor to avoid blocking the event loop
    return json.loads(path.read_text("utf-8"))


class SchemasView(HomeAssistantView):
    url = f"/api/{DOMAIN}/schemas/widgets"
    name = f"api:{DOMAIN}:schemas_widgets"
    requires_auth = False  # Panel iframe: Safari may not send cookies; panel access is gated by sidebar

    async def get(self, request):
        hass: HomeAssistant = request.app["hass"]
        schemas_path = _schemas_dir()
        items = []
        for p in sorted(schemas_path.glob("*.json")):
            wtype = p.stem
            # Std LVGL palette + designer-only extras (arc_labeled, color_picker, white_picker, …).
            # spinbox2 is prebuilt-only (Widgets pane), not listed here.
            if wtype not in COMPILABLE_WIDGET_TYPES:
                continue
            if wtype in WIDGETS_PANE_ONLY_SCHEMA_TYPES:
                continue
            try:
                data = await hass.async_add_executor_job(_read_json_path, p)
                items.append({
                    "type": data.get("type", wtype),
                    "title": data.get("title", wtype),
                    "description": data.get("description", ""),
                })
            except Exception:
                continue
        return self.json({"ok": True, "schemas": items})


class SchemaDetailView(HomeAssistantView):
    url = f"/api/{DOMAIN}/schemas/widgets/{{widget_type}}"
    name = f"api:{DOMAIN}:schemas_widgets_detail"
    requires_auth = False

    async def get(self, request, widget_type: str):
        hass: HomeAssistant = request.app["hass"]
        schemas_path = _schemas_dir() / f"{widget_type}.json"
        if not schemas_path.exists():
            return self.json({"ok": False, "error": "schema_not_found"}, status_code=404)
        data = await hass.async_add_executor_job(_read_json_path, schemas_path)
        data = await hass.async_add_executor_job(_merge_common_extras, data, widget_type)
        return self.json({"ok": True, "schema": data})


class DevicesView(HomeAssistantView):
    url = f"/api/{DOMAIN}/devices"
    name = f"api:{DOMAIN}:devices"
    requires_auth = False

    async def get(self, request):
        hass: HomeAssistant = request.app["hass"]
        entry_id = request.query.get("entry_id") or _active_entry_id(hass)
        if not entry_id:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        storage = _get_storage(hass, entry_id)
        if storage is None:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        return self.json({
            "ok": True,
            "devices": [
                {
                    "device_id": d.device_id,
                    "slug": d.slug,
                    "name": d.name,
                    "hardware_recipe_id": d.hardware_recipe_id,
                    "api_key": d.api_key,
                    "ota_password": d.ota_password,
                    "device_settings": d.device_settings or {},
                }
                for d in storage.state.devices.values()
            ]
        })

    async def post(self, request):
        hass: HomeAssistant = request.app["hass"]
        entry_id = request.query.get("entry_id") or _active_entry_id(hass)
        if not entry_id:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)

        body = await request.json()
        storage = _get_storage(hass, entry_id)
        if storage is None:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)

        existing = storage.get_device(body["device_id"])
        api_key = body.get("api_key")
        ota_password = body.get("ota_password")
        if existing is not None:
            api_key = api_key if api_key is not None and str(api_key).strip() else existing.api_key
            ota_password = ota_password if ota_password is not None else existing.ota_password
        else:
            if not api_key or not str(api_key).strip():
                api_key = base64.b64encode(secrets.token_bytes(32)).decode()
            ota_password = ota_password if ota_password is not None and str(ota_password).strip() else None

        project = body.get("project")
        if project is None and existing is not None:
            project = existing.project

        device_settings = body.get("device_settings")
        if device_settings is None and existing is not None:
            device_settings = existing.device_settings

        device = DeviceProject(
            device_id=body["device_id"],
            slug=body.get("slug", body["device_id"]).lower().replace(" ", "_"),
            name=body.get("name", body["device_id"]),
            hardware_recipe_id=body.get("hardware_recipe_id"),
            api_key=api_key or None,
            ota_password=(str(ota_password).strip() if ota_password is not None and str(ota_password).strip() else None),
            device_settings=device_settings if device_settings is not None else {},
            project=project if project is not None else DeviceProject.__dataclass_fields__["project"].default_factory(),  # type: ignore
        )
        # Design v2: when creating a new device, populate esphome_yaml from current recipe
        if existing is None and device.hardware_recipe_id:
            proj = dict(device.project or {})
            if not (proj.get("esphome_yaml") or "").strip():
                recipe_path = _find_recipe_path_by_id(hass, device.hardware_recipe_id)
                if recipe_path and recipe_path.exists():
                    recipe_text = recipe_path.read_text("utf-8")
                    default_bodies = _build_recipe_default_sections(recipe_text, device)
                    proj["esphome_yaml"] = _sections_to_yaml(default_bodies)
                    device.project = proj
        storage.upsert_device(device)
        await storage.async_save()
        return self.json({"ok": True})

    async def delete(self, request):
        hass: HomeAssistant = request.app["hass"]
        entry_id = request.query.get("entry_id") or _active_entry_id(hass)
        if not entry_id:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)

        device_id = request.query.get("device_id")
        if not device_id:
            return self.json({"ok": False, "error": "missing_device_id"}, status_code=400)
        storage = _get_storage(hass, entry_id)
        if storage is None:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        ok = storage.delete_device(device_id)
        if ok:
            await storage.async_save()
        return self.json({"ok": ok})


class DeviceProjectView(HomeAssistantView):
    url = f"/api/{DOMAIN}/devices/{{device_id}}/project"
    name = f"api:{DOMAIN}:device_project"
    requires_auth = False

    async def get(self, request, device_id: str):
        hass: HomeAssistant = request.app["hass"]
        entry_id = request.query.get("entry_id") or _active_entry_id(hass)
        if not entry_id:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        storage = _get_storage(hass, entry_id)
        if storage is None:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        device = storage.get_device(device_id)
        if not device:
            return self.json({"ok": False, "error": "device_not_found"}, status_code=404)
        project = dict(device.project) if device.project else {}
        # Do not merge recipe/compiler into project.sections here. Components panel shows only
        # user-added YAML; compile merges recipe + compiler + project.sections at compile time.
        # Enrich project with device.screen from recipe when device has hardware_recipe_id
        if device.hardware_recipe_id:
            screen = (project.get("device") or {}).get("screen") or {}
            if not (screen.get("width") and screen.get("height")):
                recipe_path = _find_recipe_path_by_id(hass, device.hardware_recipe_id)
                if recipe_path and recipe_path.exists():
                    try:
                        recipe_text = await hass.async_add_executor_job(
                            recipe_path.read_text, "utf-8"
                        )
                        meta = _extract_recipe_metadata_from_text(
                            recipe_text, recipe_id=device.hardware_recipe_id
                        )
                        res = meta.get("resolution")
                        if isinstance(res, dict) and res.get("width") and res.get("height"):
                            project.setdefault("device", {})
                            project["device"]["hardware_recipe_id"] = device.hardware_recipe_id
                            project["device"]["screen"] = {
                                "width": int(res["width"]),
                                "height": int(res["height"]),
                            }
                    except Exception:
                        pass
        return self.json({"ok": True, "project": project})

    async def put(self, request, device_id: str):
        hass: HomeAssistant = request.app["hass"]
        entry_id = request.query.get("entry_id") or _active_entry_id(hass)
        if not entry_id:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        storage = _get_storage(hass, entry_id)
        if storage is None:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        device = storage.get_device(device_id)
        if not device:
            return self.json({"ok": False, "error": "device_not_found"}, status_code=404)
        body = await request.json()
        project = body.get("project")
        if not isinstance(project, dict):
            return self.json({"ok": False, "error": "invalid_project"}, status_code=400)
        # Remove LVGL component blocks that reference deleted widgets (orphan cleanup on save)
        removed_sections = _remove_orphaned_widget_refs_from_sections(project)
        removed_comps = _remove_orphaned_widget_refs_from_esphome_components(project)
        removed = list(removed_sections) + list(removed_comps)
        device.project = project
        storage.upsert_device(device)
        await storage.async_save()
        return self.json({"ok": True, "removed_orphans": [{"section": s, "widget_id": w} for s, w in removed]})

    async def post(self, request, device_id: str):
        """Same as put: save project. Allows addons calling via Supervisor proxy (which may only allow GET/POST)."""
        return await self.put(request, device_id)


class CleanupOrphansView(HomeAssistantView):
    """POST with { project } returns project with orphaned widget refs removed from sections (for preview without saving)."""
    url = f"/api/{DOMAIN}/project/cleanup_orphans"
    name = f"api:{DOMAIN}:project_cleanup_orphans"
    requires_auth = False

    async def post(self, request):
        try:
            body = await request.json()
        except Exception:
            return self.json({"ok": False, "error": "invalid_json"}, status_code=400)
        project = body.get("project")
        if not isinstance(project, dict):
            return self.json({"ok": False, "error": "invalid_project"}, status_code=400)
        project = dict(project)
        removed_sections = _remove_orphaned_widget_refs_from_sections(project)
        removed_comps = _remove_orphaned_widget_refs_from_esphome_components(project)
        removed = list(removed_sections) + list(removed_comps)
        return self.json({
            "ok": True,
            "project": project,
            "removed": [{"section": s, "widget_id": w} for s, w in removed],
        })



def _read_recipe_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _user_recipes_root(hass: HomeAssistant) -> Path:
    """Root folder for user-managed recipes.

    We support both:
      v1 legacy: /config/esptoolkit/recipes/*.yaml
      v2:        /config/esptoolkit/recipes/user/<slug>/recipe.yaml (+ metadata.json)

    The v2 layout enables per-recipe metadata and future assets.
    """
    root = Path(hass.config.path(CONFIG_DIR)) / "recipes"
    root.mkdir(parents=True, exist_ok=True)
    return root


def list_all_recipes(hass) -> list[dict]:
    """Return builtin + user-provided recipes."""
    recipes: list[dict] = []

    # Built-in (integration shipped)
    for r in list_builtin_recipes():
        r["builtin"] = True
        r.setdefault("source", "builtin")
        recipes.append(r)

    # User recipes (config directory)
    try:
        root = _user_recipes_root(hass)

        # v2 structured recipes
        v2_dir = root / "user"
        if v2_dir.exists():
            for recipe_dir in sorted([p for p in v2_dir.iterdir() if p.is_dir()]):
                p = recipe_dir / "recipe.yaml"
                if p.exists():
                    rid = recipe_dir.name
                    meta_path = recipe_dir / "metadata.json"
                    meta = None
                    if meta_path.exists():
                        try:
                            meta = json.loads(meta_path.read_text("utf-8"))
                        except Exception:
                            meta = None
                    recipes.append({
                        "id": rid,
                        "label": (meta or {}).get("label") or f"Custom • {rid}",
                        "path": str(p),
                        "builtin": False,
                        "source": "user",
                        "meta": meta,
                    })

        # v1 legacy single-file recipes (keep supported for backwards compatibility)
        for p in sorted(root.glob("*.yaml")):
            rid = p.stem
            meta_path = root / f"{rid}.metadata.json"
            meta = None
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text("utf-8"))
                except Exception:
                    meta = None
            recipes.append({
                "id": rid,
                "label": (meta or {}).get("label") or f"Custom • {rid}",
                "path": str(p),
                "builtin": False,
                "source": "legacy",
                "meta": meta,
            })
    except Exception:
        # best-effort only
        pass

    # Stable ordering for UI (builtin first, then custom)
    def _sort_key(r: dict):
        return (0 if r.get("builtin") else 1, str(r.get("label") or r.get("id") or ""))

    return sorted(recipes, key=_sort_key)


# --- Saved entity widgets (user snapshot of a page; JSON under config) ---


def _entity_widgets_dir(hass: HomeAssistant) -> Path:
    root = Path(hass.config.path(CONFIG_DIR)) / "entity_widgets"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_entity_widget_id(raw_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]", "_", str(raw_id).strip())
    return s[:120] if s else "entity_widget"


def _entity_widget_paths_by_id(hass: HomeAssistant) -> dict[str, Path]:
    base = _entity_widgets_dir(hass)
    return {p.stem: p for p in sorted(base.glob("*.json"))}


def list_saved_entity_widgets(hass: HomeAssistant) -> list[dict]:
    out: list[dict] = []
    for wid, path in sorted(_entity_widget_paths_by_id(hass).items()):
        try:
            data = json.loads(path.read_text("utf-8"))
            if not isinstance(data, dict):
                continue
            out.append({
                "id": wid,
                "name": data.get("name") or wid,
                "description": data.get("description") or "",
                "device_types": data.get("device_types") or [],
            })
        except Exception:
            continue
    return out


class SavedEntityWidgetsListView(HomeAssistantView):
    url = f"/api/{DOMAIN}/entity-widgets"
    name = f"api:{DOMAIN}:entity_widgets_list"
    requires_auth = False

    async def get(self, request):
        hass = request.app["hass"]
        return self.json({"ok": True, "entity_widgets": list_saved_entity_widgets(hass)})


class SavedEntityWidgetDetailView(HomeAssistantView):
    url = f"/api/{DOMAIN}/entity-widgets/{{entity_widget_id}}"
    name = f"api:{DOMAIN}:entity_widget_detail"
    requires_auth = False

    async def get(self, request, entity_widget_id: str):
        hass = request.app["hass"]
        safe_id = _safe_entity_widget_id(entity_widget_id)
        paths = _entity_widget_paths_by_id(hass)
        path = paths.get(safe_id)
        if path is None or not path.is_file():
            return self.json({"ok": False, "error": "not_found"}, status_code=404)
        try:
            data = json.loads(path.read_text("utf-8"))
            return self.json({"ok": True, "entity_widget": data})
        except Exception as e:
            return self.json({"ok": False, "error": str(e)}, status_code=500)


class SavedEntityWidgetSaveView(HomeAssistantView):
    url = f"/api/{DOMAIN}/entity-widgets"
    name = f"api:{DOMAIN}:entity_widgets_save"
    requires_auth = False

    async def post(self, request):
        hass = request.app["hass"]
        try:
            body = await request.json()
        except Exception:
            return self.json({"ok": False, "error": "invalid_json"}, status_code=400)
        if not isinstance(body, dict):
            return self.json({"ok": False, "error": "invalid_body"}, status_code=400)
        ewid = body.get("id") or body.get("name")
        if not ewid or not str(ewid).strip():
            return self.json({"ok": False, "error": "id_or_name_required"}, status_code=400)
        safe_id = _safe_entity_widget_id(str(ewid).strip())
        required = ("name", "device_types", "widgets", "links")
        for k in required:
            if k not in body:
                return self.json({"ok": False, "error": f"missing_{k}"}, status_code=400)
        if not isinstance(body.get("device_types"), list) or len(body["device_types"]) < 1:
            return self.json({"ok": False, "error": "device_types_min_one"}, status_code=400)
        payload = {
            "id": safe_id,
            "name": str(body.get("name", "")).strip() or safe_id,
            "description": str(body.get("description", "")).strip(),
            "device_types": list(body["device_types"]),
            "widgets": body["widgets"],
            "links": body["links"],
            "action_bindings": body.get("action_bindings") or [],
            "scripts": body.get("scripts") or [],
        }
        path = _entity_widgets_dir(hass) / f"{safe_id}.json"
        try:
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            return self.json({"ok": False, "error": str(e)}, status_code=500)
        return self.json({"ok": True, "id": safe_id})


class SavedEntityWidgetDeleteView(HomeAssistantView):
    url = f"/api/{DOMAIN}/entity-widgets/{{entity_widget_id}}"
    name = f"api:{DOMAIN}:entity_widget_delete"
    requires_auth = False

    async def delete(self, request, entity_widget_id: str):
        hass = request.app["hass"]
        safe_id = _safe_entity_widget_id(entity_widget_id)
        paths = _entity_widget_paths_by_id(hass)
        path = paths.get(safe_id)
        if path is None or not path.exists():
            return self.json({"ok": False, "error": "not_found"}, status_code=404)
        try:
            path.unlink(missing_ok=True)
            return self.json({"ok": True})
        except Exception as e:
            return self.json({"ok": False, "error": str(e)}, status_code=500)


class RecipesView(HomeAssistantView):
    url = f"/api/{DOMAIN}/recipes"
    name = f"api:{DOMAIN}:recipes"
    requires_auth = False

    async def get(self, request):
        hass = request.app["hass"]
        recipes = await hass.async_add_executor_job(list_all_recipes, hass)
        return self.json({"ok": True, "recipes": recipes})


class RecipeUserUpdateView(HomeAssistantView):
    """Update a user/legacy recipe label."""

    url = f"/api/{DOMAIN}/recipes/user/{{recipe_id}}"
    name = f"api:{DOMAIN}:recipes_user_update"
    requires_auth = False

    async def patch(self, request, recipe_id: str):
        hass = request.app["hass"]
        body = await request.json()
        label = body.get("label")
        if not isinstance(label, str) or not label.strip():
            return self.json({"ok": False, "error": "invalid_label"}, status_code=400)

        root = _user_recipes_root(hass)

        # v2 recipe
        v2_dir = root / "user" / recipe_id
        if v2_dir.exists() and v2_dir.is_dir():
            meta_path = v2_dir / "metadata.json"
            meta = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text("utf-8"))
                except Exception:
                    meta = {}
            meta["label"] = label.strip()
            meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
            return self.json({"ok": True})

        # v1 legacy recipe
        legacy = root / f"{recipe_id}.yaml"
        if legacy.exists():
            meta_path = root / f"{recipe_id}.metadata.json"
            meta = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text("utf-8"))
                except Exception:
                    meta = {}
            meta["label"] = label.strip()
            meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
            return self.json({"ok": True})

        return self.json({"ok": False, "error": "recipe_not_found"}, status_code=404)


class RecipeUserDeleteView(HomeAssistantView):
    """Delete a user/legacy recipe."""

    url = f"/api/{DOMAIN}/recipes/user/{{recipe_id}}"
    name = f"api:{DOMAIN}:recipes_user_delete"
    requires_auth = False

    async def delete(self, request, recipe_id: str):
        hass = request.app["hass"]
        root = _user_recipes_root(hass)

        # v2 recipe folder
        v2_dir = root / "user" / recipe_id
        if v2_dir.exists() and v2_dir.is_dir():
            for p in sorted(v2_dir.rglob("*"), reverse=True):
                try:
                    if p.is_file() or p.is_symlink():
                        p.unlink(missing_ok=True)
                    elif p.is_dir():
                        p.rmdir()
                except Exception:
                    pass
            try:
                v2_dir.rmdir()
            except Exception:
                pass
            return self.json({"ok": True})

        # v1 legacy recipe file
        legacy = root / f"{recipe_id}.yaml"
        if legacy.exists():
            try:
                legacy.unlink(missing_ok=True)
            except Exception:
                return self.json({"ok": False, "error": "delete_failed"}, status_code=500)
            meta_path = root / f"{recipe_id}.metadata.json"
            try:
                meta_path.unlink(missing_ok=True)
            except Exception:
                pass
            return self.json({"ok": True})

        return self.json({"ok": False, "error": "recipe_not_found"}, status_code=404)




class EntitiesView(HomeAssistantView):
    """List Home Assistant entities for design-time binding."""

    url = f"/api/{DOMAIN}/entities"
    name = f"api:{DOMAIN}:entities"
    requires_auth = False

    async def get(self, request):
        hass = request.app["hass"]
        # Return a compact list for pickers/search
        items = []
        for st in hass.states.async_all():
            attrs = dict(st.attributes or {})
            items.append({
                "entity_id": st.entity_id,
                "state": st.state,
                "attributes": attrs,
                "friendly_name": attrs.get("friendly_name"),
                "icon": attrs.get("icon"),
                "device_class": attrs.get("device_class"),
                "unit_of_measurement": attrs.get("unit_of_measurement"),
            })
        return self.json(items)


class EntityView(HomeAssistantView):
    """Get one entity state/attributes for inspector previews."""

    url = f"/api/{DOMAIN}/entity/{{entity_id}}"
    name = f"api:{DOMAIN}:entity"
    requires_auth = False

    async def get(self, request, entity_id):
        hass = request.app["hass"]
        entity_id = entity_id.replace(",", ".")  # simple path-safe hack if needed
        st = hass.states.get(entity_id)
        if not st:
            return self.json({"error": "not_found", "entity_id": entity_id}, status_code=404)
        attrs = dict(st.attributes or {})
        return self.json({
            "entity_id": st.entity_id,
            "state": st.state,
            "attributes": attrs,
            "friendly_name": attrs.get("friendly_name"),
            "icon": attrs.get("icon"),
            "device_class": attrs.get("device_class"),
            "unit_of_measurement": attrs.get("unit_of_measurement"),
        })


class StateBatchView(HomeAssistantView):
    """Batch fetch entity states for live design-time preview (links → canvas)."""

    url = f"/api/{DOMAIN}/state/batch"
    name = f"api:{DOMAIN}:state_batch"
    requires_auth = False

    async def post(self, request):
        body = await request.json() if request.can_read_body else {}
        entity_ids = body.get("entity_ids") if isinstance(body, dict) else []
        if not isinstance(entity_ids, list):
            entity_ids = []
        entity_ids = [str(e).strip() for e in entity_ids if str(e).strip() and "." in str(e)]
        hass = request.app["hass"]
        states = {}
        for eid in entity_ids[:100]:
            st = hass.states.get(eid)
            if st:
                states[eid] = {"state": st.state, "attributes": dict(st.attributes or {})}
        return self.json({"states": states})


class CallServiceView(HomeAssistantView):
    """Call a Home Assistant service (simulator: device action → HA)."""

    url = f"/api/{DOMAIN}/call_service"
    name = f"api:{DOMAIN}:call_service"
    requires_auth = False

    async def post(self, request):
        body = await request.json() if request.can_read_body else {}
        if not isinstance(body, dict):
            return self.json({"ok": False, "error": "body must be JSON object"}, status=400)
        domain = str(body.get("domain") or "").strip()
        service = str(body.get("service") or "").strip()
        data = body.get("data")
        if not domain or not service:
            return self.json({"ok": False, "error": "domain and service required"}, status=400)
        if not isinstance(data, dict):
            data = {}
        hass: HomeAssistant = request.app["hass"]
        try:
            await hass.services.async_call(domain, service, data, blocking=True)
            return self.json({"ok": True})
        except Exception as e:
            return self.json({"ok": False, "error": str(e)}, status=500)


class StateWebSocketView(HomeAssistantView):
    """WebSocket endpoint for live state updates (design-time preview)."""

    url = f"/api/{DOMAIN}/state/ws"
    name = f"api:{DOMAIN}:state_ws"
    requires_auth = False

    async def get(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        hass: HomeAssistant = request.app["hass"]
        entity_ids: set = set()
        unsub = None

        async def send_state(eid: str) -> None:
            st = hass.states.get(eid)
            if st:
                payload = json.dumps({
                    "type": "state",
                    "entity_id": eid,
                    "state": st.state,
                    "attributes": dict(st.attributes or {}),
                })
                try:
                    await ws.send_str(payload)
                except Exception:
                    pass

        async def state_changed_listener(event):
            eid = event.data.get("entity_id") if isinstance(event.data, dict) else None
            if eid and eid in entity_ids:
                await send_state(eid)

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        if data.get("type") == "subscribe":
                            ids = data.get("entity_ids")
                            if isinstance(ids, list):
                                entity_ids.clear()
                                entity_ids.update(str(e).strip() for e in ids if str(e).strip() and "." in str(e))
                            if unsub is not None:
                                unsub()
                            unsub = hass.bus.async_listen("state_changed", state_changed_listener)
                            for eid in list(entity_ids)[:100]:
                                await send_state(eid)
                        elif data.get("type") == "unsubscribe":
                            if unsub is not None:
                                unsub()
                                unsub = None
                            entity_ids.clear()
                    except (json.JSONDecodeError, TypeError):
                        pass
                elif msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.ERROR):
                    break
        finally:
            if unsub is not None:
                unsub()
        return ws


def _resolve_native_log_level(name: str):
    import aioesphomeapi as api

    key = (name or "").strip().upper().replace("-", "_")
    if key in ("NONE", "NONE_"):
        return api.LogLevel.LOG_LEVEL_NONE
    if key == "ERROR":
        return api.LogLevel.LOG_LEVEL_ERROR
    if key == "WARN":
        return api.LogLevel.LOG_LEVEL_WARN
    if key == "INFO":
        return api.LogLevel.LOG_LEVEL_INFO
    if key == "CONFIG":
        return api.LogLevel.LOG_LEVEL_CONFIG
    if key == "DEBUG":
        return api.LogLevel.LOG_LEVEL_DEBUG
    if key == "VERBOSE":
        return api.LogLevel.LOG_LEVEL_VERBOSE
    if key == "VERY_VERBOSE":
        return api.LogLevel.LOG_LEVEL_VERY_VERBOSE
    return api.LogLevel.LOG_LEVEL_VERY_VERBOSE


class DeviceNativeLogsWebSocketView(HomeAssistantView):
    """WebSocket: connect to device via ESPHome Native API and stream logs. Clear on connect; log level settable."""

    url = f"/api/{DOMAIN}/device_native_logs/ws"
    name = f"api:{DOMAIN}:device_native_logs_ws"
    requires_auth = False

    async def get(self, request):
        import aioesphomeapi as api

        log = logging.getLogger(__name__ + ".device_logs")

        ws = web.WebSocketResponse()
        await ws.prepare(request)

        hass: HomeAssistant = request.app["hass"]
        entry_id = request.query.get("entry_id") or _active_entry_id(hass)
        device_id = (request.query.get("device_id") or "").strip()
        host_override = (request.query.get("host") or "").strip() or None

        if not entry_id:
            await ws.send_str("error: no_active_entry")
            await ws.close()
            return ws
        if not device_id:
            await ws.send_str("error: missing_device_id")
            await ws.close()
            return ws

        storage = _get_storage(hass, entry_id)
        if storage is None:
            await ws.send_str("error: no_active_entry")
            await ws.close()
            return ws
        device = storage.get_device(device_id)
        if not device:
            await ws.send_str("error: device_not_found")
            await ws.close()
            return ws

        host = host_override or f"{device.slug}.local"
        port = 6053
        api_key = (device.api_key or "").strip()
        if not api_key:
            await ws.send_str("error: device has no api_key")
            await ws.close()
            return ws

        log.debug(
            "DeviceNativeLogsWebSocketView: connecting to host=%s port=%s device_id=%s slug=%s api_key_len=%d",
            host,
            port,
            device.device_id,
            device.slug,
            len(api_key),
        )

        try:
            from homeassistant.components import zeroconf as ha_zeroconf

            zc = await ha_zeroconf.async_get_instance(hass)
        except Exception as zc_err:
            log.warning(
                "DeviceNativeLogsWebSocketView: could not get HA zeroconf: %s",
                zc_err,
            )
            zc = None

        try:
            # Match Home Assistant esphome __init__.py: 3 positionals (host, port, password)
            # then noise_psk and zeroconf_instance as keywords. password=None when using encryption.
            client = api.APIClient(
                host,
                port,
                None,  # password (legacy); we use noise_psk for encryption
                noise_psk=api_key,
                zeroconf_instance=zc,
            )
        except Exception as init_err:
            log.exception(
                "DeviceNativeLogsWebSocketView: APIClient init failed: %s",
                init_err,
            )
            await ws.send_str(f"error: APIClient init: {init_err!s}"[:300])
            await ws.close()
            return ws
        unsub_logs = None
        current_level = api.LogLevel.LOG_LEVEL_VERY_VERBOSE
        log_queue = asyncio.Queue(maxsize=500)
        parse_log_message = getattr(api, "parse_log_message", None)

        def on_log(response):
            try:
                raw = getattr(response, "message", None)
                if raw is None:
                    return
                text = raw.decode("utf-8", "backslashreplace") if isinstance(raw, bytes) else str(raw)
                if not text:
                    return
                if parse_log_message:
                    for line in parse_log_message(text, "", strip_ansi_escapes=True):
                        if line:
                            try:
                                log_queue.put_nowait(line)
                            except asyncio.QueueFull:
                                pass
                else:
                    try:
                        log_queue.put_nowait(text.strip())
                    except asyncio.QueueFull:
                        pass
            except Exception:
                pass

        async def pump_logs():
            while True:
                try:
                    line = await asyncio.wait_for(log_queue.get(), timeout=30.0)
                    await ws.send_str(line)
                except asyncio.TimeoutError:
                    try:
                        await ws.send_str("")
                    except Exception:
                        break
                except Exception:
                    break

        pump_task = None
        try:
            log.debug("DeviceNativeLogsWebSocketView: calling client.connect(login=True)")
            await client.connect(login=True)
            log.debug("DeviceNativeLogsWebSocketView: connect OK, subscribing to logs")
            await ws.send_str("[connected]")
            unsub_logs = client.subscribe_logs(on_log, log_level=current_level)

            pump_task = asyncio.create_task(pump_logs())
            try:
                async for msg in ws:
                    if msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.ERROR):
                        break
                    if msg.type == web.WSMsgType.TEXT and msg.data:
                        try:
                            data = json.loads(msg.data)
                            if isinstance(data, dict) and "log_level" in data:
                                level_name = data.get("log_level")
                                new_level = _resolve_native_log_level(level_name)
                                if unsub_logs is not None:
                                    unsub_logs()
                                unsub_logs = client.subscribe_logs(on_log, log_level=new_level)
                                current_level = new_level
                        except (json.JSONDecodeError, TypeError):
                            pass
            finally:
                pump_task.cancel()
                try:
                    await pump_task
                except asyncio.CancelledError:
                    pass
        except Exception as e:
            err_msg = str(e)[:300]
            try:
                await ws.send_str(f"error: {err_msg}")
                await asyncio.sleep(0.2)
            except Exception:
                pass
            try:
                await ws.close(code=1011, message=err_msg.encode("utf-8")[:123])
            except Exception:
                try:
                    await ws.close()
                except Exception:
                    pass
        finally:
            if pump_task is not None:
                pump_task.cancel()
                try:
                    await pump_task
                except asyncio.CancelledError:
                    pass
            if unsub_logs is not None:
                try:
                    unsub_logs()
                except Exception:
                    pass
            try:
                await client.disconnect()
            except Exception:
                pass
            try:
                await ws.close(code=1000)
            except Exception:
                pass
        return ws


class PreviewWidgetYamlView(HomeAssistantView):
    """Return the exact YAML fragment the compiler would emit for one widget."""

    url = f"/api/{DOMAIN}/preview-widget-yaml"
    name = f"api:{DOMAIN}:preview_widget_yaml"
    requires_auth = False

    async def post(self, request):
        try:
            body = await request.json()
        except Exception:
            return self.json({"ok": False, "error": "invalid_json"}, status_code=400)
        project = body.get("project")
        widget_id = body.get("widget_id")
        page_index = int(body.get("page_index") or 0)
        if not isinstance(project, dict):
            return self.json({"ok": False, "error": "project required"}, status_code=400)
        if not widget_id or not str(widget_id).strip():
            return self.json({"ok": False, "error": "widget_id required"}, status_code=400)
        result = _preview_widget_yaml(project, str(widget_id).strip(), page_index)
        if result is None:
            return self.json({"ok": False, "error": "widget not found or unsupported type"}, status_code=404)
        yaml_str, event_snippets = result
        return self.json({"ok": True, "yaml": yaml_str, "event_snippets": event_snippets})


def _build_sections_panel_data(project: dict, device=None) -> dict:
    """Legacy: user-added only. Prefer _build_sections_panel_data_v2 for Design v2."""
    stored = (project.get("sections") or {}) if isinstance(project.get("sections"), dict) else {}
    sections_full = {}
    for key in SECTION_ORDER:
        raw = (stored.get(key) or "").strip()
        if raw and not (raw.startswith(key + ":") or raw.startswith(key + " :")):
            raw = _section_full_block(key, raw)
        sections_full[key] = raw or ""
    if device is not None and getattr(device, "slug", None):
        _substitute_device_name_in_sections(sections_full, device.slug)
    sections = {
        key: (_section_body_from_value(sections_full[key], key) or "").strip()
        for key in SECTION_ORDER
    }
    default_sections = {key: "" for key in SECTION_ORDER}
    keys_with_additions = [k for k in SECTION_ORDER if (sections.get(k) or "").strip()]
    return {
        "sections": sections,
        "default_sections": default_sections,
        "keys_with_additions": keys_with_additions,
    }


def _build_sections_panel_data_v2(project: dict, device: object | None, recipe_text: str) -> dict:
    """Design v2: single stored YAML. Returns sections (stored + compiler-merged for list sections), default_sections (current recipe), section_states (empty|auto|edited), compiler_owned.
    List sections (switch, sensor, etc.) merge compiler output (e.g. Create Component) with stored so the panel shows both."""
    stored_sections = _stored_sections_from_project(project)
    default_sections = _build_recipe_default_sections(recipe_text, device)
    compiler_sections = _build_compiler_sections(project, device)
    list_sections: set[str] = {
        "sensor", "text_sensor", "binary_sensor", "switch", "number", "select", "light",
    }
    # Build sections: for list sections, merge compiler (Create Component, etc.) with stored so panel shows both
    sections = {}
    for k in SECTION_ORDER:
        stored_body = (stored_sections.get(k) or "").strip()
        if k in list_sections:
            compiler_body = (compiler_sections.get(k) or "").strip()
            if compiler_body and stored_body:
                sections[k] = _merge_list_section_bodies(compiler_body, stored_body).strip()
            else:
                sections[k] = compiler_body or stored_body
        else:
            sections[k] = stored_body
    defaults = {k: (default_sections.get(k) or "").strip() for k in SECTION_ORDER}
    if device is not None and getattr(device, "slug", None):
        repl = json.dumps(device.slug)
        for k in SECTION_ORDER:
            if sections.get(k) and ETD_DEVICE_NAME_PLACEHOLDER in sections[k]:
                sections[k] = sections[k].replace(ETD_DEVICE_NAME_PLACEHOLDER, repl)
    # For list sections, "expected" when user has not edited = compiler + recipe (same as display when stored matches recipe). So only show Edited when user actually changed stored.
    expected_for_state: dict[str, str] = {}
    for k in SECTION_ORDER:
        if k in list_sections:
            comp = (compiler_sections.get(k) or "").strip()
            recipe_def = (default_sections.get(k) or "").strip()
            if comp and recipe_def:
                expected_for_state[k] = _merge_list_section_bodies(comp, recipe_def).strip()
            else:
                expected_for_state[k] = comp or recipe_def
        else:
            expected_for_state[k] = (default_sections.get(k) or "").strip()
    if device is not None and getattr(device, "slug", None):
        repl = json.dumps(device.slug)
        for k in SECTION_ORDER:
            if expected_for_state.get(k) and ETD_DEVICE_NAME_PLACEHOLDER in expected_for_state[k]:
                expected_for_state[k] = expected_for_state[k].replace(ETD_DEVICE_NAME_PLACEHOLDER, repl)
    section_states: dict[str, str] = {}
    for k in SECTION_ORDER:
        s = (sections.get(k) or "").strip()
        expected = (expected_for_state.get(k) or "").strip()
        if not s:
            section_states[k] = SECTION_STATE_EMPTY
        elif s == expected:
            section_states[k] = SECTION_STATE_AUTO
        else:
            section_states[k] = SECTION_STATE_EDITED
    return {
        "sections": sections,
        "default_sections": defaults,
        "section_states": section_states,
        "compiler_owned": list(COMPILER_OWNED_SECTIONS),
        "keys_with_additions": [k for k in SECTION_ORDER if (sections.get(k) or "").strip()],
    }


class SectionsDefaultsView(HomeAssistantView):
    """Components panel (Design v2): sections from stored YAML, default_sections from current recipe, section_states (empty|auto|edited).
    POST body: { project, recipe_id?, device_id?, entry_id? }. Uses v2 when recipe_id is provided and recipe is found."""

    url = f"/api/{DOMAIN}/sections/defaults"
    name = f"api:{DOMAIN}:sections_defaults"
    requires_auth = False

    async def post(self, request):
        try:
            body = await request.json() if request.can_read_body else {}
        except Exception:
            return self.json({"ok": False, "error": "invalid_json"}, status_code=400)
        if not isinstance(body, dict):
            return self.json({"ok": False, "error": "body must be JSON object"}, status_code=400)
        project = body.get("project")
        if not isinstance(project, dict):
            return self.json({"ok": False, "error": "project required"}, status_code=400)
        hass = request.app.get("hass") if request.app else None
        device = None
        device_id = (body.get("device_id") or "").strip() if isinstance(body.get("device_id"), str) else ""
        if device_id and hass:
            entry_id = request.query.get("entry_id") or body.get("entry_id") or _active_entry_id(hass)
            if entry_id:
                storage = _get_storage(hass, entry_id)
                if storage is not None:
                    device = storage.get_device(device_id)
        recipe_id = (body.get("recipe_id") or "").strip() or (project.get("device") or {}).get("hardware_recipe_id") or (project.get("hardware") or {}).get("recipe_id") or ""
        if not recipe_id:
            recipe_id = "sunton_2432s028r_320x240"
        recipe_path = _find_recipe_path_by_id(hass, recipe_id) if hass else None
        recipe_text = recipe_path.read_text("utf-8") if recipe_path and recipe_path.exists() else ""
        if recipe_text:
            data = _build_sections_panel_data_v2(project, device, recipe_text)
            return self.json({
                "ok": True,
                "sections": data["sections"],
                "default_sections": data["default_sections"],
                "section_states": data["section_states"],
                "compiler_owned": data["compiler_owned"],
                "categories": dict(SECTION_CATEGORIES),
                "keys_with_additions": data["keys_with_additions"],
            })
        data = _build_sections_panel_data(project, device)
        return self.json({
            "ok": True,
            "sections": data["sections"],
            "default_sections": data["default_sections"],
            "section_states": {},
            "compiler_owned": [],
            "categories": dict(SECTION_CATEGORIES),
            "keys_with_additions": data["keys_with_additions"],
        })


class SectionsSaveView(HomeAssistantView):
    """Design v2: merge sections into single YAML and set project.esphome_yaml. POST body: { project, sections }."""

    url = f"/api/{DOMAIN}/sections/save"
    name = f"api:{DOMAIN}:sections_save"
    requires_auth = False

    async def post(self, request):
        try:
            body = await request.json() if request.can_read_body else {}
        except Exception:
            return self.json({"ok": False, "error": "invalid_json"}, status_code=400)
        if not isinstance(body, dict):
            return self.json({"ok": False, "error": "body must be JSON object"}, status_code=400)
        project = body.get("project")
        if not isinstance(project, dict):
            return self.json({"ok": False, "error": "project required"}, status_code=400)
        sections = body.get("sections")
        if not isinstance(sections, dict):
            return self.json({"ok": False, "error": "sections required (object)"}, status_code=400)
        project = dict(project)
        # Build section key -> body (accept body-only or full block)
        to_merge: dict[str, str] = {}
        for key in SECTION_ORDER:
            raw = (sections.get(key) or "").strip()
            if not raw:
                continue
            if raw.startswith(key + ":") or raw.startswith(key + " :"):
                body_str = _section_body_from_value(raw, key) or ""
            else:
                body_str = raw
            to_merge[key] = body_str.rstrip()
        project["esphome_yaml"] = _sections_to_yaml(to_merge)
        if "sections" in project:
            del project["sections"]
        if "section_overrides" in project:
            del project["section_overrides"]
        return self.json({"ok": True, "project": project})


class CompileView(HomeAssistantView):
    url = f"/api/{DOMAIN}/devices/{{device_id}}/compile"
    name = f"api:{DOMAIN}:compile"
    requires_auth = False

    async def post(self, request, device_id: str):
        """Compile ESPHome YAML for a device.

        Modes:
        - stored: compile the stored device project.
        - preview: if request JSON includes `project` and/or `hardware_recipe_id`,
          compile that model without mutating HA storage (used by live Compile tab).
        """
        hass: HomeAssistant = request.app["hass"]
        entry_id = request.query.get("entry_id") or _active_entry_id(hass)
        if not entry_id:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)

        storage = _get_storage(hass, entry_id)
        if storage is None:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        device = storage.get_device(device_id)
        if not device:
            return self.json({"ok": False, "error": "device_not_found"}, status_code=404)

        body = None
        try:
            if request.can_read_body:
                body = await request.json()
        except Exception:
            body = None

        project_override = None
        recipe_override = None
        if isinstance(body, dict):
            if isinstance(body.get("project"), dict):
                project_override = body.get("project")
            if isinstance(body.get("hardware_recipe_id"), str) and body.get("hardware_recipe_id").strip():
                recipe_override = body.get("hardware_recipe_id").strip()

        mode = "preview" if (project_override is not None or recipe_override is not None) else "stored"
        yaml_text, warnings = await hass.async_add_executor_job(
            _sync_compile_device_yaml, hass, device, project_override, recipe_override
        )
        return self.json({"ok": True, "yaml": yaml_text, "warnings": warnings, "mode": mode})


class ValidateYamlView(HomeAssistantView):
    """Validate compiled YAML via ESPHome add-on API or local CLI (esphome compile)."""

    url = f"/api/{DOMAIN}/validate_yaml"
    name = f"api:{DOMAIN}:validate_yaml"
    requires_auth = False

    async def post(self, request):
        """POST { \"yaml\": \"...\" } — validate config via add-on or esphome compile; return ok/stdout/stderr."""
        try:
            body = await request.json()
        except Exception:
            return self.json({"ok": False, "error": "invalid_json", "stderr": "", "stdout": ""}, status_code=400)
        yaml_text = (body.get("yaml") or "").strip()
        if not yaml_text:
            return self.json({"ok": False, "error": "empty_yaml", "stderr": "", "stdout": ""}, status_code=400)

        hass = request.app["hass"]
        entry_id = request.query.get("entry_id") or _active_entry_id(hass)
        conn = _get_addon_connection(hass, entry_id)
        if not conn:
            return self.json({"ok": False, "error": "no_addon_connection", "stdout": "", "stderr": "EspToolkit add-on not configured."}, status_code=503)
        base_url, token = conn
        ok, result = await _esphome_addon_request(
            hass,
            base_url,
            "api/config-check",
            {"config_source": "yaml", "yaml": yaml_text},
            token=token,
        )
        return self.json({
            "ok": ok,
            "stdout": result if ok else "",
            "stderr": "" if ok else result,
        })


def _parse_yaml_syntax(content: str) -> None:
    """Parse YAML for syntax check only. Raises yaml.YAMLError on invalid YAML.
    Uses a dedicated loader that accepts ESPHome !secret and !lambda tags."""
    import yaml as _yaml

    class _ESPHomeSafeLoader(_yaml.SafeLoader):
        pass

    def _tag_constructor(loader, node):
        if isinstance(node, _yaml.ScalarNode):
            return loader.construct_scalar(node)
        return str(node)

    _yaml.add_constructor("!secret", _tag_constructor, _ESPHomeSafeLoader)
    _yaml.add_constructor("!lambda", _tag_constructor, _ESPHomeSafeLoader)

    _yaml.load(content, Loader=_ESPHomeSafeLoader)


class ParseYamlView(HomeAssistantView):
    """Lightweight YAML syntax check only (no ESPHome validation). POST { \"yaml\": \"...\" }."""

    url = f"/api/{DOMAIN}/parse_yaml"
    name = f"api:{DOMAIN}:parse_yaml"
    requires_auth = False

    async def post(self, request):
        try:
            body = await request.json()
        except Exception:
            return self.json({"ok": False, "error": "invalid_json"}, status_code=400)
        content = (body.get("yaml") or "").strip()
        if not content:
            return self.json({"ok": True})
        try:
            import yaml as _yaml
            _parse_yaml_syntax(content)
            return self.json({"ok": True})
        except _yaml.YAMLError as e:
            line_no = None
            if hasattr(e, "problem_mark") and e.problem_mark is not None:
                line_no = e.problem_mark.line + 1
            msg = getattr(e, "problem", None) or str(e)
            return self.json({"ok": False, "error": msg, "line": line_no})
        except Exception as e:
            return self.json({"ok": False, "error": str(e)})


class DeployView(HomeAssistantView):
    url = f"/api/{DOMAIN}/deploy"
    name = f"api:{DOMAIN}:deploy"
    requires_auth = False

    async def post(self, request):
        hass: HomeAssistant = request.app["hass"]
        entry_id = request.query.get("entry_id") or _active_entry_id(hass)
        if not entry_id:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)

        body = await request.json()
        device_id = body["device_id"]

        storage = _get_storage(hass, entry_id)
        if storage is None:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        device = storage.get_device(device_id)
        if not device:
            return self.json({"ok": False, "error": "device_not_found"}, status_code=404)

        pages = device.project.get("pages", [])
        widget_count = sum(len(p.get("widgets", [])) for p in pages if isinstance(p, dict))
        yaml_text = (
            f"# Generated by {DOMAIN} vv0.25.0\n"
            f"# device_id: {device.device_id}\n"
            f"# slug: {device.slug}\n"
            f"# widgets: {widget_count}\n"
            "\n"
            f"esphome:\n  name: {device.slug}\n"
            "\n"
            "## compiled from recipe + project model\n"
        )

        esphome_dir = Path(hass.config.path("esphome"))
        esphome_dir.mkdir(parents=True, exist_ok=True)
        target = esphome_dir / f"{device.slug}.yaml"
        tmp = esphome_dir / f".{device.slug}.yaml.tmp"
        bak = esphome_dir / f"{device.slug}.yaml.bak"

        if target.exists():
            try:
                bak.write_text(target.read_text("utf-8"), encoding="utf-8")
            except Exception:
                pass

        tmp.write_text(yaml_text, encoding="utf-8")
        tmp.replace(target)

        return self.json({"ok": True, "path": str(target)})


class DeployBuildView(HomeAssistantView):
    """Run ESPHome build and upload via the configured add-on (reads YAML from exported file)."""

    url = f"/api/{DOMAIN}/deploy_build"
    name = f"api:{DOMAIN}:deploy_build"
    requires_auth = False

    async def post(self, request):
        """POST { device_id } with query entry_id — compile YAML in memory and call add-on run (no file required)."""
        hass = request.app["hass"]
        entry_id = request.query.get("entry_id") or _active_entry_id(hass)
        if not entry_id:
            return self.json({"ok": False, "error": "missing_entry_id"}, status_code=400)

        body = None
        try:
            body = await request.json()
        except Exception:
            body = {}
        device_id = (body or {}).get("device_id")
        if not device_id:
            return self.json({"ok": False, "error": "missing_device_id"}, status_code=400)

        storage = _get_storage(hass, entry_id)
        if storage is None:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        device = storage.get_device(device_id)
        if not device:
            return self.json({
                "ok": False,
                "error": "device_not_found",
                "detail": "Device not found for this entry.",
            }, status_code=404)

        conn = _get_addon_connection(hass, entry_id)
        if not conn:
            return self.json({"ok": False, "error": "no_addon_connection", "detail": "EspToolkit add-on not configured."}, status_code=503)
        base_url, token = conn

        recipe_text = _get_recipe_text_for_device(hass, device)
        try:
            yaml_content = compile_to_esphome_yaml(device, recipe_text=recipe_text)
        except Exception as e:
            return self.json({"ok": False, "error": "compile_failed", "detail": str(e)}, status_code=500)

        ok, result = await _esphome_addon_request(
            hass,
            base_url,
            "api/run",
            {"config_source": "yaml", "yaml": yaml_content},
            token=token,
        )
        if ok:
            return self.json({"ok": True, "result": result})
        return self.json({
            "ok": False,
            "error": "addon_failed",
            "detail": result,
            "result": result,
        })


class MacSimAgentWebSocketView(HomeAssistantView):
    """Mac connects here (outbound WSS/WS); authenticates with integration option mac_sim_token."""

    url = f"/api/{DOMAIN}/mac_sim/agent/ws"
    name = f"api:{DOMAIN}:mac_sim_agent_ws"
    requires_auth = False

    async def get(self, request):
        from ..const import CONF_MAC_SIM_TOKEN
        from ..mac_sim import ensure_mac_sim_hub, mac_sim_token_matches

        hass: HomeAssistant = request.app["hass"]
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        entry_id = _active_entry_id(hass)
        if not entry_id:
            await ws.close(code=4401, message=b"no active entry")
            return ws
        entry = hass.config_entries.async_get_entry(entry_id)
        if not entry:
            await ws.close(code=4401, message=b"no entry")
            return ws
        expected = ((entry.options or {}).get(CONF_MAC_SIM_TOKEN) or "").strip()
        if len(expected) < 16:
            await ws.close(code=4403, message=b"mac_sim_token not configured in integration options")
            return ws

        hub = ensure_mac_sim_hub(hass)
        log = logging.getLogger(__name__ + ".mac_sim_agent")

        authenticated = False
        out_q: asyncio.Queue[dict[str, Any]] | None = None
        session: dict | None = None
        out_task: asyncio.Task | None = None

        async def outgoing_worker():
            assert out_q is not None
            try:
                while True:
                    run_job = await out_q.get()
                    try:
                        await ws.send_str(json.dumps({"type": "run", **run_job}))
                    except Exception as exc:
                        log.debug("mac_sim send to agent failed: %s", exc)
                        break
            except asyncio.CancelledError:
                raise

        try:
            async for msg in ws:
                if msg.type != web.WSMsgType.TEXT:
                    if msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.ERROR):
                        break
                    continue
                try:
                    data = json.loads(msg.data)
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                if not authenticated:
                    if data.get("type") != "auth":
                        await ws.send_str(json.dumps({"type": "error", "message": "send auth first"}))
                        continue
                    offered = str(data.get("token") or "")
                    if not mac_sim_token_matches(expected, offered):
                        await ws.send_str(json.dumps({"type": "error", "message": "auth failed"}))
                        await ws.close(code=4403, message=b"auth failed")
                        break
                    authenticated = True
                    out_q = asyncio.Queue(maxsize=8)
                    session = {"ws": ws, "out_q": out_q, "entry_id": entry_id}
                    async with hub["lock"]:
                        old = hub.get("session")
                        if old and old.get("ws") is not None and old["ws"] is not ws:
                            try:
                                await old["ws"].close()
                            except Exception:
                                pass
                        hub["session"] = session
                    await ws.send_str(json.dumps({"type": "ready"}))
                    out_task = asyncio.create_task(outgoing_worker())
                    continue
                if data.get("type") == "ping":
                    await ws.send_str(json.dumps({"type": "pong"}))
        finally:
            if out_task is not None:
                out_task.cancel()
                try:
                    await out_task
                except asyncio.CancelledError:
                    pass
            async with hub["lock"]:
                if hub.get("session") is session:
                    hub["session"] = None
        return ws


class MacSimEnqueueView(HomeAssistantView):
    """Designer: compile device YAML and push to connected Mac agent for local host/SDL transform + run."""

    url = f"/api/{DOMAIN}/mac_sim/enqueue"
    name = f"api:{DOMAIN}:mac_sim_enqueue"
    requires_auth = False

    async def post(self, request):
        import copy

        import base64
        import secrets as secrets_mod

        from ..const import CONF_MAC_SIM_API_KEY, CONF_MAC_SIM_TOKEN
        from ..mac_sim import ensure_mac_sim_hub

        hass: HomeAssistant = request.app["hass"]
        entry_id = request.query.get("entry_id") or _active_entry_id(hass)
        if not entry_id:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)

        entry = hass.config_entries.async_get_entry(entry_id)
        if not entry:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        opts = dict(entry.options or {})
        api_key = (opts.get(CONF_MAC_SIM_API_KEY) or "").strip()
        mac_sim_api_key_generated = False
        if not api_key:
            api_key = base64.b64encode(secrets_mod.token_bytes(32)).decode()
            opts[CONF_MAC_SIM_API_KEY] = api_key
            hass.config_entries.async_update_entry(entry, options=opts)
            mac_sim_api_key_generated = True
        expected_tok = (opts.get(CONF_MAC_SIM_TOKEN) or "").strip()
        if len(expected_tok) < 16:
            return self.json(
                {
                    "ok": False,
                    "error": "mac_sim_token_not_configured",
                    "detail": "Configure a 16+ character token in EspToolkit integration options (Mac sim).",
                },
                status_code=503,
            )

        try:
            body = await request.json() if request.can_read_body else {}
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        device_id = (body.get("device_id") or "").strip()
        if not device_id:
            return self.json({"ok": False, "error": "missing_device_id"}, status_code=400)

        storage = _get_storage(hass, entry_id)
        if storage is None:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        device = storage.get_device(device_id)
        if not device:
            return self.json({"ok": False, "error": "device_not_found"}, status_code=404)

        project_override = body.get("project") if isinstance(body.get("project"), dict) else None
        recipe_override = None
        if isinstance(body.get("hardware_recipe_id"), str) and body.get("hardware_recipe_id").strip():
            recipe_override = body.get("hardware_recipe_id").strip()

        screen = body.get("screen") if isinstance(body.get("screen"), dict) else {}
        try:
            w = int(screen.get("width") or (device.project or {}).get("device", {}).get("screen", {}).get("width") or 480)
        except (TypeError, ValueError):
            w = 480
        try:
            h = int(screen.get("height") or (device.project or {}).get("device", {}).get("screen", {}).get("height") or 320)
        except (TypeError, ValueError):
            h = 320

        dev_for_compile = device
        if project_override is not None or recipe_override is not None:
            dev_for_compile = copy.deepcopy(device)
            if project_override is not None:
                dev_for_compile.project = project_override
            if recipe_override is not None:
                dev_for_compile.hardware_recipe_id = recipe_override

        try:
            yaml_text, compile_warnings = await hass.async_add_executor_job(
                _sync_compile_device_yaml, hass, dev_for_compile, None, None
            )
        except Exception as e:
            return self.json({"ok": False, "error": "compile_failed", "detail": str(e)}, status_code=500)

        hub = ensure_mac_sim_hub(hass)
        sess = hub.get("session")
        if not sess or sess.get("ws") is None or sess["ws"].closed:
            return self.json(
                {
                    "ok": False,
                    "error": "agent_offline",
                    "detail": "Start the Mac agent (ha_agent_client.py) with this HA URL and token.",
                },
                status_code=503,
            )
        try:
            sess["out_q"].put_nowait(
                {
                    "source_yaml": yaml_text,
                    "screen_width": w,
                    "screen_height": h,
                    "api_encryption_key": api_key,
                    "esphome_name": "macsim",
                }
            )
        except asyncio.QueueFull:
            return self.json({"ok": False, "error": "queue_full"}, status_code=503)

        payload = {
            "ok": True,
            "warnings": (compile_warnings or []),
            "mac_sim_esphome_name": "macsim",
            "mac_sim_api_key_generated": mac_sim_api_key_generated,
        }
        if mac_sim_api_key_generated:
            payload["mac_sim_api_key_hint"] = (
                "A Mac sim API encryption key was saved in EspToolkit → Configure. "
                "Add an ESPHome device named macsim in Home Assistant and paste that key."
            )
        return self.json(payload)


def register_api_views(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register all HTTP API views for the integration."""
    # ContextView is registered in panel so /api/context is always available
    hass.http.register_view(HealthView)
    hass.http.register_view(VersionView)
    hass.http.register_view(DiagnosticsView)
    hass.http.register_view(SelfCheckView)

    # ContextView and DevicesView are registered in panel so routes exist; they return no_active_entry when no config entry
    # Schemas / devices
    hass.http.register_view(DeviceProjectView)
    hass.http.register_view(CleanupOrphansView)

    # Saved entity widgets (user snapshots under config)
    hass.http.register_view(SavedEntityWidgetsListView)
    hass.http.register_view(SavedEntityWidgetDetailView)
    hass.http.register_view(SavedEntityWidgetSaveView)
    hass.http.register_view(SavedEntityWidgetDeleteView)

    # Hardware recipes (RecipesView is registered in panel; clone/export/etc need entry)
    hass.http.register_view(RecipeCloneView)
    hass.http.register_view(RecipeExportView)
    hass.http.register_view(RecipeUserUpdateView)
    hass.http.register_view(RecipeUserDeleteView)
    hass.http.register_view(RecipeValidateView)
    hass.http.register_view(RecipeImportView)

    # Build / deploy / export
    hass.http.register_view(PreviewWidgetYamlView)
    hass.http.register_view(SectionsDefaultsView)
    hass.http.register_view(SectionsSaveView)
    hass.http.register_view(CompileView)
    hass.http.register_view(ValidateYamlView)
    hass.http.register_view(ParseYamlView)
    hass.http.register_view(DeployView)
    hass.http.register_view(DeployBuildView)
    hass.http.register_view(EsphomePortsView)
    hass.http.register_view(DeviceExportPreviewView)
    hass.http.register_view(DeviceExportView)
    hass.http.register_view(DeviceValidateExportView)
    hass.http.register_view(DeviceDeployExportView)

    # Project backup/restore
    hass.http.register_view(DeviceProjectExportView)
    hass.http.register_view(DeviceProjectImportView)
    hass.http.register_view(ImportFromYamlView)

    # Assets
    hass.http.register_view(AssetsListView)
    hass.http.register_view(AssetsUploadView)
    hass.http.register_view(AssetsFileView)

    # Home Assistant entity helpers
    hass.http.register_view(EntitiesView)
    hass.http.register_view(EntityView)
    hass.http.register_view(StateBatchView)
    hass.http.register_view(CallServiceView)
    hass.http.register_view(StateWebSocketView)
    hass.http.register_view(DeviceNativeLogsWebSocketView)
    hass.http.register_view(MacSimAgentWebSocketView)
    hass.http.register_view(MacSimEnqueueView)
    hass.http.register_view(EntityCapabilitiesView)

    # Plugins
    hass.http.register_view(PluginsListView)


def _assets_dir(hass: HomeAssistant) -> Path:
    p = Path(hass.config.path(ASSETS_DIR))
    p.mkdir(parents=True, exist_ok=True)
    return p

class AssetsListView(HomeAssistantView):
    url = f"/api/{DOMAIN}/assets"
    name = f"api:{DOMAIN}:assets"
    requires_auth = False

    async def get(self, request):
        hass: HomeAssistant = request.app["hass"]
        p = _assets_dir(hass)
        items = []
        for f in sorted(p.iterdir()):
            if f.is_file():
                ext = f.suffix.lower().lstrip(".")
                kind = "font" if ext in ("ttf", "otf") else ("image" if ext in ("png", "jpg", "jpeg", "webp", "bmp") else "file")
                items.append({"name": f.name, "size": f.stat().st_size, "kind": kind})
        return self.json(items)

class AssetsUploadView(HomeAssistantView):
    url = f"/api/{DOMAIN}/assets/upload"
    name = f"api:{DOMAIN}:assets_upload"
    requires_auth = False

    async def post(self, request):
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        name = str(body.get("name") or "").strip()
        data_b64 = str(body.get("data_base64") or "").strip()
        if not name or not data_b64:
            return self.json({"error":"name and data_base64 required"}, status_code=400)
        raw = base64.b64decode(data_b64)
        outp = _assets_dir(hass) / name
        outp.write_bytes(raw)
        return self.json({"ok": True, "name": name, "size": len(raw)})


class AssetsFileView(HomeAssistantView):
    """Serve a file from the EspToolkit assets directory (fonts/images for designer @font-face, etc.)."""

    url = f"/api/{DOMAIN}/assets/file"
    name = f"api:{DOMAIN}:assets_file"
    requires_auth = False

    async def get(self, request):
        hass: HomeAssistant = request.app["hass"]
        name = str(request.query.get("name") or "").strip()
        if not name or "/" in name or "\\" in name or name.startswith("."):
            return self.json({"error": "invalid name"}, status_code=400)
        base = _assets_dir(hass).resolve()
        path = (base / name).resolve()
        try:
            path.relative_to(base)
        except ValueError:
            return self.json({"error": "invalid path"}, status_code=400)
        if not path.is_file():
            return self.json({"error": "not found"}, status_code=404)

        ext = path.suffix.lower()
        if ext == ".ttf":
            ctype = "font/ttf"
        elif ext == ".otf":
            ctype = "font/otf"
        elif ext in (".png",):
            ctype = "image/png"
        elif ext in (".jpg", ".jpeg"):
            ctype = "image/jpeg"
        elif ext in (".webp",):
            ctype = "image/webp"
        elif ext in (".bmp",):
            ctype = "image/bmp"
        else:
            ctype = "application/octet-stream"

        def read_bytes() -> bytes:
            return path.read_bytes()

        data = await hass.async_add_executor_job(read_bytes)
        return web.Response(
            body=data,
            content_type=ctype,
            headers={"Cache-Control": "public, max-age=86400"},
        )


class EsphomePortsView(HomeAssistantView):
    """List serial ports seen by the EspToolkit add-on (for deploy prompt)."""

    url = f"/api/{DOMAIN}/esphome/ports"
    name = f"api:{DOMAIN}:esphome_ports"
    requires_auth = False

    async def get(self, request):
        hass: HomeAssistant = request.app["hass"]
        entry_id = request.query.get("entry_id") or _active_entry_id(hass)
        if not entry_id:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        conn = _get_addon_connection(hass, entry_id)
        if not conn:
            return self.json({"ok": False, "error": "no_addon_connection", "detail": "EspToolkit add-on not configured."}, status_code=503)
        base_url, token = conn
        ok, data = await _esphome_addon_get(hass, base_url, "api/ports", token=token)
        if not ok:
            return self.json({"ok": False, **(data or {})}, status_code=502)
        ports = data.get("ports") if isinstance(data, dict) else None
        return self.json({"ok": True, "ports": ports if isinstance(ports, list) else []})

import yaml

import hashlib

_RECIPE_MARKER = "#__LVGL_PAGES__"

_RECIPE_STRIP_TOPLEVEL_KEYS = {
    # Common non-hardware sections we strip when importing full device YAML into a recipe.
    # Users can keep these in their main ESPHome file or secrets include, while recipes focus on hardware + LVGL.
    "wifi",
    "captive_portal",
    "api",
    "ota",
    "logger",
    "web_server",
    "improv_serial",
    "dashboard_import",
    "esp32_improv",
    "bluetooth_proxy",
    "packages",
    "substitutions",
}

def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "recipe"

def _extract_recipe_metadata(model: dict, yaml_text: str, label: str | None = None) -> dict:
    """Best-effort metadata extraction for UI display.

    This is intentionally heuristic and must never block import.
    """
    meta: dict = {"label": label or None}

    # Board/platform
    board = None
    platform = None
    for k in ("esp32", "esp32_s3", "esp32_p4"):
        if isinstance(model.get(k), dict):
            platform = k
            board = model[k].get("board") or board
    if isinstance(model.get("esphome"), dict):
        meta["project_name"] = model["esphome"].get("name")
    if board: meta["board"] = board
    if platform: meta["platform"] = platform

    # Resolution heuristics: look for width/height in display (top-level or dimensions block)
    width = height = None
    # Known MIPI / board display models when width/height are implied by the driver
    _DISPLAY_MODEL_RESOLUTION: dict[str, tuple[int, int]] = {
        "jc1060p470": (1024, 600),
    }
    try:
        displays = model.get("display")
        if isinstance(displays, list) and displays:
            d0 = displays[0]
            if isinstance(d0, dict):
                width = d0.get("width") or width
                height = d0.get("height") or height
                dims = d0.get("dimensions")
                if isinstance(dims, dict) and (width is None or height is None):
                    width = dims.get("width") or width
                    height = dims.get("height") or height
                model_name = d0.get("model")
                if model_name is not None and (not isinstance(width, int) or not isinstance(height, int)):
                    mk = str(model_name).strip().lower()
                    wh = _DISPLAY_MODEL_RESOLUTION.get(mk)
                    if wh:
                        width, height = wh
    except Exception:
        pass
    # fallback regex
    if not (isinstance(width, int) and isinstance(height, int)):
        m = re.search(r"\bwidth:\s*(\d+)\b.*?\bheight:\s*(\d+)\b", yaml_text, flags=re.S)
        if m:
            width = int(m.group(1)); height = int(m.group(2))
    if isinstance(width, int) and isinstance(height, int):
        meta["resolution"] = {"width": width, "height": height}

    # Touch platform
    touch = None
    ts = model.get("touchscreen")
    if isinstance(ts, list) and ts:
        t0 = ts[0]
        if isinstance(t0, dict):
            touch = t0.get("platform") or touch
    if touch:
        meta["touch"] = {"platform": touch}

    # Backlight pin heuristics
    backlight = None
    out = model.get("output")
    if isinstance(out, list):
        for o in out:
            if isinstance(o, dict) and "id" in o and "pin" in o and "backlight" in str(o.get("id")):
                backlight = o.get("pin")
                break
    if backlight:
        meta["backlight_pin"] = backlight

    # PSRAM hint
    meta["psram"] = bool(model.get("psram")) or ("psram" in yaml_text.lower())

    return meta

def _normalize_recipe_yaml(raw_text: str, label: str | None = None) -> tuple[str, dict]:
    """Normalize an imported device YAML into a recipe YAML (Option B).

    - Parses YAML
    - Strips common non-hardware top-level keys
    - Ensures lvgl block exists
    - Ensures #__LVGL_PAGES__ marker exists in lvgl block
    - Dumps canonical YAML (sorted keys, consistent indentation)
    - Re-inserts the marker comment under lvgl:
    """
    model = _yaml_import.load_yaml_lenient(raw_text) or {}
    if not isinstance(model, dict):
        raise ValueError("Top-level YAML must be a mapping/object")

    # Strip non-hardware top-level keys
    for k in list(model.keys()):
        if k in _RECIPE_STRIP_TOPLEVEL_KEYS:
            model.pop(k, None)

    # Ensure lvgl exists
    if "lvgl" not in model:
        model["lvgl"] = {}

    # Dump canonical YAML
    dumped = yaml.safe_dump(
        model,
        sort_keys=True,
        allow_unicode=True,
        default_flow_style=False,
        width=120,
    )

    # Ensure marker in lvgl
    if _RECIPE_MARKER not in dumped:
        # Insert after 'lvgl:' line
        lines = dumped.splitlines()
        out_lines = []
        inserted = False
        for line in lines:
            out_lines.append(line)
            if not inserted and re.match(r"^lvgl:\s*$", line):
                out_lines.append(f"  {_RECIPE_MARKER}")
                inserted = True
        dumped = "\n".join(out_lines) + ("\n" if not dumped.endswith("\n") else "")

    meta = _extract_recipe_metadata(model, dumped, label=label)
    # Derive default label if missing
    if not meta.get("label"):
        # Use board + resolution if present
        parts = []
        if meta.get("board"): parts.append(str(meta["board"]))
        if isinstance(meta.get("resolution"), dict):
            parts.append(f'{meta["resolution"]["width"]}x{meta["resolution"]["height"]}')
        meta["label"] = " • ".join(parts) if parts else "Custom recipe"

    return dumped, meta

# Section keys used for recipe fingerprint (hardware identity for matching import to recipe).
_RECIPE_FINGERPRINT_KEYS = (
    "esphome", "esp32", "esp8266", "rp2040", "esp32_hosted", "psram", "esp_ldo",
    "i2c", "spi", "display", "touchscreen", "output", "light",
)


def _build_recipe_fingerprint(yaml_text: str) -> str:
    """Build a normalized string from hardware sections for recipe matching.
    Strips device name in esphome, normalizes whitespace and order."""
    sections = _yaml_str_to_section_map(yaml_text)
    parts: list[str] = []
    for key in _RECIPE_FINGERPRINT_KEYS:
        body = (sections.get(key) or "").strip()
        if not body:
            continue
        if key == "esphome":
            body = re.sub(r"^\s*name\s*:\s*.*$", "  name: __PLACEHOLDER__", body, count=1, flags=re.MULTILINE)
        body = re.sub(r"#.*$", "", body, flags=re.MULTILINE)
        body = re.sub(r"\s+", " ", body).strip()
        parts.append(f"{key}:{body}")
    return "\n".join(parts)


def _relax_recipe_fingerprint(fp: str) -> str:
    """Remove volatile fragments from fingerprint for fallback matching."""
    if not fp:
        return ""
    lines = [ln.strip() for ln in fp.splitlines() if ln.strip()]
    # Ignore esphome section in relaxed mode; name/min_version can vary between equivalent configs.
    lines = [ln for ln in lines if not ln.startswith("esphome:")]
    return "\n".join(lines)


def _match_recipe_by_fingerprint(hass: HomeAssistant, import_fingerprint: str) -> str | None:
    """Return recipe_id of first recipe whose fingerprint equals import_fingerprint, else None.
    Prefers builtin over user recipes."""
    if not import_fingerprint or not import_fingerprint.strip():
        return None
    import_relaxed = _relax_recipe_fingerprint(import_fingerprint)
    recipes = list_all_recipes(hass)
    builtin_first = sorted(recipes, key=lambda r: (0 if r.get("builtin") else 1, str(r.get("id") or "")))
    for r in builtin_first:
        rid = r.get("id")
        path = r.get("path")
        if not rid or not path:
            continue
        try:
            recipe_text = Path(path).read_text("utf-8")
        except Exception:
            continue
        recipe_fp = _build_recipe_fingerprint(recipe_text)
        if recipe_fp.strip() == import_fingerprint.strip():
            return rid
        if import_relaxed and _relax_recipe_fingerprint(recipe_fp).strip() == import_relaxed.strip():
            return rid
    return None


def _find_recipe_path_by_id(hass: HomeAssistant, recipe_id: str) -> Path | None:
    for r in list_all_recipes(hass):
        if r.get("id") == recipe_id:
            try:
                return Path(str(r.get("path")))
            except Exception:
                return None
    return None



def _validate_recipe_text(recipe_text: str) -> list[str]:
    """Return a list of issues/warnings for a recipe YAML text.

    This is best-effort and should not be treated as a schema validator; it is a preflight UX helper.
    """
    issues: list[str] = []
    if "lvgl:" not in recipe_text:
        issues.append("Missing top-level `lvgl:` block.")
    if _RECIPE_MARKER not in recipe_text and "pages:" not in recipe_text:
        issues.append("Missing `#__LVGL_PAGES__` marker (recommended) and no obvious `pages:` key was found.")
    # YAML parse check
    try:
        yaml.safe_load(recipe_text)
    except Exception as e:
        issues.append(f"Recipe YAML parse failed: {e}")
    # Friendly hints
    if "display:" not in recipe_text:
        issues.append("No `display:` section detected (is this a full hardware recipe?).")
    if "touchscreen:" not in recipe_text:
        issues.append("No `touchscreen:` section detected (touch may not be configured).")
    return issues


def _extract_recipe_metadata_from_text(recipe_text: str, recipe_id: str | None = None) -> dict:
    """Extract metadata from a stored recipe file.

    We try to parse YAML; if it fails we fall back to lightweight regex hints.
    If resolution still missing, try to extract WxH from recipe_id (e.g. jc1060p470_esp32p4_1024x600).
    """
    meta: dict = {"label": None}
    try:
        model = _yaml_import.load_yaml_lenient(recipe_text) or {}
        if isinstance(model, dict):
            meta = _extract_recipe_metadata(model, recipe_text, label=None)
    except Exception:
        pass
    if not isinstance(meta.get("resolution"), dict) or not (meta["resolution"].get("width") and meta["resolution"].get("height")):
        m = re.search(r"\bwidth:\s*(\d+)\b.*?\bheight:\s*(\d+)\b", recipe_text, flags=re.S)
        if m:
            meta["resolution"] = {"width": int(m.group(1)), "height": int(m.group(2))}
    if not isinstance(meta.get("resolution"), dict) or not (meta["resolution"].get("width") and meta["resolution"].get("height")):
        if recipe_id:
            rx = re.search(r"(\d{3,4})\s*[x×]\s*(\d{3,4})", recipe_id, re.I) or re.search(r"(\d{3,4})x(\d{3,4})", recipe_id)
            if rx:
                meta["resolution"] = {"width": int(rx.group(1)), "height": int(rx.group(2))}
    if "psram" not in meta:
        meta["psram"] = ("psram" in recipe_text.lower())
    return meta




class RecipeCloneView(HomeAssistantView):
    """Clone a recipe (builtin or user) into a new v2 user recipe.

    This supports the end-user workflow: start from a known-good builtin board
    scaffold, then tweak it safely as a custom recipe.

    Body:
      - source_id: str (required)
      - id: str (optional)  -> destination recipe id (slug). If omitted, derived.
      - label: str (optional)
    """

    url = f"/api/{DOMAIN}/recipes/clone"
    name = f"api:{DOMAIN}:recipes_clone"
    requires_auth = False

    async def post(self, request):
        hass = request.app["hass"]
        body = await request.json()
        source_id = body.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            return self.json({"ok": False, "error": "invalid_source_id"}, status_code=400)

        dest_id = body.get("id")
        label = body.get("label")

        if dest_id is not None and (not isinstance(dest_id, str) or not dest_id.strip()):
            return self.json({"ok": False, "error": "invalid_id"}, status_code=400)
        if label is not None and (not isinstance(label, str) or not label.strip()):
            return self.json({"ok": False, "error": "invalid_label"}, status_code=400)

        all_recipes = list_all_recipes(hass)
        src = next((r for r in all_recipes if r.get("id") == source_id), None)
        if not src:
            return self.json({"ok": False, "error": "recipe_not_found"}, status_code=404)

        try:
            src_text = _read_recipe_file(Path(src.get("path")))
        except Exception as e:
            return self.json({"ok": False, "error": "read_failed", "detail": str(e)}, status_code=500)

        base = re.sub(r"[^a-zA-Z0-9_\-]+", "_", (dest_id or source_id).strip()).strip("_") or "recipe"
        dest_id = base
        root = _user_recipes_root(hass)
        v2_dir = root / "user" / dest_id
        i = 2
        while v2_dir.exists():
            dest_id = f"{base}_{i}"
            v2_dir = root / "user" / dest_id
            i += 1

        v2_dir.mkdir(parents=True, exist_ok=True)
        (v2_dir / "recipe.yaml").write_text(src_text, encoding="utf-8")

        meta = {}
        if src.get("label"):
            meta["label"] = src.get("label")
        if isinstance(label, str) and label.strip():
            meta["label"] = label.strip()
        meta["cloned_from"] = source_id
        (v2_dir / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")

        return self.json({"ok": True, "id": dest_id, "label": meta.get("label")})


class RecipeExportView(HomeAssistantView):
    """Export a recipe's YAML + metadata for download/backup."""

    url = f"/api/{DOMAIN}/recipes/{{recipe_id}}/export"
    name = f"api:{DOMAIN}:recipes_export"
    requires_auth = False

    async def get(self, request, recipe_id: str):
        hass = request.app["hass"]
        all_recipes = list_all_recipes(hass)
        r = next((x for x in all_recipes if x.get("id") == recipe_id), None)
        if not r:
            return self.json({"ok": False, "error": "recipe_not_found"}, status_code=404)

        try:
            yaml_text = _read_recipe_file(Path(r.get("path")))
        except Exception as e:
            return self.json({"ok": False, "error": "read_failed", "detail": str(e)}, status_code=500)

        meta = {}
        if r.get("builtin"):
            meta = {"label": r.get("label"), "builtin": True}
        else:
            root = _user_recipes_root(hass)
            v2_meta = root / "user" / recipe_id / "metadata.json"
            legacy_meta = root / f"{recipe_id}.metadata.json"
            mp = v2_meta if v2_meta.exists() else legacy_meta
            if mp.exists():
                try:
                    meta = json.loads(mp.read_text("utf-8"))
                except Exception:
                    meta = {}
            if r.get("label") and "label" not in meta:
                meta["label"] = r.get("label")

        return self.json({"ok": True, "id": recipe_id, "label": r.get("label"), "yaml": yaml_text, "metadata": meta})

class RecipeValidateView(HomeAssistantView):
    url = f"/api/{DOMAIN}/recipes/validate"
    name = f"api:{DOMAIN}:recipes_validate"
    requires_auth = False

    async def post(self, request):
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        recipe_id = str(body.get("recipe_id") or "").strip()
        if not recipe_id:
            return self.json({"error": "recipe_id required"}, status_code=400)

        recipe_path = _find_recipe_path_by_id(hass, recipe_id)
        if not recipe_path or not recipe_path.exists():
            return self.json({"error": "recipe not found"}, status_code=404)

        recipe_text = await hass.async_add_executor_job(
            recipe_path.read_text, "utf-8"
        )
        issues = _validate_recipe_text(recipe_text)
        meta = _extract_recipe_metadata_from_text(recipe_text)
        return self.json({"ok": len(issues) == 0, "issues": issues, "meta": meta})





class RecipeImportView(HomeAssistantView):
    """Import a raw ESPHome device YAML and convert it into a normalized hardware recipe (Option B).

    This creates a v2 user recipe under:
      /config/esptoolkit/recipes/user/<slug>/{recipe.yaml,metadata.json}
    """

    url = f"/api/{DOMAIN}/recipes/import"
    name = f"api:{DOMAIN}:recipes_import"
    requires_auth = False

    async def post(self, request):
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        raw_yaml = str(body.get("yaml") or "")
        label = str(body.get("label") or "").strip() or None
        recipe_id = str(body.get("id") or "").strip() or None

        if not raw_yaml.strip():
            return self.json({"ok": False, "error": "yaml_required"}, status_code=400)

        try:
            norm_yaml, meta = _normalize_recipe_yaml(raw_yaml, label=label)
        except Exception as e:
            return self.json({"ok": False, "error": "import_failed", "detail": str(e)}, status_code=400)

        rid = _slugify(recipe_id or meta.get("label") or "recipe")
        # Avoid collisions by suffixing hash
        root = _user_recipes_root(hass) / "user"
        root.mkdir(parents=True, exist_ok=True)
        target_dir = root / rid
        if target_dir.exists():
            h = hashlib.sha1(norm_yaml.encode("utf-8")).hexdigest()[:6]
            target_dir = root / f"{rid}_{h}"

        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "recipe.yaml").write_text(norm_yaml, encoding="utf-8")
        (target_dir / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")

        return self.json({
            "ok": True,
            "id": target_dir.name,
            "label": meta.get("label"),
            "path": str(target_dir / "recipe.yaml"),
            "meta": meta,
        })


class ImportFromYamlView(HomeAssistantView):
    """Import full ESPHome YAML: match/create recipe, create device, reverse LVGL to project, save."""

    url = f"/api/{DOMAIN}/import/from-yaml"
    name = f"api:{DOMAIN}:import_from_yaml"
    requires_auth = False

    async def post(self, request):
        hass: HomeAssistant = request.app["hass"]
        entry_id = _active_entry_id(hass)
        if not entry_id:
            return self.json({"ok": False, "error": "no_active_entry", "log": []}, status_code=500)
        storage = _get_storage(hass, entry_id)
        if storage is None:
            return self.json({"ok": False, "error": "no_active_entry", "log": []}, status_code=500)

        body = await request.json()
        raw_yaml = str(body.get("yaml") or "").strip()
        raw_yaml = raw_yaml.lstrip("\ufeff")
        device_name_override = str(body.get("device_name_override") or "").strip() or None
        log: list[str] = []

        if not raw_yaml:
            return self.json({"ok": False, "error": "yaml_required", "log": []}, status_code=400)

        def _run_import() -> dict:
            nonlocal log
            log.append("Parsing YAML sections…")
            sections = _yaml_str_to_section_map(raw_yaml)
            parsed_root: dict | None = None
            try:
                pr = _yaml_import.load_yaml_lenient(raw_yaml)
                parsed_root = pr if isinstance(pr, dict) else None
            except Exception as e:
                log.append(f"Full-document YAML parse skipped: {e}")
            esphome_body = (sections.get("esphome") or "").strip()
            device_name = device_name_override
            if not device_name and esphome_body:
                name_m = re.search(r"^\s*name\s*:\s*(.+)$", esphome_body, re.MULTILINE)
                if name_m:
                    device_name = name_m.group(1).strip().strip('"\'')
            if not device_name:
                device_name = "imported-device"
            log.append(f"Device name: {device_name}")

            log.append("Matching recipe…")
            fingerprint = _build_recipe_fingerprint(raw_yaml)
            recipe_id = _match_recipe_by_fingerprint(hass, fingerprint)
            created_recipe = False
            if recipe_id:
                log.append(f"Matched recipe: {recipe_id}")
            else:
                log.append("No match; creating new user recipe.")
                try:
                    norm_yaml, meta = _normalize_recipe_yaml(raw_yaml, label=device_name)
                except Exception as e:
                    log.append(f"Recipe create failed: {e}")
                    return {"ok": False, "error": "recipe_create_failed", "detail": str(e)}
                root = _user_recipes_root(hass) / "user"
                root.mkdir(parents=True, exist_ok=True)
                rid = _slugify(device_name or "recipe")
                target_dir = root / rid
                if target_dir.exists():
                    h = hashlib.sha1(norm_yaml.encode("utf-8")).hexdigest()[:6]
                    target_dir = root / f"{rid}_{h}"
                target_dir.mkdir(parents=True, exist_ok=True)
                (target_dir / "recipe.yaml").write_text(norm_yaml, encoding="utf-8")
                (target_dir / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
                recipe_id = target_dir.name
                created_recipe = True
                log.append(f"Created recipe: {recipe_id}")

            slug = re.sub(r"[^a-z0-9]+", "_", (device_name or "").lower()).strip("_") or "device"
            device_id = slug
            existing = storage.get_device(device_id)
            if existing:
                device_id = f"{slug}_{hashlib.sha1(raw_yaml.encode()).hexdigest()[:6]}"
                slug = device_id
            log.append(f"Device id: {device_id}")

            screen: dict = {}
            root_w: int | None = None
            root_h: int | None = None
            try:
                rmeta = _extract_recipe_metadata_from_text(raw_yaml, recipe_id)
                res = rmeta.get("resolution") if isinstance(rmeta, dict) else None
                if isinstance(res, dict):
                    rw = res.get("width")
                    rh = res.get("height")
                    if isinstance(rw, int) and isinstance(rh, int) and rw > 0 and rh > 0:
                        root_w, root_h = rw, rh
                        screen = {"width": rw, "height": rh}
                        log.append(f"Display resolution (import): {rw}×{rh}")
            except Exception as e:
                log.append(f"Resolution hint skipped: {e}")

            log.append("Parsing LVGL to project pages…")
            lvgl_body = (sections.get("lvgl") or "").rstrip()
            if not lvgl_body:
                lvgl_body = _yaml_import.extract_lvgl_section_from_full_yaml(raw_yaml)
            lvgl_warn: list[str] = []
            pages = _yaml_import.parse_lvgl_section_to_pages(
                lvgl_body,
                warn=lvgl_warn,
                root_parent_w=root_w,
                root_parent_h=root_h,
            )
            for w in lvgl_warn:
                log.append(w)
            widget_count = sum(len(p.get("widgets") or []) for p in pages)
            log.append(f"Parsed {len(pages)} page(s), {widget_count} widget(s).")

            widget_ids = set()
            for p in pages:
                for w in p.get("widgets") or []:
                    if isinstance(w, dict) and w.get("id"):
                        widget_ids.add(str(w["id"]))

            log.append("Reversing bindings and links…")
            bindings, links = _yaml_import.reverse_bindings_and_links(
                sections,
                widget_ids,
                parsed_root=parsed_root,
                strict_widget_ids=False,
            )
            log.append(f"Found {len(bindings)} binding(s), {len(links)} link(s).")
            action_bindings = _yaml_import.reverse_action_bindings_from_pages(pages)
            log.append(f"Found {len(action_bindings)} action binding(s) from widget events.")
            if len(bindings) == 0 and len(links) == 0 and "homeassistant" in raw_yaml.lower():
                log.append(
                    "No homeassistant bindings detected — sensors may be under `packages:`/`!include` "
                    "(merge into one file for import), or use `platform: homeassistant` with `entity_id`."
                )

            scripts = _yaml_import.reverse_scripts(sections, parsed_root=parsed_root)
            if scripts:
                log.append(f"Parsed {len(scripts)} script(s) (thermostat inc/dec).")

            default_project = _default_project()
            project = dict(default_project)
            project["model_version"] = 1
            project["pages"] = pages
            project["bindings"] = bindings
            project["links"] = links
            project["action_bindings"] = action_bindings
            project["scripts"] = scripts
            project["device"] = {"hardware_recipe_id": recipe_id, "screen": screen}
            disp_bg = None
            try:
                first_page = pages[0] if pages else {}
                if isinstance(first_page, dict):
                    bg = first_page.get("bg_color")
                    if bg is not None:
                        if isinstance(bg, int):
                            disp_bg = f"#{bg:06x}"
                        else:
                            disp_bg = str(bg)
            except Exception:
                pass
            if disp_bg:
                project["disp_bg_color"] = disp_bg
            # Omit "script" from sections when we parsed any into project.scripts to avoid duplicate emit
            section_keys_omit = {"lvgl", "esphome"}
            if scripts:
                section_keys_omit.add("script")
            project["sections"] = {k: v for k, v in sections.items() if k not in section_keys_omit and (v or "").strip()}

            device = DeviceProject(
                device_id=device_id,
                slug=slug,
                name=device_name or device_id,
                hardware_recipe_id=recipe_id,
                api_key=None,
                device_settings={},
                project=project,
            )
            storage.upsert_device(device)
            log.append("Saved device and project.")

            return {
                "ok": True,
                "device_id": device_id,
                "recipe_id": recipe_id,
                "created_recipe": created_recipe,
                "project_summary": {"pages": len(pages), "widget_count": widget_count, "bindings_count": len(bindings), "links_count": len(links)},
                "log": log,
            }

        try:
            result = await hass.async_add_executor_job(_run_import)
        except Exception as e:
            log.append(f"Error: {e}")
            return self.json({"ok": False, "error": "import_failed", "detail": str(e), "log": log}, status_code=500)
        return self.json(result)


class DeviceProjectExportView(HomeAssistantView):
    """Export the current device project model as JSON (for backups / cross-chat portability)."""

    url = f"/api/{DOMAIN}/devices/{{device_id}}/project/export"
    name = f"api:{DOMAIN}:device_project_export"
    requires_auth = False

    async def get(self, request, device_id: str):
        hass: HomeAssistant = request.app["hass"]
        entry_id = _active_entry_id(hass)
        if not entry_id:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        storage = _get_storage(hass, entry_id)
        if storage is None:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        device = storage.get_device(device_id)
        if not device:
            return self.json({"ok": False, "error": "device_not_found"}, status_code=404)

        payload = {
            "device_id": device.device_id,
            "slug": device.slug,
            "name": device.name,
            "hardware_recipe_id": device.hardware_recipe_id,
            "api_key": device.api_key,
            "ota_password": device.ota_password,
            "project": device.project,
        }
        return self.json({"ok": True, "export": payload})


class DeviceProjectImportView(HomeAssistantView):
    """Import/replace a device project model from JSON."""

    url = f"/api/{DOMAIN}/devices/{{device_id}}/project/import"
    name = f"api:{DOMAIN}:device_project_import"
    requires_auth = False

    async def post(self, request, device_id: str):
        hass: HomeAssistant = request.app["hass"]
        entry_id = _active_entry_id(hass)
        if not entry_id:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        storage = _get_storage(hass, entry_id)
        if storage is None:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        device = storage.get_device(device_id)
        if not device:
            return self.json({"ok": False, "error": "device_not_found"}, status_code=404)

        body = await request.json()
        export = body.get("export") if isinstance(body, dict) else None
        if not isinstance(export, dict):
            return self.json({"ok": False, "error": "export_required"}, status_code=400)

        project = export.get("project")
        if not isinstance(project, dict):
            return self.json({"ok": False, "error": "project_required"}, status_code=400)

        # Minimal validation + migration hook
        if "model_version" not in project:
            project["model_version"] = 1

        device.project = project
        if isinstance(export.get("hardware_recipe_id"), str):
            device.hardware_recipe_id = export.get("hardware_recipe_id") or None
        if export.get("api_key") is not None:
            device.api_key = str(export["api_key"]).strip() or None
        if export.get("ota_password") is not None:
            device.ota_password = str(export["ota_password"]).strip() or None

        storage.upsert_device(device)
        await storage.async_save()
        return self.json({"ok": True})



def _export_merge_yaml(existing: str, generated_block: str, begin_marker: str, end_marker: str) -> tuple[str, str]:
    """Compute new file content and mode. Removes any previous designer-generated block when no markers."""
    if begin_marker in existing and end_marker in existing:
        begin_idx = existing.find(begin_marker)
        end_idx = existing.find(end_marker)
        if end_idx < begin_idx:
            raise ValueError("END appears before BEGIN")
        pre = existing[:begin_idx]
        post = existing[end_idx + len(end_marker):]
        new_text = pre.rstrip() + "\n\n" + generated_block + "\n" + post.lstrip()
        return new_text, "merged"
    comment = "\n" + "# --- USER YAML BELOW (preserved on future exports if you keep the marker block above) ---\n" + "# Add sensors, switches, substitutions, packages, etc.\n"
    gen_marker = f"# Generated by {DOMAIN}"
    if gen_marker in existing:
        lines = existing.splitlines(keepends=True)
        start_i = None
        end_i = len(lines)
        for i, line in enumerate(lines):
            if gen_marker in line:
                start_i = i
                break
        if start_i is not None:
            for i in range(start_i + 1, len(lines)):
                if lines[i].strip().startswith("# --- ") and "USER YAML" in lines[i]:
                    end_i = i
                    break
            before = "".join(lines[:start_i]).rstrip()
            after = "".join(lines[end_i:]).lstrip()
            new_text = (before + "\n\n" + generated_block + comment + ("\n" + after if after else "")).strip() + "\n"
        else:
            new_text = generated_block + comment
    else:
        new_text = generated_block + comment
    return new_text, "new"


class DeviceExportPreviewView(HomeAssistantView):
    """Preview an export (safe-merge) and return a diff + expected hash."""

    url = f"/api/{DOMAIN}/devices/{{device_id}}/export/preview"
    name = f"api:{DOMAIN}:device_export_preview"
    requires_auth = False

    async def post(self, request, device_id: str):
        hass = request.app["hass"]
        entry_id = request.query.get("entry_id")
        if not entry_id:
            return self.json({"ok": False, "error": "missing_entry_id"}, status_code=400)

        storage = _get_storage(hass, entry_id)
        if storage is None:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        device = storage.get_device(device_id)
        if not device:
            return self.json({"ok": False, "error": "device_not_found"}, status_code=404)

        yaml_text, _ = await hass.async_add_executor_job(
            _sync_compile_device_yaml, hass, device, None, None
        )

        BEGIN = "# --- BEGIN ESPHOME_TOUCH_DESIGNER GENERATED ---"
        END = "# --- END ESPHOME_TOUCH_DESIGNER GENERATED ---"

        esphome_dir = Path(hass.config.path("esphome"))
        esphome_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{device.slug or device.device_id}.yaml"
        outp = esphome_dir / fname

        generated_block = f"{BEGIN}\n{yaml_text.rstrip()}\n{END}\n"

        def _read_existing(p: Path) -> str:
            return p.read_text("utf-8", errors="ignore") if p.exists() else ""

        existing = await hass.async_add_executor_job(_read_existing, outp)

        try:
            new_text, mode = _export_merge_yaml(existing, generated_block, BEGIN, END)
        except ValueError as e:
            return self.json({"ok": False, "error": "marker_corrupt", "detail": str(e), "path": str(outp)}, status_code=409)

        import hashlib, difflib
        existing_hash = hashlib.sha256(existing.encode("utf-8")).hexdigest()
        new_hash = hashlib.sha256(new_text.encode("utf-8")).hexdigest()
        diff = "\n".join(difflib.unified_diff(
            existing.splitlines(),
            new_text.splitlines(),
            fromfile=str(outp),
            tofile=str(outp),
            lineterm="",
        ))

        return self.json({
            "ok": True,
            "path": str(outp),
            "mode": mode,
            "expected_hash": existing_hash,
            "new_hash": new_hash,
            "diff": diff,
            "new_text": new_text,
            "exists": outp.exists(),
        })


class DeviceExportView(HomeAssistantView):
    """Write the safe-merged YAML to /config/esphome/<slug>.yaml."""

    url = f"/api/{DOMAIN}/devices/{{device_id}}/export"
    name = f"api:{DOMAIN}:device_export"
    requires_auth = False

    async def post(self, request, device_id: str):
        hass = request.app["hass"]
        entry_id = request.query.get("entry_id")
        if not entry_id:
            return self.json({"ok": False, "error": "missing_entry_id"}, status_code=400)

        storage = _get_storage(hass, entry_id)
        if storage is None:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        device = storage.get_device(device_id)
        if not device:
            return self.json({"ok": False, "error": "device_not_found"}, status_code=404)

        body = None
        try:
            body = await request.json()
        except Exception:
            body = None
        expected_hash = body.get("expected_hash") if isinstance(body, dict) else None

        yaml_text, _ = await hass.async_add_executor_job(
            _sync_compile_device_yaml, hass, device, None, None
        )

        BEGIN = "# --- BEGIN ESPHOME_TOUCH_DESIGNER GENERATED ---"
        END = "# --- END ESPHOME_TOUCH_DESIGNER GENERATED ---"

        esphome_dir = Path(hass.config.path("esphome"))
        esphome_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{device.slug or device.device_id}.yaml"
        outp = esphome_dir / fname

        generated_block = f"{BEGIN}\n{yaml_text.rstrip()}\n{END}\n"

        def _read_existing(p: Path) -> str:
            return p.read_text("utf-8", errors="ignore") if p.exists() else ""

        existing = await hass.async_add_executor_job(_read_existing, outp)

        import hashlib
        existing_hash = hashlib.sha256(existing.encode("utf-8")).hexdigest()
        if expected_hash and str(expected_hash) != existing_hash:
            return self.json({"ok": False, "error": "externally_modified", "detail": "File changed since preview.", "path": str(outp)}, status_code=409)

        try:
            new_text, mode = _export_merge_yaml(existing, generated_block, BEGIN, END)
        except ValueError as e:
            return self.json({"ok": False, "error": "marker_corrupt", "detail": str(e), "path": str(outp)}, status_code=409)

        await hass.async_add_executor_job(outp.write_text, new_text, "utf-8")
        new_hash = hashlib.sha256(new_text.encode("utf-8")).hexdigest()

        return self.json({"ok": True, "path": str(outp), "mode": mode, "hash": new_hash})


def _write_device_yaml_to_esphome(hass: HomeAssistant, device: DeviceProject) -> tuple[Path | None, dict | None]:
    """Compile device to YAML and write to /config/esphome/<slug>.yaml. Returns (path, None) on success or (None, error_json_response).
    Uses same recipe source (builtin or user) as Compile/Deploy so LVGL and all sections are included."""
    recipe_text = _get_recipe_text_for_device(hass, device)
    try:
        yaml_text = compile_to_esphome_yaml(device, recipe_text=recipe_text)
    except Exception as e:
        return None, {"ok": False, "error": "compile_failed", "detail": str(e)}
    BEGIN = "# --- BEGIN ESPHOME_TOUCH_DESIGNER GENERATED ---"
    END = "# --- END ESPHOME_TOUCH_DESIGNER GENERATED ---"
    esphome_dir = Path(hass.config.path("esphome"))
    esphome_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{device.slug or device.device_id}.yaml"
    outp = esphome_dir / fname
    generated_block = f"{BEGIN}\n{yaml_text.rstrip()}\n{END}\n"
    existing = outp.read_text("utf-8", errors="ignore") if outp.exists() else ""
    try:
        new_text, _mode = _export_merge_yaml(existing, generated_block, BEGIN, END)
    except ValueError as e:
        return None, {"ok": False, "error": "marker_corrupt", "detail": str(e), "path": str(outp)}
    outp.write_text(new_text, encoding="utf-8")
    return outp, None


class DeviceValidateExportView(HomeAssistantView):
    """Write compiled YAML to esphome/ then call add-on config-check (validate) HA service."""

    url = f"/api/{DOMAIN}/devices/{{device_id}}/validate_export"
    name = f"api:{DOMAIN}:device_validate_export"
    requires_auth = False

    async def post(self, request, device_id: str):
        hass: HomeAssistant = request.app["hass"]
        entry_id = request.query.get("entry_id") or _active_entry_id(hass)
        if not entry_id:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        storage = _get_storage(hass, entry_id)
        if storage is None:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        device = storage.get_device(device_id)
        if not device:
            return self.json({"ok": False, "error": "device_not_found"}, status_code=404)
        outp, err = await hass.async_add_executor_job(_write_device_yaml_to_esphome, hass, device)
        if err is not None:
            return self.json(err, status_code=500 if err.get("error") == "compile_failed" else 409)
        conn = _get_addon_connection(hass, entry_id)
        if not conn:
            return self.json({"ok": False, "error": "no_addon_connection", "stdout": "", "stderr": "EspToolkit add-on not configured."}, status_code=503)
        base_url, token = conn
        fname = outp.name
        ok, result = await _esphome_addon_request(
            hass,
            base_url,
            "api/config-check",
            {"config_source": "file", "filename": fname},
            token=token,
        )
        return self.json({
            "ok": ok,
            "stdout": result if ok else "",
            "stderr": "" if ok else result,
        })


class DeviceDeployExportView(HomeAssistantView):
    """Write compiled YAML to esphome/ then call add-on run (validate + compile + upload)."""

    url = f"/api/{DOMAIN}/devices/{{device_id}}/deploy_export"
    name = f"api:{DOMAIN}:device_deploy_export"
    requires_auth = False

    async def post(self, request, device_id: str):
        hass: HomeAssistant = request.app["hass"]
        entry_id = request.query.get("entry_id") or _active_entry_id(hass)
        if not entry_id:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        storage = _get_storage(hass, entry_id)
        if storage is None:
            return self.json({"ok": False, "error": "no_active_entry"}, status_code=500)
        device = storage.get_device(device_id)
        if not device:
            return self.json({"ok": False, "error": "device_not_found"}, status_code=404)
        outp, err = await hass.async_add_executor_job(_write_device_yaml_to_esphome, hass, device)
        if err is not None:
            return self.json(err, status_code=500 if err.get("error") == "compile_failed" else 409)
        conn = _get_addon_connection(hass, entry_id)
        if not conn:
            return self.json({"ok": False, "error": "no_addon_connection", "detail": "EspToolkit add-on not configured."}, status_code=503)
        base_url, token = conn
        fname = outp.name
        payload = {"config_source": "file", "filename": fname}
        try:
            body = await request.json() if request.can_read_body else {}
        except Exception:
            body = {}
        device_override = (body or {}).get("device")
        if isinstance(device_override, str) and device_override.strip():
            payload["device"] = device_override.strip()
        # Use run (validate + compile + upload); upload alone expects existing firmware.bin
        ok, result = await _esphome_addon_request(
            hass,
            base_url,
            "api/run",
            payload,
            token=token,
        )
        if ok:
            return self.json({"ok": True, "path": str(outp), "result": result})
        return self.json({"ok": False, "error": "addon_failed", "detail": result, "path": str(outp)}, status_code=502)


class EntityCapabilitiesView(HomeAssistantView):

    url = f"/api/{DOMAIN}/ha/entities/{{entity_id}}/capabilities"
    name = f"api:{DOMAIN}:ha_entity_capabilities"
    requires_auth = False

    async def get(self, request, entity_id: str):
        hass: HomeAssistant = request.app["hass"]
        st = hass.states.get(entity_id)
        if not st:
            return self.json({"error":"entity not found"}, status_code=404)
        domain = entity_id.split(".",1)[0]
        # Expose supported_features and common attributes for template selection.
        attrs = dict(st.attributes)
        sf = attrs.get("supported_features")
        # Service availability (best-effort)
        svc = hass.services.async_services().get(domain, {})
        services = sorted(list(svc.keys())) if isinstance(svc, dict) else []
        return self.json({
            "entity_id": entity_id,
            "domain": domain,
            "state": st.state,
            "supported_features": sf,
            "attributes": attrs,
            "services": services,
        })

def _plugins_dir(hass: HomeAssistant) -> Path:
    p = Path(hass.config.path(PLUGINS_DIR))
    (p / "controls").mkdir(parents=True, exist_ok=True)
    (p / "widgets").mkdir(parents=True, exist_ok=True)
    return p

class PluginsListView(HomeAssistantView):
    url = f"/api/{DOMAIN}/plugins"
    name = f"api:{DOMAIN}:plugins"
    requires_auth = False

    async def get(self, request):
        hass: HomeAssistant = request.app["hass"]
        p = _plugins_dir(hass)
        controls=[]
        for f in sorted((p/"controls").glob("*.json")):
            try:
                controls.append(json.loads(f.read_text("utf-8")))
            except Exception as e:
                controls.append({"id": f.stem, "title": f.stem, "error": str(e)})
        widgets=[]
        for f in sorted((p/"widgets").glob("*.json")):
            try:
                widgets.append({"name": f.name, "schema": json.loads(f.read_text("utf-8"))})
            except Exception as e:
                widgets.append({"name": f.name, "error": str(e)})
        return self.json({"controls": controls, "widgets": widgets, "dir": str(p)})
