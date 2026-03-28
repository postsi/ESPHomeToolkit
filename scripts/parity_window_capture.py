#!/usr/bin/env python3
"""Find an on-screen SDL/LVGL-sized window and capture it to PNG (macOS, Quartz)."""
from __future__ import annotations

import os
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


def _window_line(w: dict) -> str:
    ow = w.get("kCGWindowOwnerName") or "?"
    nm = w.get("kCGWindowName") or ""
    b = w.get("kCGWindowBounds") or {}
    bw, bh = _bounds_wh(b)
    return f"owner={ow!r} title={nm!r} outer≈{int(bw)}×{int(bh)}"


def window_dict_by_id(target_wid: int) -> dict | None:
    for w in _quartz_windows():
        try:
            if int(w.get("kCGWindowNumber", 0)) == target_wid:
                return w
        except (TypeError, ValueError):
            continue
    return None


def _looks_like_sdl_esphome(owner_l: str, name_l: str) -> bool:
    if "python" in owner_l or "esphome" in owner_l:
        return True
    if "sdl" in name_l or "lvgl" in name_l or "esphome" in name_l:
        return True
    return False


def find_window_id_for_display_size(
    want_w: int,
    want_h: int,
    *,
    w_slack: int = 12,
    h_slack: int = 120,
    strict_sdl: bool = False,
) -> int | None:
    """
    Pick a top-level window whose outer size is close to the LVGL display (allow title bar on height).

    strict_sdl: only consider windows whose owner/title hints at Python/ESPHome/SDL (avoids another
    app that happens to be ~1024×600). If none match, returns None.
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
            if strict_sdl and not _looks_like_sdl_esphome(owner, name):
                continue
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


def _backing_store_looks_2x_logical(w: int, h: int, want_w: int, want_h: int) -> bool:
    """Quartz often returns @2x pixels; window bounds are logical points. Halve before cropping."""
    if w % 2 or h % 2:
        return False
    if not (want_w * 1.88 <= w <= want_w * 2.28):
        return False
    # Height: 2×(framebuffer + title bar) or 2×framebuffer only
    h_min = int(want_h * 1.82) + 8
    h_max = int(want_h * 2.55) + 260
    return h_min <= h <= h_max


def _normalize_snapshot_png(path: Path, want_w: int, want_h: int) -> None:
    """Match designer export: logical WxH (HiDPI halve, then crop macOS title bar).

    Quartz returns backing-store pixels (often 2× logical on Retina). Cropping to want_w×want_h
    without halving first zooms content ~2× vs the real simulator. Window chrome: skip title bar
    on the *logical*-size image after halving.
    """
    try:
        from PIL import Image
    except ImportError:
        return
    im = Image.open(path).convert("RGBA")
    W, H = im.size
    if W == want_w and H == want_h:
        return
    for _ in range(3):
        if not _backing_store_looks_2x_logical(W, H, want_w, want_h):
            break
        print(
            f"[parity] HiDPI snapshot {W}×{H} → halving to match device logical px ({want_w}×{want_h} content)",
            flush=True,
        )
        im = im.resize((W // 2, H // 2), Image.Resampling.LANCZOS)
        W, H = im.size
    if W == want_w and H == want_h:
        im.save(path)
        return
    # Exact 2× framebuffer, no title in bitmap (rare)
    if abs(W - want_w * 2) <= 4 and abs(H - want_h * 2) <= 4:
        im.resize((want_w, want_h), Image.Resampling.LANCZOS).save(path)
        return
    if W >= want_w and H >= want_h:
        left_off = (W - want_w) // 2 if W > want_w else 0
        extra_top = H - want_h
        # Prefer skipping exactly the title-bar band (client flush to bottom of window).
        if 8 <= extra_top <= 120:
            box = (left_off, extra_top, left_off + want_w, extra_top + want_h)
            if box[2] <= W and box[3] <= H:
                im.crop(box).save(path)
                return
        # Try larger top insets first (title bar), then smaller — never prefer tb=0 while a deeper inset fits.
        for tb in range(min(120, H - want_h), -1, -1):
            box = (left_off, tb, left_off + want_w, tb + want_h)
            if box[2] <= W and box[3] <= H:
                im.crop(box).save(path)
                return
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
    strict = os.environ.get("PARITY_CAPTURE_STRICT_SDL", "").strip().lower() in ("1", "true", "yes")
    stabilize = float(os.environ.get("PARITY_CAPTURE_STABILIZE_S", "0.85"))
    deadline = time.monotonic() + timeout_s
    last_msg = 0.0
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now - last_msg >= 15.0:
            remain = max(0.0, deadline - now)
            print(
                f"[parity] still waiting for ~{want_w}×{want_h} SDL window ({remain:.0f}s left)…",
                flush=True,
            )
            last_msg = now
        wid = find_window_id_for_display_size(want_w, want_h, strict_sdl=strict)
        if wid:
            wd = window_dict_by_id(wid)
            if wd:
                print(f"[parity] capture target: {_window_line(wd)}", flush=True)
                ol = str(wd.get("kCGWindowOwnerName") or "").lower()
                if any(x in ol for x in ("chrome", "safari", "firefox", "cursor", "electron")):
                    print(
                        "[parity] warning: window owner looks like a browser/app — "
                        "if the PNG is wrong, set PARITY_CAPTURE_STRICT_SDL=1",
                        flush=True,
                    )
            if stabilize > 0:
                print(
                    f"[parity] stabilizing {stabilize}s for LVGL first frame (was grabbing too early)…",
                    flush=True,
                )
                time.sleep(stabilize)
                wid2 = find_window_id_for_display_size(want_w, want_h, strict_sdl=strict)
                if wid2:
                    wid = wid2
                    wd2 = window_dict_by_id(wid)
                    if wd2:
                        print(f"[parity] capture target after wait: {_window_line(wd2)}", flush=True)
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
