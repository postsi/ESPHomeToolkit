#!/usr/bin/env python3
"""Send fixtures/test_host_sdl_lvgl.yaml to the local sim agent (default ws://127.0.0.1:8765)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import websockets


async def _main(uri: str, yaml_path: Path, token: str | None) -> int:
    text = yaml_path.read_text(encoding="utf-8")
    async with websockets.connect(uri) as ws:
        if token:
            await ws.send(json.dumps({"type": "auth", "token": token}))
            raw = await ws.recv()
            msg = json.loads(raw)
            if msg.get("type") != "auth_ok":
                print("auth failed:", msg, file=sys.stderr)
                return 1
        await ws.send(json.dumps({"type": "run", "yaml": text}))
        while True:
            raw = await ws.recv()
            msg = json.loads(raw)
            mtype = msg.get("type")
            if mtype == "log":
                line = msg.get("line", "")
                stream = msg.get("stream", "")
                print(f"[{stream}] {line}")
            elif mtype == "started":
                print("started:", msg.get("path"))
            elif mtype == "finished":
                print("finished, returncode=", msg.get("returncode"))
                return int(msg.get("returncode") or 0)
            elif mtype == "error":
                print("error:", msg.get("message"), file=sys.stderr)
                return 1
            else:
                print(msg)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--uri", default="ws://127.0.0.1:8765")
    p.add_argument(
        "--fixture",
        type=Path,
        default=Path(__file__).resolve().parent / "fixtures" / "test_host_sdl_lvgl.yaml",
    )
    p.add_argument("--token", default="", help="Optional auth token if agent uses --token")
    args = p.parse_args()
    token = args.token.strip() or None
    rc = asyncio.run(_main(args.uri, args.fixture, token))
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
