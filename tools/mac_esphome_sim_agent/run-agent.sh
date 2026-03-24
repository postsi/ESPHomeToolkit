#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
if [[ ! -d .venv ]]; then
  echo "Run ./install-macos.sh first."
  exit 1
fi
# shellcheck source=/dev/null
source .venv/bin/activate
exec python sim_agent.py "$@"
