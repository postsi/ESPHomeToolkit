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
        # Hardware-only sections that don't apply to host SDL.
        # Note: we *do not* drop "switch"/"light" here — we rewrite hardware-backed entries to template stubs.
        "output",
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


def _patch_api_encryption_key(body: str, key_b64: str | None) -> str:
    body = _trim_outer_blank_lines(body)
    if not body:
        if key_b64:
            q = json.dumps(key_b64)
            return f"  encryption:\n    key: {q}\n  reboot_timeout: 0s\n"
        return "  reboot_timeout: 0s\n"
    if key_b64:
        q = json.dumps(key_b64)
        if re.search(r"(?m)^\s*key\s*:", body):
            body = re.sub(r"(?m)^(\s*)key\s*:\s*.+$", rf"\1key: {q}", body, count=1)
        else:
            body = f"  encryption:\n    key: {q}\n{body}"
    if re.search(r"(?m)^\s*reboot_timeout\s*:", body):
        body = re.sub(r"(?m)^(\s*)reboot_timeout\s*:\s*.+$", r"\1reboot_timeout: 0s", body, count=1)
    else:
        body = body.rstrip() + "\n  reboot_timeout: 0s"
    return body


def _iter_yaml_list_items(lines: list[str]) -> list[tuple[int, int, int]]:
    """Return [(start_idx, end_idx, indent_spaces)] for top-level list items in lines."""
    out: list[tuple[int, int, int]] = []
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)-\s+", lines[i])
        if not m:
            i += 1
            continue
        item_indent = len(m.group(1))
        j = i + 1
        while j < len(lines):
            m2 = re.match(r"^(\s*)-\s+", lines[j])
            if m2 and len(m2.group(1)) == item_indent:
                break
            j += 1
        out.append((i, j, item_indent))
        i = j
    return out


def _rewrite_yaml_list_items(
    body: str,
    *,
    marker_re: re.Pattern[str],
    rewrite: callable,
) -> str:
    """Rewrite list items in a section body when marker_re matches inside an item."""
    lines = (body or "").splitlines()
    out: list[str] = []
    idxs = _iter_yaml_list_items(lines)
    if not idxs:
        return "\n".join(lines).rstrip()
    last = 0
    for start, end, indent in idxs:
        # copy any non-item lines between items
        if start > last:
            out.extend(lines[last:start])
        chunk = "\n".join(lines[start:end])
        if marker_re.search(chunk):
            out.extend(rewrite(chunk, indent))
        else:
            out.extend(lines[start:end])
        last = end
    if last < len(lines):
        out.extend(lines[last:])
    return "\n".join(out).rstrip()


def _extract_field(chunk: str, field: str) -> str | None:
    m = re.search(rf"(?m)^\s*{re.escape(field)}\s*:\s*(.+?)\s*$", chunk)
    if not m:
        return None
    val = m.group(1).strip()
    # remove inline comments
    val = val.split("#", 1)[0].strip()
    return val or None


def _rewrite_output_switch_to_template(chunk: str, indent: int) -> list[str]:
    sp = " " * indent
    name = _extract_field(chunk, "name") or "\"Switch\""
    # preserve id if present (useful for internal refs)
    idv = _extract_field(chunk, "id")
    out = [f"{sp}- platform: template"]
    if idv:
        out.append(f"{sp}  id: {idv}")
    out.append(f"{sp}  name: {name}")
    out.append(f"{sp}  optimistic: true")
    return out


def _rewrite_time_sntp_to_host(chunk: str, indent: int) -> list[str]:
    """Rewrite `time: - platform: sntp` into host-compatible time."""
    lines = chunk.splitlines()
    out: list[str] = []
    replaced = False
    for ln in lines:
        if re.search(r"^\s*(-\s*)?platform\s*:\s*sntp\s*$", ln):
            out.append(re.sub(r"sntp\s*$", "host", ln))
            replaced = True
        else:
            out.append(ln)
    if not replaced:
        sp = " " * indent
        out.insert(0, f"{sp}- platform: host")
    return out


