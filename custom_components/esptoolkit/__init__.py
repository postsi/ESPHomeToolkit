"""ESPToolkit integration: API services (add-on) + Designer panel and storage."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_CONFIG_NAME,
    ATTR_FILENAME,
    ATTR_YAML,
    CONF_BASE_URL,
    DOMAIN,
    PANEL_DESIGNER_URL,
    PANEL_PAGE_URL,
    SERVICE_COMPILE,
    SERVICE_RUN,
    SERVICE_SET_LIGHT_COLOR_TEMP,
    SERVICE_SET_LIGHT_RGB,
    SERVICE_UPLOAD,
    SERVICE_VALIDATE,
)

_LOGGER = logging.getLogger(__name__)

# File written by the add-on so we can create a config entry without user config flow
_INTEGRATION_CONFIG_FILE = ".esptoolkit_addon_config.json"

# Service call schema: filename/config_name (file) or yaml (inline)
SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_FILENAME): cv.string,
        vol.Optional(ATTR_CONFIG_NAME): cv.string,
        vol.Optional(ATTR_YAML): cv.string,
    }
)

SET_LIGHT_RGB_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("red"): vol.All(vol.Coerce(int), vol.Range(0, 255)),
        vol.Required("green"): vol.All(vol.Coerce(int), vol.Range(0, 255)),
        vol.Required("blue"): vol.All(vol.Coerce(int), vol.Range(0, 255)),
    }
)

SET_LIGHT_COLOR_TEMP_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("color_temp"): vol.All(vol.Coerce(int), vol.Range(1, 1000)),
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up ESPToolkit. Auto-create or sync config entry from add-on file. Register Designer services."""
    # --- Config entry from add-on file (no config flow) ---
    entries = hass.config_entries.async_entries(DOMAIN)
    config_path = Path(hass.config.config_dir) / _INTEGRATION_CONFIG_FILE
    if config_path.is_file():
        try:
            data = json.loads(await hass.async_add_executor_job(config_path.read_text))
        except Exception as e:
            _LOGGER.debug("Could not read add-on config file %s: %s", config_path, e)
        else:
            base_url = (data.get("base_url") or "").strip().rstrip("/")
            token = (data.get("token") or "").strip()
            if base_url and token:
                if entries:
                    entry = entries[0]
                    cur_url = (entry.data.get(CONF_BASE_URL) or "").strip().rstrip("/")
                    cur_tok = (entry.data.get(CONF_TOKEN) or "").strip()
                    if cur_url != base_url or cur_tok != token:
                        _LOGGER.info("Syncing config entry from add-on file (base_url %s -> %s)", cur_url, base_url)
                        hass.config_entries.async_update_entry(
                            entry, data={CONF_BASE_URL: base_url, CONF_TOKEN: token}
                        )
                        await hass.config_entries.async_reload(entry.entry_id)
                else:
                    entry = ConfigEntry(
                        version=1,
                        domain=DOMAIN,
                        title="ESPToolkit",
                        data={CONF_BASE_URL: base_url, CONF_TOKEN: token},
                        source="import",
                    )
                    hass.config_entries.async_add(entry)
                    _LOGGER.info("Created config entry from add-on config file (base_url=%s)", base_url)

    # --- Designer services (no config entry needed) ---
    async def async_set_light_rgb(call: ServiceCall) -> None:
        entity_id = call.data["entity_id"]
        rgb = [call.data["red"], call.data["green"], call.data["blue"]]
        await hass.services.async_call("light", "turn_on", {"entity_id": entity_id, "rgb_color": rgb}, blocking=True)

    async def async_set_light_color_temp(call: ServiceCall) -> None:
        entity_id = call.data["entity_id"]
        await hass.services.async_call(
            "light", "turn_on", {"entity_id": entity_id, "color_temp": call.data["color_temp"]}, blocking=True
        )

    hass.services.async_register(DOMAIN, SERVICE_SET_LIGHT_RGB, async_set_light_rgb, schema=SET_LIGHT_RGB_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_SET_LIGHT_COLOR_TEMP, async_set_light_color_temp, schema=SET_LIGHT_COLOR_TEMP_SCHEMA
    )

    # Register Designer panel at /api/esptoolkit/panel so the panel appears even when no config entry yet
    from .panel import async_register_designer_panel
    await async_register_designer_panel(hass)
    _LOGGER.info("ESPToolkit loaded: panel at %s (Designer tab at %s), diagnostic at /api/esptoolkit/panel-check", PANEL_PAGE_URL, PANEL_DESIGNER_URL)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up API services and Designer (storage, panel, API views)."""
    base_url = (entry.data.get(CONF_BASE_URL) or "").strip().rstrip("/")
    token = (entry.data.get(CONF_TOKEN) or "").strip()
    if not base_url or not token:
        _LOGGER.error("Config entry missing base_url or token")
        return False

    async def _call_addon(
        service: str,
        filename: str | None = None,
        config_name: str | None = None,
        yaml_content: str | None = None,
    ) -> dict[str, Any]:
        if yaml_content is not None and yaml_content.strip():
            payload = {"config_source": "yaml", "yaml": yaml_content.strip()}
        else:
            fn = (filename or "").strip()
            cn = (config_name or "").strip()
            fname = fn or (f"{cn}.yaml" if cn else None)
            if not fname:
                raise HomeAssistantError("Provide filename, config_name, or yaml")
            if not fname.endswith(".yaml"):
                fname = f"{fname}.yaml"
            payload = {"config_source": "file", "filename": fname}
        url = f"{base_url}/api/{service}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        _LOGGER.debug("Calling add-on: url=%s", url)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=600)) as resp:
                resp_body = await resp.text()
                if resp.status >= 400:
                    raise HomeAssistantError(
                        f"Add-on returned {resp.status}: {resp_body[:500] if resp_body else resp.reason}"
                    )
                if resp.content_type == "application/json":
                    try:
                        data = json.loads(resp_body)
                        return data if isinstance(data, dict) else {"output": resp_body}
                    except Exception:
                        pass
                return {"output": resp_body}

    async def handle_compile(call: ServiceCall) -> None:
        result = await _call_addon(
            "compile",
            filename=call.data.get(ATTR_FILENAME),
            config_name=call.data.get(ATTR_CONFIG_NAME),
            yaml_content=call.data.get(ATTR_YAML),
        )
        _LOGGER.info("Compile result: %s", result)

    async def handle_upload(call: ServiceCall) -> None:
        result = await _call_addon(
            "upload",
            filename=call.data.get(ATTR_FILENAME),
            config_name=call.data.get(ATTR_CONFIG_NAME),
            yaml_content=call.data.get(ATTR_YAML),
        )
        _LOGGER.info("Upload result: %s", result)

    async def handle_validate(call: ServiceCall) -> None:
        result = await _call_addon(
            "config-check",
            filename=call.data.get(ATTR_FILENAME),
            config_name=call.data.get(ATTR_CONFIG_NAME),
            yaml_content=call.data.get(ATTR_YAML),
        )
        _LOGGER.info("Validate result: %s", result)

    async def handle_run(call: ServiceCall) -> None:
        result = await _call_addon(
            "run",
            filename=call.data.get(ATTR_FILENAME),
            config_name=call.data.get(ATTR_CONFIG_NAME),
            yaml_content=call.data.get(ATTR_YAML),
        )
        _LOGGER.info("Run result: %s", result)

    hass.services.async_register(DOMAIN, SERVICE_COMPILE, handle_compile, schema=SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UPLOAD, handle_upload, schema=SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_VALIDATE, handle_validate, schema=SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RUN, handle_run, schema=SERVICE_SCHEMA)

    # --- Designer: storage, panel, API views ---
    from .storage import DashboardStorage
    from .panel import async_register_panel

    storage = DashboardStorage(hass, entry.entry_id)
    await storage.async_load()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"storage": storage, "entry": entry}
    hass.data[DOMAIN]["active_entry_id"] = entry.entry_id

    await async_register_panel(hass, entry)
    _LOGGER.info("ESPToolkit services and Designer registered (base_url=%s)", base_url)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry: remove API services and Designer panel."""
    from .panel import _unregister_panel

    hass.services.async_remove(DOMAIN, SERVICE_COMPILE)
    hass.services.async_remove(DOMAIN, SERVICE_UPLOAD)
    hass.services.async_remove(DOMAIN, SERVICE_VALIDATE)
    hass.services.async_remove(DOMAIN, SERVICE_RUN)
    _unregister_panel(hass)
    if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN].pop(entry.entry_id)
    if hass.data.get(DOMAIN, {}).get("active_entry_id") == entry.entry_id:
        hass.data[DOMAIN].pop("active_entry_id", None)
    return True
