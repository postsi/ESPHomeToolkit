from __future__ import annotations

import logging
from pathlib import Path

from aiohttp import web
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components import frontend
from homeassistant.components.http import HomeAssistantView, StaticPathConfig

from .const import DOMAIN, PANEL_TITLE, PANEL_PAGE_URL, PANEL_URL_PATH, STATIC_URL_PATH
from .api.views import register_api_views

_LOGGER = logging.getLogger(__name__)


class PanelCheckView(HomeAssistantView):
    """Diagnostic: GET /api/esptoolkit/panel-check returns whether Designer panel and web/dist are present."""
    url = f"/api/{DOMAIN}/panel-check"
    name = f"{DOMAIN}:panel_check"
    requires_auth = False

    async def get(self, request):
        index_path = Path(__file__).parent / "web" / "dist" / "index.html"
        dist_dir = Path(__file__).parent / "web" / "dist"
        web_dist_exists = index_path.is_file()
        assets_dir = dist_dir / "assets"
        assets_count = len(list(assets_dir.glob("*"))) if assets_dir.is_dir() else 0
        return web.json_response({
            "panel": "esptoolkit",
            "web_dist_exists": web_dist_exists,
            "web_dist_path": str(dist_dir),
            "assets_count": assets_count,
            "message": "Designer panel and assets OK" if web_dist_exists and assets_count else "web/dist missing or empty — reinstall add-on or update to latest",
        })


def _unregister_panel(hass: HomeAssistant) -> None:
    """Remove the panel (call from async_unload_entry)."""
    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)


class PanelIndexView(HomeAssistantView):
    """Serves the SPA entrypoint at /api/esptoolkit/panel (under /api/ for reliable routing)."""
    url = PANEL_PAGE_URL
    name = f"api:{DOMAIN}:panel"
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


async def async_register_designer_panel(hass: HomeAssistant) -> None:
    """Register Designer panel and routes only (no API). Call from async_setup so panel shows even without config entry."""
    hass.data.setdefault(DOMAIN, {})
    dist_path = str(Path(__file__).parent / "web" / "dist")
    if "_designer_routes_registered" not in hass.data[DOMAIN]:
        await hass.http.async_register_static_paths([
            StaticPathConfig(STATIC_URL_PATH, dist_path, False),
        ])
        hass.http.register_view(PanelIndexView)
        hass.http.register_view(PanelCheckView)
        hass.data[DOMAIN]["_designer_routes_registered"] = True
    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
    frontend.async_register_built_in_panel(
        hass,
        component_name="iframe",
        sidebar_title=PANEL_TITLE,
        sidebar_icon="mdi:gesture-tap",
        frontend_url_path=PANEL_URL_PATH,
        config={"url": PANEL_PAGE_URL},
        require_admin=True,
    )
    _LOGGER.debug("Designer panel registered at /%s", PANEL_URL_PATH)


async def async_register_panel(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register API views and ensure Designer panel is registered (panel may already be from async_setup)."""
    register_api_views(hass, entry)
    await async_register_designer_panel(hass)
