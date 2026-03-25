"""
Build TestDummy project JSON for maximum coverage:
- One widget per standard schema type (base widgets)
- Prebuilt widgets (battery, HA connection, arc_labeled, nav bar, color/white picker, etc.)
- HA links and bindings using entities that exercise rich properties
  (e.g. light with color + white, battery sensor for bar/label)

Saved entity widgets: GET /api/esptoolkit/entity-widgets was empty at implementation time. When
definitions exist, extend this script (or a test) to apply one to the project so
it contains entity-widget widgets, links, and scripts for full coverage.
"""
import json

# From GET /api/esptoolkit/schemas/widgets
WIDGET_TYPES = [
    "animimg", "arc", "bar", "button", "buttonmatrix", "canvas", "checkbox",
    "container", "dropdown", "image", "keyboard", "label", "led", "line",
    "meter", "msgboxes", "obj", "qrcode", "roller", "slider", "spinbox",
    "spinner", "switch", "tabview", "textarea", "tileview",
]

# HA entities chosen via Home Assistant MCP (HAMCPTools): rich properties for coverage
# light.table_led_lights: supported_color_modes hs + color_temp, brightness
LIGHT_ENTITY = "light.table_led_lights"
# sensor.iphone_battery_level: 0-100 for bar/label
BATTERY_SENSOR = "sensor.iphone_battery_level"

# Prebuilt style constants (from frontend prebuiltWidgets)
PAD = 8
BG_DARK = 0x1e1e1e
BG_TRACK = 0x333333
TEXT_MUTED = 0x888888
TEXT_NORMAL = 0xaaaaaa


def _wrap_in_group(ox: int, oy: int, widgets: list[dict]) -> list[dict]:
    """Wrap widgets in a root container; children get parent_id and relative positions."""
    if not widgets:
        return []
    if len(widgets) == 1:
        w = {**widgets[0], "x": ox, "y": oy}
        return [w]
    min_x = min(w.get("x", 0) for w in widgets)
    min_y = min(w.get("y", 0) for w in widgets)
    max_x = max(w.get("x", 0) + w.get("w", 0) for w in widgets)
    max_y = max(w.get("y", 0) + w.get("h", 0) for w in widgets)
    gw, gh = max(1, max_x - min_x), max(1, max_y - min_y)
    root_id = widgets[0].get("id", "root")
    if not any(w.get("id") == root_id for w in widgets):
        root_id = "pb_grp_root"
    root = {"id": root_id, "type": "container", "x": ox, "y": oy, "w": gw, "h": gh, "props": {}, "style": {"bg_color": BG_DARK, "radius": 8}}
    out = [root]
    for w in widgets:
        if w.get("id") == root_id:
            continue
        out.append({
            **w,
            "parent_id": root_id,
            "x": w.get("x", 0) - min_x,
            "y": w.get("y", 0) - min_y,
        })
    return out


def build_base_widgets() -> list[dict]:
    """Page 1: one widget per standard type."""
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
    return widgets


