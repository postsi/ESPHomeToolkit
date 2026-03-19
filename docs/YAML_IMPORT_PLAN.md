# YAML Import – Full Implementation Plan

**Goal:** Import existing ESPHome YAML so that (1) the Designer can fully edit the imported project (layout, widgets, bindings, events), and (2) Deploy produces equivalent YAML. No manual re-binding; all state→UI and UI→action behaviour is reverse-engineered into the binding model and action bindings.

---

## 1. Overview

| Area | Scope |
|------|--------|
| **Recipe** | Match imported YAML to an existing device recipe (builtin + user) by fingerprint; if no match, create a new user recipe from the YAML. |
| **LVGL → Project** | Full reverse: parse `lvgl.pages[].widgets` into `project.pages[].widgets` (obj/container, label, button, arc, slider, etc.) with correct nesting, `parent_id`, props, style, events. |
| **Events** | Widget `on_click` / `on_release` etc. → `action_bindings` where it’s a HA service call; else store as `yaml_override` or `custom_events` so round-trip and editing work. |
| **Bindings & Links** | Reverse sensor/switch/climate/interval → widget updates into `project.bindings` and `project.links` (including extended source types: local_switch, climate_state, interval). |
| **Scripts / Sections** | Scripts that match known patterns (e.g. thermostat inc/dec) → `project.scripts`; everything else (and raw sections) → `project.sections` or equivalent so compile re-emits them. |
| **UI** | “Import YAML” next to Open / Add / Manage; Import log tab (after ESPHome Output or in right panel) for progress and debugging. |

**Success criteria:** User pastes/uploads YAML → import runs → new device + project appear → user opens in Designer, edits layout/bindings/events → Save → Deploy → resulting YAML is behaviourally equivalent to the original.

---

## 2. Prerequisites (existing)

- **Section parsing:** `_yaml_str_to_section_map`, `_parse_recipe_into_sections`, `SECTION_ORDER` (esphome_sections.py, views.py).
- **Recipe import:** `RecipeImportView`, `_normalize_recipe_yaml`, `_extract_recipe_metadata` (create user recipe from full YAML).
- **Recipe list:** Builtin recipes from `RECIPES_BUILTIN_DIR`; user recipes from `_user_recipes_root`; `list_all_recipes`.
- **Compile:** `compile_to_esphome_yaml`, `_compile_lvgl_pages_schema_driven`, `_compile_ha_bindings`, `_compile_scripts`, section merge.
- **Widget schemas:** Per-type JSON under `schemas/widgets/` with `esphome.root_key`, `esphome.props`, `esphome.style`, `esphome.events` (Designer key → YAML key).
- **Project model:** `ProjectModel` (pages, widgets, bindings, links, action_bindings, scripts, sections / esphome_yaml, device, lvgl_config).
- **Device/project API:** `upsertDevice`, `putProject`, `getProject`.

---

## 3. Phase 1 – Recipe matching and creation

**Owner:** Backend.  
**Input:** Full ESPHome YAML string.  
**Output:** `recipe_id` (matched or newly created), optional new user recipe on disk.

### 1.1 Fingerprint (hardware identity)

- Parse YAML into sections (reuse `_yaml_str_to_section_map` or equivalent).
- Build a **normalized fingerprint** from hardware-only sections, e.g.:
  - `esphome` (min_version, etc.; strip `name` or replace with placeholder).
  - `esp32` / `esp8266` / `rp2040` (board, framework, variant).
  - `display`: platform, model, dimensions (width/height), rotation.
  - `touchscreen`: platform, id.
  - `i2c`, `spi` (id, pins) if relevant to display/touch.
  - `output`, `light` (backlight/RGB) – ids and pin/platform.
- Normalize: strip comments, canonicalize key order, ignore whitespace; optionally sort list items so order doesn’t break match.

### 1.2 Match against known recipes

- Load all recipes (builtin + user) via existing helpers.
- For each recipe: load YAML, normalize to recipe form (same as current recipe import: strip wifi/ota/logger etc., keep hardware + lvgl with `#__LVGL_PAGES__`).
- Compute fingerprint for each recipe.
- Compare fingerprint of imported YAML (after same normalization) to each recipe fingerprint.
- **Match:** First recipe with equal (or subset) fingerprint wins. Prefer builtin over user if multiple; optionally prefer by resolution.
- **No match:** Proceed to create.

