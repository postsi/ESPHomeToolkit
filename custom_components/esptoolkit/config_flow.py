"""Config flow for ESPToolkit. Configuration is created by the add-on (import), not via UI."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.data_entry_flow import AbortFlow, FlowResult

from .const import CONF_BASE_URL, CONF_TOKEN, DOMAIN


class ESPToolkitConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ESPToolkit. No user step; config comes from add-on file."""

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
            title="ESPToolkit",
            data={CONF_BASE_URL: base_url, CONF_TOKEN: token},
        )
