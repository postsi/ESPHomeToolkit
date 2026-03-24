"""Constants for EspToolkit integration (API services + Designer)."""

DOMAIN = "esptoolkit"
PLATFORMS: list[str] = []

# --- API wrapper (add-on connection) ---
CONF_BASE_URL = "base_url"
CONF_TOKEN = "token"

ATTR_FILENAME = "filename"
ATTR_CONFIG_NAME = "config_name"
ATTR_YAML = "yaml"

SERVICE_COMPILE = "compile"
SERVICE_UPLOAD = "upload"
SERVICE_VALIDATE = "validate"
SERVICE_RUN = "run"

# --- Designer services (called by ESPHome devices / simulator) ---
SERVICE_SET_LIGHT_RGB = "set_light_rgb"
SERVICE_SET_LIGHT_COLOR_TEMP = "set_light_color_temp"

# --- Designer device/project config ---
CONF_WIFI_SSID = "wifi_ssid"
CONF_WIFI_PASSWORD_SECRET = "wifi_password"
CONF_DEFAULT_LOG_LEVEL = "default_log_level"
# Long random secret: Mac agent sends this after connecting to HA WebSocket (integration options).
CONF_MAC_SIM_TOKEN = "mac_sim_token"

STORAGE_VERSION = 1

# --- Panel (root-level paths like working esphome_touch_designer; /api/ caused 404) ---
PANEL_URL_PATH = "esptoolkit"  # sidebar panel id (frontend_url_path); HA frontend handles GET /esptoolkit
PANEL_IFRAME_URL = f"/{PANEL_URL_PATH}/panel"  # Tabbed wrapper served only in iframe so /esptoolkit can show HA sidebar
PANEL_DESIGNER_URL = f"/{PANEL_URL_PATH}/designer"  # Raw Designer SPA (iframe or direct)
PANEL_TITLE = "EspToolkit"

# Static assets under /api/esptoolkit/static (API path is fine for static)
STATIC_URL_PATH = f"/api/{DOMAIN}/static"

# Config dirs (under /config on HA host)
CONFIG_DIR = "esptoolkit"
ASSETS_DIR = "esptoolkit_assets"
PLUGINS_DIR = "esptoolkit_plugins"
