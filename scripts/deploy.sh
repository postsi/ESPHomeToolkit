#!/usr/bin/env bash
# Deploy ESPHomeToolkit: bump version, commit, push, then wait for GitHub build.
# For local build then push (faster): ./scripts/deploy-local.sh <version> [message]
# Usage: ./scripts/deploy.sh <version> [commit message suffix] [--no-wait]
# Example: ./scripts/deploy.sh 1.0.1 "Initial release"
#          ./scripts/deploy.sh 1.0.2 "Fix panel path" --no-wait
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

NO_WAIT=""
ARGS=()
for a in "$@"; do
  if [[ "$a" == "--no-wait" ]]; then NO_WAIT=1; else ARGS+=("$a"); fi
done

VERSION="${ARGS[0]:?Usage: $0 <version> [message] [--no-wait]}"
MSG="${ARGS[1]:-release}"

ADDON="$REPO_ROOT/esptoolkit_addon"
CONFIG="$ADDON/config.yaml"
INIT="$ADDON/app/__init__.py"
MANIFEST="$REPO_ROOT/custom_components/esptoolkit/manifest.json"

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

echo "=== Staging and committing ==="
git add -A
git status -s
git commit -m "Release v$VERSION: $MSG"

echo "=== Pushing to origin main ==="
git push origin main

if [[ -n "$NO_WAIT" ]]; then
  echo "=== Done (skipped wait). GitHub Actions will run (test then build). ==="
  exit 0
fi

echo "=== Waiting for GitHub Actions build to complete (poll every 10s) ==="
exec "$REPO_ROOT/scripts/wait-for-build.sh" "$(git rev-parse HEAD)"
