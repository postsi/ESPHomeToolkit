# ESPHome LVGL Widget Properties (Designer Exposed)

This document lists, by widget type, the **main properties**, **style properties**, **part properties**, and **events** that the designer exposes in the properties editor. The list is derived from the widget schemas in `schemas/widgets/*.json` merged with `schemas/common_extras.json` (same merge as at runtime). Designer-only options that do not exist in ESPHome LVGL (e.g. `font_size`, `value_label_offset_x` / `value_label_offset_y`) have been removed from the schemas and are not emitted by the compiler.

**Common extras** (object flags, align_to, size override, text style, border, shadow, outline, padding, size limits, transform, state styles, scrollbar part) are merged into every widget schema and appear in the lists below where applicable.

## Audit status (ESPHome as source of truth)

- **Not yet done:** A full widget-by-widget audit of ESPHome source (`esphome/components/lvgl/widgets/*.py`) has **not** been completed. So we do **not** yet guarantee that we show exactly the ESPHome props and only those.
- **Done so far:** Removed designer-only props; canvas arc has no value label (matches device). Palette and compiler use only the 26 ESPHome-backed widget types; non-ESPHome types have been removed.
- **Recommended next step:** For each widget type, open the corresponding file in [esphome/components/lvgl/widgets/](https://github.com/esphome/esphome/tree/dev/esphome/components/lvgl/widgets), read the schema (and parts), and align our `schemas/widgets/<type>.json` and canvas drawing so that we expose only those props and mimic any default UI (e.g. no extra text/graphics the device doesn’t draw).

---

## animimg

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, duration, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, srcs, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

on_click

---

## arc

### Main properties (props)

adjustable, adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, bg_end_angle, bg_start_angle, click_focusable, clickable, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, knob_offset, max, min, mode, opacity, overflow_visible, press_lock, rotation, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, value, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **indicator**: bg_color, radius
- **knob**: bg_color, height, pad_right, radius, width
- **scrollbar**: bg_color, bg_opa

### Events

on_release, on_value

---

## bar

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, max, min, mode, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, start_value, value, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **indicator**: bg_color, radius
- **knob**: bg_color, height, padding, radius, width
- **scrollbar**: bg_color, bg_opa

### Events

on_release, on_value

---

## button

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, checkable, click_focusable, clickable, event_bubble, floating, font, gesture_bubble, group, height_override, hidden, ignore_layout, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, text, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, pad_bottom, pad_left, pad_right, pad_top, radius, shadow_color, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, shadow_width, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

on_click, on_long_press, on_short_click

---

## buttonmatrix

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, control, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, map, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, width, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

on_button

---

## canvas

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, clip_corner, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, transparent, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

*none*

---

## checkbox

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, checked, click_focusable, clickable, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, text, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

on_change

---

## container

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, clip_children, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, layout, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, pad_bottom, pad_left, pad_right, pad_top, radius, shadow_color, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, shadow_width, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

*none*

---

## dropdown

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, opacity, options, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, selected_index, snappable, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **items**: bg_color, text_color
- **scrollbar**: bg_color, bg_opa
- **selected**: bg_color, text_color

### Events

on_change

---

## image

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, opa, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, src, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

on_click

---

## keyboard

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, textarea_id, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

on_key

---

## label

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, event_bubble, floating, font, gesture_bubble, group, height_override, hidden, ignore_layout, long_mode, opacity, overflow_visible, press_lock, recolor, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, text, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, pad_bottom, pad_left, pad_right, pad_top, radius, shadow_color, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, shadow_width, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

on_click

---

## led

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, brightness, click_focusable, clickable, color, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

*none*

---

## line

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, line_color, line_rounded, line_width, opacity, overflow_visible, points, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

*none*

---

## meter

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

*none*

---

## msgboxes

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

*none*

---

## obj

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

on_click

---

## qrcode

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, dark_color, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, light_color, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, size, snappable, text, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

*none*

---

## roller

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, opacity, options, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, selected, snappable, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **items**: bg_color, text_color
- **scrollbar**: bg_color, bg_opa
- **selected**: bg_color, text_color

### Events

on_change

---

## slider

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, max, min, mode, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, start_value, value, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **indicator**: bg_color, radius
- **knob**: bg_color, height, padding, radius, width
- **scrollbar**: bg_color, bg_opa

### Events

on_release, on_value

---

## spinbox

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, max, min, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, step, value, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **cursor**: color, width
- **scrollbar**: bg_color, bg_opa

### Events

on_change

---

## spinner

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, arc_length, click_focusable, clickable, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, time, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

on_click

---

## switch

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, state, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

on_change

---

## tabview

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, tabs, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

on_value

---

## textarea

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, max_length, one_line, opacity, overflow_visible, placeholder_text, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, text, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **cursor**: color, width
- **scrollbar**: bg_color, bg_opa

### Events

on_defocus, on_focus, on_ready

---

## tileview

### Main properties (props)

adv_hittest, align, align_to_align, align_to_id, align_to_x, align_to_y, click_focusable, clickable, event_bubble, floating, gesture_bubble, group, height_override, hidden, ignore_layout, opacity, overflow_visible, press_lock, scroll_chain_hor, scroll_chain_ver, scroll_dir, scroll_elastic, scroll_momentum, scroll_on_focus, scroll_one, scroll_with_arrow, scrollable, scrollbar_mode, snappable, tiles, width_override

### Style properties

bg_color, bg_opa, border_color, border_opa, border_post, border_side, border_width, clip_corner, max_height, max_width, min_height, min_width, opa, outline_color, outline_opa, outline_pad, outline_width, pad_all, radius, shadow_ofs_x, shadow_ofs_y, shadow_opa, shadow_spread, text_align, text_color, text_decor, text_letter_space, text_line_space, text_opa, transform_angle, transform_zoom, translate_x, translate_y

### Part properties

- **scrollbar**: bg_color, bg_opa

### Events

on_value

---
