#!/usr/bin/env python3
"""Patch pioarduino platform penv_setup.py so platformio is satisfied by pioarduino_core."""
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
# When checking what to install, treat "platformio" as satisfied if "pioarduino_core" is installed
# (pioarduino fork installs as pioarduino-core; uv reports it as pioarduino_core)
old = "    for package, spec in deps.items():\n        name = package.lower()\n        if name not in installed_packages:"
new = """    for package, spec in deps.items():
        name = package.lower()
        if name == "platformio" and "pioarduino_core" in installed_packages:
            continue
        if name not in installed_packages:"""
if old not in text:
    sys.exit(f"Pattern not found in {path}")
path.write_text(text.replace(old, new, 1))
print(f"Patched {path}")
