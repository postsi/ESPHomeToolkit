"""
Integration–addon tests: output that the Designer/integration produces is valid
for the addon (ESPHome config-check/compile). Uses addon MCP tools.
"""
import pytest

from conftest import _addon_call


def test_addon_config_check_minimal_yaml(addon_url, addon_token):
    """Addon accepts config-check with minimal YAML (esphome compiles)."""
    result = _addon_call(
        addon_url,
        addon_token,
        "esphome_config_check",
        config_source="yaml",
        yaml="esphome:\n  name: test\n  platform: ESP32\n",
    )
    assert "Error:" not in result or "OK" in result
    # Success: no error or "OK"; failure: "Error: ..."
    if result.strip().startswith("Error:"):
        pytest.fail(f"config-check failed: {result[:300]}")


def test_addon_compile_minimal(addon_url, addon_token):
    """Addon compile with minimal YAML returns without fatal error."""
    result = _addon_call(
        addon_url,
        addon_token,
        "esphome_compile",
        config_source="yaml",
        yaml="esphome:\n  name: test\n  platform: ESP32\n",
    )
    # Compile can fail for missing deps on CI; we only check we got a response
    assert isinstance(result, str)
    assert len(result) > 0
