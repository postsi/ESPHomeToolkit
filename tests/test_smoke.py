"""
Smoke tests: addon and HA are reachable and respond.
Run first; failures mean the test environment (ADDON_URL, ADDON_TOKEN, HA) is not ready.
"""
import json
import pytest

from conftest import _addon_call


def test_addon_mcp_reachable(addon_url, addon_token):
    """Addon MCP endpoint accepts requests (auth works)."""
    result = _addon_call(addon_url, addon_token, "esphome_version")
    assert "ESPHome" in result or "Add-on" in result


def test_ha_core_reachable_via_proxy(ha_api):
    """HA Core API is reachable via addon local_http proxy."""
    status, body = ha_api.get("/api/config")
    assert status == 200
    assert body
    data = json.loads(body)
    assert "components" in data or "config_dir" in data or "latitude" in data or "location_name" in data


def test_ha_states_endpoint(ha_api):
    """HA /api/states returns list of entities."""
    status, body = ha_api.get("/api/states")
    assert status == 200
    # local_http tool truncates long bodies; don't JSON-parse here.
    assert body.lstrip().startswith("["), "Expected JSON array"
    assert "\"entity_id\"" in body


def test_esptoolkit_integration_context(ha_api):
    """EspToolkit integration context endpoint returns entry_id or error (integration installed)."""
    status, data = ha_api.get_json("/api/esptoolkit/context")
    # May be 200 with entry_id, or 4xx if no config entry
    assert status in (200, 401, 404, 500)
    if status == 200:
        assert "entry_id" in data or "ok" in data
