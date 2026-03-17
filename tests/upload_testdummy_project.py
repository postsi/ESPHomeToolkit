"""One-off: upload TestDummy project via addon MCP (uses ~/.cursor/mcp.json if no env)."""
import json
import os
import sys

# Add repo root so we can import conftest and build_testdummy_project
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import _load_cursor_mcp_esptoolkit, _mcp_tools_call

def _build_project():
    from tests.build_testdummy_project import WIDGET_TYPES
    widgets = []
    for i, wtype in enumerate(WIDGET_TYPES):
        x, y = (i % 6) * 85, (i // 6) * 53
        w, h = 80, 48
        props, style, events = {}, {}, {}
        if wtype == "label": props = {"text": wtype}
        if wtype == "button": props = {"text": wtype}
        if wtype in ("arc", "bar", "meter", "slider"): props = {"min_value": 0, "max_value": 100, "value": 50}
        if wtype == "led": props = {"color": 65280}
        if wtype == "dropdown": props = {"options": "A\nB\nC", "selected": 0}
        if wtype == "roller": props = {"options": "One\nTwo\nThree", "selected": 0}
        if wtype == "spinbox": props = {"value": 0, "min": -10, "max": 10}
        if wtype == "textarea": props = {"text": ""}
        if wtype == "qrcode": props = {"data": "Test"}
        widgets.append({"id": f"w_{wtype}", "type": wtype, "x": x, "y": y, "w": w, "h": h, "props": props, "style": style, "events": events})
    return {
        "model_version": 1,
        "pages": [{"page_id": "main", "name": "Main", "widgets": widgets}],
        "palette": {"color.bg": "#0B0F14", "color.card": "#111827", "color.text": "#E5E7EB", "color.muted": "#9CA3AF"},
        "lvgl_config": {"main": {"disp_bg_color": "#0B0F14", "buffer_size": "100%"}, "style_definitions": [], "theme": {}, "gradients": [], "top_layer": {"widgets": []}},
    }

def main():
    base, token = _load_cursor_mcp_esptoolkit()
    if not base or not token:
        base = os.environ.get("ESPTOOLKIT_ADDON_URL", "").strip()
        token = os.environ.get("ESPTOOLKIT_ADDON_TOKEN", "").strip()
    if not base or not token:
        print("Set ESPTOOLKIT_ADDON_URL and ESPTOOLKIT_ADDON_TOKEN or configure ~/.cursor/mcp.json", file=sys.stderr)
        sys.exit(1)
    entry_id = os.environ.get("ESPTOOLKIT_ENTRY_ID", "01KKSXY9ZNS18R8CKYKDDWRD9P")
    put_body = json.dumps({"project": _build_project()}, separators=(",", ":"))
    path = f"/api/esptoolkit/devices/testdummy/project?entry_id={entry_id}"
    # Use POST (Supervisor proxy to Core often allows only GET/POST; integration supports POST for save)
    raw = _mcp_tools_call(base, token, "local_http", {"method": "POST", "path": path, "body": put_body})
    if raw.startswith("Error:"):
        print(raw, file=sys.stderr)
        sys.exit(1)
    print("OK:", raw[:300])

if __name__ == "__main__":
    main()
