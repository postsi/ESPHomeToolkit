# Example Designer projects (binding style)

These JSON files are **EspToolkit project** shapes you can **paste into a device**, **merge by hand**, or use as a reference when recreating the same layout in the Designer.

## `project_light_control.json`

Light toggle + brightness slider bound to one `light.*` entity (`bindings` + `links`).

## `project_climate_card_grimwood.json`

A single **card-style** screen (container + labels + arc) that mirrors the **normal HA binding model**:

| Piece | Mechanism |
|-------|-----------|
| HA → “current temp” label | `bindings[]` + `links[]` → `attribute_number` **`current_temperature`** → **`label_text`** |
| HA → setpoint arc | `bindings[]` + `links[]` → `attribute_number` **`temperature`** → **`arc_value`** |
| Arc → HA setpoint | `action_bindings[]` → **`climate.set_temperature`** on **`on_release`** |

1. Open or create a device in the Designer.
2. Import / merge widgets and binding sections, **or** rebuild the same widgets and use **Binding Builder** + **Add recommended** for domain **Thermostat (climate)** on the same entity, then attach display/actions to these widget ids.
3. Replace **`climate.grimwood_all_thermostats`** everywhere with your entity (e.g. `climate.grimwood`, `climate.living_rm`).
4. Adjust **`hardware.recipe_id`** and geometry for your panel resolution.

**Note:** HA climate attributes can differ slightly by integration; if `temperature` / `current_temperature` don’t update, check **Developer tools → States** for that entity’s attributes and adjust binding `attribute` values to match.
