# HA integration test suite

Tests run against **the app as it actually appears in HA**: they call the EspToolkit addon via MCP (`local_http`) to hit the integration and HA Core APIs. No mocks.

## Requirements

- Python 3.10+
- Addon running and reachable (e.g. via Nabu Casa or your HA URL)
- Addon API token (same token you use in Cursor MCP config)

## Setup

```bash
cd /path/to/ESPHomeToolkit
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r tests/requirements.txt
```

## Environment

Set these before running tests:

| Variable | Required | Description |
|---------|----------|-------------|
| `ESPTOOLKIT_ADDON_URL` | Yes | Base URL of the addon (e.g. `https://my-ha.nabu.casa/addons/local/esptoolkit_addon` or your ingress URL). No trailing slash. |
| `ESPTOOLKIT_ADDON_TOKEN` | Yes | Addon API token (Configuration → API token). |
| `ESPTOOLKIT_ENTRY_ID` | For some tests | Integration config entry ID (so the integration can list devices/project). |
| `ESPTOOLKIT_DEVICE_ID` | For some tests | A device ID that has a project (for project/schema/data tests). |

Tests that need `ENTRY_ID` or `DEVICE_ID` will skip if not set.

## Run

```bash
# All tests
pytest tests/ -v

# Smoke only (fast; checks addon + HA reachability)
pytest tests/test_smoke.py -v

# API contract only
pytest tests/test_api_contract.py -v

# With env in one line
ESPTOOLKIT_ADDON_URL=https://... ESPTOOLKIT_ADDON_TOKEN=... pytest tests/ -v
```

## Test groups

| File | What it proves |
|------|----------------|
| `test_smoke.py` | Addon MCP and HA proxy are reachable; integration context responds. |
| `test_api_contract.py` | Integration endpoints return expected status and response shape. |
| `test_data_consistency.py` | Project entity refs exist; pages/widgets structure is valid. |
| `test_schema_contract.py` | Every widget type in project has a schema; props are valid. |
| `test_e2e_workflow.py` | Get→put→get project roundtrip; cards list then get one. |

## Adding fixtures (optional)

For full coverage of project/device tests, create a **test device** in the Designer and note its `entry_id` and `device_id`, then set them in env. You can also add a snapshot of that project and restore it after destructive tests if needed.
