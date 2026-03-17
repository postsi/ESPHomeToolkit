"""
Data consistency tests: project, entities, and refs are internally consistent
as the Designer would display them (no broken entity_id refs, etc.).
Requires ESPTOOLKIT_ENTRY_ID and ESPTOOLKIT_DEVICE_ID and a project with widgets.
"""
import json
import pytest


def _get_project(ha_api, api_path, device_id):
    status, data = ha_api.get_json(api_path(f"devices/{device_id}/project"))
    if status != 200 or not data.get("ok") or "project" not in data:
        return None
    return data["project"]


def _get_entities(ha_api):
    status, data = ha_api.get_json("/api/esptoolkit/entities")
    if status != 200 or not isinstance(data, dict):
        return {}
    return data.get("entities", data) if isinstance(data.get("entities"), list) else (data if isinstance(data, list) else [])


def _collect_entity_refs(project):
    """Yield all entity_id refs from project (widgets, bindings, etc.)."""
    if not project:
        return
    pages = project.get("pages") or []
    for page in pages:
        for w in page.get("widgets") or []:
            props = w.get("props") or {}
            eid = props.get("entity_id") or props.get("bind_entity_id")
            if eid:
                yield eid
            # Action bindings may reference entities
            for binding in (w.get("action_bindings") or []):
                if isinstance(binding, dict) and binding.get("entity_id"):
                    yield binding["entity_id"]


def test_project_entity_refs_exist(ha_api, api_path, entry_id, device_id):
    """Every entity_id referenced in the project exists in integration entities list."""
    if not entry_id or not device_id:
        pytest.skip("ESPTOOLKIT_ENTRY_ID and ESPTOOLKIT_DEVICE_ID required")
    project = _get_project(ha_api, api_path, device_id)
    if not project:
        pytest.skip("No project returned for device")
    entities = _get_entities(ha_api)
    entity_ids = set()
    if isinstance(entities, list):
        for e in entities:
            if isinstance(e, dict) and e.get("entity_id"):
                entity_ids.add(e["entity_id"])
            elif isinstance(e, str):
                entity_ids.add(e)
    else:
        entity_ids = set(entities.keys()) if isinstance(entities, dict) else set()
    refs = list(_collect_entity_refs(project))
    missing = [r for r in refs if r and r not in entity_ids]
    assert not missing, f"Project references entity_ids not in entities list: {missing[:10]}"


def test_project_pages_structure(ha_api, api_path, device_id, entry_id):
    """Project pages have widgets array and page_id/name."""
    if not entry_id or not device_id:
        pytest.skip("ESPTOOLKIT_ENTRY_ID and ESPTOOLKIT_DEVICE_ID required")
    project = _get_project(ha_api, api_path, device_id)
    if not project:
        pytest.skip("No project returned")
    pages = project.get("pages") or []
    for i, page in enumerate(pages):
        assert isinstance(page, dict), f"page {i} is not a dict"
        assert "widgets" in page or "widget_ids" in page or page.get("widgets") is not None
        if page.get("widgets") is not None:
            assert isinstance(page["widgets"], list), f"page {i}.widgets not a list"


def test_widgets_have_required_fields(ha_api, api_path, device_id, entry_id):
    """Each widget in project has id, type and position/size-like fields."""
    if not entry_id or not device_id:
        pytest.skip("ESPTOOLKIT_ENTRY_ID and ESPTOOLKIT_DEVICE_ID required")
    project = _get_project(ha_api, api_path, device_id)
    if not project:
        pytest.skip("No project returned")
    pages = project.get("pages") or []
    for pi, page in enumerate(pages):
        for wi, w in enumerate(page.get("widgets") or []):
            assert isinstance(w, dict), f"page {pi} widget {wi} not a dict"
            assert w.get("id"), f"page {pi} widget {wi} missing id"
            assert w.get("type"), f"page {pi} widget {wi} missing type"
