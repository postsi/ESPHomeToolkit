# Clean environment for deploy (run via MCP)

This procedure removes the ESPToolkit add-on’s custom integration and `configuration.yaml` additions so you can prove deployment into an effectively clean environment. It is intended to be **run by the Cursor agent** using the **Home Assistant MCP server** (`user-home-assistant` or similar) on this machine.

**Default:** When you ask for a **local deploy** (e.g. “do local deploy”), the agent runs this procedure first, then runs `./scripts/deploy-local.sh`. To run only the clean script, ask: *"Run the clean environment for deploy script"*. To deploy without cleaning first, say *"local deploy without clean"*.

---

## Steps (executed via HA MCP tools)

1. **List** `custom_components/esptoolkit` (to get all files/dirs to delete).
2. **Delete** the integration directory or each file under `custom_components/esptoolkit/` as appropriate for your MCP (e.g. delete the directory, or delete key files such as `__init__.py`, `manifest.json`, `const.py`, `services.yaml`, `panel.py`, `storage.py`, and the `api/`, `schemas/`, `recipes/`, `web/` trees). Skip any that don’t exist.
3. **Delete** the add-on config file (so the next start is from a clean state):
   - `.esptoolkit_addon_config.json`
4. **Read** `configuration.yaml` via the HA file read tool (e.g. `ha_read_file` or equivalent).
5. **Remove** the block we add from the content:
   - Remove the substring: `\n# ESPToolkit add-on integration (auto-added so services and Designer load)\nesptoolkit:\n` (or the same with `\r\n` on Windows). If present, also trim any trailing newline so the file doesn’t end with an extra blank line.
   - In code: `new_content = content.replace("\n# ESPToolkit add-on integration (auto-added so services and Designer load)\nesptoolkit:\n", "").rstrip()` (then ensure the file ends with a single newline if desired).
6. **Write** the modified content back with the HA file write tool to `configuration.yaml`.

After this, the next time you start or update the add-on, it will run against a clean environment (no existing integration files, no `esptoolkit:` in `configuration.yaml`).

**Note:** The config entry in `.storage/core.config_entries` is not removed; HA may show a single “discovered” or orphaned entry until the add-on runs and re-creates/syncs it. Optionally you can remove the `esptoolkit` entry from that file for a fully clean state; this script does not modify it by default.
