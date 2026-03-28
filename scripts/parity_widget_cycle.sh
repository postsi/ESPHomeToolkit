#!/usr/bin/env bash
# Per-widget parity: for each public/parity-fixtures/widget_*.json — HA enqueue → capture → Playwright compare.
# Prereq: cd frontend && npm run generate:parity-fixtures && npm run generate:parity-widget-fixtures
# Env: same as run-designer-mac-parity.sh / parity_prepare_mac.py (ESPTOOLKIT_HA_URL, ENTRY_ID, PARITY_DEVICE_ID, …).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "parity_widget_cycle.sh is macOS-only."
  exit 1
fi

parity_print_last_report() {
  local base url
  base="${ESPTOOLKIT_HA_URL:-}"
  base="${base%/}"
  if [[ -z "$base" || -z "${ESPTOOLKIT_ENTRY_ID:-}" ]]; then
    echo "[parity_widget_cycle] Set ESPTOOLKIT_HA_URL and ESPTOOLKIT_ENTRY_ID to fetch last_report after failures."
    return 0
  fi
  url="${base}/api/esptoolkit/mac_sim/last_report?entry_id=$(python3 -c "import os, urllib.parse; print(urllib.parse.quote(os.environ.get('ESPTOOLKIT_ENTRY_ID',''), safe=''))")"
  echo "[parity_widget_cycle] GET last_report → $url"
  if [[ -n "${ESPTOOLKIT_HA_TOKEN:-}" ]]; then
    curl -sS -H "Authorization: Bearer ${ESPTOOLKIT_HA_TOKEN}" "$url" || true
  else
    curl -sS "$url" || true
  fi
  echo
}

shopt -s nullglob
_wfiles=("$ROOT/frontend/public/parity-fixtures"/widget_*.json)
if [[ ${#_wfiles[@]} -eq 0 ]]; then
  echo "No widget_*.json under frontend/public/parity-fixtures. Run:"
  echo "  cd frontend && npm run generate:parity-fixtures && npm run generate:parity-widget-fixtures"
  exit 1
fi

for f in $(printf '%s\n' "${_wfiles[@]}" | sort); do
  base="$(basename "$f" .json)"
  echo "========================================"
  echo "[parity_widget_cycle] ${base}"
  echo "========================================"
  export ESPTOOLKIT_PARITY_FIXTURES="$base"
  export PARITY_FIXTURE_NAMES="$base"
  if ! bash "$ROOT/scripts/run-designer-mac-parity.sh"; then
    echo "[parity_widget_cycle] FAILED: ${base}"
    echo "[parity_widget_cycle] Artifacts: frontend/test-results/parity/${base}-*.png (if any), *-result.json"
    parity_print_last_report
    exit 1
  fi
done

echo "[parity_widget_cycle] All widget fixtures passed."
