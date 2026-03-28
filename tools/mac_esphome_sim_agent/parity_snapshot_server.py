#!/usr/bin/env python3
"""
Serve PNGs for Playwright canvas-vs-sim checks.

Automated path: `scripts/parity_prepare_mac.py` (or `npm run parity:mac`) fills
`parity_snapshots/<fixture>.png` via HA mac_sim/enqueue + Quartz window capture.

Manual path: drop PNGs into `parity_snapshots/` yourself.

Playwright:

  export MACSIM_SNAPSHOT_URL_TEMPLATE='http://127.0.0.1:9777/snapshot/{fixture}.png'

Override directory: PARITY_SNAPSHOT_DIR
"""
from __future__ import annotations

import argparse
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def _snapshot_dir() -> Path:
    raw = os.environ.get("PARITY_SNAPSHOT_DIR", "").strip()
    if raw:
        return Path(raw).resolve()
    return (Path(__file__).resolve().parent / "parity_snapshots").resolve()


class Handler(BaseHTTPRequestHandler):
    server_version = "ParitySnapshot/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        # Quieter default
        if os.environ.get("PARITY_SNAPSHOT_VERBOSE"):
            super().log_message(fmt, *args)

    def do_GET(self) -> None:  # noqa: N802
        base = _snapshot_dir()
        parsed = urlparse(self.path)
        path = parsed.path.strip("/")
        # /snapshot/min_rect.png or /min_rect.png
        name: str | None = None
        if path.startswith("snapshot/"):
            name = path.removeprefix("snapshot/").removesuffix(".png")
        elif path.endswith(".png"):
            name = Path(path).stem
        if not name and "fixture" in (q := parse_qs(parsed.query)):
            name = (q["fixture"][0] or "").strip()
        if not name:
            self.send_error(400, "use /snapshot/<fixture>.png or ?fixture=<name>")
            return
        if not name.replace("_", "").replace("-", "").isalnum():
            self.send_error(400, "bad fixture name")
            return
        file = base / f"{name}.png"
        if not file.is_file():
            # Reason phrase must be latin-1 for BaseHTTPRequestHandler (no em-dash etc.).
            self.send_error(
                404,
                f"missing {file}; save Mac LVGL screenshot there (same WxH as designer parity export)",
            )
            return
        data = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    p = argparse.ArgumentParser(description="HTTP server: fixture-named PNGs for canvas vs sim tests")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9777)
    args = p.parse_args()
    d = _snapshot_dir()
    d.mkdir(parents=True, exist_ok=True)
    print(f"Parity snapshots: {d}")
    print(f"Serving http://{args.host}:{args.port}/snapshot/<fixture>.png")
    HTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