def build_prebuilt_widgets() -> list[dict]:
    """Page 2: prebuilt widgets with deterministic IDs for coverage."""
    out = []
    # Grid layout: (x, y) steps
    step_x, step_y = 100, 70
    idx = [0]

    def at():
        i = idx[0]
        idx[0] += 1
        col, row = i % 4, i // 4
        return col * step_x, row * step_y

    # 1. Battery
    x, y = at()
    body_w, body_h, tip_w, tip_h = 44, 20, 6, 8
    fill_pad = 4
    raw = [
        {"id": "pb_bat_body", "type": "container", "x": 0, "y": 4, "w": body_w, "h": body_h, "props": {}, "style": {"bg_color": BG_TRACK, "radius": 4}},
        {"id": "pb_bat_tip", "type": "container", "x": body_w, "y": 8, "w": tip_w, "h": tip_h, "props": {}, "style": {"bg_color": BG_TRACK, "radius": 2}},
        {"id": "pb_bat_fill", "type": "bar", "x": fill_pad, "y": 8, "w": body_w - fill_pad * 2, "h": body_h - 8, "props": {"min_value": 0, "max_value": 100, "value": 75}, "style": {"bg_color": BG_DARK, "radius": 3}},
        {"id": "pb_bat_lbl", "type": "label", "x": body_w + tip_w + 6, "y": 2, "w": 28, "h": 24, "props": {"text": "75%"}, "style": {"text_color": TEXT_MUTED}},
    ]
    grp = _wrap_in_group(x, y, [{"id": "pb_bat_root", "type": "container", "x": 0, "y": 0, "w": 90, "h": 28, "props": {}, "style": {}}] + raw)
    if grp and grp[0].get("style") is not None:
        grp[0]["style"] = {**(grp[0].get("style") or {}), "bg_opa": 0}
    out.extend(grp)

    # 2. WiFi bar (4 bars)
    x, y = at()
    bar_h_list = [8, 14, 20, 26]
    bar_w, gap = 6, 6
    raw = []
    for i, bh in enumerate(bar_h_list):
        raw.append({
            "id": f"pb_wifi_b{i}", "type": "bar",
            "x": i * (bar_w + gap), "y": 26 - bh, "w": bar_w, "h": bh,
            "props": {"min_value": 0, "max_value": 100, "value": 100},
            "style": {"bg_color": BG_DARK, "radius": 2},
        })
    grp = _wrap_in_group(x, y, [{"id": "pb_wifi_root", "type": "container", "x": 0, "y": 0, "w": 50, "h": 28, "props": {}, "style": {}}] + raw)
    out.extend(grp)

    # 3. Color picker (single widget)
    x, y = at()
    out.append({"id": "pb_cp", "type": "color_picker", "x": x, "y": y, "w": 80, "h": 36, "props": {"value": 0x4080ff}, "style": {"bg_color": 0x4080ff, "radius": 8}})

    # 4. White picker (single widget)
    x, y = at()
    out.append({"id": "pb_wp", "type": "white_picker", "x": x, "y": y, "w": 80, "h": 36, "props": {"value": 326}, "style": {"bg_color": 0xffd9bc, "radius": 8}})

    # 5. HA connection (container + led + label)
    x, y = at()
    raw = [
        {"id": "pb_ha_box", "type": "container", "x": 0, "y": 0, "w": 140, "h": 32, "props": {}, "style": {"bg_color": BG_DARK, "radius": 6}},
        {"id": "pb_ha_led", "type": "led", "x": PAD, "y": 8, "w": 16, "h": 16, "props": {"color": TEXT_MUTED}},
        {"id": "pb_ha_lbl", "type": "label", "x": 28, "y": 6, "w": 104, "h": 20, "props": {"text": "..."}, "style": {"text_color": TEXT_MUTED}},
    ]
    out.extend(_wrap_in_group(x, y, [{"id": "pb_ha_root", "type": "container", "x": 0, "y": 0, "w": 140, "h": 32, "props": {}, "style": {}}] + raw))

    # 6. Arc with scale labels (arc_labeled)
    x, y = at()
    out.append({
        "id": "pb_arc_lbl", "type": "arc_labeled", "x": x, "y": y, "w": 120, "h": 120,
        "props": {"min_value": 0, "max_value": 100, "value": 50, "start_angle": 135, "end_angle": 45, "rotation": 0, "mode": "NORMAL", "adjustable": True},
        "style": {"bg_color": BG_TRACK, "radius": 4, "tick_color": TEXT_NORMAL, "tick_width": 3, "tick_length": 0, "label_text_color": TEXT_NORMAL, "label_text_font": "", "label_font_size": 0},
    })

    # 7. Nav bar (prev / home / next)
    x, y = at()
    w, h, btn_w = 200, 44, 56
    gap = (w - 3 * btn_w) / 4
    raw = [
        {"id": "pb_nav_bg", "type": "container", "x": 0, "y": 0, "w": w, "h": h, "props": {}, "style": {"bg_color": BG_DARK, "radius": 8}},
        {"id": "pb_nav_prev", "type": "button", "x": gap, "y": 6, "w": btn_w, "h": 32, "props": {"text": "<"}, "style": {"bg_color": BG_TRACK, "radius": 6}},
        {"id": "pb_nav_home", "type": "button", "x": gap * 2 + btn_w, "y": 6, "w": btn_w, "h": 32, "props": {"text": "H"}, "style": {"bg_color": BG_TRACK, "radius": 6}},
        {"id": "pb_nav_next", "type": "button", "x": gap * 3 + btn_w * 2, "y": 6, "w": btn_w, "h": 32, "props": {"text": ">"}, "style": {"bg_color": BG_TRACK, "radius": 6}},
    ]
    out.extend(_wrap_in_group(x, y, [{"id": "pb_nav_root", "type": "container", "x": 0, "y": 0, "w": w, "h": h, "props": {}, "style": {}}] + raw))

    # 8. Screen saver
    x, y = at()
    raw = [
        {"id": "pb_ss_root", "type": "container", "x": 0, "y": 0, "w": 140, "h": 28, "props": {"timeout_seconds": 60, "backlight_id": "display_backlight"}, "style": {"bg_color": BG_DARK, "radius": 6}},
        {"id": "pb_ss_lbl", "type": "label", "parent_id": "pb_ss_root", "x": PAD, "y": 4, "w": 120, "h": 20, "props": {"text": "Screen saver (60s)"}, "style": {"text_color": TEXT_MUTED, "text_font": "montserrat_14"}},
    ]
    grp = _wrap_in_group(x, y, raw)
    grp[0]["parent_id"] = None
    out.extend(grp)

    # 9. Spinbox +/- (spinbox2 prebuilt equivalent)
    x, y = at()
    out.append({
        "id": "pb_spin2",
        "type": "spinbox2",
        "x": x, "y": y, "w": 200, "h": 48,
        "props": {
            "value": 15, "min_value": 5, "max_value": 30, "step": 1, "decimal_places": 1,
            "minus_text": "-", "plus_text": "+",
        },
        "style": {"radius": 6},
        "events": {},
    })

    # 10. Progress bar + label
    x, y = at()
    raw = [
        {"id": "pb_prog_bar", "type": "bar", "x": 0, "y": 0, "w": 160, "h": 24, "props": {"min_value": 0, "max_value": 100, "value": 50}, "style": {"bg_color": BG_TRACK, "radius": 4}},
        {"id": "pb_prog_lbl", "type": "label", "x": 164, "y": 0, "w": 40, "h": 24, "props": {"text": "50%"}, "style": {"text_color": TEXT_MUTED}},
    ]
    out.extend(_wrap_in_group(x, y, [{"id": "pb_prog_root", "type": "container", "x": 0, "y": 0, "w": 210, "h": 24, "props": {}, "style": {}}] + raw))

    # 11. Section title, 12. Divider, 13. LED dot, 14. Back button, 15. Page indicator
    x, y = at()
    out.append({"id": "pb_sec", "type": "label", "x": x, "y": y, "w": 200, "h": 26, "props": {"text": "Section"}, "style": {"text_color": TEXT_NORMAL}})
    x, y = at()
    out.append({"id": "pb_div", "type": "container", "x": x, "y": y, "w": 200, "h": 2, "props": {}, "style": {"bg_color": BG_TRACK, "radius": 0}})
    x, y = at()
    out.append({"id": "pb_led_dot", "type": "led", "x": x, "y": y, "w": 24, "h": 24, "props": {}, "style": {}})
    x, y = at()
    out.append({"id": "pb_back_btn", "type": "button", "x": x, "y": y, "w": 80, "h": 36, "props": {"text": "< Back"}, "style": {"bg_color": BG_TRACK, "radius": 6}})
    x, y = at()
    out.append({"id": "pb_page_ind", "type": "label", "x": x, "y": y, "w": 48, "h": 24, "props": {"text": "1/3"}, "style": {"text_color": TEXT_MUTED}})

    # 16. Countdown, 17. Status badge, 18. Spacer, 19. Icon, 20. Scrolling text
    x, y = at()
    out.append({"id": "pb_countdown", "type": "label", "x": x, "y": y, "w": 80, "h": 28, "props": {"text": "5:00"}, "style": {"text_color": TEXT_NORMAL}})
    x, y = at()
    out.append({"id": "pb_badge", "type": "label", "x": x, "y": y, "w": 60, "h": 28, "props": {"text": "OK"}, "style": {"bg_color": 0x22c55e, "radius": 6, "text_color": 0xffffff}})
    x, y = at()
    out.append({"id": "pb_spacer", "type": "container", "x": x, "y": y, "w": 24, "h": 24, "props": {}, "style": {"bg_opa": 0}})
    x, y = at()
    out.append({"id": "pb_icon", "type": "label", "x": x, "y": y, "w": 40, "h": 40, "props": {"text": "\u263c"}, "style": {"text_color": TEXT_NORMAL}})
    x, y = at()
    out.append({"id": "pb_scroll_txt", "type": "label", "x": x, "y": y, "w": 200, "h": 24, "props": {"text": "Scrolling text..."}, "style": {"text_color": TEXT_MUTED}})

    # 21. Color temp (white to warm) slider
    x, y = at()
    raw = [
        {"id": "pb_ct_label", "type": "label", "x": 0, "y": 0, "w": 180, "h": 18, "props": {"text": "Cool \u2190  \u2014  \u2192 Warm"}, "style": {"text_color": TEXT_MUTED}},
        {"id": "pb_ct_slider", "type": "slider", "x": 0, "y": 20, "w": 180, "h": 24, "props": {"min_value": 153, "max_value": 500, "value": 250}, "style": {"bg_color": BG_TRACK, "radius": 4}},
    ]
    out.extend(_wrap_in_group(x, y, [{"id": "pb_ct_root", "type": "container", "x": 0, "y": 0, "w": 180, "h": 44, "props": {}, "style": {}}] + raw))

    # 22. Clock (label + time SNTP + interval; validates timezone POSIX in config-check)
    x, y = at()
    out.append({
        "id": "pb_clock_lbl",
        "type": "label",
        "x": x,
        "y": y,
        "w": 100,
        "h": 28,
        "props": {"text": "--:--"},
        "style": {"text_color": TEXT_NORMAL},
    })

    # 23. List / menu (dropdown)
    x, y = at()
    out.append({"id": "pb_list_menu", "type": "dropdown", "x": x, "y": y, "w": 180, "h": 40, "props": {"options": ["Option A", "Option B", "Option C"]}, "style": {"bg_color": BG_TRACK, "radius": 6}})

    # 24. Numeric keypad (container + 12 buttons)
    x, y = at()
    keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "C", "0", "\u232b"]
    cell_w, cell_h, gap = 44, 40, 6
    raw = [{"id": "pb_kp_root", "type": "container", "x": 0, "y": 0, "w": 3 * cell_w + 2 * gap, "h": 4 * cell_h + 3 * gap, "props": {}, "style": {"bg_color": BG_DARK, "radius": 8}}]
    for i, k in enumerate(keys):
        row, col = i // 3, i % 3
        raw.append({
            "id": f"pb_kp_{i}", "type": "button",
            "x": gap + col * (cell_w + gap), "y": gap + row * (cell_h + gap), "w": cell_w, "h": cell_h,
            "props": {"text": k}, "style": {"bg_color": BG_TRACK, "radius": 6},
        })
    out.extend(_wrap_in_group(x, y, raw))

    return out


