from __future__ import annotations

import dataclasses
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION


def _default_project() -> dict[str, Any]:
    return {
        "model_version": 1,
        "pages": [
            {
                "page_id": "main",
                "name": "Main",
                "widgets": [],
            }
        ],
        "palette": {
            "color.bg": "#0B0F14",
            "color.card": "#111827",
            "color.text": "#E5E7EB",
            "color.muted": "#9CA3AF"
        },
        "lvgl_config": {
            "main": {
                "disp_bg_color": "#0B0F14",
                "buffer_size": "100%",
            },
            "style_definitions": [],
            "theme": {},
            "gradients": [],
            "top_layer": {"widgets": []},
        }
    }


def _migrate_project(project: dict[str, Any] | None) -> dict[str, Any]:
    """Best-effort project migration.

    For personal-use stability: ensure required keys exist and preserve unknown fields.
    """
    if not isinstance(project, dict):
        return _default_project()

    # v1: ensure model_version exists
    if "model_version" not in project:
        project["model_version"] = 1

    # Ensure pages structure exists
    if not isinstance(project.get("pages"), list) or not project["pages"]:
        project["pages"] = _default_project()["pages"]

    # Ensure palette exists
    if not isinstance(project.get("palette"), dict):
        project["palette"] = _default_project()["palette"]

    # Ensure lvgl_config exists (theme, style_definitions, gradients, main, top_layer)
    default_lvgl = _default_project()["lvgl_config"]
    if not isinstance(project.get("lvgl_config"), dict):
        project["lvgl_config"] = dict(default_lvgl)
    else:
        lc = project["lvgl_config"]
        if not isinstance(lc.get("main"), dict):
            lc["main"] = dict(default_lvgl.get("main", {}))
        if not isinstance(lc.get("style_definitions"), list):
            lc["style_definitions"] = []
        if not isinstance(lc.get("theme"), dict):
            lc["theme"] = {}
        if not isinstance(lc.get("gradients"), list):
            lc["gradients"] = []
        if "top_layer" not in lc or not isinstance(lc.get("top_layer"), dict):
            lc["top_layer"] = {"widgets": []}

    return project


@dataclasses.dataclass
class DeviceProject:
    """Per-device project: design model + device-specific settings."""
    device_id: str
    slug: str
    name: str
    hardware_recipe_id: str | None = None
    api_key: str | None = None  # ESPHome API encryption key (32-byte base64)
    device_settings: dict[str, Any] = dataclasses.field(default_factory=dict)
    project: dict[str, Any] = dataclasses.field(default_factory=_default_project)


@dataclasses.dataclass
class DashboardState:
    devices: dict[str, DeviceProject] = dataclasses.field(default_factory=dict)
    updated_at: float = dataclasses.field(default_factory=lambda: time.time())


class DashboardStorage:
    """Per-config-entry storage for device projects."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store[dict[str, Any]](hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")
        self.state = DashboardState()

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if not data:
            return
        devices: dict[str, DeviceProject] = {}
        for d in data.get("devices", []):
            devices[d["device_id"]] = DeviceProject(
                device_id=d["device_id"],
                slug=d["slug"],
                name=d.get("name", d["device_id"]),
                hardware_recipe_id=d.get("hardware_recipe_id"),
                api_key=d.get("api_key"),
                device_settings=d.get("device_settings", {}),
                project=_migrate_project(d.get("project")),
            )
        self.state = DashboardState(devices=devices, updated_at=data.get("updated_at", time.time()))

    async def async_save(self) -> None:
        payload = {
            "updated_at": time.time(),
            "devices": [
                {
                    "device_id": d.device_id,
                    "slug": d.slug,
                    "name": d.name,
                    "hardware_recipe_id": d.hardware_recipe_id,
                    "api_key": d.api_key,
                    "device_settings": d.device_settings,
                    "project": d.project,
                }
                for d in self.state.devices.values()
            ],
        }
        await self._store.async_save(payload)

    def get_device(self, device_id: str) -> DeviceProject | None:
        return self.state.devices.get(device_id)

    def upsert_device(self, device: DeviceProject) -> None:
        self.state.devices[device.device_id] = device

    def delete_device(self, device_id: str) -> bool:
        if device_id in self.state.devices:
            self.state.devices.pop(device_id)
            return True
        return False