### 1.3 Create recipe when no match

- Call existing `_normalize_recipe_yaml(raw_yaml)` (or equivalent) to produce recipe YAML.
- Save as user recipe (existing recipe-import path: `_user_recipes_root` / `user` / `<slug>_<hash>` / `recipe.yaml`, `metadata.json`).
- Return new `recipe_id` (directory name).

### 1.4 API (optional for Phase 1)

- `POST /api/esptoolkit/import/preview`: body `{ yaml }` → `{ recipe_id, matched: bool, created_recipe: bool, device_name_suggestion, errors?: [] }`.  
  Used by frontend to show “will use recipe X” or “will create new recipe Y” before running full import.

---

## 4. Phase 2 – Extend binding model (local switch, climate state, interval)

**Owner:** Backend (+ frontend Binding Builder later).  
**Purpose:** So that “template switch → widget”, “climate heat_action/idle_action/off_mode → widget”, and “interval → widgets” are represented as links and emitted by the compiler.

### 4.1 Link source types

- **Current:** `source: { entity_id, kind, attribute }` (HA only).
- **Add:**
  - **Local switch:** `source: { type: "local_switch", switch_id: string }` with **state** (on/off). Each link describes one (switch_id, state) → list of target updates. So two “virtual” sources: `(local_switch, id, on)` and `(local_switch, id, off)`.
  - **Climate state:** `source: { type: "local_climate", climate_id: string, state: "HEAT"|"IDLE"|"OFF" }` (and optionally preset). One link per (climate_id, state) → list of target updates.
  - **Interval:** `source: { type: "interval", interval_seconds: number }` with a **list of updates**: each update has `local_id` (sensor/climate id), `attribute` (e.g. state, target_temperature), `widget_id`, `action` (label_text, arc_value, etc.), `format` / `yaml_override` as needed.

Representation options:

- **Option A – Same `links[]`:** Allow `source.type` to be optional (default “ha”) and `source.entity_id` | `source.switch_id` | `source.climate_id` + `source.state` | `source.interval_seconds` + `source.updates[]`. Compiler branches on `source.type`.
- **Option B – Separate arrays:** `local_switch_links[]`, `climate_state_links[]`, `interval_links[]` for clarity. Compiler reads all and emits switch/climate/interval blocks accordingly.

Recommendation: **Option A** (single `links[]` with discriminated `source.type`) to keep one place for “something → widget” and avoid duplication in UI.

### 4.2 Target format for new source types

- For local_switch: target same as today (`widget_id`, `action`). For “widget_checked”-like behaviour we have `action: widget_checked`; for “set bg_color” we may need `action: widget_bg_color` with a value, or `yaml_override` for the exact `lvgl.widget.update` block. Prefer `yaml_override` for now so we don’t proliferate actions.
- For climate_state: same (widget_id, action, optional format/scale/yaml_override).
- For interval: each item in `source.updates` has widget_id, action, format, yaml_override (lambda often needed).

### 4.3 Compiler changes

- **Switch:** When emitting `switch:` section (from recipe or project.sections), after emitting each switch block, check `links` for `source.type == "local_switch"` and `source.switch_id == id`. For each such link with state on/off, append to that switch’s `on_turn_on` / `on_turn_off` the corresponding `then:` list (lvgl.*.update). If switch block is compiler-generated from links only, generate full block (template switch with id, name, optimistic, on_turn_on, on_turn_off).
- **Climate:** Similarly, for each climate block (from sections), find links with `source.type == "local_climate"` and `source.climate_id == id` and `source.state` in (HEAT|IDLE|OFF). Append to `heat_action` / `idle_action` / `off_mode` the then: list. If we ever generate climate from project only, generate full block.
- **Interval:** For links with `source.type == "interval"`, emit one `interval:` block with `interval: <n>s` and `then:` a list of lvgl updates. Lambdas in each update can use `id(local_id).state` or `id(climate_id).target_temperature` etc.; use `yaml_override` per update when lambda is custom, else generate simple `return x` pattern if we have a single “sensor” source per update (interval is trickier: often one interval with many actions, so yaml_override per update is likely).

