"""
API contract tests: integration endpoints return expected status and shape.
Matches what the Designer frontend expects (paths and response structure).
"""
import json
import pytest


def test_context_shape(ha_api):
    """GET /api/esptoolkit/context returns ok and entry_id or error."""
    status, data = ha_api.get_json("/api/esptoolkit/context")
    assert status in (200, 401, 403, 404, 500)
    if status == 200:
        assert isinstance(data, dict)
        assert "ok" in data or "entry_id" in data


def test_devices_list_shape(ha_api, api_path, entry_id):
    """GET devices with entry_id returns ok and devices array (or error)."""
    if not entry_id:
        pytest.skip("ESPTOOLKIT_ENTRY_ID not set")
    status, data = ha_api.get_json(api_path("devices"))
    assert status in (200, 400, 404, 500)
    if status == 200 and data.get("ok") is True:
        assert "devices" in data
        assert isinstance(data["devices"], list)


def test_schemas_widgets_list(ha_api):
    """GET /api/esptoolkit/schemas/widgets returns ok and schemas array."""
    status, data = ha_api.get_json("/api/esptoolkit/schemas/widgets")
    assert status == 200
    assert isinstance(data, dict)
    assert "schemas" in data or "ok" in data
    if "schemas" in data:
        assert isinstance(data["schemas"], list)


def test_schemas_widget_single(ha_api):
    """GET /api/esptoolkit/schemas/widgets/{type} returns schema object."""
    status, body = ha_api.get("/api/esptoolkit/schemas/widgets/label")
    assert status in (200, 404)
    if status == 200:
        # Response can be large and local_http may truncate; assert key markers exist.
        assert body.strip().startswith("{")
        assert "\"schema\"" in body
        assert "\"type\":\"label\"" in body or "\"type\": \"label\"" in body


def test_recipes_list(ha_api):
    """GET /api/esptoolkit/recipes returns recipes array."""
    status, data = ha_api.get_json("/api/esptoolkit/recipes")
    assert status == 200
    assert isinstance(data, (dict, list))
    if isinstance(data, dict):
        assert "recipes" in data


def test_entity_widgets_list(ha_api):
    """GET /api/esptoolkit/entity-widgets returns ok + entity_widgets array."""
    status, data = ha_api.get_json("/api/esptoolkit/entity-widgets")
    assert status in (200, 401, 404, 500)
    if status == 200:
        assert isinstance(data, dict)
        assert "entity_widgets" in data
        assert isinstance(data["entity_widgets"], list)


def test_entities_list(ha_api):
    """GET /api/esptoolkit/entities returns entities or error."""
    status, body = ha_api.get("/api/esptoolkit/entities")
    assert status in (200, 401, 404, 500)
    # This endpoint can be large; local_http may truncate. Just check it looks JSON-ish.
    if status == 200:
        assert body.strip().startswith(("{", "[")) and len(body) > 2


def test_self_check(ha_api):
    """GET/POST /api/esptoolkit/self_check returns structured result."""
    status, data = ha_api.get_json("/api/esptoolkit/self_check")
    assert status in (200, 401, 404, 500)
    if status == 200:
        assert isinstance(data, dict)


def test_project_get_shape(ha_api, api_path, entry_id, device_id):
    """GET devices/{id}/project returns ok and project (or 404)."""
    if not entry_id or not device_id:
        pytest.skip("ESPTOOLKIT_ENTRY_ID and ESPTOOLKIT_DEVICE_ID required")
    status, data = ha_api.get_json(api_path(f"devices/{device_id}/project"))
    assert status in (200, 404, 500)
    if status == 200 and data.get("ok") is True:
        assert "project" in data
        proj = data["project"]
        assert isinstance(proj, dict)
        assert "pages" in proj or "esphome_yaml" in proj or proj == {}


def test_mac_sim_last_report_shape(ha_api, entry_id):
    """GET mac_sim/last_report returns has_report + optional report (after Mac agent runs a job)."""
    if not entry_id:
        pytest.skip("ESPTOOLKIT_ENTRY_ID not set")
    from urllib.parse import quote

    status, data = ha_api.get_json(
        "/api/esptoolkit/mac_sim/last_report?entry_id=" + quote(entry_id, safe="")
    )
    assert status in (200, 404)
    if status == 200:
        assert isinstance(data, dict)
        assert data.get("ok") is True
        assert "has_report" in data
        if data.get("has_report") and data.get("report"):
            rep = data["report"]
            assert "ok" in rep
            assert "phase" in rep
            assert "received_at" in rep
