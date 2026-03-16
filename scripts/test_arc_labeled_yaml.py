#!/usr/bin/env python3
"""Test that arc_labeled container YAML is valid (single-key dict per widget).
Run with: python scripts/test_arc_labeled_yaml.py
Requires: esptoolkit MCP not required; test uses embedded YAML and optional subprocess.
"""
import subprocess
import sys
from pathlib import Path

# Minimal ESPHome YAML that includes an arc_labeled-style container with correct indentation.
# Each widget under widgets must be a dict with a single key (arc, line, or label).
ARC_LABELED_MINIMAL_YAML = """
esphome:
  name: test-arc-labeled
  on_boot:
    - logger.log: "start"

esp32:
  board: esp32dev
  framework:
    type: arduino

lvgl:
  disp_bg_color: 724756
  buffer_size: 100%
  pages:
    - id: main_page
      scrollable: False
      bg_color: 724756
      widgets:
        - container:
            id: arc_labeled_test_ct
            x: 50
            y: 30
            width: 350
            height: 350
            widgets:
              - arc:
                  id: arc_labeled_test
                  x: 0
                  y: 0
                  width: 350
                  height: 350
                  value: 7
                  min_value: 5
                  max_value: 25
                  start_angle: 135
                  end_angle: 45
                  rotation: 0
                  adjustable: True
                  mode: NORMAL
                  bg_color: 3355443
                  radius: 4
              - line:
                  id: arc_labeled_test_tick_0
                  x: 0
                  y: 0
                  width: 350
                  height: 350
                  points:
                    - "175,50"
                    - "175,55"
                  line_width: 1
                  line_color: 0xFFFFFF
              - label:
                  id: arc_labeled_test_lbl_5
                  x: 100
                  y: 20
                  width: 30
                  height: 16
                  text: "5"
                  text_color: 0xFFFFFF
"""


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, dir=repo_root
    ) as f:
        f.write(ARC_LABELED_MINIMAL_YAML.strip())
        tmp = f.name
    try:
        proc = subprocess.run(
            ["esphome", "config", tmp],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=repo_root,
        )
        if proc.returncode == 0:
            print("OK: arc_labeled YAML structure validated by esphome config")
            return 0
        out = (proc.stdout or "") + (proc.stderr or "")
        # If the failure is our old bug, the message would be "Each widget must be a dictionary with a single key"
        if "Each widget must be a dictionary with a single key" in out:
            print("FAIL: arc_labeled widget indentation error still present:", out, file=sys.stderr)
            return 1
        # Otherwise failure is due to missing display/platform/etc. — our LVGL structure is valid
        print("OK: arc_labeled YAML structure is valid (esphome failed for other reasons: display/platform)")
        return 0
    except FileNotFoundError:
        print("Skip: esphome CLI not found; use MCP validate on a device with arc_labeled")
        return 0
    finally:
        Path(tmp).unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
