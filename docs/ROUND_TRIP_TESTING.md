# Phase 8 – Round-trip testing (YAML Import)

Manual and automated checks to verify that Import YAML → Designer → Deploy produces behaviourally equivalent YAML.

## Manual test steps

### 1. Heating controller (full device)

1. Paste the full heating-controller YAML (Guition JC1060P470, 1024×600) into **Import YAML** on the welcome screen.
2. Click **Import**. Confirm device is created and opens in the Designer.
3. **Verify:** All widgets visible on canvas (labels, buttons, arc, etc.); no missing or broken layout.
4. Open **HA Bindings** tab: confirm bindings and links appear (sensor → label, switch/climate/interval → widgets as applicable).
5. Open **Widget YAML** for one widget: confirm events/props are present.
6. **Save** (if you made no changes, still Save to persist).
7. **Deploy** → export YAML (or use Validate/Export).
8. **Diff:** Compare compiled YAML to original (ignore comments, key order, and exact whitespace). Key sections to compare:
   - `lvgl.pages[].widgets`: same structure and ids.
   - `sensor` / `text_sensor` / `binary_sensor`: same entity_ids and `on_value`/`on_state` with correct `lvgl.*.update` targets.
   - `switch`: same ids and `on_turn_on`/`on_turn_off` actions.
   - `climate`: same ids and `heat_action`/`idle_action`/`off_mode` actions.
   - `interval`: same interval and `then` list with lvgl updates.
   - `script`: same script ids and thermostat inc/dec behaviour.

### 2. Minimal YAML

Use a minimal device YAML: one page, one label, one `sensor` (platform: homeassistant) with `on_value` → `lvgl.label.update` to that label.

1. Import → open in Designer.
2. Verify one page, one label; HA Bindings shows one binding and one link.
3. Edit label text in Properties → Save → Deploy.
4. Confirm compiled YAML still has the sensor and the label update.

### 3. Recipe match

- **Match:** Use YAML that matches an existing builtin recipe (e.g. same display/touch/board). After import, check Import log: should say "Matched recipe: <id>". Device project should have that `hardware_recipe_id`.
- **Create:** Use YAML that does not match any recipe. Import log should say "No match; creating new user recipe." and "Created recipe: <id>". New user recipe should exist under the configured user recipes path.

## Edge cases

- **Widget without id:** Import YAML that has a widget block without `id`. Parser assigns a stable generated id (e.g. `gen_label_...`). No broken refs in bindings/links.
- **Unknown widget type:** If a root_key is not in the schema, it is treated as container/obj; no crash.
- **Malformed YAML:** Paste invalid YAML → Import returns error, log shows parsing error; no partial device created.

## Automated tests

Unit tests for the import pipeline live in `tests/test_yaml_import.py`:

- `parse_lvgl_section_to_pages`: LVGL section string → list of pages with flattened widgets.
- `reverse_bindings_and_links`: Sections (sensor, switch, climate, interval) → bindings + links.
- `reverse_scripts`: Script section with thermostat inc/dec pattern → project.scripts list.

Run: `pytest tests/test_yaml_import.py -v` (from repo root; may require `PYTHONPATH` or conftest that adds repo root).