# Clock prebuilt: time SNTP + interval. Use UTC0 (POSIX); bare "UTC" fails in ESPHome 2026.
ESPHOME_TIME_SNTP = """
time:
  - platform: sntp
    id: etd_time
    timezone: "UTC0"
"""


def build_clock_interval_yaml(label_id: str) -> str:
    """Interval that updates clock label from etd_time (so compiled YAML includes time block)."""
    return f"""
interval:
  - interval: 1s
    then:
      - lvgl.label.update:
          id: {label_id}
          text: !lambda |-
            auto t = id(etd_time).now();
            if (!t.is_valid()) return std::string("--:--");
            char buf[6];
            snprintf(buf, sizeof(buf), "%02d:%02d", t.hour, t.minute);
            return std::string(buf);
"""


def build_esphome_components() -> list:
    """YAML snippets merged by compiler (prebuilts that add time/interval/etc). Includes clock so validate test covers timezone."""
    return [
        {"yaml": ESPHOME_TIME_SNTP.strip(), "_source_root_id": "pb_clock_lbl"},
        {"yaml": build_clock_interval_yaml("pb_clock_lbl").strip(), "_source_root_id": "pb_clock_lbl"},
    ]


def build_bindings() -> list[dict]:
    """Bindings: entity + kind (+ attribute) so compiler creates homeassistant sensors."""
    return [
        {"entity_id": LIGHT_ENTITY, "kind": "binary"},
        {"entity_id": LIGHT_ENTITY, "kind": "attribute_number", "attribute": "brightness"},
        {"entity_id": LIGHT_ENTITY, "kind": "attribute_text", "attribute": "rgb_color"},
        {"entity_id": LIGHT_ENTITY, "kind": "attribute_number", "attribute": "color_temp"},
        {"entity_id": BATTERY_SENSOR, "kind": "state"},
    ]