def _rewrite_text_sensor_wifi_info_to_template(
    chunk: str,
    indent: int,
    *,
    host_ip: str | None,
    host_hostname: str | None,
) -> list[str]:
    """Rewrite `text_sensor: - platform: wifi_info` to template stubs (host has no wifi component)."""
    sp = " " * indent
    # Best-effort: preserve any `id:` and `name:` fields present in the chunk.
    # wifi_info subkeys like ip_address:/ssid:/bssid: become separate template sensors.
    ids = re.findall(r"(?m)^\s*id\s*:\s*([A-Za-z0-9_]+)\s*$", chunk)
    names = re.findall(r"(?m)^\s*name\s*:\s*(.+?)\s*$", chunk)
    pairs = list(zip(ids, names)) if ids and names and len(ids) == len(names) else []
    out: list[str] = []
    def _guess_value(_id: str, _name: str) -> str:
        lid = _id.lower()
        lname = _name.lower()
        if "ip" in lid or "ip" in lname:
            return host_ip or "..."
        if "host" in lid or "host" in lname or "name" in lid or "name" in lname:
            return host_hostname or "..."
        return "..."

    if pairs:
        for _id, _name in pairs:
            val = _guess_value(_id, _name)
            out.extend(
                [
                    f"{sp}- platform: template",
                    f"{sp}  id: {_id}",
                    f"{sp}  name: {_name}",
                    f"{sp}  update_interval: 30s",
                    f"{sp}  lambda: |-",
                    f"{sp}    return std::string({json.dumps(val)});",
                ]
            )
    else:
        # If parsing failed, just emit one stub entry to avoid config failure.
        out.extend(
            [
                f"{sp}- platform: template",
                f"{sp}  update_interval: 30s",
                f"{sp}  lambda: |-",
                f"{sp}    return std::string(\"...\");",
            ]
        )
    return out


def _sanitize_id(raw: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9_]", "_", raw.strip())
    if not out:
        out = "stub"
    if out[0].isdigit():
        out = f"_{out}"
    return out


def _rewrite_output_light_to_monochromatic(chunk: str, indent: int) -> tuple[list[str], str]:
    sp = " " * indent
    name = _extract_field(chunk, "name")
    idv = _extract_field(chunk, "id")
    if not idv:
        # Ensure an id exists so we can wire output -> light reliably.
        idv = _sanitize_id((name or "light").strip("'\"")) + "_stub"
    out_id = f"{_sanitize_id(idv)}_out"
    out = [f"{sp}- platform: monochromatic"]
    if idv:
        out.append(f"{sp}  id: {idv}")
    if name:
        out.append(f"{sp}  name: {name}")
    out.append(f"{sp}  output: {out_id}")
    out.append(f"{sp}  default_transition_length: 0s")
    return out, out_id


def _ensure_template_light_for_id(sections: dict[str, str], light_id: str, *, name: str | None = None) -> None:
    body = sections.get("light") or ""
    if re.search(rf"(?m)^\s*id\s*:\s*{re.escape(light_id)}\s*$", body):
        return
    sp = "  "
    out_id = f"{_sanitize_id(light_id)}_out"
    chunk = [f"{sp}- platform: monochromatic", f"{sp}  id: {light_id}"]
    if name:
        chunk.append(f"{sp}  name: {json.dumps(name)}")
    chunk.append(f"{sp}  output: {out_id}")
    chunk.append(f"{sp}  default_transition_length: 0s")
    stub = "\n".join(chunk) + "\n"
    sections["light"] = (body.rstrip() + "\n\n" + stub).strip() + "\n" if body.strip() else stub


