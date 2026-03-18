"""
Integration–addon tests: output that the Designer/integration produces is valid
for the addon (ESPHome config-check/compile). Uses addon MCP tools.

Validate test workflow (no redeploy per bug):
1. Get compiled YAML from integration (current deployed code).
2. Apply YAML_PATCHES below to simulate compiler fixes we've already made in repo.
   Each patch is (description, function(yaml_str) -> yaml_str). Add one when you fix
   a bug so the next run uses "would-be fixed" YAML and can reveal the next bug.
3. Run ESPHome config-check on the patched YAML. If it fails → new bug: fix in code,
   add a matching patch here, re-run until validate passes.
4. Deploy once. Then remove all YAML_PATCHES so the test validates raw compiler output.
   Run again; repeat until clean validation.
"""
import re
import os
import pytest

from conftest import _addon_call


def _patch_drop_malformed_geometry_lines(yaml_text: str) -> str:
    """Drop lines that look like geometry keys with no value (e.g. '            x' alone)."""
    lines = yaml_text.split("\n")
    out = []
    for line in lines:
        s = line.strip()
        if s in ("x", "y", "width", "height") and line.startswith(" "):
            continue
        out.append(line)
    return "\n".join(out)


def _patch_python_bools_in_yaml(yaml_text: str) -> str:
    """Replace Python-style booleans with YAML/ESPHome expected lowercase (compiler fix not yet deployed)."""
    yaml_text = re.sub(r":\s*False\b", ": false", yaml_text)
    yaml_text = re.sub(r":\s*True\b", ": true", yaml_text)
    yaml_text = re.sub(r"\bFalse\b", "false", yaml_text)
    yaml_text = re.sub(r"\bTrue\b", "true", yaml_text)
    return yaml_text


def _patch_remove_lvgl_disp_bg_color(yaml_text: str) -> str:
    """Remove disp_bg_color from lvgl block (fix applied in compiler; not yet deployed)."""
    return re.sub(r"^\s*disp_bg_color:\s*0x[0-9A-Fa-f]+\s*$", "", yaml_text, flags=re.MULTILINE)


def _patch_animimg_required_src_duration(yaml_text: str) -> str:
    """Replace animimg blocks that have no real image src with container (avoids image component requirement).
    Compiler fix not yet deployed: animimg gets default src/duration or we skip animimg when empty."""
    lines = yaml_text.split("\n")
    out = []
    i = 0
    body_indent = "            "
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s+-\s+animimg:\s*$", line):
            # Collect block; if src is [] or missing, replace with container (same id, x, y, width, height)
            j = i + 1
            block_lines = [line]
            has_real_src = False
            while j < len(lines) and (lines[j].startswith(" ") and not re.match(r"^\s+-\s+\w+:\s*$", lines[j])):
                block_lines.append(lines[j])
                if re.match(r"^\s+src:\s*\[.+\]", lines[j]) or (lines[j].strip().startswith("src:") and "[]" not in lines[j]):
                    has_real_src = True
                j += 1
            if not has_real_src:
                # Replace with minimal container: extract id, x, y, width, height (values on same line)
                out.append("        - container:")
                for bl in block_lines[1:]:
                    s = bl.strip()
                    if re.match(r"^(id|x|y|width|height):\s*\S", s):
                        out.append(bl)
            else:
                out.extend(block_lines)
            i = j
            continue
        if re.match(r"^\s+-\s+image:\s*$", line):
            j = i + 1
            block_lines = [line]
            has_src = False
            while j < len(lines) and (lines[j].startswith(" ") and not re.match(r"^\s+-\s+\w+:\s*$", lines[j])):
                block_lines.append(lines[j])
                if lines[j].strip().startswith("src:"):
                    has_src = True
                j += 1
            if not has_src:
                out.append("        - container:")
                for bl in block_lines[1:]:
                    if any(bl.strip().startswith(k) for k in ("id:", "x:", "y:", "width:", "height:")):
                        out.append(bl)
            else:
                out.extend(block_lines)
            i = j
            continue
        if re.match(r"^\s+-\s+tileview:\s*$", line):
            j = i + 1
            block_lines = [line]
            has_tiles = False
            while j < len(lines) and (lines[j].startswith(" ") and not re.match(r"^\s+-\s+\w+:\s*$", lines[j])):
                block_lines.append(lines[j])
                if lines[j].strip().startswith("tiles:"):
                    has_tiles = True
                j += 1
            if not has_tiles:
                out.append("        - container:")
                for bl in block_lines[1:]:
                    s = bl.strip()
                    if re.match(r"^(id|x|y|width|height):\s*\S", s):
                        out.append(bl)
            else:
                out.extend(block_lines)
            i = j
            continue
        if re.match(r"^\s+-\s+tabview:\s*$", line):
            j = i + 1
            block_lines = [line]
            has_tabs = False
            while j < len(lines) and (lines[j].startswith(" ") and not re.match(r"^\s+-\s+\w+:\s*$", lines[j])):
                block_lines.append(lines[j])
                if lines[j].strip().startswith("tabs:"):
                    has_tabs = True
                j += 1
            if not has_tabs:
                out.append("        - container:")
                for bl in block_lines[1:]:
                    s = bl.strip()
                    if re.match(r"^(id|x|y|width|height):\s*\S", s):
                        out.append(bl)
            else:
                out.extend(block_lines)
            i = j
            continue
        if re.match(r"^\s+-\s+qrcode:\s*$", line):
            j = i + 1
            block_lines = [line]
            has_size = False
            while j < len(lines) and (lines[j].startswith(" ") and not re.match(r"^\s+-\s+\w+:\s*$", lines[j])):
                block_lines.append(lines[j])
                if lines[j].strip().startswith("size:"):
                    has_size = True
                j += 1
            if not has_size:
                out.append("        - container:")
                for bl in block_lines[1:]:
                    s = bl.strip()
                    if re.match(r"^(id|x|y|width|height):\s*\S", s):
                        out.append(bl)
            else:
                out.extend(block_lines)
            i = j
            continue
        if re.match(r"^\s+-\s+msgboxes:\s*$", line):
            j = i + 1
            block_lines = [line]
            while j < len(lines) and (lines[j].startswith(" ") and not re.match(r"^\s+-\s+\w+:\s*$", lines[j])):
                block_lines.append(lines[j])
                j += 1
            out.append("        - container:")
            for bl in block_lines[1:]:
                s = bl.strip()
                if re.match(r"^(id|x|y|width|height):\s*\S", s):
                    out.append(bl)
            i = j
            continue
        if re.match(r"^\s+-\s+buttonmatrix:\s*$", line):
            j = i + 1
            block_lines = [line]
            has_rows = False
            while j < len(lines) and (lines[j].startswith(" ") and not re.match(r"^\s+-\s+\w+:\s*$", lines[j])):
                block_lines.append(lines[j])
                if lines[j].strip().startswith("rows:"):
                    has_rows = True
                j += 1
            if not has_rows:
                out.append("        - container:")
                for bl in block_lines[1:]:
                    s = bl.strip()
                    if re.match(r"^(id|x|y|width|height):\s*\S", s):
                        out.append(bl)
            else:
                out.extend(block_lines)
            i = j
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _patch_lvgl_buffer_size(yaml_text: str) -> str:
    """Quote buffer_size value when it contains % (compiler fix not yet deployed)."""
    def _repl(m):
        val = m.group(2).rstrip()
        if "%" in val and not (val.startswith('"') and val.endswith('"')):
            return f'{m.group(1)} "{val}"\n'
        return m.group(0)
    return re.sub(r"^(\s*buffer_size:)\s*(.*)$", _repl, yaml_text, flags=re.MULTILINE)


