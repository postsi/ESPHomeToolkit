"""
Offline parity for spinbox2 vertical layout: same formula as
custom_components/esptoolkit/api/views.py::_emit_spinbox2_yaml (row_h).

The designer Canvas uses frontend/src/fontMetrics.ts::fontPxFromId — keep all three in sync.
If this test fails after a compiler change, update fontMetrics.ts and Canvas spinbox2 layoutH.
"""
from __future__ import annotations

import re


def _font_px_from_id(font_id: object, default_px: int = 14) -> int:
    s = str(font_id or "").strip()
    if not s:
        return int(default_px)
    m_asset = re.search(r":(\d{1,3})$", s)
    if m_asset:
        try:
            return max(6, min(96, int(m_asset.group(1))))
        except (TypeError, ValueError):
            return int(default_px)
    m_suffix = re.search(r"_(\d{1,3})$", s)
    if m_suffix:
        try:
            return max(6, min(96, int(m_suffix.group(1))))
        except (TypeError, ValueError):
            return int(default_px)
    return int(default_px)


def spinbox2_row_h_from_widget(w: dict) -> int:
    props = dict(w.get("props") or {})
    style = dict(w.get("style") or {})
    h_val = int(w.get("h", 48))
    text_font = str(style.get("text_font") or props.get("font") or "").strip() or None
    font_px = _font_px_from_id(text_font, 14)
    border_w = int(style.get("border_width", 1) or 0)
    outline_w = int(style.get("outline_width", 0) or 0)
    edge = max(0, border_w, outline_w)
    return max(h_val, font_px + 16 + 2 * edge)


def test_spinbox2_row_h_default_prebuilt_like():
    w = {
        "id": "sb",
        "type": "spinbox2",
        "x": 0,
        "y": 0,
        "w": 200,
        "h": 48,
        "props": {"value": 15, "min_value": 5, "max_value": 30, "step": 1, "decimal_places": 1},
        "style": {"bg_color": 0x1E293B, "border_width": 1, "border_color": 0x475569, "radius": 6, "text_color": 0xE2E8F0},
        "events": {},
    }
    assert spinbox2_row_h_from_widget(w) == 48


def test_spinbox2_row_h_large_font_needs_taller_box():
    w = {
        "id": "sb",
        "type": "spinbox2",
        "x": 0,
        "y": 0,
        "w": 200,
        "h": 48,
        "props": {"value": 0},
        "style": {"text_font": "montserrat_40", "border_width": 1},
        "events": {},
    }
    # 40 + 16 + 2*1 = 58
    assert spinbox2_row_h_from_widget(w) == 58


def test_spinbox2_row_h_respects_explicit_small_height_and_font():
    w = {
        "id": "sb",
        "type": "spinbox2",
        "x": 0,
        "y": 0,
        "w": 200,
        "h": 72,
        "props": {},
        "style": {"text_font": "montserrat_24", "border_width": 1},
        "events": {},
    }
    # max(72, 24+16+2) = 72
    assert spinbox2_row_h_from_widget(w) == 72
