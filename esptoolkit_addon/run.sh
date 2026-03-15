#!/bin/sh
set -e

# Match official ESPHome add-on: PlatformIO platforms/packages/cache under /data so tool-cmake
# and platforms resolve to the same paths (avoids FileNotFoundError for tool-cmake in packages/).
readonly pio_cache_base=/data/cache/platformio
export PLATFORMIO_GLOBALLIB_DIR=/piolibs
export PLATFORMIO_PLATFORMS_DIR="${pio_cache_base}/platforms"
export PLATFORMIO_PACKAGES_DIR="${pio_cache_base}/packages"
export PLATFORMIO_CACHE_DIR="${pio_cache_base}/cache"
mkdir -p "${pio_cache_base}"

echo "[ESPToolkit] Starting (see app for version)..." >&2
# Install or update bundled custom integration into /config/custom_components (restarts HA if updated)
echo "[ESPToolkit] Running integration install/update..." >&2
python3 -c "from app.install_integration import install_or_update; install_or_update()" || true
echo "[ESPToolkit] Integration install/update complete." >&2
# ESPHome is installed from source at /esphome (like the official add-on); do not overwrite with PyPI.

cd /app
exec python3 -m app.main