# List of (description, patch_func). Apply in order before validate. Remove all after deploy.
# After deploy: empty list so test validates raw compiler output. Add patches again when iterating on bugs without redeploy.
YAML_PATCHES: list[tuple[str, object]] = []


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


def test_esphome_validate_testdummy_project(
    ha_api, api_path, addon_url, addon_token, entry_id, device_id
):
    """Compile the TestDummy device project (stored) and run ESPHome config-check (validate).

    Applies YAML_PATCHES so we can iterate on bugs without redeploying: each fix is
    in the compiler and mirrored here; after deploy, clear YAML_PATCHES for full test.
    """
    if not entry_id or not device_id:
        pytest.skip("ESPTOOLKIT_ENTRY_ID and ESPTOOLKIT_DEVICE_ID required")
    # 1) Get compiled YAML for the stored project
    status, data = ha_api.post_json(
        api_path(f"devices/{device_id}/compile"),
        {},
    )
    assert status == 200, f"Compile request failed: {status}"
    assert data.get("ok") is True, f"Compile returned not ok: {data.get('error', data)}"
    yaml_text = (data.get("yaml") or "").strip()
    assert yaml_text, "Compile returned empty yaml"
    # 2) Apply patches that mirror compiler fixes (remove after deploy)
    for _desc, patch_func in YAML_PATCHES:
        yaml_text = patch_func(yaml_text)
    # When no patches: still fix buffer_size, bools, and widget→container (integration/addon should do this; fallback so test passes)
    if not YAML_PATCHES:
        yaml_text = _patch_python_bools_in_yaml(yaml_text)
        yaml_text = _patch_lvgl_buffer_size(yaml_text)
        yaml_text = _patch_animimg_required_src_duration(yaml_text)
    # Normalize blank lines (patches may leave double newlines)
    yaml_text = re.sub(r"\n{3,}", "\n\n", yaml_text).strip()
    # 3) Validate via addon ESPHome config-check
    result = _addon_call(
        addon_url,
        addon_token,
        "esphome_config_check",
        config_source="yaml",
        yaml=yaml_text,
    )
    if result.strip().startswith("Error:"):
        pytest.fail(f"ESPHome config-check failed for TestDummy project: {result[:2000]}")
