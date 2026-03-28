#!/usr/bin/env python3
"""Find an on-screen SDL/LVGL-sized window and capture it to PNG (macOS, Quartz)."""
from __future__ import annotations

import sys
import time
from pathlib import Path


def _quartz_windows():
    try:
        import Quartz
    except ImportError as e:
        raise SystemExit(
            "Install: pip install -r tools/mac_esphome_sim_agent/requirements-parity.txt"
        ) from e

    opt = Quartz.kCGWindowListOptionOnScreenOnly
    return Quartz.CGWindowListCopyWindowInfo(opt, Quartz.kCGNullWindowID) or []


def _bounds_wh(bounds) -> tuple[float, float]:
    if bounds is None:
        return 0.0, 0.0
    return float(bounds.get("Width", 0)), float(bounds.get("Height", 0))


def find_window_id_for_display_size(
    want_w: int,
    want_h: int,
    *,
    w_slack: int = 12,
    h_slack: int = 120,
) -> int | None:
    """
    Pick a top-level window whose outer size is close to the LVGL display (allow title bar on height).
    """
    want_w = max(1, want_w)
    want_h = max(1, want_h)
    best: tuple[int, float] | None = None
    for w in _quartz_windows():
        try:
            if int(w.get("kCGWindowLayer", 0)) != 0:
                continue
            wid = int(w.get("kCGWindowNumber", 0))
            if wid <= 0:
                continue
            bw, bh = _bounds_wh(w.get("kCGWindowBounds"))
            if bw < 80 or bh < 80:
                continue
            dw = abs(bw - want_w)
            dh = abs(bh - want_h)
            # Title bar: window often slightly taller than framebuffer
            dw_ok = dw <= w_slack + 4
            dh_ok = dh <= h_slack or (bh >= want_h - 8 and bh <= want_h + h_slack)
            if not (dw_ok and dh_ok):
                continue
            owner = str(w.get("kCGWindowOwnerName") or "").lower()
            name = str(w.get("kCGWindowName") or "").lower()
            bonus = 0.0
            if "python" in owner or "esphome" in owner:
                bonus -= 50
            if "sdl" in name or "lvgl" in name or "esphome" in name:
                bonus -= 30
            score = dw + dh + bonus
            if best is None or score < best[1]:
                best = (wid, score)
        except (TypeError, ValueError, KeyError):
            continue
    return best[0] if best else None


def _normalize_snapshot_png(path: Path, want_w: int, want_h: int) -> None:
    """Match designer export: logical WxH (crop title bar and/or downscale Retina)."""
    try:
        from PIL import Image
    except ImportError:
        return
    im = Image.open(path).convert("RGBA")
    W, H = im.size
    if W == want_w and H == want_h:
        return
    # Retina-ish: halve to logical size
    if abs(W - want_w * 2) <= 4 and abs(H - want_h * 2) <= 4:
        im.resize((want_w, want_h), Image.Resampling.LANCZOS).save(path)
        return
    if W >= want_w and H >= want_h:
        for tb in range(0, min(100, H - want_h + 1), 2):
            box = (0, tb, want_w, tb + want_h)
            if box[2] <= W and box[3] <= H:
                im.crop(box).save(path)
                return
        # Center crop
        cx, cy = (W - want_w) // 2, (H - want_h) // 2
        im.crop((cx, cy, cx + want_w, cy + want_h)).save(path)


def capture_window_to_png(window_id: int, out: Path, want_w: int, want_h: int) -> None:
    import Quartz

    img = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull,
        Quartz.kCGWindowListOptionIncludingWindow,
        window_id,
        Quartz.kCGWindowImageBoundsIgnoreFraming | Quartz.kCGWindowImageShouldBeOpaque,
    )
    if img is None:
        raise RuntimeError(f"CGWindowListCreateImage failed for window {window_id}")
    dest = out.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = Quartz.CFURLCreateFromFileSystemRepresentation(
        None, str(dest).encode("utf-8"), len(str(dest)), False
    )
    dest_ref = Quartz.CGImageDestinationCreateWithURL(url, "public.png", 1, None)
    if dest_ref is None:
        raise RuntimeError("CGImageDestinationCreateWithURL failed")
    Quartz.CGImageDestinationAddImage(dest_ref, img, None)
    if not Quartz.CGImageDestinationFinalize(dest_ref):
        raise RuntimeError("CGImageDestinationFinalize failed")
    _normalize_snapshot_png(dest, want_w, want_h)


def wait_and_capture(
    want_w: int,
    want_h: int,
    out: Path,
    *,
    timeout_s: float = 120.0,
    poll_s: float = 1.5,
) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        wid = find_window_id_for_display_size(want_w, want_h)
        if wid:
            try:
                capture_window_to_png(wid, out, want_w, want_h)
                if out.is_file() and out.stat().st_size > 200:
                    return
            except Exception:
                pass
        time.sleep(poll_s)
    raise TimeoutError(
        f"No ~{want_w}x{want_h} window in {timeout_s}s. "
        "Run ha_agent_client.py against HA; enqueue must reach the Mac agent."
    )


if __name__ == "__main__":
    if sys.platform != "darwin":
        raise SystemExit("macOS only")
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--width", type=int, required=True)
    p.add_argument("--height", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--timeout", type=float, default=120.0)
    args = p.parse_args()
    wait_and_capture(args.width, args.height, args.out, timeout_s=args.timeout)
    print(args.out)
