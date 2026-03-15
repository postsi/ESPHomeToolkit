#!/usr/bin/env bash
# Deploy ESPHomeToolkit add-on by building the container the same way as the original add-on:
#   docker build -f addon/docker/Dockerfile addon
# then tag, push to ghcr.io, and push code to git.
# Prereqs: docker. For push: docker login ghcr.io (or set GITHUB_TOKEN and we log in).
#
# Usage: ./scripts/deploy-local.sh [--fast] <version> [message]
#   --fast  Use pre-built esptoolkit-base (build it once with ./scripts/build-base.sh).
# Example: ./scripts/deploy-local.sh 1.0.1 "Release"
# Example: ./scripts/deploy-local.sh --fast 1.0.2 "Quick fix"
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

USE_FAST=false
if [ "${1:-}" = "--fast" ]; then
  USE_FAST=true
  shift
fi

VERSION="${1:?Usage: $0 [--fast] <version> [message]}"
MSG="${2:-release}"

ADDON="$REPO_ROOT/esptoolkit_addon"
CONFIG="$ADDON/config.yaml"
INIT="$ADDON/app/__init__.py"
MANIFEST="$REPO_ROOT/custom_components/esptoolkit/manifest.json"
DOCKERFILE_FULL="$ADDON/docker/Dockerfile"
DOCKERFILE_FAST="$ADDON/docker/Dockerfile.fast"

DOCKER_HUB="ghcr.io/postsi"
# Map host arch to add-on image name (config.yaml has image: "ghcr.io/postsi/esptoolkit-addon-{arch}")
case "$(uname -m)" in
  x86_64|amd64)  ARCH="amd64" ;;
  aarch64|arm64) ARCH="aarch64" ;;
  *)             ARCH="$(uname -m)" ;;
esac
IMAGE_NAME="${DOCKER_HUB}/esptoolkit-addon-${ARCH}"

echo "=== Bumping version to $VERSION ==="
sed -i.bak "s/^version: .*/version: \"$VERSION\"/" "$CONFIG" && rm -f "$CONFIG.bak"
sed -i.bak "s/^__version__ = .*/__version__ = \"$VERSION\"/" "$INIT" && rm -f "$INIT.bak"
if [ -f "$MANIFEST" ]; then
  python3 -c "
import json, sys
p = sys.argv[1]
with open(p) as f: d = json.load(f)
d['version'] = sys.argv[2]
with open(p, 'w') as f: json.dump(d, f, indent=2)
print('Updated', p, 'to version', sys.argv[2])
" "$MANIFEST" "$VERSION"
fi

if [ "$USE_FAST" = true ]; then
  BASE_TAG=$(grep 'ARG BUILD_BASE_VERSION=' "$DOCKERFILE_FULL" | head -1 | sed 's/.*=//' | tr -d ' ')
  if ! docker image inspect "esptoolkit-base:${BASE_TAG}" >/dev/null 2>&1; then
    echo "=== Base image esptoolkit-base:${BASE_TAG} not found. Run: ./scripts/build-base.sh ==="
    exit 1
  fi
  echo "=== Building production image (fast: FROM esptoolkit-base) ==="
  docker build \
    -f "$DOCKERFILE_FAST" \
    --build-arg BUILD_VERSION="$VERSION" \
    --build-arg BASE_TAG="$BASE_TAG" \
    -t "${IMAGE_NAME}:${VERSION}" \
    -t "${IMAGE_NAME}:latest" \
    "$ADDON"
  echo "=== Quick smoke test ==="
  docker run --rm --entrypoint python3 "${IMAGE_NAME}:${VERSION}" -c "
from app.main import app
print('version', app.version)
print('Smoke OK')
"
else
  echo "=== Running tests locally (Docker) ==="
  docker build \
    -f "$DOCKERFILE_FULL" \
    --target test \
    -t esptoolkit-addon-test \
    "$ADDON"
  docker run --rm --entrypoint python3 esptoolkit-addon-test -c "
from app.main import app
print('version', app.version)
print('Smoke OK')
"
  if [ -d "$ADDON/tests" ]; then
    docker run --rm \
      --entrypoint python3 \
      -v "$ADDON/tests:/tests:ro" \
      -e PYTHONPATH=/app \
      esptoolkit-addon-test \
      -m pytest /tests -v --tb=short
  else
    echo "No tests dir in addon; skipping pytest."
  fi

  echo "=== Building production image (full: from ESPHome base) ==="
  docker build \
    -f "$DOCKERFILE_FULL" \
    --build-arg BUILD_VERSION="$VERSION" \
    -t "${IMAGE_NAME}:${VERSION}" \
    -t "${IMAGE_NAME}:latest" \
    "$ADDON"
fi

echo "=== Pushing to ghcr.io ==="
if [ -n "${GITHUB_TOKEN:-}" ] || [ -f "$REPO_ROOT/.github-token" ]; then
  [ -z "${GITHUB_TOKEN:-}" ] && GITHUB_TOKEN="$(head -1 "$REPO_ROOT/.github-token" 2>/dev/null | tr -d '\r\n')"
  echo "$GITHUB_TOKEN" | docker login ghcr.io -u "${GITHUB_USER:-postsi}" --password-stdin 2>/dev/null || true
fi
docker push "${IMAGE_NAME}:${VERSION}"
docker push "${IMAGE_NAME}:latest" 2>/dev/null || true

echo "=== Staging and committing (with [skip build] so CI skips build job) ==="
git rm -r --cached esptoolkit_addon/esphome 2>/dev/null || true
git rm -r -f --cached esphome-ref 2>/dev/null || true
git add -A
git status -s
git commit -m "Release v$VERSION: $MSG [skip build]"

echo "=== Pushing to origin main ==="
git push origin main

echo "=== Done. Image ${IMAGE_NAME}:${VERSION} pushed (arch: ${ARCH}). Home Assistant can pick up v$VERSION from the repo. ==="
