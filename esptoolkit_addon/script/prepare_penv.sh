#!/bin/sh
# Pre-create PlatformIO penv and install python_deps so first compile does not fail.
# Must run after platformio_install_deps.py, with PLATFORMIO_CORE_DIR set.
set -e
PIO="$PLATFORMIO_CORE_DIR"
PENV="$PIO/penv"
PYTHON="${PYTHONEXE:-/usr/bin/python3}"

# Same deps as pioarduino platform espressif32/builder/penv_setup.py (python_deps)
# Use URL only for platformio (pioarduino fork installs as pioarduino-core)
# --index-strategy unsafe-best-match for Alpine/musl (pyyaml wheels)
uv venv --clear --python="$PYTHON" "$PENV"
uv pip install "uv>=0.1.0" --python="$PENV/bin/python"
"$PENV/bin/uv" pip install --python="$PENV/bin/python" --index-strategy unsafe-best-match \
  "https://github.com/pioarduino/platformio-core/archive/refs/tags/v6.1.19.zip" \
  "littlefs-python>=0.16.0" "fatfs-ng>=0.1.14" "pyyaml>=6.0.2" "rich-click>=1.8.6" \
  "zopfli>=0.2.2" "intelhex>=2.3.0" "rich>=14.0.0" "urllib3<2" "cryptography>=45.0.3" \
  "certifi>=2025.8.3" "ecdsa>=0.19.1" "bitstring>=4.3.1" "reedsolo>=1.5.3,<1.8" \
  "esp-idf-size>=2.0.0" "esp-coredump>=1.14.0"
echo "penv ready at $PENV"
