"""
End-to-end import lifecycle checks (LVGL parse + bindings reverse) without Home Assistant.
Run: pytest tests/test_import_lifecycle.py -v

**Real heating-controller.yaml** (optional, gitignored): pull from HA with GrimwoodAI MCP
``ha_read_file`` → path ``esphome/heating-controller.yaml`` (relative to ``/config``), save as
``tests/fixtures/heating-controller.yaml``. Tests use that file if present.

Alternatively set ``HEATING_CONTROLLER_YAML`` or ``ESPHOME_CONFIG_DIR`` (see
``test_heating_controller_yaml_resolved_path``).
"""
import importlib.util
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
YAML_IMPORT_PATH = ROOT / "custom_components" / "esptoolkit" / "api" / "yaml_import.py"


def _load_yaml_import():
    spec = importlib.util.spec_from_file_location("yaml_import", YAML_IMPORT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


yi = _load_yaml_import()


def _section_map_from_full_yaml(yaml_str: str) -> dict[str, str]:
    """Same top-level split as views._yaml_str_to_section_map (regex line-based)."""
    sections: dict[str, str] = {}
    lines = yaml_str.splitlines()
    key_re = re.compile(r"^([A-Za-z0-9_]+)\s*:\s*(?:#.*)?$")
    i = 0
    while i < len(lines):
        line = lines[i]
        m = key_re.match(line)
        if m:
            key = m.group(1).strip().lower()
            i += 1
            content_lines = []
            while i < len(lines):
                next_line = lines[i]
                if next_line and not next_line[0].isspace() and key_re.match(next_line):
                    break
                content_lines.append(next_line)
                i += 1
            sections[key] = "\n".join(content_lines).rstrip()
        else:
            i += 1
    return sections


# Realistic merged-style YAML (no packages): sensor + nested LVGL + nested if in on_value
LIFECYCLE_YAML = """
esphome:
  name: lifecycle_test

sensor:
  - platform: homeassistant
    id: ha_out_temp
    entity_id: sensor.outside_temperature
    on_value:
      then:
        - if:
            condition:
              lambda: "return true;"
            then:
              - lvgl.label.update:
                  id: temp_lbl
                  text: !lambda |-
                    return x;

lvgl:
  pages:
    - id: main_page
      widgets:
        - obj:
            id: panel1
            x: 20
            y: 30
            width: 400
            height: 300
            widgets:
              - label:
                  id: temp_lbl
                  align: CENTER
                  x: 0
                  y: 0
                  width: 120
                  height: 40
                  text: "--"
"""


def test_lifecycle_sections_parse_and_bindings_and_geometry():
    yaml_str = LIFECYCLE_YAML.lstrip("\n")
    pr = yi.load_yaml_lenient(yaml_str)
    assert isinstance(pr, dict)

    sections = _section_map_from_full_yaml(yaml_str)
    assert "sensor" in sections
    assert "lvgl" in sections

    pages = yi.parse_lvgl_section_to_pages(
        sections.get("lvgl") or "",
        root_parent_w=800,
        root_parent_h=480,
    )
    flat: list[dict] = []
    for pg in pages:
        flat.extend(pg.get("widgets") or [])
    ids = {w.get("id"): w for w in flat}
    assert "panel1" in ids and "temp_lbl" in ids
    child = ids["temp_lbl"]
    assert child.get("parent_id") == "panel1"
    # 120x40 centered in 400x300 => (140, 130)
    assert child.get("x") == 140
    assert child.get("y") == 130
    assert child.get("props", {}).get("align") == "TOP_LEFT"

    widget_ids = {str(w["id"]) for w in flat if w.get("id")}
    bindings, links = yi.reverse_bindings_and_links(
        sections,
        widget_ids,
        parsed_root=pr,
        strict_widget_ids=False,
    )
    assert len(bindings) >= 1
    for b in bindings:
        assert "." in str(b.get("entity_id") or ""), b
        assert b.get("kind"), b
    assert any(ln.get("target", {}).get("widget_id") == "temp_lbl" for ln in links)


def test_heating_controller_fixture_import_sample():
    """Run heating-style fixture (tests/fixtures/heating_controller_import_sample.yaml) through import pipeline."""
    path = ROOT / "tests" / "fixtures" / "heating_controller_import_sample.yaml"
    yaml_str = path.read_text(encoding="utf-8")
    pr = yi.load_yaml_lenient(yaml_str)
    assert isinstance(pr, dict)

    sections = _section_map_from_full_yaml(yaml_str)
    assert "sensor" in sections and "lvgl" in sections

    pages = yi.parse_lvgl_section_to_pages(
        sections.get("lvgl") or "",
        root_parent_w=1024,
        root_parent_h=600,
    )
    flat: list[dict] = []
    for pg in pages:
        flat.extend(pg.get("widgets") or [])
    by_id = {w.get("id"): w for w in flat}
    assert "lbl_hw_temp" in by_id and "lbl_room" in by_id
    assert by_id["lbl_hw_temp"].get("parent_id") == "card_hw"
    # 200x36 centered in 360x200 => (80, 82)
    assert by_id["lbl_hw_temp"].get("x") == 80
    assert by_id["lbl_hw_temp"].get("y") == 82

    widget_ids = {str(w["id"]) for w in flat if w.get("id")}
    bindings, links = yi.reverse_bindings_and_links(
        sections,
        widget_ids,
        parsed_root=pr,
        strict_widget_ids=False,
    )
    assert len(bindings) >= 2
    for b in bindings:
        assert "." in str(b.get("entity_id") or ""), b
        assert "kind" in b, b
    wids = {ln.get("target", {}).get("widget_id") for ln in links}
    assert "lbl_hw_temp" in wids
    assert "lbl_room" in wids


def _resolve_heating_controller_path() -> Path | None:
    """Prefer local fixture (from MCP pull), then env vars."""
    local = ROOT / "tests" / "fixtures" / "heating-controller.yaml"
    if local.is_file():
        return local
    path_str = (os.environ.get("HEATING_CONTROLLER_YAML") or "").strip()
    if path_str and Path(path_str).is_file():
        return Path(path_str)
    cfg = (os.environ.get("ESPHOME_CONFIG_DIR") or "").strip()
    if cfg:
        candidate = Path(cfg) / "heating-controller.yaml"
        if candidate.is_file():
            return candidate
    return None


def test_heating_controller_yaml_resolved_path():
    """Import pipeline on real heating-controller.yaml: fixture file and/or HA path via MCP/env."""
    path = _resolve_heating_controller_path()
    if path is None:
        pytest.skip(
            "No heating-controller.yaml: save MCP ha_read_file esphome/heating-controller.yaml to "
            "tests/fixtures/heating-controller.yaml, or set HEATING_CONTROLLER_YAML / ESPHOME_CONFIG_DIR."
        )

    yaml_str = path.read_text(encoding="utf-8")
    pr = yi.load_yaml_lenient(yaml_str)
    assert isinstance(pr, dict)

    sections = _section_map_from_full_yaml(yaml_str)
    pages = yi.parse_lvgl_section_to_pages(
        sections.get("lvgl") or "",
        root_parent_w=1024,
        root_parent_h=600,
    )
    flat: list[dict] = []
    for pg in pages:
        flat.extend(pg.get("widgets") or [])
    widget_ids = {str(w["id"]) for w in flat if w.get("id")}
    assert len(widget_ids) > 0, "expected at least one widget id from LVGL parse"

    bindings, links = yi.reverse_bindings_and_links(
        sections,
        widget_ids,
        parsed_root=pr,
        strict_widget_ids=False,
    )
    # Real project should expose HA bindings; if zero, import still completed but log why in CI.
    assert len(bindings) > 0 or len(links) > 0, (
        "heating-controller.yaml parsed but no homeassistant bindings/links — "
        "check sensors under packages/includes or on_value shape"
    )
    for b in bindings:
        assert "." in str(b.get("entity_id") or ""), b
        assert "kind" in b, b