def build_links() -> list[dict]:
    """Links: source (entity, kind, attribute) -> target (widget_id, action, scale?)."""
    return [
        # Light: on/off -> switch
        {"source": {"entity_id": LIGHT_ENTITY, "kind": "binary"}, "target": {"widget_id": "w_switch", "action": "widget_checked"}},
        # Light: brightness -> bar (0-255 -> 0-100 scale)
        {"source": {"entity_id": LIGHT_ENTITY, "kind": "attribute_number", "attribute": "brightness"}, "target": {"widget_id": "w_bar", "action": "bar_value", "scale": 100.0 / 255.0}},
        # Light: brightness -> slider (prebuilt progress bar)
        {"source": {"entity_id": LIGHT_ENTITY, "kind": "attribute_number", "attribute": "brightness"}, "target": {"widget_id": "pb_prog_bar", "action": "bar_value", "scale": 100.0 / 255.0}},
        # Light: rgb_color -> color_picker (prebuilt)
        {"source": {"entity_id": LIGHT_ENTITY, "kind": "attribute_text", "attribute": "rgb_color"}, "target": {"widget_id": "pb_cp", "action": "button_bg_color"}},
        # Light: color_temp -> white_picker (prebuilt)
        {"source": {"entity_id": LIGHT_ENTITY, "kind": "attribute_number", "attribute": "color_temp"}, "target": {"widget_id": "pb_wp", "action": "button_white_temp"}},
        # Battery sensor state -> label (state is string; bar_value needs numeric)
        {"source": {"entity_id": BATTERY_SENSOR, "kind": "state"}, "target": {"widget_id": "pb_bat_lbl", "action": "label_text", "format": "%s%%"}},
    ]


def build_action_bindings() -> list[dict]:
    """Action bindings: widget event -> HA service call (e.g. color_picker/white_picker apply)."""
    return [
        {"widget_id": "pb_cp", "event": "on_click", "call": {"domain": "light", "service": "turn_on", "entity_id": LIGHT_ENTITY, "data": {}}},
        {"widget_id": "pb_wp", "event": "on_click", "call": {"domain": "light", "service": "turn_on", "entity_id": LIGHT_ENTITY, "data": {}}},
    ]


def main():
    base = build_base_widgets()
    prebuilts = build_prebuilt_widgets()
    project = {
        "model_version": 1,
        "pages": [
            {"page_id": "main", "name": "Main", "widgets": base},
            {"page_id": "prebuilts", "name": "Prebuilts & HA", "widgets": prebuilts},
        ],
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
        "bindings": build_bindings(),
        "links": build_links(),
        "action_bindings": build_action_bindings(),
        "esphome_components": build_esphome_components(),
    }
    print(json.dumps(project, separators=(",", ":")))


if __name__ == "__main__":
    main()
