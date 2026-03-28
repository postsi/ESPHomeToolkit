#!/usr/bin/env bash
# Full pipeline (macOS): HA compile → Mac agent ESPHome SDL → Quartz capture → HTTP serve → Playwright pixel compare.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

say() { printf '%s\n' "[parity:mac] $*"; }

say "starting (repo root: $ROOT)"

# Machine-local HA URL + parity device (gitignored). Copy from scripts/parity-local.env.example
if [[ -f "$ROOT/scripts/.parity-local.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/scripts/.parity-local.env"
  set +a
  say "loaded scripts/.parity-local.env (HA URL + device id; not printed)"
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "run-designer-mac-parity.sh is macOS-only."
  exit 1
fi

python3 -c "import Quartz" 2>/dev/null || {
  echo "Install parity capture deps:"
  echo "  pip install -r tools/mac_esphome_sim_agent/requirements-parity.txt"
  exit 1
}

# Playwright defaults to four fixtures; align tests with what we actually captured.
if [[ -z "${PARITY_FIXTURE_NAMES:-}" ]]; then
  _pf=""
  if [[ -n "${ESPTOOLKIT_PARITY_FIXTURES:-}" ]]; then
    _pf="$ESPTOOLKIT_PARITY_FIXTURES"
  else
    _prev=""
    for _a in "$@"; do
      if [[ "$_prev" == "--fixtures" ]]; then
        _pf="$_a"
        break
      fi
      _prev="$_a"
    done
  fi
  _pfl=$(echo "$_pf" | tr "[:upper:]" "[:lower:]")
  if [[ -n "$_pf" && "$_pfl" != "all" ]]; then
    export PARITY_FIXTURE_NAMES="$_pf"
  fi
fi

if [[ -n "${PARITY_FIXTURE_NAMES:-}" ]]; then
  say "Playwright will only run fixtures: $PARITY_FIXTURE_NAMES (matches captured PNG names)"
else
  say "Playwright will run default fixture set (four tests)"
fi

say "phase 1/3: HA compile + mac_sim enqueue → SDL opens per fixture → Quartz capture → SDL closes (SIGINT esphome)"
python3 "$ROOT/scripts/parity_prepare_mac.py" "$@"
say "phase 1/3 done"

say "phase 2/3: serving parity_snapshots/*.png on http://127.0.0.1:9777/snapshot/<fixture>.png"
python3 "$ROOT/tools/mac_esphome_sim_agent/parity_snapshot_server.py" --host 127.0.0.1 --port 9777 &
HTTP_PID=$!
cleanup() { kill "$HTTP_PID" 2>/dev/null || true; }
trap cleanup EXIT
sleep 0.5
say "snapshot server pid=$HTTP_PID"

export MACSIM_SNAPSHOT_URL_TEMPLATE='http://127.0.0.1:9777/snapshot/{fixture}.png'
cd "$ROOT/frontend"
say "phase 3/3: Playwright — Vite preview, designer canvas PNG vs sim PNG (pixelmatch); first run can take 1–2 min"
# If CI is set in the shell, Playwright treats this as CI and refuses reuseExistingServer,
# then fails when vite preview's port 4173 is already in use.
( unset CI; exec npm run test:parity -- --reporter=list )
say "phase 3/3 done — parity pipeline finished"
