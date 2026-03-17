"""One-off: upload TestDummy project via addon MCP (uses ~/.cursor/mcp.json if no env)."""
import json
import os
import sys

# Add repo root so we can import conftest and build_testdummy_project
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import _load_cursor_mcp_esptoolkit, _mcp_tools_call

def _build_project():
    from tests.build_testdummy_project import (
        build_base_widgets,
        build_prebuilt_widgets,
        build_bindings,
        build_links,
        build_action_bindings,
    )
    return {
        "model_version": 1,
        "pages": [
            {"page_id": "main", "name": "Main", "widgets": build_base_widgets()},
            {"page_id": "prebuilts", "name": "Prebuilts & HA", "widgets": build_prebuilt_widgets()},
        ],
        "palette": {"color.bg": "#0B0F14", "color.card": "#111827", "color.text": "#E5E7EB", "color.muted": "#9CA3AF"},
        "lvgl_config": {"main": {"disp_bg_color": "#0B0F14", "buffer_size": "100%"}, "style_definitions": [], "theme": {}, "gradients": [], "top_layer": {"widgets": []}},
        "bindings": build_bindings(),
        "links": build_links(),
        "action_bindings": build_action_bindings(),
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
