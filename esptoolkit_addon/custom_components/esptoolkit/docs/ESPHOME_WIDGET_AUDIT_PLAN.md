# ESPHome Widget Audit Plan — Per-Widget Plan (No Code Yet)

This document explains **what will be done for every widget** so that:
1. We expose **only** the props/parts/events that ESPHome’s LVGL component supports (and all of them).
2. The **canvas** mimics the **default display behaviour** of each widget on the device (no extra visuals the device doesn’t draw).

Source of truth: **ESPHome source**  
`esphome/components/lvgl/widgets/*.py` and `schemas.py` (base: obj_schema, part_schema, STYLE_PROPS, OBJ_FLAGS, automation_schema).

---

## 1) Palette (26 widgets, ESPHome-backed only)

Six former palette types that do not exist in ESPHome have been removed (schema files deleted, all code references removed). The palette and compiler use only these 26:

| # | Widget       | ESPHome |
|---|--------------|---------|
| 1 | animimg      | animimg.py |
| 2 | arc          | arc.py |
| 3 | bar          | lv_bar.py |
| 4 | button       | button.py |
| 5 | buttonmatrix | buttonmatrix.py |
| 6 | canvas       | canvas.py |
| 7 | checkbox     | checkbox.py |
| 8 | container    | container.py |
| 9 | dropdown     | dropdown.py |
|10 | image        | img.py |
|11 | keyboard     | keyboard.py |
|12 | label        | label.py |
|13 | led          | led.py |
|14 | line         | line.py |
|15 | meter        | meter.py |
|16 | msgboxes     | msgbox.py |
|17 | obj          | obj.py |
|18 | qrcode       | qrcode.py |
|19 | roller       | roller.py |
|20 | slider       | slider.py |
|21 | spinbox      | spinbox.py |
|22 | spinner      | spinner.py |
|23 | switch       | switch.py |
|24 | tabview      | tabview.py |
|25 | textarea     | textarea.py |
|26 | tileview     | tileview.py |

---

## 2) Does this cover events as well as properties?

**Yes.** The audit covers both:

- **Properties:** Widget-specific props, **main** style, and **part** properties (indicator, knob, scrollbar, etc.) — only what ESPHome supports.
- **Events:** For each widget we will list the exact **on_*** events from ESPHome. In ESPHome these come from:
  - **Base** `automation_schema(widget_type)` (LV_EVENT_TRIGGERS: on_click, on_press, on_release, on_long_press, on_short_click, on_value, on_focus, on_defocus, etc., plus SWIPE_TRIGGERS where applicable).
  - **Widget-specific** additions (e.g. arc/slider add `on_value`; dropdown/roller add `on_change`).

**What we’ll do:**

- In each widget’s ESPHome source, note which **on_*** keys are in the schema (or inherited from base).
- Align our **schema `events` section** so we only expose those keys (no fake events).
- Align **frontend** `EVENTS_BY_WIDGET_TYPE` in `bindings/bindingConfig.ts` with that list so the UI only offers valid events for action bindings.

So the plan applies to **events** as well as **props** and **parts**; the per-widget sections below will be extended to include “Events: …” where it wasn’t already stated.

---

## 3) Does the ESPHome view suggest a better grouping in the UI?

**Yes.** ESPHome’s structure is:

- **Base (all widgets):** object flags, align_to, group, state (for styling).
- **Widget-specific:** value, text, options, etc.
- **Style:** one block for the **main** part (STYLE_PROPS).
- **Parts:** one block per **part** (main, indicator, knob, scrollbar, selected, cursor, …), each with its own style keys.
- **Events:** on_click, on_value, on_change, etc.

A **clearer, ESPHome-aligned grouping** in the properties panel would be:

| Group | Contents | Same for all? |
|-------|----------|----------------|
| **Common / Object** | hidden, clickable, scrollable, align_to, group, size override, etc. (flags + layout) | Yes |
| **Widget** | Widget-specific props only (value, text, options, min/max, mode, …) | No — per widget |
| **Style (main)** | Main part style: bg_color, border_*, radius, pad_*, text_*, etc. | Same keys, different defaults |
| **Part: &lt;name&gt;** | One collapsible section per part: **indicator**, **knob**, **scrollbar**, **selected**, **cursor**, etc. Only show parts that this widget type has. | Parts vary by widget (arc: main, indicator, knob; bar: main, indicator; etc.) |
| **State** | State-based style overrides (pressed, checked, focused) — e.g. our `state._yaml` or expanded state blocks | Yes (concept) |
| **Events** | on_click, on_value, on_release, … — only the events this widget supports | Per widget |