def _ensure_template_output_ids(sections: dict[str, str], output_ids: list[str]) -> None:
    body = sections.get("output") or ""
    existing = set(re.findall(r"(?m)^\s*id\s*:\s*([A-Za-z0-9_]+)\s*$", body))
    add_chunks: list[str] = []
    seen_local: set[str] = set()
    for oid in output_ids:
        if oid in seen_local:
            continue
        seen_local.add(oid)
        if oid in existing:
            continue
        add_chunks.append(
            "\n".join(
                [
                    "  - platform: template",
                    f"    id: {oid}",
                    "    type: float",
                    "    write_action:",
                    "      - lambda: |-",
                    "          // host/SDL sim stub output",
                    "          (void) state;",
                ]
            )
        )
    if not add_chunks:
        return
    merged = ((body.rstrip() + "\n\n") if body.strip() else "") + "\n\n".join(add_chunks) + "\n"
    sections["output"] = merged


def transform_esphome_yaml_for_host_sdl(
    full_yaml: str,
    width: int,
    height: int,
    *,
    api_encryption_key: str,
    esphome_name: str | None = None,
    host_ip: str | None = None,
    host_hostname: str | None = None,
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    w = max(120, min(4096, int(width)))
    h = max(120, min(4096, int(height)))
    api_key = (api_encryption_key or "").strip() if api_encryption_key is not None else None

    sections = _yaml_str_to_sections(full_yaml)
    display_body = _trim_outer_blank_lines(sections.get("display") or "")
    touch_body = _trim_outer_blank_lines(sections.get("touchscreen") or "")

    display_id = _first_id_in_section_body(display_body) or "main_display"
    touchscreen_id = _first_id_in_section_body(touch_body) or "main_touchscreen"

    for drop_key in _DROP_SECTION_KEYS:
        sections.pop(drop_key, None)

    # Host/SDL sim: replace hardware-backed entities with template stubs so HA still sees them.
    # - output-based switches -> template switches
    sections["switch"] = _rewrite_yaml_list_items(
        sections.get("switch") or "",
        marker_re=re.compile(r"(?m)^\s*(-\s*)?platform:\s*output\s*$"),
        rewrite=_rewrite_output_switch_to_template,
    )
    # - sntp time is MCU-only; rewrite to host time for SDL host builds
    sections["time"] = _rewrite_yaml_list_items(
        sections.get("time") or "",
        marker_re=re.compile(r"(?m)^\s*(-\s*)?platform:\s*sntp\s*$"),
        rewrite=_rewrite_time_sntp_to_host,
    )
    # - wifi_info text_sensors require wifi: (MCU). Replace with template stubs.
    sections["text_sensor"] = _rewrite_yaml_list_items(
        sections.get("text_sensor") or "",
        marker_re=re.compile(r"(?m)^\s*(-\s*)?platform:\s*wifi_info\s*$"),
        rewrite=lambda chunk, indent: _rewrite_text_sensor_wifi_info_to_template(
            chunk,
            indent,
            host_ip=host_ip,
            host_hostname=host_hostname,
        ),
    )
    # - output/pin-based lights -> template lights
    light_body = sections.get("light") or ""
    created_output_ids: list[str] = []
    if light_body.strip():
        lines = light_body.splitlines()
        rebuilt: list[str] = []
        idxs = _iter_yaml_list_items(lines)
        last = 0
        for start, end, indent in idxs:
            if start > last:
                rebuilt.extend(lines[last:start])
            chunk = "\n".join(lines[start:end])
            if re.search(r"(?m)^\s*(output|pin)\s*:\s*.+$", chunk):
                new_item, out_id = _rewrite_output_light_to_monochromatic(chunk, indent)
                rebuilt.extend(new_item)
                created_output_ids.append(out_id)
            else:
                rebuilt.extend(lines[start:end])
            last = end
        if last < len(lines):
            rebuilt.extend(lines[last:])
        sections["light"] = "\n".join(rebuilt).rstrip()
    # Ensure common backlight id exists so actions like `light.turn_off: id: display_backlight` validate.
    if "display_backlight" in full_yaml:
        _ensure_template_light_for_id(sections, "display_backlight", name="Display Backlight")
        created_output_ids.append(f"{_sanitize_id('display_backlight')}_out")
    _ensure_template_output_ids(sections, created_output_ids)

    sections.pop("display", None)
    sections.pop("touchscreen", None)
    sections.pop("host", None)

    # Preserve original device name by default; allow explicit override when provided.
    if esphome_name:
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
