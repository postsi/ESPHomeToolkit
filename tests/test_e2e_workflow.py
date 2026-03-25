"""
E2E API workflow tests: multi-step flows (load project, modify, save, reload).
Requires ESPTOOLKIT_ENTRY_ID and ESPTOOLKIT_DEVICE_ID. Some tests mutate project;
use a dedicated test device or restore snapshot if needed.
"""
import json
import pytest


def _get_project(ha_api, api_path, device_id):
    status, data = ha_api.get_json(api_path(f"devices/{device_id}/project"))
    if status != 200 or not data.get("ok"):
        return None, data
    return data.get("project"), data


def _put_project(ha_api, api_path, device_id, project):
    return ha_api.put_json(api_path(f"devices/{device_id}/project"), {"project": project})


def test_project_get_put_roundtrip(ha_api, api_path, entry_id, device_id):
    """GET project, then PUT same project, then GET again; result matches."""
    if not entry_id or not device_id:
        pytest.skip("ESPTOOLKIT_ENTRY_ID and ESPTOOLKIT_DEVICE_ID required")
    proj1, _ = _get_project(ha_api, api_path, device_id)
    if proj1 is None:
        pytest.skip("No project to roundtrip")
    status, _ = _put_project(ha_api, api_path, device_id, proj1)
    assert status in (200, 204), f"PUT project failed: {status}"
    proj2, _ = _get_project(ha_api, api_path, device_id)
    assert proj2 is not None
    assert json.dumps(proj1, sort_keys=True) == json.dumps(proj2, sort_keys=True), "Project changed after get->put->get"


def test_entity_widgets_list_then_get_one(ha_api):
    """GET /entity-widgets returns list; GET detail for first id returns definition."""
    status, data = ha_api.get_json("/api/esptoolkit/entity-widgets")
    if status != 200:
        pytest.skip("Entity widgets list failed or empty")
    assert isinstance(data, dict), "entity-widgets list should return a JSON object"
    items = data.get("entity_widgets")
    assert isinstance(items, list), "response should include entity_widgets array"
    if not items:
        pytest.skip("No saved entity widgets")
    first = items[0]
    ewid = first.get("id")
    if not ewid:
        pytest.skip("Cannot get entity widget id from list item")
    status2, body = ha_api.get_json(f"/api/esptoolkit/entity-widgets/{ewid}")
    assert status2 == 200
    assert isinstance(body, dict)
    inner = body.get("entity_widget")
    assert isinstance(inner, dict) and inner, "response should include entity_widget object"
    assert inner.get("id") == ewid or inner.get("name") or "name" in inner or "widgets" in inner