Benefits:

- **Matches ESPHome YAML:** “Widget” = top-level widget keys; “Style (main)” = main part; “Part: indicator” = indicator block; “Events” = on_*.
- **Less confusion:** No “style” keys that are actually for a part mixed into main style; each part is explicit.
- **Common first:** Object/Common at top, then widget-specific, then main style, then parts, then events.

**Implementation note:** Our schemas already have `groups` (e.g. “Value & range”, “Knob”, “Indicator”, “Events”). We would refactor those so that (1) “Common” = base flags + align_to + size override, (2) “Widget” = widget-only props, (3) “Style (main)” = current style keys, (4) one group per part named after the part (e.g. “indicator”, “knob”), (5) “State” and “Events” as today. So the **new view of the world leads to a better, consistent grouping**: Common → Widget → Style (main) → Part (indicator) → Part (knob) → … → State → Events.

---

## Base (all widgets)

From `schemas.py` and `defines.py`, **every** widget gets:

- **Object flags** (OBJ_FLAGS): hidden, clickable, click_focusable, checkable, scrollable, scroll_elastic, scroll_momentum, scroll_one, scroll_chain_hor, scroll_chain_ver, scroll_chain, scroll_on_focus, scroll_with_arrow, snappable, press_lock, event_bubble, gesture_bubble, adv_hittest, ignore_layout, floating, overflow_visible, layout_1, layout_2, widget_1, widget_2, user_1–4.
- **State** (SET_STATE_SCHEMA): checked, focused, etc. for styling.
- **align_to**: id, align, x, y.
- **group**: for encoder/keypad.
- **Automation**: on_* events (from LV_EVENT_TRIGGERS + SWIPE_TRIGGERS; some widgets add on_value).
- **Style**: STYLE_PROPS apply to main part (and to optional parts). No `font_size` in ESPHome; they use `text_font` (font id).

Our **common_extras** add many of these; we must **remove** anything not in ESPHome (e.g. we already removed `font_size`) and ensure we don’t **omit** any ESPHome option.

---

## 1. **arc**

- **ESPHome** (`arc.py`): Props: value, min_value, max_value, start_angle, end_angle, rotation, adjustable, mode (NORMAL/REVERSE/SYMMETRICAL), change_rate. Parts: main, indicator, knob. No child widgets, no built-in value label.
- **Default UI**: Arc track + indicator arc + knob only. No text.
- **Our schema**: We had value_label_offset_x/y and font_size (removed). We have knob_offset; ESPHome arc doesn’t expose knob_offset in the schema (LVGL might). Need to confirm and possibly remove. We use bg_start_angle/bg_end_angle; ESPHome uses start_angle/end_angle (mapped to bg_start_angle/bg_end_angle in to_code). We should align key names with ESPHome (start_angle, end_angle) in our schema and compiler.
- **Canvas**: Already updated to draw only arc + indicator + knob (no value label). No further change for “default UI.” If we add scaling, it’s only for the arc graphic, not text.

**Planned changes:**
- Schema: Ensure only value, min_value, max_value, start_angle, end_angle, rotation, adjustable, mode, change_rate (+ base flags/state/align_to/group/events). Remove knob_offset if not in ESPHome schema. Map our keys to ESPHome names (start_angle → bg_start_angle in compiler if needed).
- Canvas: No value text; already done. Optionally scale track/knob with size for readability.

---

## 2. **bar**

- **ESPHome** (`lv_bar.py`): Props: value, start_value (only for RANGE mode), min_value, max_value, mode (BAR_MODES), animated. Parts: main, indicator (no knob).
- **Default UI**: Bar track + indicator fill. No text, no value label.
- **Our schema**: Compare our bar.json props/style/parts to this list; add missing (e.g. animated), remove any non-ESPHome (e.g. any font_size/value_label if present).
- **Canvas**: Draw only bar track + indicator; no value label. Match device.

**Planned changes:**
- Schema: Align props and parts with lv_bar.py; add animated if missing.
- Canvas: Ensure we never draw a value label; only bar + indicator.

---

## 3. **button**

