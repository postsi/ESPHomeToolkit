#!/usr/bin/env bash
# Run tests inside the built add-on Docker image (same image we deploy).
# Catches import/dependency bugs before deployment.
# First run: ~3–5 min (build). Later runs: ~30–60 s (cached build + tests).
# Run from repo root: ./esptoolkit_addon/scripts/test_in_docker.sh
set -e

ADDON_DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-esptoolkit-addon-test}"
IMAGE_TEST="${IMAGE_NAME}-pytest"
BUILD_FROM="${BUILD_FROM:-ghcr.io/esphome/docker-base:debian-ha-addon-2025.04.0}"

echo ""
echo "=============================================="
echo "  ESPToolkit add-on — test in Docker"
echo "  (First run: ~3–5 min. Later: ~30–60 s)"
echo "=============================================="
echo ""

echo "[1/4] Building production image... (Docker output below)"
docker build \
  --progress=plain \
  --build-arg BUILD_FROM="$BUILD_FROM" \
  --build-arg BUILD_ARCH=amd64 \
  -t "$IMAGE_NAME" \
  "$ADDON_DIR"
echo "[1/4] Done."
echo ""

echo "[2/4] Smoke test: importing app and printing version..."
docker run --rm --entrypoint python3 "$IMAGE_NAME" -c "
from app.main import app
print('[ESPToolkit] version', app.version)
print('Smoke OK')
"
echo "[2/4] Done."
echo ""

echo "[3/4] Building test image (production + pytest)... (Docker output below)"
docker build \
  --progress=plain \
  --target test \
  --build-arg BUILD_FROM="$BUILD_FROM" \
  --build-arg BUILD_ARCH=amd64 \
  -t "$IMAGE_TEST" \
  "$ADDON_DIR"
echo "[3/4] Done."
echo ""

echo "[4/4] Running pytest inside container (if tests exist)..."
if [ -d "$ADDON_DIR/tests" ]; then
  docker run --rm \
    --entrypoint python3 \
    -v "$ADDON_DIR/tests:/tests:ro" \
    -e PYTHONPATH=/app \
    "$IMAGE_TEST" \
    -m pytest /tests -v --tb=short
else
  echo "No tests/ dir; skipping pytest."
fi
echo "[4/4] Done."
echo ""

echo "=============================================="
echo "  All checks passed."
echo "=============================================="
echo ""
