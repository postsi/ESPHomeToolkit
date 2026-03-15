from __future__ import annotations

import logging
from pathlib import Path

from aiohttp import web
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components import frontend
from homeassistant.components.http import HomeAssistantView, StaticPathConfig

from .const import DOMAIN, PANEL_TITLE, PANEL_PAGE_URL, PANEL_DESIGNER_URL, PANEL_URL_PATH, STATIC_URL_PATH
from .api.views import register_api_views

_LOGGER = logging.getLogger(__name__)


class PingView(HomeAssistantView):
    """Diagnostic: GET /esptoolkit/ping - if this returns 200, the integration loaded and registers views."""
    url = f"/{PANEL_URL_PATH}/ping"
    name = f"{DOMAIN}:ping"
    requires_auth = False

    async def get(self, request):
        return web.json_response({
            "ok": True,
            "integration": DOMAIN,
            "message": "ESPToolkit integration is loaded. If /esptoolkit still 404s, ensure config entry exists (add-on writes .esptoolkit_addon_config.json) and restart HA.",
        })


class PanelCheckView(HomeAssistantView):
    """Diagnostic: GET /esptoolkit/panel-check returns whether Designer panel and web/dist are present."""
    url = f"/{PANEL_URL_PATH}/panel-check"
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


def _designer_fallback_html() -> str:
    """Fallback when web/dist is missing."""
    return (
        "<html><body style='font-family:system-ui;margin:16px'>"
        f"<h1>{PANEL_TITLE}</h1>"
        "<p>The Designer frontend has not been built yet.</p>"
        "<p>Build it from the repo root:</p>"
        "<pre>cd frontend\n\nnpm install\nnpm run build</pre>"
        "</body></html>"
    )


class PanelDesignerView(HomeAssistantView):
    """Serves the raw Designer SPA at /esptoolkit/designer (for iframe or direct open)."""
    url = PANEL_DESIGNER_URL
    name = f"{DOMAIN}:designer"
    requires_auth = False

    async def get(self, request):
        hass: HomeAssistant = request.app["hass"]
        index_path = Path(__file__).parent / "web" / "dist" / "index.html"
        if not index_path.exists():
            return web.Response(text=_designer_fallback_html(), content_type="text/html")
        html = await hass.async_add_executor_job(index_path.read_text, "utf-8")
        return web.Response(
            text=html,
            content_type="text/html",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )


def _tabbed_panel_html() -> str:
    """HTML for the tabbed panel (Overview + Designer as tabs)."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{PANEL_TITLE}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: var(--ha-font-family, system-ui); background: var(--ha-background-color, #121212); color: var(--ha-text-color, #e1e1e1); }}
    .tabs {{ display: flex; padding: 0 16px; gap: 0; border-bottom: 1px solid var(--ha-border-color, #333); background: var(--ha-card-background, #1c1c1c); }}
    .tabs button {{ padding: 12px 20px; background: none; border: none; color: inherit; cursor: pointer; font-size: 1rem; border-bottom: 3px solid transparent; }}
    .tabs button:hover {{ background: rgba(255,255,255,0.05); }}
    .tabs button.active {{ border-bottom-color: var(--ha-primary-color, #03a9f4); }}
    .panels {{ padding: 16px; }}
    .panel {{ display: none; height: calc(100vh - 120px); }}
    .panel.active {{ display: block; }}
    .panel.iframe-panel iframe {{ width: 100%; height: 100%; border: none; }}
    .overview {{ max-width: 600px; }}
    .overview a {{ color: var(--ha-primary-color); }}
  </style>
</head>
<body>
  <div class="tabs">
    <button type="button" class="tab active" data-tab="overview">Overview</button>
    <button type="button" class="tab" data-tab="designer">Designer</button>
  </div>
  <div class="panels">
    <div id="overview" class="panel active">
      <div class="overview">
        <h2>{PANEL_TITLE}</h2>
        <p>Use the <strong>Designer</strong> tab to build and manage ESPHome LVGL dashboards.</p>
        <p>Open the Designer in this panel or in a new window:</p>
        <ul>
          <li><a href="{PANEL_DESIGNER_URL}" target="_blank">Open Designer in new window</a></li>
        </ul>
      </div>
    </div>
    <div id="designer" class="panel iframe-panel">
      <iframe src="{PANEL_DESIGNER_URL}" title="ESPToolkit Designer"></iframe>
    </div>
  </div>
  <script>
    document.querySelectorAll('.tab').forEach(function(btn) {{
      btn.addEventListener('click', function() {{
        var tab = this.getAttribute('data-tab');
        document.querySelectorAll('.tab').forEach(function(b) {{ b.classList.remove('active'); }});
        document.querySelectorAll('.panel').forEach(function(p) {{ p.classList.remove('active'); }});
        this.classList.add('active');
        var el = document.getElementById(tab);
        if (el) el.classList.add('active');
      }});
    }});
  </script>
</body>
</html>"""


class PanelIndexView(HomeAssistantView):
    """Serves the tabbed wrapper at /esptoolkit (Overview + Designer tab). Root-level path like working repo."""
    url = PANEL_PAGE_URL
    name = f"{DOMAIN}:panel"
    requires_auth = False

    async def get(self, request):
        return web.Response(
            text=_tabbed_panel_html(),
            content_type="text/html",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )


async def async_register_designer_panel(hass: HomeAssistant) -> None:
    """Register Designer panel and HTTP views. Called from async_setup_entry (like working esphome_touch_designer)."""
    hass.data.setdefault(DOMAIN, {})
    dist_path = str(Path(__file__).parent / "web" / "dist")
    if "_designer_routes_registered" not in hass.data[DOMAIN]:
        await hass.http.async_register_static_paths([
            StaticPathConfig(STATIC_URL_PATH, dist_path, False),
        ])
        hass.http.register_view(PanelIndexView)
        hass.http.register_view(PanelDesignerView)
        hass.http.register_view(PanelCheckView)
        hass.data[DOMAIN]["_designer_routes_registered"] = True
        _LOGGER.warning("ESPToolkit panel routes registered: %s and %s — Designer should load now.", PANEL_PAGE_URL, PANEL_DESIGNER_URL)
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
