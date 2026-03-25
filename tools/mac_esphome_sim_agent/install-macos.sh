#!/usr/bin/env bash
# Install Homebrew deps (SDL2, libsodium), Python venv, esphome + websockets.
# Run from repo clone on macOS:  ./install-macos.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script targets macOS. On Linux use: sudo apt install libsdl2-dev libsodium-dev"
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required: https://brew.sh"
  exit 1
fi

if ! xcode-select -p >/dev/null 2>&1; then
  echo "Install Xcode Command Line Tools first: xcode-select --install"
  exit 1
fi

echo "==> Installing / updating SDL2 and libsodium (brew)"
brew install sdl2 libsodium
brew link sdl2 libsodium 2>/dev/null || true

if command -v sdl2-config >/dev/null 2>&1; then
  echo "sdl2-config: OK ($(command -v sdl2-config))"
else
  echo "Warning: sdl2-config not on PATH; try: brew link sdl2"
fi

echo "==> Creating Python venv at ${SCRIPT_DIR}/.venv"
python3 -m venv .venv
# shellcheck source=/dev/null
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "Smoke test (opens SDL window; close window when done):"
echo "  cd \"$SCRIPT_DIR\" && source .venv/bin/activate && python -m esphome run fixtures/test_host_sdl_lvgl.yaml"
echo ""
echo "Start WebSocket agent (listens on 127.0.0.1:8765):"
echo "  cd \"$SCRIPT_DIR\" && ./run-agent.sh"
echo ""
echo "From another terminal, send the fixture over WS (requires agent running):"
echo "  cd \"$SCRIPT_DIR\" && source .venv/bin/activate && python test_ws_client.py"
echo ""
echo "Home Assistant (outbound — recommended): set Mac sim token in EspToolkit integration options,"
echo "then run (use your HA URL and a file containing the same token):"
echo "  cd \"$SCRIPT_DIR\" && source .venv/bin/activate && \\"
echo "    python ha_agent_client.py --ha-url http://YOUR_HA:8123 --token-file ~/.esptoolkit_mac_sim_token"
echo "    (use https:// only if your browser uses https:// for HA)"