### 4.4 Backward compatibility

- Existing links (no `source.type` or `source.entity_id` set) continue to be treated as HA entity links. No change to existing projects.

---

## 5. Phase 3 – LVGL YAML → project (full widget reverse)

**Owner:** Backend.  
**Input:** `lvgl` section YAML (or full YAML; we extract lvgl).  
**Output:** `project.pages` (and widget tree with parent_id), `project.disp_bg_color`, `project.lvgl_config` if present.

### 5.1 LVGL block parser

- Parse `lvgl:` section into structure: `displays`, `touchscreens`, `buffer_size`, `pages`.
- For each page: `id`, `bg_color`, `widgets` (list of top-level items).
- Each list item is a single-key block: `- obj:` or `- label:` or `- button:` or `- arc:` etc. (root_key). Parse the value as a map: `id`, `x`, `y`, `width`, `height`, `align`, style keys, props, `widgets` (nested), `on_click`, `on_release`, etc.
- Build a **tree**: root widgets have no parent; nested `widgets:` give children; assign `parent_id` from parent’s `id`.

### 5.2 Widget type mapping

- Map ESPHome root_key → Designer widget type:
  - `obj` → `obj` (or `container` if schema uses container; align with schema).
  - `label` → `label`, `button` → `button`, `arc` → `arc`, `slider` → `slider`, `bar` → `bar`, `dropdown` → `dropdown`, `switch` → `switch`, etc.
  - Special: button with `styles: etd_cp_*` and on_click `script.execute: etd_cp_*_open` → `color_picker`. Similarly `etd_wp_*` → `white_picker`.

### 5.3 Props / style / events (inverse of schema)

- For each widget type, load schema (same as compiler). Invert `esphome.props`, `esphome.style`, `esphome.events`: YAML key → Designer key.
- For each parsed widget block, for each key (id, x, y, width, height, align, text, bg_color, …): map to props/style/events and set on the widget object. Geometry: `x`, `y`, `width`, `height` → `x`, `y`, `w`, `h`. If `align` present, keep it in props (and optionally reverse x/y from LVGL offset to top-left if we have parent size).
- Events: `on_click`, `on_release`, etc. Value is a YAML block (then: - ...). Store as string in widget `events.on_click` or in `custom_events`, or (if we detect homeassistant.action) parse into action_bindings (see Phase 4). Otherwise keep as yaml_override / custom_events for round-trip.

### 5.4 Nested structure

- Recursively walk `widgets`; assign `parent_id` on each child. Emit `project.pages[i].widgets` as list of root widgets; each widget may have `widgets` (children) or we flatten with parent_id (Designer uses parent_id). Confirm Designer’s expected shape (nested vs flat with parent_id) and emit that.

### 5.5 arc_labeled

- If we detect a container with id ending `_ct` containing one arc + many line + many label children in a tick pattern, optionally collapse to a single `arc_labeled` widget. Otherwise leave as container + arc + children (still editable).

### 5.6 IDs and stability

- Preserve all `id` values from YAML so bindings and action_bindings can reference them. Generate stable ids for any widget that has no id (e.g. `gen_<type>_<index>`).

---

## 6. Phase 4 – Reverse bindings and links (automated)

**Owner:** Backend.  
**Input:** Parsed YAML (sections: sensor, text_sensor, binary_sensor, switch, climate, interval).  
**Output:** `project.bindings`, `project.links` (HA + local_switch + climate_state + interval).

### 6.1 HA entity → widget (sensor, text_sensor, binary_sensor)

- For each `sensor:` / `text_sensor:` / `binary_sensor:` item with `platform: homeassistant`, extract `entity_id`, `id`, `attribute` (if any). Determine kind: state, attribute_number, attribute_text, binary.
- For each `on_value` / `on_state` that contains `lvgl.label.update` / `lvgl.arc.update` / etc.: extract widget `id` and update type (text, value, state.checked, etc.). Map to link target action: label_text, arc_value, slider_value, bar_value, widget_checked.
- If the lambda is a simple `return x` or format/args, set target `format` / `scale`. If it’s custom (e.g. snprintf "%.1f°C"), set target `yaml_override` to that update block.
- Add binding `{ entity_id, kind, attribute }` (dedupe). Add link `{ source: { entity_id, kind, attribute }, target: { widget_id, action, format?, scale?, yaml_override? } }`.

