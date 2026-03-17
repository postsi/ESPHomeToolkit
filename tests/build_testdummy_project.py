"""Build TestDummy project JSON with one widget per standard type. Run once to get payload for PUT."""
import json

# From GET /api/esptoolkit/schemas/widgets
WIDGET_TYPES = [
    "animimg", "arc", "bar", "button", "buttonmatrix", "canvas", "checkbox",
    "container", "dropdown", "image", "keyboard", "label", "led", "line",
    "meter", "msgboxes", "obj", "qrcode", "roller", "slider", "spinbox",
    "spinner", "switch", "tabview", "textarea", "tileview",
]

def main():
    widgets = []
    for i, wtype in enumerate(WIDGET_TYPES):
        x = (i % 6) * 85
        y = (i // 6) * 53
        w, h = 80, 48
        props, style, events = {}, {}, {}
        if wtype == "label":
            props = {"text": wtype}
        if wtype == "button":
            props = {"text": wtype}
        if wtype in ("arc", "bar", "meter", "slider"):
            props = {"min_value": 0, "max_value": 100, "value": 50}
        if wtype == "led":
            props = {"color": 65280}
        if wtype == "dropdown":
            props = {"options": "A\nB\nC", "selected": 0}
        if wtype == "roller":
            props = {"options": "One\nTwo\nThree", "selected": 0}
        if wtype == "spinbox":
            props = {"value": 0, "min": -10, "max": 10}
        if wtype == "textarea":
            props = {"text": ""}
        if wtype == "qrcode":
            props = {"data": "Test"}
        widgets.append({
            "id": f"w_{wtype}",
            "type": wtype,
            "x": x, "y": y, "w": w, "h": h,
            "props": props, "style": style, "events": events,
        })
    project = {
        "model_version": 1,
        "pages": [{"page_id": "main", "name": "Main", "widgets": widgets}],
        "palette": {
            "color.bg": "#0B0F14",
            "color.card": "#111827",
            "color.text": "#E5E7EB",
            "color.muted": "#9CA3AF",
        },
        "lvgl_config": {
            "main": {"disp_bg_color": "#0B0F14", "buffer_size": "100%"},
            "style_definitions": [],
            "theme": {},
            "gradients": [],
            "top_layer": {"widgets": []},
        },
    }
    print(json.dumps(project, separators=(",", ":")))

if __name__ == "__main__":
    main()
