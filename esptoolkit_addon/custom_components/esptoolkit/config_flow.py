"""Config flow for EspToolkit. Configuration is created by the add-on (import), not via UI."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow, FlowResult
from homeassistant.helpers import selector

from .const import CONF_BASE_URL, CONF_MAC_SIM_TOKEN, CONF_TOKEN, DOMAIN


class ESPToolkitOptionsFlow(config_entries.OptionsFlow):
    """Optional Mac SDL simulator agent token (outbound WebSocket from Mac to HA)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            token = (user_input.get(CONF_MAC_SIM_TOKEN) or "").strip()
            merged = dict(self.config_entry.options)
            merged[CONF_MAC_SIM_TOKEN] = token
            return self.async_create_entry(title="", data=merged)

        cur = (self.config_entry.options or {}).get(CONF_MAC_SIM_TOKEN) or ""
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_MAC_SIM_TOKEN,
                    default=cur,
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD,
                        autocomplete="off",
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


class ESPToolkitConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EspToolkit. No user step; config comes from add-on file."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """No UI configuration; integration is set up by the add-on."""
        return self.async_abort(reason="configure_via_addon")

    async def async_step_import(self, import_data: dict) -> FlowResult:
        """Import a config entry from the add-on config file (called internally)."""
        base_url = (import_data.get(CONF_BASE_URL) or "").strip().rstrip("/")
        token = (import_data.get(CONF_TOKEN) or "").strip()
        if not base_url or not token:
            raise AbortFlow(reason="invalid_config")
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="EspToolkit",
            data={CONF_BASE_URL: base_url, CONF_TOKEN: token},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ESPToolkitOptionsFlow:
        return ESPToolkitOptionsFlow(config_entry)
