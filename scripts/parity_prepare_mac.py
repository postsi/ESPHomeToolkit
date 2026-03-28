#!/usr/bin/env python3
"""
For each parity fixture: POST project to HA mac_sim/enqueue → Mac agent runs ESPHome SDL →
capture the SDL window to parity_snapshots/<fixture>.png → SIGINT esphome so the agent can take the next job.

Requires (same machine as ha_agent_client.py):
  - ha_agent_client.py running (WebSocket to HA, token in integration options).
  - pip install -r tools/mac_esphome_sim_agent/requirements-parity.txt (Quartz capture).

Env (or flags):
  ESPTOOLKIT_HA_URL            e.g. http://grimwoodha:8123
  ESPTOOLKIT_PARITY_DEVICE_ID  existing device_id (recipe must allow compile), e.g. yellow_p4 for JC1060
  ESPTOOLKIT_ENTRY_ID          optional; omit if only one EspToolkit entry (HA uses active entry)
  ESPTOOLKIT_HA_TOKEN          optional long-lived HA token (Bearer)
  ESPTOOLKIT_HA_INSECURE_SSL   1 for self-signed HTTPS

  PARITY_CAPTURE_STABILIZE_S   seconds to wait after SDL window appears before Quartz grab (default 0.85).
  PARITY_CAPTURE_STRICT_SDL    if 1, only match windows whose owner/title hints Python/ESPHome/SDL.

Local file (sourced by run-designer-mac-parity.sh): scripts/.parity-local.env — see scripts/parity-local.env.example
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "frontend" / "public" / "parity-fixtures"
SNAP_DIR = REPO_ROOT / "tools" / "mac_esphome_sim_agent" / "parity_snapshots"
DEFAULT_FIXTURES = ["min_rect", "standard_widgets", "prebuilt_widgets", "entity_small_climate"]


def _import_capture():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from parity_window_capture import wait_and_capture

    return wait_and_capture


def load_project(fixture: str) -> dict:
    p = FIXTURES_DIR / f"{fixture}.json"
    if not p.is_file():
        raise SystemExit(f"Missing fixture file: {p} (run: cd frontend && npm run generate:parity-fixtures)")
    return json.loads(p.read_text(encoding="utf-8"))


def screen_size(project: dict) -> tuple[int, int]:
    dev = project.get("device") or {}
    scr = dev.get("screen") or {}
    try:
        w = int(scr.get("width") or 0)
        h = int(scr.get("height") or 0)
    except (TypeError, ValueError):
        w, h = 0, 0
    if w < 120 or h < 120:
        raise SystemExit("Fixture must set device.screen.width/height (>=120)")
    return w, h


def post_enqueue(
    ha_url: str,
    entry_id: str | None,
    device_id: str,
    project: dict,
    token: str | None,
    insecure: bool,
) -> dict:
    base = f"{ha_url.rstrip('/')}/api/esptoolkit/mac_sim/enqueue"
    eid = (entry_id or "").strip()
    if eid:
        url = f"{base}?entry_id={urllib.parse.quote(eid, safe='')}"
    else:
        url = base
    payload: dict = {"device_id": device_id, "project": project}
    rid = (project.get("device") or {}).get("hardware_recipe_id")
    if isinstance(rid, str) and rid.strip():
        payload["hardware_recipe_id"] = rid.strip()
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token.strip()}")
    ctx = ssl.create_default_context()
    if insecure:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=180) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        txt = e.read().decode(errors="replace")
        raise SystemExit(f"mac_sim/enqueue HTTP {e.code}: {txt[:1200]}") from e


def kill_esphome_run() -> None:
    """Stop the current SDL run so the Mac agent can dequeue the next job."""
    subprocess.run(["/usr/bin/pkill", "-INT", "-f", "esphome run"], check=False)
    time.sleep(2.5)


def main() -> None:
    if sys.platform != "darwin":
        raise SystemExit("parity_prepare_mac.py runs on macOS only.")

    p = argparse.ArgumentParser(description="Capture Mac SDL frames for designer parity PNGs")
    p.add_argument(
        "--fixtures",
        default=os.environ.get("ESPTOOLKIT_PARITY_FIXTURES", "all"),
        help="Comma-separated names or 'all'",
    )
    p.add_argument("--ha-url", default=os.environ.get("ESPTOOLKIT_HA_URL", "").strip())
    p.add_argument("--entry-id", default=os.environ.get("ESPTOOLKIT_ENTRY_ID", "").strip())
    p.add_argument("--device-id", default=os.environ.get("ESPTOOLKIT_PARITY_DEVICE_ID", "").strip())
    p.add_argument("--token", default=os.environ.get("ESPTOOLKIT_HA_TOKEN", "").strip() or None)
    p.add_argument(
        "--insecure-ssl",
        action="store_true",
        default=os.environ.get("ESPTOOLKIT_HA_INSECURE_SSL", "").strip() in ("1", "true", "yes"),
    )
    p.add_argument("--capture-timeout", type=float, default=float(os.environ.get("ESPTOOLKIT_CAPTURE_TIMEOUT", "120")))
    args = p.parse_args()

    if not args.ha_url or not args.device_id:
        raise SystemExit(
            "Set ESPTOOLKIT_HA_URL and ESPTOOLKIT_PARITY_DEVICE_ID "
            "(or pass --ha-url --device-id). Optional: ESPTOOLKIT_ENTRY_ID. "
            "Or create scripts/.parity-local.env — see scripts/parity-local.env.example"
        )

    if args.fixtures.strip().lower() == "all":
        fixtures = list(DEFAULT_FIXTURES)
    else:
        fixtures = [x.strip() for x in args.fixtures.split(",") if x.strip()]

    wait_and_capture = _import_capture()
    SNAP_DIR.mkdir(parents=True, exist_ok=True)

    for i, name in enumerate(fixtures):
        print(f"[parity] ({i + 1}/{len(fixtures)}) fixture={name!r}", flush=True)
        proj = load_project(name)
        w, h = screen_size(proj)
        r = post_enqueue(
            args.ha_url,
            args.entry_id.strip() or None,
            args.device_id,
            proj,
            args.token,
            args.insecure_ssl,
        )
        if not r.get("ok"):
            raise SystemExit(f"enqueue failed: {r}")
        print(
            f"[parity] enqueued OK; Mac agent should open SDL (~{w}×{h}). "
            "Waiting for window to screenshot…",
            flush=True,
        )
        out = SNAP_DIR / f"{name}.png"
        try:
            wait_and_capture(w, h, out, timeout_s=args.capture_timeout)
            print(f"[parity] captured → {out}", flush=True)
        finally:
            print(
                "[parity] sending SIGINT to esphome (SDL window closes; normal — next job or Playwright can run)",
                flush=True,
            )
            kill_esphome_run()

    print(
        "[parity] all captures done (run-designer-mac-parity.sh continues: snapshot server + Playwright)",
        flush=True,
    )


if __name__ == "__main__":
    main()
