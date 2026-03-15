from __future__ import annotations

import logging
from pathlib import Path

from aiohttp import web
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components import frontend
from homeassistant.components.http import HomeAssistantView, StaticPathConfig

from .const import DOMAIN, PANEL_TITLE, PANEL_URL_PATH, STATIC_URL_PATH
from .api.views import register_api_views

_LOGGER = logging.getLogger(__name__)


def _unregister_panel(hass: HomeAssistant) -> None:
    """Remove the panel (call from async_unload_entry)."""
    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)


class PanelIndexView(HomeAssistantView):
    """Serves the SPA entrypoint. requires_auth=False so iframe loads reliably (sidebar is admin-only)."""
    url = f"/{PANEL_URL_PATH}"
    name = f"{DOMAIN}:panel"
    requires_auth = False

    async def get(self, request):
        hass: HomeAssistant = request.app["hass"]
        index_path = Path(__file__).parent / "web" / "dist" / "index.html"
        if not index_path.exists():
            fallback = (
                "<html><body style='font-family:system-ui;margin:16px'>"
                f"<h1>{PANEL_TITLE}</h1>"
                "<p>The frontend has not been built yet.</p>"
                "<p>Build it from the repo root:</p>"
                "<pre>cd frontend\n\n# install deps\nnpm install\n\n# build into custom_components/.../web/dist\nnpm run build</pre>"
                "</body></html>"
            )
            return web.Response(text=fallback, content_type="text/html")
        html = await hass.async_add_executor_job(index_path.read_text, "utf-8")
        return web.Response(
            text=html,
            content_type="text/html",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )


async def async_register_panel(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register sidebar panel + HTTP views."""
    register_api_views(hass, entry)

    dist_path = str(Path(__file__).parent / "web" / "dist")
    await hass.http.async_register_static_paths([
        StaticPathConfig(STATIC_URL_PATH, dist_path, False),
    ])

    hass.http.register_view(PanelIndexView)

    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
    frontend.async_register_built_in_panel(
        hass,
        component_name="iframe",
        sidebar_title=PANEL_TITLE,
        sidebar_icon="mdi:gesture-tap",
        frontend_url_path=PANEL_URL_PATH,
        config={"url": f"/{PANEL_URL_PATH}"},
        require_admin=True,
    )
    _LOGGER.debug("Panel registered at /%s (static at %s)", PANEL_URL_PATH, STATIC_URL_PATH)
