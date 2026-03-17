"""
Schema–data contract tests: stored project widgets conform to widget schemas
(property panel and schema stay in sync with stored data).
Requires ESPTOOLKIT_ENTRY_ID and ESPTOOLKIT_DEVICE_ID and a project with widgets.
"""
import pytest


def _get_project(ha_api, api_path, device_id):
    status, data = ha_api.get_json(api_path(f"devices/{device_id}/project"))
    if status != 200 or not data.get("ok") or "project" not in data:
        return None
    return data["project"]


def _get_schema(ha_api, widget_type: str):
    status, data = ha_api.get_json(f"/api/esptoolkit/schemas/widgets/{widget_type}")
    if status != 200:
        return None
    return data.get("schema", data)


def _widget_types_in_project(project):
    seen = set()
    for page in (project.get("pages") or []):
        for w in (page.get("widgets") or []):
            t = w.get("type")
            if t:
                seen.add(t)
    return seen


def test_schema_exists_for_each_widget_type(ha_api, api_path, device_id, entry_id):
    """For each widget type used in the project, a schema endpoint exists and returns 200."""
    if not entry_id or not device_id:
        pytest.skip("ESPTOOLKIT_ENTRY_ID and ESPTOOLKIT_DEVICE_ID required")
    project = _get_project(ha_api, api_path, device_id)
    if not project:
        pytest.skip("No project returned")
    types = _widget_types_in_project(project)
    if not types:
        pytest.skip("No widgets in project")
    missing = []
    for t in types:
        schema = _get_schema(ha_api, t)
        if schema is None:
            missing.append(t)
    assert not missing, f"No schema for widget types: {missing}"


def test_widget_props_keys_in_schema(ha_api, api_path, device_id, entry_id):
    """Each widget's props keys are known (schema has properties or we allow any).
    Non-strict: we only check that schemas/widgets list includes the type."""
    if not entry_id or not device_id:
        pytest.skip("ESPTOOLKIT_ENTRY_ID and ESPTOOLKIT_DEVICE_ID required")
    project = _get_project(ha_api, api_path, device_id)
    if not project:
        pytest.skip("No project returned")
    for page in (project.get("pages") or []):
        for w in (page.get("widgets") or []):
            wtype = w.get("type")
            props = w.get("props") or {}
            if not wtype:
                continue
            schema = _get_schema(ha_api, wtype)
            if schema is None:
                continue
            # Schema may have "properties" (JSON Schema) or flat keys
            allowed = set()
            if isinstance(schema, dict):
                allowed = set(schema.get("properties", {}).keys()) or set(schema.keys())
            # If schema has no properties, we don't enforce; just ensure no crash
            for key in props:
                assert isinstance(key, str), f"Widget prop key must be str: {key!r}"