- **ESPHome** (`button.py`): Parts: main only. Schema: TEXT_SCHEMA (text). When `text` is set, ESPHome creates a **child label** (lv.label_create(var)) and sets its text. So the device shows: button background + one child label with the button text.
- **Default UI**: Button (styled rect) + one label child showing `text`. No other default content.
- **Our schema**: We have text, checkable, font; no widgets (button can have widgets instead of text in ESPHome, but we can keep it text-only for simplicity). Ensure we don’t have props ESPHome doesn’t have.
- **Canvas**: Draw button (rect) + text in the centre (or per text_align). That matches device (one label child with text). No extra decorations.

**Planned changes:**
- Schema: text, checkable, and base; remove any non-ESPHome props. Style: only ESPHome STYLE_PROPS (no font_size; use text_font if we ever support font id).
- Canvas: Keep current behaviour (button + text); ensure text alignment and padding match LVGL default (e.g. centred, padding from style).

---

## 4. **slider**

- **ESPHome** (`slider.py`): Props: value, min_value, max_value, mode, animated. Parts: main, indicator, knob.
- **Default UI**: Slider track + indicator + knob. No value label.
- **Our schema**: Align with SLIDER_SCHEMA; add animated if missing.
- **Canvas**: Draw track + indicator + knob only; no value text. Match device.

**Planned changes:**
- Schema: value, min_value, max_value, mode, animated; parts main, indicator, knob.
- Canvas: No value label; only track, indicator, knob.

---

## 5. **switch**

- **ESPHome** (`switch.py`): No widget-specific props in schema. Parts: main, indicator, knob. to_code is empty; switch is just the LVGL switch widget.
- **Default UI**: Switch track + knob (on/off). No text.
- **Our schema**: Only base + parts (main, indicator, knob). No extra props.
- **Canvas**: Draw track + knob; no label. Already typical.

**Planned changes:**
- Schema: No widget-specific props; only base and parts.
- Canvas: Ensure only track + knob; no extra text or value.

---

## 6. **checkbox**

- **ESPHome** (`checkbox.py`): Schema: TEXT_SCHEMA (text), pad_column (optional). Parts: main, indicator. to_code: sets checkbox text via lv.checkbox_set_text. So device shows: checkbox box + label text (built into checkbox widget).
- **Default UI**: Checkbox indicator (box) + text beside it. One widget, not a separate label.
- **Our schema**: text, pad_column; parts main, indicator. No font_size.
- **Canvas**: Draw checkbox box + text; match alignment/size to LVGL default (e.g. text to the right of box, one line).

**Planned changes:**
- Schema: text, pad_column; parts main, indicator. Remove any non-ESPHome.
- Canvas: Keep checkbox + text; no extra value label or decoration.

---

## 7. **dropdown**

- **ESPHome** (`dropdown.py`): Schema: options (required), selected_index or selected_text (exclusive), dir (default BOTTOM), symbol (optional), dropdown_list (part styling). Parts: main, indicator. Dropdown list is a separate object (dropdown_list_spec: main, selected, scrollbar). Device shows: button-like area with selected option text + arrow; opening shows list.
- **Default UI**: Closed: selected option text + symbol. Open: list of options. No extra “value” label beyond the selected text.
- **Our schema**: options, selected_index, dir, symbol; dropdown_list part styling. Align with DROPDOWN_SCHEMA.
- **Canvas**: Draw closed state: rectangle + selected option text + arrow/symbol. No separate numeric value.

**Planned changes:**
- Schema: options, selected_index (or selected_text), dir, symbol, dropdown_list (parts: main, selected, scrollbar for list). Remove any non-ESPHome.
- Canvas: Closed dropdown: selected text + symbol only; no extra labels.

---

## 8. **label**

- **ESPHome** (`label.py`): Schema: TEXT_SCHEMA (text), recolor, long_mode. Parts: main, scrollbar, selected. No child widgets; label is a single widget.
- **Default UI**: Text only (with optional recolor, long_mode behaviour). No icon, no value formatting beyond text.
- **Our schema**: text, font (we use font; ESPHome uses text_font as font id), recolor, long_mode. Remove font_size; if we keep “font” it should map to text_font (id).
- **Canvas**: Draw text only; use long_mode (wrap/clip/dot/scroll) and recolor if set. No extra visuals.

