"""Local Mac-side ESPHome YAML transform for host + SDL simulation."""

from __future__ import annotations

import json
import re

_TOP_LEVEL_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*$")

_DROP_SECTION_KEYS: frozenset[str] = frozenset(
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


def _trim_outer_blank_lines(s: str) -> str:
    if not s:
        return ""
    lines = s.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _yaml_str_to_sections(yaml_str: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    lines = yaml_str.splitlines()
    i = 0
    while i < len(lines):
        m = _TOP_LEVEL_KEY_RE.match(lines[i])
        if not m:
            i += 1
            continue
        key = m.group(1).strip().lower()
        i += 1
        content: list[str] = []
        while i < len(lines):
            nxt = lines[i]
            if nxt and not nxt[0].isspace() and _TOP_LEVEL_KEY_RE.match(nxt):
                break
            content.append(nxt)
            i += 1
        body = "\n".join(content).rstrip()
        if key in sections and body:
            sections[key] = f"{sections[key].rstrip()}\n\n{body}"
        else:
            sections[key] = body
    return sections


def _sections_to_yaml(sections: dict[str, str]) -> str:
    parts: list[str] = []
    for key, raw in sections.items():
        body = _trim_outer_blank_lines(raw)
        if not body and key not in ("wifi", "ota", "logger"):
            continue
        parts.append(f"{key}:\n{(body or '').rstrip()}\n")
    return "\n".join(parts).rstrip() + "\n" if parts else ""


def _first_id_in_section_body(body: str, key: str = "id") -> str | None:
    for line in (body or "").splitlines():
        s = line.strip()
        if s.startswith(f"{key}:"):
            val = s.split(":", 1)[1].strip().split("#")[0].strip().strip("'\"")
            if val:
                return val
    return None


def _patch_esphome_name(body: str, name: str) -> str:
    body = _trim_outer_blank_lines(body)
    q = json.dumps(name)
    line = f"name: {q}"
    if not body:
        return f"  {line}\n"
    if re.search(r"(?m)^\s*name\s*:", body):
        return re.sub(r"(?m)^(\s*)name\s*:\s*.+$", lambda m: m.group(1) + line, body, count=1)
    return f"  {line}\n{body}"


def _patch_api_encryption_key(body: str, key_b64: str) -> str:
    body = _trim_outer_blank_lines(body)
    q = json.dumps(key_b64)
    if not body:
        return f"  encryption:\n    key: {q}\n"
    if re.search(r"(?m)^\s*key\s*:", body):
        return re.sub(r"(?m)^(\s*)key\s*:\s*.+$", rf"\1key: {q}", body, count=1)
    return f"  encryption:\n    key: {q}\n{body}"


def transform_esphome_yaml_for_host_sdl(
    full_yaml: str,
    width: int,
    height: int,
    *,
    api_encryption_key: str,
    esphome_name: str = "macsim",
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    w = max(120, min(4096, int(width)))
    h = max(120, min(4096, int(height)))
    api_key = (api_encryption_key or "").strip()
    if not api_key:
        raise ValueError("api_encryption_key is required")

    sections = _yaml_str_to_sections(full_yaml)
    display_body = _trim_outer_blank_lines(sections.get("display") or "")
    touch_body = _trim_outer_blank_lines(sections.get("touchscreen") or "")

    display_id = _first_id_in_section_body(display_body) or "main_display"
    touchscreen_id = _first_id_in_section_body(touch_body) or "main_touchscreen"

    for drop_key in _DROP_SECTION_KEYS:
        sections.pop(drop_key, None)

    sections.pop("display", None)
    sections.pop("touchscreen", None)
    sections.pop("host", None)

    sections["esphome"] = _patch_esphome_name(sections.get("esphome") or "", esphome_name)
    sections["host"] = "  mac_address: \"06:35:69:ab:f6:79\"\n"
    sections["api"] = _patch_api_encryption_key(sections.get("api") or "", api_key)
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
        "# esptoolkit mac sim — transformed on Mac host + SDL (mouse as touch).\n"
        f"# Display {w}x{h}; display_id={display_id}; touchscreen_id={touchscreen_id}\n\n"
    )
    merged = _sections_to_yaml(sections)
    if not merged.strip():
        warnings.append("transform produced empty YAML")
    return header + merged, warnings
