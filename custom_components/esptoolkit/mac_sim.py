"""Host/SDL YAML transform + shared state for Mac simulator agent (outbound WebSocket to HA)."""

from __future__ import annotations

import asyncio
import logging
import secrets
from typing import TYPE_CHECKING, Any

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Top-level ESPHome sections removed for host/SDL sim (hardware, connectivity, backlight, etc.).
_MAC_SIM_DROP_SECTION_KEYS: frozenset[str] = frozenset(
    {
        "esp32",
        "esp8266",
        "rp2040",
        "libretiny",
        "nrf52",
        "esp32_hosted",
        "psram",
        "esp_ldo",
        "deep_sleep",
        "preferences",
        "wifi",
        "ethernet",
        "openthread",
        "captive_portal",
        "mdns",
        "ota",
        "improv_serial",
        "esp32_improv",
        "espnow",
        "web_server",
        "mqtt",
        "http_request",
        "wireguard",
        "statsd",
        "udp",
        "packet_transport",
        "zigbee",
        "esp32_ble_beacon",
        "ble_client",
        "esp32_ble_tracker",
        "esp32_ble_server",
        "bluetooth_proxy",
        "ble_nus",
        "one_wire",
        "canbus",
        "i2c",
        "spi",
        "uart",
        "i2s_audio",
        "opentherm",
        "tinyusb",
        "usb_cdc_acm",
        "usb_host",
        "usb_uart",
        "output",
        "light",
        "display_menu",
    }
)


def ensure_mac_sim_hub(hass: HomeAssistant) -> dict[str, Any]:
    """Singleton hub: one outbound agent session + outbound job queue."""
    root = hass.data.setdefault(DOMAIN, {})
    if "mac_sim_hub" not in root:
        root["mac_sim_hub"] = {"lock": asyncio.Lock(), "session": None}
    return root["mac_sim_hub"]


def _first_id_in_section_body(body: str, key: str = "id") -> str | None:
    for line in (body or "").splitlines():
        s = line.strip()
        if s.startswith(f"{key}:"):
            val = s.split(":", 1)[1].strip().split("#")[0].strip().strip("'\"")
            if val:
                return val
    return None


def transform_esphome_yaml_for_host_sdl(
    full_yaml: str,
    width: int,
    height: int,
) -> tuple[str, list[str]]:
    """Strip MCU hardware, inject host + SDL display + SDL touchscreen. Returns (yaml, warnings)."""
    from .api.views import _sections_to_yaml, _yaml_str_to_section_map

    warnings: list[str] = []
    w = max(120, min(4096, int(width)))
    h = max(120, min(4096, int(height)))

    sections = _yaml_str_to_section_map(full_yaml)
    display_body = (sections.get("display") or "").strip()
    touch_body = (sections.get("touchscreen") or "").strip()

    display_id = _first_id_in_section_body(display_body) or "main_display"
    touchscreen_id = _first_id_in_section_body(touch_body) or "main_touchscreen"

    for key in _MAC_SIM_DROP_SECTION_KEYS:
        sections.pop(key, None)

    sections.pop("display", None)
    sections.pop("touchscreen", None)
    sections.pop("host", None)

    sections["host"] = "  mac_address: \"06:35:69:ab:f6:79\"\n"

    sections["display"] = (
        f"  - id: {display_id}\n"
        "    platform: sdl\n"
        "    update_interval: never\n"
        "    auto_clear_enabled: false\n"
        "    dimensions:\n"
        f"      width: {w}\n"
        f"      height: {h}\n"
    )

    sections["touchscreen"] = (
        f"  - id: {touchscreen_id}\n"
        "    platform: sdl\n"
    )

    header = (
        f"# {DOMAIN} mac sim — host + SDL (mouse as touch). Not for flashing.\n"
        f"# Display {w}x{h}; display_id={display_id}; touchscreen_id={touchscreen_id}\n"
        "# Fonts/paths pointing at HA /config may need files on the Mac.\n\n"
    )

    merged = _sections_to_yaml(sections)
    if not merged.strip():
        warnings.append("transform produced empty YAML")
    return header + merged, warnings


def mac_sim_token_matches(expected: str, offered: str) -> bool:
    """Constant-time compare for UTF-8 tokens."""
    if not expected or not offered:
        return False
    try:
        a = expected.encode("utf-8")
        b = offered.encode("utf-8")
    except Exception:
        return False
    if len(a) != len(b):
        return False
    return secrets.compare_digest(a, b)
