# ESPHomeToolkit

Combined Home Assistant **add-on** and **custom integration**: runs ESPHome (compile/upload/validate) via REST API and MCP, and provides the **ESPToolkit** Designer (LVGL touch screen UI designer) in one install.

- **Add-on**: ESPToolkit — runs the ESPHome container, exposes REST API and MCP at port 8098, and installs the custom integration into Home Assistant.
- **Integration**: ESPToolkit — no config flow; add-on writes URL and token. Provides:
  - **API services**: `esptoolkit.compile`, `esptoolkit.upload`, `esptoolkit.validate`, `esptoolkit.run` (by filename/config_name or inline YAML).
  - **Designer**: Panel at **ESPToolkit** (sidebar); project storage under `/config/esptoolkit/`; assets under `/config/esptoolkit_assets/`.
- **Build / Deploy**: Designer compiles project to YAML in memory and calls the add-on with inline YAML (no file required). Optional **Export to ESPHome folder** writes to `/config/esphome/<slug>.yaml` for inspection or native ESPHome UI.

## Installation

1. Add this repository in Home Assistant: **Settings → Add-ons → Add-on store → ⋮ → Repositories**  
   `https://github.com/postsi/ESPHomeToolkit`
2. Install **ESPToolkit** add-on, set **api_token** (and optional **port**) in Configuration, then **Start**.
3. The add-on installs the integration and adds `esptoolkit:` to `configuration.yaml`; it may restart Home Assistant. Open **ESPToolkit** from the sidebar to use the Designer.

## Configuration

- **api_token** (required): Long-lived token for API and MCP.
- **port** (default 8098): Port for API/MCP.

## MCP (Cursor / VSCode)

Use the add-on Web UI (Open Web UI from the add-on page) → **Setup** tab to generate MCP config for Cursor or VSCode (paste your API token, then generate and add the JSON to your MCP config). Restart the editor.

## Rebuilding the Designer frontend

**Local deploy** (`./scripts/deploy-local.sh`) builds the frontend automatically before building the add-on image (runs `npm ci`/`npm install` and `npm run build` in `frontend/`, then syncs the integration including `web/dist` into the add-on). So you don’t need to build the frontend by hand for deploy.

If you only change the frontend and want to test locally without a full deploy:

```bash
cd frontend
npm install
npm run build
```

The build writes to `custom_components/esptoolkit/web/dist`. To run the add-on image locally with that build, sync into the add-on folder and rebuild:

```bash
rsync -a custom_components/esptoolkit/ esptoolkit_addon/custom_components/esptoolkit/
```

## Repository structure

- `esptoolkit_addon/` — Add-on (config, Dockerfile, app, install script). Bundles `custom_components/esptoolkit` in the image.
- `custom_components/esptoolkit/` — Single integration (API wrapper + Designer backend, schemas, recipes, panel).
- `frontend/` — Designer React app; build output goes to `custom_components/esptoolkit/web/dist`.

## Deployment (local and CI)

- **Local deploy** (build images on your machine, push to ghcr.io, then push code):  
  `./scripts/deploy-local.sh <version> [message]`  
  Prereqs: docker, jq; set `GITHUB_TOKEN` (and optionally `GITHUB_USER`) for ghcr.io. Optionally run the clean-environment steps first (see `scripts/clean_environment_for_deploy.md`) so the add-on installs into a clean HA.

- **Fast local deploy** (reuses a pre-built base image so only app + integration are rebuilt):  
  1. Build the base once (takes a long time; run when the ESPHome base or deps change):  
     `./scripts/build-base.sh`  
  2. Deploy with:  
     `./scripts/deploy-local.sh --fast <version> [message]`  
  The base is tagged `esptoolkit-base:2025.04.0` (and `latest`). Re-run `build-base.sh` if you change `BUILD_BASE_VERSION` or the ESPHome ref in the main Dockerfile.

- **CI deploy** (bump version, push, wait for GitHub Actions to build):  
  `./scripts/deploy.sh <version> [message]`  
  Use `--no-wait` to skip waiting for the build.

- **Wait for build** (after a push):  
  `./scripts/wait-for-build.sh [commit_sha]`

- **Test in Docker** (before deploying):  
  `./esptoolkit_addon/scripts/test_in_docker.sh`

See `.cursor/rules/deployment.mdc` for the full checklist and version-bump locations (add-on config, app `__init__.py`, integration `manifest.json`).

## License

MIT
