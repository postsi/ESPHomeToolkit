"""Constants for ESPToolkit integration (API services + Designer)."""

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

STORAGE_VERSION = 1

# --- Panel ---
PANEL_URL_PATH = "esptoolkit"
PANEL_TITLE = "ESPToolkit"

# Static assets under /api/esptoolkit/static
STATIC_URL_PATH = f"/api/{DOMAIN}/static"

# Config dirs (under /config on HA host)
CONFIG_DIR = "esptoolkit"
ASSETS_DIR = "esptoolkit_assets"
PLUGINS_DIR = "esptoolkit_plugins"
