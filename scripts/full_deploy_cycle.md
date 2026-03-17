# Full deploy cycle (test → deploy → HA update → restart → test)

This process runs the validate test, deploys the addon using the **fast** deploy script, triggers HA to update and restart the addon (and optionally restart HA), then re-runs the validate test. Use it to verify that the live integration and addon run the latest code and pass validation.

**When to use:** After compiler/test fixes are in the repo and you want to run the full cycle without manual steps (or with minimal manual steps). The agent can execute this when you ask to "run the full deploy cycle" or "run the deployment cycle".

---

## Terminology (don’t confuse with deploy-local.sh)

- **Fast deploy** = `./scripts/deploy-local.sh --fast <version> ...` — reuses the pre-built base image; does **not** rebuild the base container. Use this in the deploy cycle.
- **Full deploy** = `./scripts/deploy-local.sh <version> ...` (no `--fast`) — rebuilds the base container from scratch. Slower; use when the base (e.g. ESPHome version) has changed.
- **Full deploy cycle** = this document’s process: the end-to-end flow (test → deploy → HA update → restart → test). It uses the script’s **fast** deploy, not the script’s full deploy.

---

## Prerequisites

- **Base image** for fast deploy: run `./scripts/build-base.sh` once.
- **Push to registry:** `GITHUB_TOKEN` set (or `docker login ghcr.io`) so `deploy-local.sh` can push.
- **Test env:** `ESPTOOLKIT_ENTRY_ID`, `ESPTOOLKIT_DEVICE_ID`; addon URL/token via `ESPTOOLKIT_ADDON_URL` / `ESPTOOLKIT_ADDON_TOKEN` or `~/.cursor/mcp.json` (esptoolkit).
- **HA MCP:** Home Assistant MCP server (e.g. **user-HAGrimwood**) configured so the agent can call `ha_update_addon`, `ha_restart_addon`, `ha_restart`.
- **Addon slug:** Usually `esptoolkit_addon`; if your install uses a different slug (e.g. with repo prefix), resolve it via `ha_list_installed_addons` and use that slug below.

---

## Steps (agent or human)

Run from repo root.

### 1. Run validate test (no patches)

- In `tests/test_integration_addon.py`, set **`YAML_PATCHES = []`** (clear all patches so we validate raw compiler output).
- Run:
  ```bash
  ESPTOOLKIT_RUN_SLOW=1 ESPTOOLKIT_ENTRY_ID=<entry_id> ESPTOOLKIT_DEVICE_ID=testdummy python -m pytest tests/test_integration_addon.py::test_esphome_validate_testdummy_project -v --tb=short
  ```
  Use your real `ESPTOOLKIT_ENTRY_ID` (and ensure `ESPTOOLKIT_ADDON_URL` / `ESPTOOLKIT_ADDON_TOKEN` or mcp.json are set).

- **If the test fails:** Fix the bugs in the compiler (integration and addon `api/views.py`) and/or add the minimal YAML patches so the test passes, then re-run this step until it passes (with patches if needed). Record that patches are in place for the next deploy.

### 2. Bump version and run fast deploy (script’s “fast” deploy, not full)

- Read current version from `esptoolkit_addon/config.yaml` (e.g. `1.0.45`). Choose new version: bump patch to `1.0.46` (or minor/major if appropriate). The deploy script will update `config.yaml`, `app/__init__.py`, and `manifest.json` to this version.
- Run **fast** deploy (reuses base image; do not use full deploy here):
  ```bash
  ./scripts/deploy-local.sh --fast <new_version> "Full deploy cycle: validate → deploy → HA update → test"
  ```
  Example: `./scripts/deploy-local.sh --fast 1.0.46 "Full deploy cycle"`

- This bumps the version in all three places, builds the frontend, syncs the integration into the addon, builds the addon image (from base), pushes to ghcr.io, and pushes the repo with `[skip build]`. Ensure the command completes successfully.

### 3. Update the addon in Home Assistant

- Using the **Home Assistant MCP server** (e.g. user-HAGrimwood), call:
  - **`ha_update_addon`** with `slug`: `esptoolkit_addon` (or the slug from `ha_list_installed_addons` if different).
- This pulls the new image and updates the addon. Wait for the call to complete (may take 1–2 minutes).

### 4. Wait for addon to be running (optional but recommended)

- Optionally call **`ha_restart_addon`** with the same slug so the addon restarts with the new code and copies the integration into `custom_components` (if your addon does that on start).
- Or poll **`ha_addon_info`** (or addon status) until the addon is running. Suggested wait: **30–60 seconds** after update/restart.

### 5. Restart Home Assistant

- Using the same MCP, call **`ha_restart`** (no arguments). This restarts HA Core so it loads the updated integration from the addon’s `custom_components` (if applicable).
- **HA will be unavailable for about 30–60 seconds.** Wait **60–90 seconds** (or poll HA health) before the next step.

### 6. Re-run validate test (no patches)

- Ensure **`YAML_PATCHES = []`** is still set in `tests/test_integration_addon.py`.
- Run the same test again:
  ```bash
  ESPTOOLKIT_RUN_SLOW=1 ESPTOOLKIT_ENTRY_ID=<entry_id> ESPTOOLKIT_DEVICE_ID=testdummy python -m pytest tests/test_integration_addon.py::test_esphome_validate_testdummy_project -v --tb=short
  ```

- **If it passes:** The full cycle succeeded; the deployed integration and addon pass validation with no patches.
- **If it fails:** Fix the compiler (and add patches if needed for the next iteration), then you can run the cycle again from step 1 or from step 2 (if only a quick fix and no version bump yet).

---

## Summary checklist

| Step | Action |
|------|--------|
| 1 | Clear `YAML_PATCHES`, run validate test; fix bugs / add patches until test passes. |
| 2 | Bump version (script does it), run **fast** deploy: `./scripts/deploy-local.sh --fast <version> "message"` (not full deploy). |
| 3 | MCP: `ha_update_addon` (slug `esptoolkit_addon`). |
| 4 | Wait 30–60 s; optionally `ha_restart_addon`. |
| 5 | MCP: `ha_restart` (restart HA); wait 60–90 s. |
| 6 | Re-run validate test (patches still cleared). |

---

## Notes

- **No clean-environment:** This cycle does not run the clean-environment script; it assumes the integration is already installed and the addon is already in place. For a clean install test, run the steps in `scripts/clean_environment_for_deploy.md` before step 1 (or use the standard "local deploy" flow which cleans first).
- **Version:** The deploy script bumps version in `config.yaml`, `app/__init__.py`, and `manifest.json`; step 2 uses that same version for the git commit message.
- **Slug:** If `ha_update_addon` fails, list addons with `ha_list_installed_addons` and use the slug that corresponds to the ESPToolkit addon (often `esptoolkit_addon` or a prefixed form).