### 6.2 Template switch → widget (local_switch)

- For each `switch:` platform template (or similar) with `on_turn_on` / `on_turn_off`: extract switch `id`. For each action list item that is `lvgl.widget.update` or `lvgl.label.update`, extract target widget id and the update (bg_color, text, text_color). Create links with `source: { type: "local_switch", switch_id, state: "on"|"off" }`, `target: { widget_id, yaml_override }` (store the exact lvgl update block so compiler re-emits it).

### 6.3 Climate heat_action / idle_action / off_mode → widget (climate_state)

- For each `climate:` block with `heat_action` / `idle_action` / `off_mode`: extract climate `id`. For each action list, collect lvgl.*.update items (widget id, property). Create links with `source: { type: "local_climate", climate_id, state: "HEAT"|"IDLE"|"OFF" }`, target widget_id + yaml_override or action (e.g. label_text with fixed text). Repeat for presets if we support them.

### 6.4 Interval → widgets (interval)

- Parse `interval:` blocks: `interval: 1s`, `then:` list. For each item that is `lvgl.label.update` or `lvgl.arc.update` with a lambda: parse lambda to see which local id is read (e.g. `id(temp_zone_1).state`, `id(climate_all).target_temperature`). Create one link with `source: { type: "interval", interval_seconds: 1, updates: [ { local_id, attribute?, widget_id, action, format?, yaml_override? } ] }`. If lambda is complex, use yaml_override for that item.

### 6.5 Action bindings (widget event → service/script)

- Already partially covered in Phase 3 (events stored as yaml_override). Optionally: when we see `on_click:` / `on_release:` with `homeassistant.action` or `switch.toggle` / `climate.control` etc., parse into `action_bindings[]` (widget_id, event, call) so they show in Binding Builder. If not parseable, keep as custom_events/yaml_override.

---

## 7. Phase 5 – Scripts and sections

**Owner:** Backend.

### 7.1 Scripts

- Parse `script:` list. For each script with a known pattern (e.g. thermostat inc/dec: lambda that reads climate id, does set_target_temperature), map to `project.scripts[]` (id, entity_id or climate_id, step, direction) if we have that shape. Otherwise keep full script block in project.sections.script (or equivalent) so compile re-emits it.

### 7.2 Other sections

- All remaining top-level sections (wifi, ota, logger, api, substitutions, packages, etc.) that are not “recipe” and not generated from bindings/scripts: store in `project.sections` (key → body) or in a single `project.esphome_yaml` blob. Compiler already merges sections; ensure we don’t double-emit (e.g. sensor from bindings vs sensor from sections: prefer bindings-generated, merge or dedupe user sections).

### 7.3 Device name and metadata

- From `esphome.name` (and optional `friendly_name`) set device name; derive slug. From `display` dimensions set `project.device.screen.width/height`. Set `project.device.hardware_recipe_id` to matched or created recipe_id.

---

## 8. Phase 6 – Import API and device creation

**Owner:** Backend.

### 8.1 Single import endpoint

- `POST /api/esptoolkit/import/from-yaml`: body `{ yaml: string, device_name_override?: string }`.
- Steps (with log lines for Import log tab):
  1. Parse YAML; validate basic structure.
  2. Recipe: fingerprint, match or create recipe (log: "Matched recipe X" / "Created recipe Y").
  3. Extract device name; create or resolve device (upsertDevice with name, slug, hardware_recipe_id).
  4. LVGL reverse: build project.pages, widgets, tree (log: "Parsed N pages, M widgets").
  5. Bindings reverse: build bindings + links (HA + local_switch + climate_state + interval) (log: "Found K bindings, L links").
  6. Action bindings / events: attach to widgets (log: "Parsed J action bindings").
  7. Scripts and sections: fill project.scripts, project.sections (log: "Stored scripts and sections").
  8. Save project: putProject(entryId, deviceId, project).
  9. Return `{ ok: true, device_id, recipe_id, project_summary: { pages, widget_count, bindings_count, links_count } }`.
