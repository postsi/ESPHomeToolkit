from __future__ import annotations

import logging
from pathlib import Path

from aiohttp import web
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components import frontend
from homeassistant.components.http import HomeAssistantView, StaticPathConfig

from .const import DOMAIN, PANEL_TITLE, PANEL_IFRAME_URL, PANEL_DESIGNER_URL, PANEL_URL_PATH, STATIC_URL_PATH
from .api.views import register_api_views, ContextView, DevicesView, SchemasView, SchemaDetailView, RecipesView

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
            "message": "EspToolkit integration is loaded. If /esptoolkit still 404s, ensure config entry exists (add-on writes .esptoolkit_addon_config.json) and restart HA.",
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


class PanelDeviceLogView(HomeAssistantView):
    """Device log viewer: connect to device via ESPHome Native API; clear on connect; log level settable."""

    url = f"/{PANEL_URL_PATH}/device-log"
    name = f"{DOMAIN}:device_log"
    requires_auth = False

    async def get(self, request):
        return web.Response(
            text=f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{PANEL_TITLE} — Device Log</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; padding: 16px; font-family: var(--ha-font-family, system-ui); background: var(--ha-background-color, #121212); color: var(--ha-text-color, #e1e1e1); }}
    .row {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
    select, input {{ background: var(--ha-card-background, #1c1c1c); color: inherit; border: 1px solid var(--ha-border-color, #333); border-radius: 8px; padding: 8px 10px; }}
    button {{ background: var(--ha-primary-color, #03a9f4); color: #fff; border: none; border-radius: 8px; padding: 8px 12px; cursor: pointer; font-weight: 600; }}
    button.secondary {{ background: transparent; border: 1px solid var(--ha-border-color, #333); color: inherit; }}
    button:disabled {{ opacity: 0.6; cursor: not-allowed; }}
    .muted {{ color: var(--ha-secondary-text-color, #9aa0a6); font-size: 13px; }}
    pre {{ margin-top: 12px; padding: 12px; background: rgba(0,0,0,0.25); border: 1px solid var(--ha-border-color, #333); border-radius: 10px; height: calc(100vh - 150px); overflow: auto; white-space: pre-wrap; word-break: break-word; }}
    code {{ font-family: ui-monospace, monospace; }}
  </style>
</head>
<body>
  <div class="row">
    <strong>Device Log</strong>
    <span class="muted">Stream device runtime logs via ESPHome Native API. Host = device name (<code>.local</code>).</span>
  </div>
  <div class="row" style="margin-top: 10px">
    <label class="muted">Device</label>
    <select id="deviceSelect" style="min-width: 220px"></select>
    <label class="muted">Host override (optional)</label>
    <input id="hostInput" placeholder="e.g. 192.168.1.50" style="min-width: 180px" />
    <label class="muted">Log level</label>
    <select id="logLevelSelect" style="min-width: 140px">
      <option value="VERY_VERBOSE">Very verbose</option>
      <option value="VERBOSE">Verbose</option>
      <option value="DEBUG">Debug</option>
      <option value="CONFIG">Config</option>
      <option value="INFO" selected>Info</option>
      <option value="WARN">Warn</option>
      <option value="ERROR">Error</option>
      <option value="NONE">None</option>
    </select>
    <button id="connectBtn">Connect</button>
    <button id="disconnectBtn" class="secondary" disabled>Disconnect</button>
    <button id="clearBtn" class="secondary">Clear</button>
  </div>
  <div id="status" class="muted" style="margin-top: 8px"></div>
  <pre id="logBox"></pre>

  <script>
    (function() {{
      var statusEl = document.getElementById('status');
      var logBox = document.getElementById('logBox');
      var deviceSelect = document.getElementById('deviceSelect');
      var hostInput = document.getElementById('hostInput');
      var logLevelSelect = document.getElementById('logLevelSelect');
      var connectBtn = document.getElementById('connectBtn');
      var disconnectBtn = document.getElementById('disconnectBtn');
      var clearBtn = document.getElementById('clearBtn');

      function setStatus(s) {{ statusEl.textContent = s || ''; }}
      function appendLine(line) {{
        if (line === null || line === undefined) return;
        logBox.textContent += String(line) + "\\n";
        logBox.scrollTop = logBox.scrollHeight;
      }}
      function clearLog() {{ logBox.textContent = ''; }}

      async function getContext() {{
        var res = await fetch('/api/{DOMAIN}/context', {{ credentials: 'include' }});
        return res.json();
      }}
      async function loadDevices(entryId) {{
        var res = await fetch('/api/{DOMAIN}/devices?entry_id=' + encodeURIComponent(entryId), {{ credentials: 'include' }});
        return res.json();
      }}

      var entryId = '';
      var ws = null;
      var lastErrorFromMessage = null;

      function buildWsUrl() {{
        var proto = (location.protocol === 'https:') ? 'wss:' : 'ws:';
        var deviceId = deviceSelect.value || '';
        var url = proto + '//' + location.host + '/api/{DOMAIN}/device_native_logs/ws?entry_id=' + encodeURIComponent(entryId) + '&device_id=' + encodeURIComponent(deviceId);
        var host = (hostInput.value || '').trim();
        if (host) url += '&host=' + encodeURIComponent(host);
        return url;
      }}

      function connect() {{
        var deviceId = deviceSelect.value || '';
        if (!deviceId) {{ setStatus('Pick a device first.'); return; }}
        lastErrorFromMessage = null;
        clearLog();
        setStatus('Connecting…');
        try {{ if (ws) ws.close(); }} catch (e) {{}}
        ws = new WebSocket(buildWsUrl());
        ws.onopen = function() {{ setStatus('Connecting to device…'); }};
        ws.onmessage = function(ev) {{
          var data = ev.data;
          if (data === '[connected]') {{
            lastErrorFromMessage = null;
            setStatus('Connected.');
            connectBtn.disabled = true;
            disconnectBtn.disabled = false;
            deviceSelect.disabled = true;
            return;
          }}
          if (data && data.indexOf('error:') === 0) {{
            lastErrorFromMessage = data;
            setStatus(data);
            connectBtn.disabled = false;
            disconnectBtn.disabled = true;
            deviceSelect.disabled = false;
            return;
          }}
          if (data !== '') appendLine(data);
        }};
        ws.onclose = function(ev) {{
          var reason = (ev.reason && ev.reason.trim()) ? ev.reason.trim() : '';
          var code = ev.code || 0;
          if (lastErrorFromMessage) {{
            setStatus(lastErrorFromMessage);
          }} else if (reason) {{
            setStatus('Disconnected: ' + reason);
          }} else if (code && code !== 1000) {{
            setStatus('Disconnected: connection failed (code ' + code + '). Device unreachable or wrong API key?');
          }} else {{
            setStatus('Disconnected.');
          }}
          lastErrorFromMessage = null;
          connectBtn.disabled = false;
          disconnectBtn.disabled = true;
          deviceSelect.disabled = false;
          ws = null;
        }};
        ws.onerror = function() {{
          if (!lastErrorFromMessage) setStatus('WebSocket error. Check device is on and API key is correct.');
        }};
      }}

      function disconnect() {{
        if (ws) {{ ws.close(); ws = null; }}
      }}

      function sendLogLevel() {{
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        var level = logLevelSelect.value || 'INFO';
        ws.send(JSON.stringify({{ log_level: level }}));
      }}

      async function init() {{
        setStatus('Loading…');
        var ctx = await getContext();
        if (!ctx || !ctx.ok) {{
          setStatus('Not connected: ' + (ctx && ctx.error ? ctx.error : 'unknown'));
          return;
        }}
        entryId = ctx.entry_id || '';
        if (!entryId) {{
          setStatus('No active config entry. Configure the add-on first.');
          return;
        }}
        var d = await loadDevices(entryId);
        var list = (d && d.ok && d.devices) ? d.devices : [];
        deviceSelect.innerHTML = '';
        if (!list.length) {{
          var opt = document.createElement('option');
          opt.value = '';
          opt.textContent = '(no devices)';
          deviceSelect.appendChild(opt);
        }} else {{
          list.forEach(function(dev) {{
            var opt = document.createElement('option');
            opt.value = dev.device_id;
            opt.textContent = dev.name + ' (' + dev.slug + ')';
            deviceSelect.appendChild(opt);
          }});
        }}
        setStatus('Select a device and click Connect.');
      }}

      connectBtn.addEventListener('click', connect);
      disconnectBtn.addEventListener('click', disconnect);
      clearBtn.addEventListener('click', clearLog);
      logLevelSelect.addEventListener('change', sendLogLevel);

      init();
    }})();
  </script>
</body>
</html>""",
            content_type="text/html",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )


def _tabbed_panel_html(addon_base_url: str = "") -> str:
    """HTML for the tabbed panel: Designer (default), Device Log, ESPHome Output, Setup. No header."""
    addon_operational_url = (addon_base_url.rstrip("/") + "/?tab=operational") if addon_base_url else ""
    addon_setup_url = (addon_base_url.rstrip("/") + "/?tab=setup") if addon_base_url else ""
    # When no add-on URL, show placeholder instead of empty iframe
    operational_iframe_style = "" if addon_operational_url else "display:none;"
    operational_ph_style = "display:block;" if not addon_operational_url else "display:none;"
    setup_iframe_style = "" if addon_setup_url else "display:none;"
    setup_ph_style = "display:block;" if not addon_setup_url else "display:none;"
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
    .panels {{ padding: 0; height: calc(100vh - 56px); }}
    .panel {{ display: none; height: 100%; }}
    .panel.active {{ display: block; }}
    .panel.iframe-panel iframe {{ width: 100%; height: 100%; border: none; }}
    .panel-placeholder {{ padding: 16px; color: var(--ha-secondary-text-color, #888); }}
  </style>
</head>
<body>
  <div class="tabs">
    <button type="button" class="tab active" data-tab="designer">Designer</button>
    <button type="button" class="tab" data-tab="device-log">Device Log</button>
    <button type="button" class="tab" data-tab="esphome-output">ESPHome Output</button>
    <button type="button" class="tab" data-tab="setup">Setup</button>
  </div>
  <div class="panels">
    <div id="designer" class="panel iframe-panel active">
      <iframe src="{PANEL_DESIGNER_URL}" title="Designer"></iframe>
    </div>
    <div id="device-log" class="panel iframe-panel">
      <iframe src="/{PANEL_URL_PATH}/device-log" title="Device Log"></iframe>
    </div>
    <div id="esphome-output" class="panel iframe-panel">
      <iframe src="{addon_operational_url}" title="ESPHome Output" style="{operational_iframe_style}"></iframe>
      <div class="panel-placeholder" style="{operational_ph_style}">Configure the add-on (Setup tab) and ensure it is running to use ESPHome Output.</div>
    </div>
    <div id="setup" class="panel iframe-panel">
      <iframe src="{addon_setup_url}" title="Setup EspToolkit" style="{setup_iframe_style}"></iframe>
      <div class="panel-placeholder" style="{setup_ph_style}">Set the API token in Settings → Add-ons → EspToolkit → Configuration and restart the add-on to load Setup.</div>
    </div>
  </div>
  <script>
    (function() {{
      var tabs = document.querySelectorAll('.tab');
      var panels = document.querySelectorAll('.panel');
      tabs.forEach(function(btn) {{
        btn.addEventListener('click', function() {{
          var tab = this.getAttribute('data-tab');
          tabs.forEach(function(b) {{ b.classList.remove('active'); }});
          panels.forEach(function(p) {{ p.classList.remove('active'); }});
          this.classList.add('active');
          var el = document.getElementById(tab);
          if (el) el.classList.add('active');
        }});
      }});
    }})();
  </script>
</body>
</html>"""


class PanelIndexView(HomeAssistantView):
    """Serves the tabbed wrapper at /esptoolkit/panel (Designer, Device Log, etc.). Only loaded in iframe so /esptoolkit can be handled by HA frontend (sidebar + panel)."""
    url = PANEL_IFRAME_URL
    name = f"{DOMAIN}:panel"
    requires_auth = False

    async def get(self, request):
        hass: HomeAssistant = request.app["hass"]
        addon_base_url = ""
        from .api.views import _active_entry_id, _get_addon_connection
        eid = _active_entry_id(hass)
        conn = _get_addon_connection(hass, eid)
        if conn:
            addon_base_url = conn[0]
        return web.Response(
            text=_tabbed_panel_html(addon_base_url),
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
        hass.http.register_view(PanelDeviceLogView)
        hass.http.register_view(PanelCheckView)
        # Context so frontend gets entry_id (or "" if no config entry) and doesn't bail before loading schemas
        hass.http.register_view(ContextView)
        # Register schemas and recipes API so LVGL widgets and hardware recipes show even without a config entry
        hass.http.register_view(SchemasView)
        hass.http.register_view(SchemaDetailView)
        hass.http.register_view(RecipesView)
        hass.http.register_view(DevicesView)
        hass.data[DOMAIN]["_designer_routes_registered"] = True
        _LOGGER.warning("EspToolkit panel routes registered: %s, %s, and API (schemas/recipes).", PANEL_IFRAME_URL, PANEL_DESIGNER_URL)
    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
    frontend.async_register_built_in_panel(
        hass,
        component_name="iframe",
        sidebar_title=PANEL_TITLE,
        sidebar_icon="mdi:gesture-tap",
        frontend_url_path=PANEL_URL_PATH,
        config={"url": PANEL_IFRAME_URL},
        require_admin=True,
    )
    _LOGGER.debug("Designer panel registered at /%s", PANEL_URL_PATH)


async def async_register_panel(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register API views and ensure Designer panel is registered (panel may already be from async_setup)."""
    register_api_views(hass, entry)
    await async_register_designer_panel(hass)
