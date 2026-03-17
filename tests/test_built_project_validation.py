"""
Offline validation of the built TestDummy project (no addon/HA required).
Proves: structure, coverage of widget types and prebuilts, links/bindings shape,
and that we use entities that exercise rich properties (e.g. light with color + white).
"""
import json
import pytest

# Build the same project as upload_testdummy_project
def _built_project():
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
        "palette": {},
        "lvgl_config": {"main": {}, "style_definitions": [], "theme": {}, "gradients": [], "top_layer": {"widgets": []}},
        "bindings": build_bindings(),
        "links": build_links(),
        "action_bindings": build_action_bindings(),
    }


def test_built_project_has_two_pages():
    """Project has Main (base widgets) and Prebuilts & HA page."""
    project = _built_project()
    pages = project.get("pages") or []
    assert len(pages) >= 2
    ids = {p.get("page_id") for p in pages}
    assert "main" in ids
    assert "prebuilts" in ids


def test_built_project_base_widgets_coverage():
    """Main page has one widget per standard schema type (26 types)."""
    from tests.build_testdummy_project import WIDGET_TYPES
    project = _built_project()
    main = next((p for p in project.get("pages") or [] if p.get("page_id") == "main"), None)
    assert main is not None
    widgets = main.get("widgets") or []
    types = {w.get("type") for w in widgets if w.get("type")}
    for wtype in WIDGET_TYPES:
        assert wtype in types, f"Missing base widget type: {wtype}"
    assert len(widgets) == len(WIDGET_TYPES)


def test_built_project_prebuilt_widget_types():
    """Prebuilts page includes arc_labeled, color_picker, white_picker, and other prebuilts."""
    project = _built_project()
    prebuilts_page = next((p for p in project.get("pages") or [] if p.get("page_id") == "prebuilts"), None)
    assert prebuilts_page is not None
    widgets = prebuilts_page.get("widgets") or []
    types = {w.get("type") for w in widgets if w.get("type")}
    # Must include extra widget types and prebuilt building blocks
    assert "arc_labeled" in types
    assert "color_picker" in types
    assert "white_picker" in types
    assert "bar" in types
    assert "led" in types
    assert "button" in types
    assert "slider" in types
    assert "spinbox" in types
    assert "container" in types
    assert "label" in types


def test_built_project_widgets_have_required_fields():
    """Every widget has id, type, and position/size-like fields."""
    project = _built_project()
    for pi, page in enumerate(project.get("pages") or []):
        for wi, w in enumerate(page.get("widgets") or []):
            assert isinstance(w, dict), f"page {pi} widget {wi} not a dict"
            assert w.get("id"), f"page {pi} widget {wi} missing id"
            assert w.get("type"), f"page {pi} widget {wi} missing type"
            assert "x" in w and "y" in w
            assert "w" in w and "h" in w


def test_built_project_links_use_rich_entities():
    """Links reference light (color/white) and sensor entities for coverage."""
    project = _built_project()
    links = project.get("links") or []
    assert len(links) >= 5
    entity_ids = set()
    for ln in links:
        src = ln.get("source") or {}
        eid = src.get("entity_id")
        if eid:
            entity_ids.add(eid)
    # We expect light.table_led_lights (color + white) and a sensor (e.g. battery)
    assert any("light." in eid for eid in entity_ids)
    assert any("sensor." in eid for eid in entity_ids)


def test_built_project_links_target_diverse_actions():
    """Links exercise widget_checked, bar_value, button_bg_color, button_white_temp, label_text."""
    project = _built_project()
    links = project.get("links") or []
    actions = { (ln.get("target") or {}).get("action") for ln in links }
    actions.discard(None)
    assert "widget_checked" in actions
    assert "bar_value" in actions
    assert "button_bg_color" in actions
    assert "button_white_temp" in actions
    assert "label_text" in actions


def test_built_project_bindings_include_light_and_sensor():
    """Bindings declare binary, attribute_number, attribute_text, state for compiler."""
    project = _built_project()
    bindings = project.get("bindings") or []
    assert len(bindings) >= 4
    kinds = {(b.get("entity_id"), b.get("kind"), b.get("attribute")) for b in bindings if b.get("entity_id")}
    # Light: binary, brightness, rgb_color, color_temp
    assert any(k[1] == "binary" for k in kinds)
    assert any(k[1] == "attribute_number" and (k[2] == "brightness" or k[2] == "color_temp") for k in kinds)
    assert any(k[1] == "attribute_text" and k[2] == "rgb_color" for k in kinds)
    # Sensor state (e.g. battery)
    assert any(k[1] == "state" for k in kinds)


def test_built_project_action_bindings_for_pickers():
    """Action bindings send light.turn_on for color_picker and white_picker."""
    project = _built_project()
    actions = project.get("action_bindings") or []
    assert len(actions) >= 2
    widget_ids = {a.get("widget_id") for a in actions}
    assert any("pb_cp" in (wid or "") for wid in widget_ids)
    assert any("pb_wp" in (wid or "") for wid in widget_ids)
    for a in actions:
        call = a.get("call") or {}
        assert call.get("domain") == "light"
        assert call.get("service") == "turn_on"


def test_built_project_serializes_to_valid_json():
    """Built project is JSON-serializable (no non-serializable types)."""
    project = _built_project()
    s = json.dumps(project, separators=(",", ":"))
    back = json.loads(s)
    assert back.get("model_version") == project.get("model_version")
    assert len(back.get("pages", [])) == len(project.get("pages", []))
