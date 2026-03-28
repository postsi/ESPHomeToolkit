# Designer canvas ↔ Mac LVGL parity (wired)

## What you run (macOS)

1. **Home Assistant** running with EspToolkit configured (`mac_sim_token` 16+ chars in integration options).

2. **Mac agent** (same Mac as SDL), connected to HA:

   ```bash
   cd tools/mac_esphome_sim_agent
   source .venv/bin/activate   # or your venv
   python ha_agent_client.py --ha-url http://grimwoodha:8123 --token-file ~/.esptoolkit_mac_sim_token
   ```

3. **Parity capture deps** on that Mac:

   ```bash
   pip install -r tools/mac_esphome_sim_agent/requirements-parity.txt
   ```

4. **Env** (device must exist under that entry; compile must succeed for the fixture project). Easiest: copy `scripts/parity-local.env.example` → `scripts/.parity-local.env` (gitignored), or:

   ```bash
   export ESPTOOLKIT_HA_URL='http://grimwoodha:8123'
   export ESPTOOLKIT_ENTRY_ID='your_config_entry_uuid'   # optional if single EspToolkit entry
   export ESPTOOLKIT_PARITY_DEVICE_ID='your_device_id'
   # optional:
   export ESPTOOLKIT_HA_TOKEN='long_lived_access_token'
   export ESPTOOLKIT_HA_INSECURE_SSL=1   # self-signed HTTPS only
   ```

5. **One command** (from repo):

   ```bash
   cd frontend && npm run parity:mac
   ```

This will:

- For each parity fixture JSON → **POST** `/api/esptoolkit/mac_sim/enqueue` with `project` override (same JSON the designer would save).
- Your **ha_agent_client** receives the job, transforms YAML, runs **`esphome run`**, SDL opens.
- **Quartz** finds the window ~matching `device.screen` size, captures PNG, **crops/scales** to exact logical WxH to match the designer export.
- **SIGINT** `esphome run` so the agent can run the next fixture.
- Starts **parity_snapshot_server**, then **Playwright** compares Konva export vs those PNGs (`pixelmatch`).

## Designer export hook (unchanged)

- `?etd_parity=1&etd_fixture=<name>` loads `parity-fixtures/<name>.json`.
- `html[data-etd-parity-ready='1']`, `window.__ETD_EXPORT_CANVAS_PNG__()`.

## Fixtures

Regenerate after palette/prebuilt changes:

```bash
cd frontend && npm run generate:parity-fixtures
```

## `npm run test:parity` alone

Only runs Playwright vs **MACSIM_SNAPSHOT_URL_TEMPLATE** (or legacy `MACSIM_SNAPSHOT_URL`). It **fails** if that env is unset — use **`npm run parity:mac`** for the full pipeline, or set the URL and pre-fill `parity_snapshots/` yourself.

## Tuning

- `PARITY_PIXEL_THRESHOLD`, `PARITY_MAX_DIFF_PIXELS` — passed through Playwright to `pixelmatch`.
- `ESPTOOLKIT_CAPTURE_TIMEOUT` — wait for SDL window (seconds).
- `ESPTOOLKIT_PARITY_FIXTURES` — comma list or `all` (default) for `parity_prepare_mac.py`.

## When a comparison fails (fix → rerun without extra plumbing)

There is **no separate HTTP “parity API”** for live results: the pipeline is **exit code + files on disk**, which is enough for a local agent (Cursor) or CI to read, patch code, and rerun the same command.

After each fixture run, Playwright writes **`frontend/test-results/parity/<fixture>-result.json`** with `passed`, `numDiffPixels`, limits, and paths to any failure artifacts.

If **`passed` is false**, the same folder also gets:

- **`<fixture>-diff.png`** — pixelmatch heatmap
- **`<fixture>-designer.png`** — Konva export
- **`<fixture>-sim.png`** — Mac SDL capture

The full Playwright JSON report is **`frontend/test-results/parity/playwright-report.json`** (suites, statuses, errors).

**Typical loop:** read `*-result.json` (and open `*-diff.png` if needed) → change Canvas/compiler/capture → `cd frontend && npm run parity:mac` (or `npm run test:parity` if snapshots are already in place). The command exits **non-zero** on any failure, **zero** when all fixtures pass.

## What is still not automated

- **Palette drag in Playwright** — fixtures are project JSON (same as a saved page). True UI drag-and-drop E2E against the HA iframe is not implemented.
- **pkill** — uses `pkill -INT -f "esphome run"` between fixtures; if you run other ESPHome jobs, coordinate manually.

## Rollback tag

`pre-parity-pipeline-2026-03-27`

## CLI: compare two files

```bash
node scripts/parity-compare.mjs a.png b.png
```
