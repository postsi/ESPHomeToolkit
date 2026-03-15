#!/usr/bin/env bash
# Build the ESPHome/add-on base image once; then use deploy-local.sh --fast for quick deploys.
# Run this when the base changes (e.g. BUILD_BASE_VERSION or ESPHome ref in the main Dockerfile).
#
# Usage: ./scripts/build-base.sh [BASE_TAG]
# Example: ./scripts/build-base.sh 2025.04.0
# If omitted, BASE_TAG is read from esptoolkit_addon/docker/Dockerfile (BUILD_BASE_VERSION).
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

ADDON="$REPO_ROOT/esptoolkit_addon"
DOCKERFILE="$ADDON/docker/Dockerfile"

if [ -n "${1:-}" ]; then
  BASE_TAG="$1"
else
  BASE_TAG=$(grep 'ARG BUILD_BASE_VERSION=' "$DOCKERFILE" | head -1 | sed 's/.*=//' | tr -d ' ')
  [ -z "$BASE_TAG" ] && { echo "Could not read BUILD_BASE_VERSION from $DOCKERFILE"; exit 1; }
fi

echo "=== Building base image (target: final) — this can take a long time ==="
docker build \
  -f "$DOCKERFILE" \
  --target final \
  -t "esptoolkit-base:${BASE_TAG}" \
  -t "esptoolkit-base:latest" \
  "$ADDON"

echo "=== Done. Tagged esptoolkit-base:${BASE_TAG} and esptoolkit-base:latest ==="
echo "Use: ./scripts/deploy-local.sh --fast <version> \"<message>\" for quick deploys."
