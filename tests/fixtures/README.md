# Test fixtures

## `heating-controller.yaml` (optional, gitignored)

Real device YAML is **not committed** (may contain SSIDs, etc.). Refresh from Home Assistant:

1. **GrimwoodAI Agent MCP** → `ha_read_file` with path `esphome/heating-controller.yaml` (relative to `/config`).
2. Save the response body to `tests/fixtures/heating-controller.yaml`.

`pytest tests/test_import_lifecycle.py` then runs `test_heating_controller_yaml_resolved_path` against that file.

Fallback: set `HEATING_CONTROLLER_YAML` or `ESPHOME_CONFIG_DIR` to a local path.