**Planned changes:**
- Schema: text, recolor, long_mode; style includes text_font (not font_size). Align with label.py.
- Canvas: Text only; respect long_mode and recolor. No value label or icon unless we add a separate widget.

---

## 9. **container**

- **ESPHome** (`container.py`): Schema: width, height (default 100%). Parts: main, scrollbar. on_create: removes all styles (lv.obj_remove_style_all). So it’s a plain obj that can hold children; no default content.
- **Default UI**: Empty (or children). No built-in border/text.
- **Our schema**: width, height; parts main, scrollbar. No extra props.
- **Canvas**: Draw empty rect (or placeholder “container”); children drawn on top. No value label.

**Planned changes:**
- Schema: width, height; parts main, scrollbar. Remove non-ESPHome.
- Canvas: Empty container; no default text or value.

---

## 10. **obj**

- **ESPHome** (`obj.py`): No widget-specific schema. Parts: main, scrollbar. Base object; no default content.
- **Default UI**: Empty (or styled). No text, no value.
- **Our schema**: Only base. No extra props.
- **Canvas**: Empty rect or “obj” placeholder. No value label.

**Planned changes:**
- Schema: Base only; parts main, scrollbar.
- Canvas: No extra content.

---

## 11. **image** (ESPHome: img)

- **ESPHome** (`img.py`): Schema: src (required), pivot_x, pivot_y, angle, zoom, offset_x, offset_y, antialias, mode (VIRTUAL/REAL). Parts: main only. No child label. Device shows: image only.
- **Default UI**: Image (or placeholder if no src). No text overlay.
- **Our schema**: src and style (e.g. clip_corner, radius); align with IMG_SCHEMA (pivot, angle, zoom, offset, antialias, mode).
- **Canvas**: Draw image or placeholder; no value label or text unless it’s part of the image.

**Planned changes:**
- Schema: src, pivot_x, pivot_y, angle, zoom, offset_x, offset_y, antialias, mode; parts main. Remove non-ESPHome.
- Canvas: Image/placeholder only; no default text.

---

## 12. **textarea**

- **ESPHome** (`textarea.py`): Schema: text, placeholder_text, accepted_chars, one_line, password_mode, max_length. Parts: main, scrollbar, selected, cursor, textarea_placeholder. Device shows: editable text area (and placeholder when empty).
- **Default UI**: Text area with optional placeholder. Cursor when focused. No extra “value” label.
- **Our schema**: Align with TEXTAREA_SCHEMA; parts main, scrollbar, selected, cursor, textarea_placeholder.
- **Canvas**: Draw text (or placeholder) and optional cursor; no separate value label.

**Planned changes:**
- Schema: text, placeholder_text, accepted_chars, one_line, password_mode, max_length; parts as above.
- Canvas: Text/placeholder + cursor; match device.

---

## 13. **roller**

- **ESPHome** (`roller.py`): Schema: options (required), selected_index or selected_text, visible_row_count, mode. Parts: main, selected. Device shows: rolling list of options with one selected.
- **Default UI**: List of option strings; selected one highlighted. No numeric value label.
- **Our schema**: options, selected_index, visible_row_count, mode; parts main, selected (and items if we have it). Align with ROLLER_SCHEMA.
- **Canvas**: Draw options list + selected style; no extra value text.

**Planned changes:**
- Schema: options, selected_index/selected_text, visible_row_count, mode; parts main, selected.
- Canvas: Roller list only; no value label.

---

## 14. **spinbox**

- **ESPHome** (`spinbox.py`): Schema: value, range_from, range_to, digits, selected_digit, decimal_places, rollover. Parts: main, scrollbar, selected, cursor, textarea_placeholder. Device shows: number with digits; optional +/- or edit. Spinbox has built-in text (the number).
- **Default UI**: Number display (and buttons/arrows in LVGL). No separate “value” label; the widget shows the value.
- **Our schema**: value, range_from, range_to, digits, selected_digit, decimal_places, rollover; parts as in spinbox.py.
- **Canvas**: Draw the number (value) as the main content; optionally +/- or digit indicators. Match device (value is the main visible content).

**Planned changes:**
- Schema: Align with SPINBOX_SCHEMA; parts as ESPHome.
- Canvas: Show value as the spinbox content (one number); no duplicate value label.

---

## 15. **spinner**

