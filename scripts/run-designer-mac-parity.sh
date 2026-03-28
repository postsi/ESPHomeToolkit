#!/usr/bin/env bash
# Full pipeline (macOS): HA compile → Mac agent ESPHome SDL → Quartz capture → HTTP serve → Playwright pixel compare.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "run-designer-mac-parity.sh is macOS-only."
  exit 1
fi

python3 -c "import Quartz" 2>/dev/null || {
  echo "Install parity capture deps:"
  echo "  pip install -r tools/mac_esphome_sim_agent/requirements-parity.txt"
  exit 1
}

python3 "$ROOT/scripts/parity_prepare_mac.py" "$@"

python3 "$ROOT/tools/mac_esphome_sim_agent/parity_snapshot_server.py" --host 127.0.0.1 --port 9777 &
HTTP_PID=$!
cleanup() { kill "$HTTP_PID" 2>/dev/null || true; }
trap cleanup EXIT
sleep 0.5

export MACSIM_SNAPSHOT_URL_TEMPLATE='http://127.0.0.1:9777/snapshot/{fixture}.png'
cd "$ROOT/frontend"
# If CI is set in the shell, Playwright treats this as CI and refuses reuseExistingServer,
# then fails when vite preview's port 4173 is already in use.
( unset CI; exec npm run test:parity -- --reporter=list )