- On error: return `{ ok: false, error, step?, detail }` and log.

### 8.2 Streaming log (optional)

- If frontend supports streaming: endpoint that streams SSE or chunked response with log lines. Else: return log lines in response body (e.g. `log: string[]`) so Import log tab can display them after completion.

---

## 9. Phase 7 – Frontend: Import entry point and Import log tab

**Owner:** Frontend.

### 9.1 Import entry point

- In `WelcomePanel`, add button **“Import YAML”** (same row as Open device, Add device, Manage devices). On click: open modal (or inline flow).
- Modal: textarea for paste (or file upload); optional device name override; “Preview” (call preview endpoint if implemented) showing recipe and device name; **“Import”** button. On Import: call `POST /api/esptoolkit/import/from-yaml`, show progress (e.g. spinner + log lines in Import log tab). On success: close modal, refresh device list, optionally open the new device in the Designer or show toast “Imported: <name>. Open it to edit.”

### 9.2 Import log tab

- New tab **“Import log”** (or “Log”): place after “ESPHome Output” (or as 5th tab in right panel). Content: scrollable log area showing last run’s lines (from import response or from streaming). Optional “Clear” button. Reuse same tab for other operations (e.g. deploy log) if desired for debugging.

### 9.3 API client

- Add `importFromYaml(yaml: string, deviceNameOverride?: string): Promise<ImportResult>` in api.ts or lib/api. ImportResult = { ok, device_id?, recipe_id?, project_summary?, log?, error?, step?, detail? }.

---

## 10. Phase 8 – Round-trip testing and edge cases

**Owner:** QA / implementation.

### 10.1 Test cases

- **Heating controller YAML** (provided): Import → open in Designer → verify all widgets visible and editable, bindings in HA Bindings, events in Widget YAML / Binding Builder → Save → Deploy → diff compiled YAML to original (ignore comments/order where safe). Fix reverse or compiler until equivalent.
- **Minimal YAML:** One page, one label, one sensor → label link. Import → edit label text → Deploy → verify.
- **Recipe match:** Use YAML that matches an existing builtin recipe; verify recipe_id is that builtin. Use YAML that doesn’t match; verify new user recipe created and used.

### 10.2 Edge cases

- Widget without id: assign stable id; ensure no broken refs.
- Unknown widget type: treat as container or skip; log warning.
- Duplicate widget ids: dedupe or suffix; log warning.
- Malformed YAML: clear error and log; no partial import.

---

## 11. Implementation order (recommended)

| Order | Phase | Dependency |
|-------|--------|------------|
| 1 | Phase 2 – Extend binding model (link source types + compiler) | None |
| 2 | Phase 1 – Recipe fingerprint + match + create | None (can parallel with 1) |
| 3 | Phase 3 – LVGL full reverse | None |
| 4 | Phase 4 – Reverse bindings/links (automated) | Phase 2, 3 |
| 5 | Phase 5 – Scripts and sections | 3 |
| 6 | Phase 6 – Import API + device creation | 1–5 |
| 7 | Phase 7 – Frontend Import + Log tab | 6 |
| 8 | Phase 8 – Round-trip testing | 7 |

---

## 12. Out of scope / later

- **Prebuilt widget collapse:** Reverse expanded prebuilt (e.g. nav bar) back to single “prebuilt_nav_bar” widget.
- **arc_labeled collapse:** Heuristic to merge container+arc+lines+labels into one arc_labeled (optional; leaving as container+children is acceptable).
- **Dropdown/roller option list from lambda:** Parse `if (x==0) return "A";` into options; low priority.
- **Idempotent re-import:** Same YAML twice → update existing device vs create new; can be an option (e.g. “Replace existing device with same name”).

---

## 13. Doc and schema references

- Link format (current): `custom_components/esptoolkit/api/views.py` `_compile_ha_bindings` docstring (lines 678–684).
- Project model: `frontend/src/api.ts` `ProjectModel`, `ActionBinding`.
- Widget schemas: `custom_components/esptoolkit/schemas/widgets/*.json` (esphome.root_key, props, style, events).
- Section order: `custom_components/esptoolkit/esphome_sections.py` `SECTION_ORDER`.