- **ESPHome** (`spinner.py`): Schema: arc_length (required), spin_time (required). Parts: main, indicator. No text, no value. Device shows: spinning arc animation.
- **Default UI**: Animated spinning arc only. No label.
- **Our schema**: arc_length, spin_time; parts main, indicator. Remove any font_size/value.
- **Canvas**: Draw arc segment (and optionally animate or static); no value label.

**Planned changes:**
- Schema: arc_length, spin_time only; parts main, indicator.
- Canvas: Spinner arc only; no text.

---

## 16. **line**

- **ESPHome** (`line.py`): Schema: points (required; list of {x, y}). Parts: main only. Device shows: line through points. No text.
- **Default UI**: Line only. No value label.
- **Our schema**: points; parts main. Style may include line_width, line_color, etc. (from STYLE_PROPS).
- **Canvas**: Draw line through points; no text.

**Planned changes:**
- Schema: points; parts main. Style from STYLE_PROPS (line_width, line_color, etc.).
- Canvas: Line only; no value label.

---

## 17. **led**

- **ESPHome** (`led.py`): Schema: color, brightness. Parts: main only. Device shows: LED indicator (coloured dot/round). No text.
- **Default UI**: LED colour + brightness only. No label.
- **Our schema**: color, brightness; parts main.
- **Canvas**: Draw LED (e.g. circle with color/brightness); no value text.

**Planned changes:**
- Schema: color, brightness; parts main.
- Canvas: LED only; no text.

---

## 18. **qrcode**

- **ESPHome** (`qrcode.py`): Schema: text (required for update), dark_color, light_color, size. Parts: main. Device shows: QR code image. No separate value label; the QR is the content.
- **Default UI**: QR code only. No text overlay.
- **Our schema**: text, dark_color, light_color, size; parts main.
- **Canvas**: Draw QR placeholder or decoded pattern; no value label.

**Planned changes:**
- Schema: text, dark_color, light_color, size; parts main.
- Canvas: QR only; no extra label.

---

## 19. **keyboard**

- **ESPHome** (`keyboard.py`): (Fetch timed out; will need to re-check.) Typically: textarea reference, mode. Parts: main. Device shows: key grid. No “value” label; keys are the UI.
- **Our schema**: Align with ESPHome keyboard schema when re-fetched.
- **Canvas**: Draw key grid placeholder; no value label.

**Planned changes:**
- Schema: From keyboard.py (textarea, mode, etc.); parts main.
- Canvas: Keyboard keys only; no value text.

---

## 20. **tabview**

- **ESPHome** (`tabview.py`): Schema: tabs (list of {name, id, widgets}), tab_style, content_style, position, size. Parts: main. Device shows: tab bar + content area. No built-in “value” label; selected tab is visual.
- **Our schema**: tabs, tab_style, content_style, position, size; align with TABVIEW_SCHEMA.
- **Canvas**: Tab bar + content area; selected tab highlighted. No value label.

**Planned changes:**
- Schema: tabs, tab_style, content_style, position, size; parts main.
- Canvas: Tabs + content; no value text.

---

## 21. **tileview**

- **ESPHome** (`tileview.py`): Schema: tiles (list of {row, column, id, dir}). Parts: main, scrollbar. Device shows: tile grid; active tile. No value label.
- **Our schema**: tiles; parts main, scrollbar. Align with TILEVIEW_SCHEMA.
- **Canvas**: Tiles placeholder; no value label.

**Planned changes:**
- Schema: tiles (row, column, id, dir); parts main, scrollbar.
- Canvas: Tiles only; no value text.

---

## 22. **canvas**

- **ESPHome** (`canvas.py`): Schema: width, height, transparent. Parts: main. No default drawing; user draws via actions. Device shows: buffer (or drawn content). No built-in value label.
- **Default UI**: Empty or user-drawn. No default text.
- **Our schema**: width, height, transparent; parts main.
- **Canvas**: Empty canvas or “canvas” placeholder; no value label.

**Planned changes:**
- Schema: width, height, transparent; parts main.
- Canvas: No default content; no value label.

---

## 23. **buttonmatrix**

- **ESPHome** (`buttonmatrix.py`): Schema: rows (list of buttons), one_checked, pad_row, pad_column. Each button: text, key_code, width, control. Parts: main, items. Device shows: grid of buttons. No separate value label; selected/checked is visual.
- **Our schema**: rows (buttons: text, width, control); one_checked, pad_row, pad_column; parts main, items. Align with BUTTONMATRIX_SCHEMA.
- **Canvas**: Draw button grid with labels; no value label.

