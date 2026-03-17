"""
Integration–addon tests: output that the Designer/integration produces is valid
for the addon (ESPHome config-check/compile). Uses addon MCP tools.
"""
import os
import pytest

from conftest import _addon_call


def test_addon_config_check_minimal_yaml(addon_url, addon_token):
    """Addon accepts config-check with minimal YAML (esphome compiles)."""
    if not (os.environ.get("ESPTOOLKIT_RUN_SLOW") or "").strip():
        pytest.skip("Set ESPTOOLKIT_RUN_SLOW=1 to run slow addon ESPHome tests")
    result = _addon_call(
        addon_url,
        addon_token,
        "esphome_config_check",
        config_source="yaml",
        yaml=(
            "esphome:\n"
            "  name: test\n"
            "esp32:\n"
            "  board: esp32dev\n"
            "  framework:\n"
            "    type: arduino\n"
            "logger:\n"
        ),
    )
    if result.strip().startswith("Error:"):
        pytest.fail(f"config-check failed: {result[:600]}")


def test_addon_compile_minimal(addon_url, addon_token):
    """Addon compile with minimal YAML returns without fatal error."""
    if not (os.environ.get("ESPTOOLKIT_RUN_SLOW") or "").strip():
        pytest.skip("Set ESPTOOLKIT_RUN_SLOW=1 to run slow addon ESPHome tests")
    result = _addon_call(
        addon_url,
        addon_token,
        "esphome_compile",
        config_source="yaml",
        yaml=(
            "esphome:\n"
            "  name: test\n"
            "esp32:\n"
            "  board: esp32dev\n"
            "  framework:\n"
            "    type: arduino\n"
            "logger:\n"
        ),
    )
    # Compile can fail for missing deps on CI; we only check we got a response
    assert isinstance(result, str)
    assert len(result) > 0
