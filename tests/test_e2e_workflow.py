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


def test_cards_list_then_get_one(ha_api):
    """GET /cards returns list; GET /cards/{id} for first id returns card object."""
    status, data = ha_api.get_json("/api/esptoolkit/cards")
    if status != 200:
        pytest.skip("Cards list failed or empty")
    cards = data if isinstance(data, list) else data.get("cards", data.get("items", []))
    if not cards:
        pytest.skip("No cards")
    first = cards[0]
    card_id = first.get("id") or first.get("card_id") or (first if isinstance(first, str) else None)
    if not card_id:
        pytest.skip("Cannot get card id from list item")
    status2, card = ha_api.get_json(f"/api/esptoolkit/cards/{card_id}")
    assert status2 == 200
    assert isinstance(card, dict)
    assert card.get("id") == card_id or card.get("name") or "name" in card or "widgets" in card