**Planned changes:**
- Schema: rows (buttons with text, width, control), one_checked, pad_row, pad_column; parts main, items.
- Canvas: Button matrix only; no value text.

---

## 24. **meter**

- **ESPHome** (`meter.py`): Schema: scales (list of scale configs: range_from, range_to, angle_range, rotation, ticks, indicators). Parts: main, indicator, ticks, items. Device shows: meter with scale(s) and indicator(s). Value is shown by indicator position, not a separate label (unless user adds one).
- **Default UI**: Meter arc/scale + indicator(s). No built-in numeric value label in the meter widget.
- **Our schema**: scales (with ticks, indicators); parts main, indicator, ticks, items. Align with METER_SCHEMA.
- **Canvas**: Draw meter scale + indicator(s); no value label unless we explicitly add a separate label widget type.

**Planned changes:**
- Schema: scales (range_from, range_to, angle_range, rotation, ticks, indicators); parts as ESPHome.
- Canvas: Meter graphic only; no value label.

---

## 25. **animimg**

- **ESPHome** (`animimg.py`): (Fetch timed out.) Typically: srcs (list of images), duration. Parts: main. Device shows: animated image. No value label.
- **Our schema**: Align when we have animimg.py.
- **Canvas**: Animated image or first frame; no value label.

**Planned changes:**
- Schema: From animimg.py (srcs, duration, etc.); parts main.
- Canvas: Animimg only; no value text.

---

## Summary of approach (every widget)

1. **Schema (per widget)**  
   - Open `esphome/components/lvgl/widgets/<type>.py` (and `schemas.py` / `defines.py` for base).  
   - List every **Optional/Required** key in the widget’s schema and the **parts** tuple.  
   - Add **base** (flags, state, align_to, group, events, main style) from obj_schema/part_schema.  
   - **Our change**: Set our `schemas/widgets/<type>.json` (and common_extras) so we expose **exactly** that set: add missing, remove anything not in ESPHome (e.g. font_size, value_label_offset_*). Use ESPHome key names (e.g. start_angle not bg_start_angle if that’s what ESPHome uses in YAML).

2. **Canvas (per widget)**  
   - From the same source and (if needed) LVGL docs, determine **default UI**: does the widget create a child? draw text? show only a graphic?  
   - **Our change**: In `Canvas.tsx`, for that widget type, draw **only** what the device shows by default. Remove any “value” text or extra decoration we added unless the device has it (e.g. spinbox shows the number as its content; arc does not show a number). For widgets that have no default text (arc, bar, slider, switch, led, line, spinner, canvas, etc.), canvas must **not** draw a value label.

3. **Compiler**  
   - Emit only keys that exist in the widget schema (and in esphome.props / esphome.style). Already skipping font_size, value_label_offset_*; after schema audit, there should be no other “designer-only” keys left to skip.

4. **Doc**  
   - After changes, regenerate `ESPHOME_WIDGET_PROPERTIES.md` from the updated schemas so it lists exactly what we expose per widget.

---

## Order of work (when coding)

1. **Arc** (already partially done: no value label on canvas; schema trimmed). Finish: align key names (start_angle/end_angle), remove knob_offset if not in ESPHome, add change_rate if missing.  
2. **Bar, slider, switch** (simple; no value label on device). Schema + canvas.  
3. **Button, checkbox, label** (text is the content). Schema (no font_size; text_font if needed) + canvas (text only).  
4. **Dropdown, roller, spinbox** (selection/number is the content). Schema + canvas (no extra value label).  
5. **Container, obj, image, textarea, line, led, qrcode, spinner, canvas** (no default value label). Schema + canvas.  
6. **Tabview, tileview, buttonmatrix, meter** (complex schemas). Schema + canvas.  
7. **Keyboard, animimg** (re-fetch source if needed). Schema + canvas.  
8. **common_extras**: After all widget schemas are correct, ensure common_extras only adds base flags/style that exist in ESPHome’s part_schema/STATE_SCHEMA/FLAG_SCHEMA.  
9. Regenerate **ESPHOME_WIDGET_PROPERTIES.md** and update **ESPHOME_WIDGET_AUDIT_PLAN.md** with “Done” notes.

This is the full plan for every widget before writing code.
