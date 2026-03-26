/**
 * Visual bounds for arc_labeled: tick marks and scale labels extend outside the widget w×h
 * used for the base rect (same math as Canvas.tsx). Used when fitting parent containers.
 */
import { valueToAngle } from "./arcGeometry";
import { fontSizeFromFontId, layoutInt } from "./canvasUtils";

/** Pixels of content that extend past the nominal top-left (0,0) and bottom-right (w,h) box. */
export function arcLabeledVisualOverflowPad(w: any): { left: number; top: number; right: number; bottom: number } {
  if (!w || w.type !== "arc_labeled") return { left: 0, top: 0, right: 0, bottom: 0 };
  const p = w.props || {};
  const s = w.style || {};
  const ww = Number(w.w ?? 0);
  const hh = Number(w.h ?? 0);
  if (ww <= 0 || hh <= 0) return { left: 0, top: 0, right: 0, bottom: 0 };

  const cx = ww / 2;
  const cy = hh / 2;

  const arcWidthProp = Number(p.arc_width ?? 0);
  const trackW =
    arcWidthProp > 0 ? Math.max(1, Math.min(16, arcWidthProp)) : Math.max(4, Math.min(16, Math.min(ww, hh) / 8));
  const half = Math.min(ww, hh) / 2;
  const r = Math.max(trackW / 2 + 1, half - trackW / 2 - 2);
  const outerR = r + trackW / 2;

  const rot = Number(p.rotation ?? 0);
  const bgStart = Number(p.start_angle ?? 135);
  const bgEnd = Number(p.end_angle ?? 45);
  const mode = String(p.mode ?? "NORMAL").toUpperCase() as "NORMAL" | "REVERSE" | "SYMMETRICAL";
  const min = Number(p.min_value ?? 0);
  const max = Number(p.max_value ?? 100);

  const labelOffset = Math.max(4, Math.min(20, Math.min(ww, hh) / 10));
  const labelR = outerR + labelOffset;
  const tickLenAuto = Math.max(2, Math.min(6, Math.min(ww, hh) / 40));
  const tickLengthProp = Number(s.tick_length ?? p.tick_length ?? 0);
  const tickLen = tickLengthProp > 0 ? Math.max(2, Math.min(48, tickLengthProp)) : tickLenAuto;
  const tickWidth = Math.max(1, Math.min(16, Number(s.tick_width ?? p.tick_width ?? 3) || 3));

  const labelFontSizeProp = Number(s.label_font_size ?? 0);
  const labelFontId = s.label_text_font ?? p.label_text_font ?? s.text_font ?? p.text_font;
  const labelFontSize =
    labelFontSizeProp > 0
      ? Math.max(8, Math.min(48, labelFontSizeProp))
      : (() => {
          const baseFontSize = fontSizeFromFontId(labelFontId) ?? 12;
          const scaleRef = 100;
          const scaleFactor = Math.min(ww, hh) / scaleRef;
          return Math.max(8, Math.min(24, layoutInt(baseFontSize * scaleFactor)));
        })();

  const minInt = Math.ceil(min);
  const maxInt = Math.floor(max);
  const tickInterval = Math.max(1, Number(s.tick_interval ?? p.tick_interval ?? 1));
  const labelInterval = Math.max(1, Number(s.label_interval ?? p.label_interval ?? 2));

  let minPx = 0;
  let maxPx = ww;
  let minPy = 0;
  let maxPy = hh;
  const tw = tickWidth / 2;

  for (let v = minInt; v <= maxInt; v++) {
    if ((v - minInt) % tickInterval !== 0) continue;
    const angleDeg = valueToAngle(rot, bgStart, bgEnd, mode, min, max, v);
    const angleRad = (angleDeg * Math.PI) / 180;
    const c = Math.cos(angleRad);
    const s_ = Math.sin(angleRad);
    const x1 = cx + (outerR - tickLen) * c;
    const y1 = cy + (outerR - tickLen) * s_;
    const x2 = cx + (outerR + tickLen) * c;
    const y2 = cy + (outerR + tickLen) * s_;
    minPx = Math.min(minPx, x1 - tw, x2 - tw);
    maxPx = Math.max(maxPx, x1 + tw, x2 + tw);
    minPy = Math.min(minPy, y1 - tw, y2 - tw);
    maxPy = Math.max(maxPy, y1 + tw, y2 + tw);
  }

  for (let v = minInt; v <= maxInt; v++) {
    if ((v - minInt) % labelInterval !== 0) continue;
    const angleDeg = valueToAngle(rot, bgStart, bgEnd, mode, min, max, v);
    const angleRad = (angleDeg * Math.PI) / 180;
    const lx = cx + labelR * Math.cos(angleRad);
    const ly = cy + labelR * Math.sin(angleRad);
    const text = String(v);
    const pad = 6;
    const box = Math.max(20, text.length * labelFontSize * 0.6 + pad);
    const halfBox = box / 2;
    const textH = labelFontSize + 2;
    minPx = Math.min(minPx, lx - halfBox);
    maxPx = Math.max(maxPx, lx + halfBox);
    minPy = Math.min(minPy, ly - textH / 2);
    maxPy = Math.max(maxPy, ly + textH / 2);
  }

  return {
    left: Math.max(0, -minPx),
    top: Math.max(0, -minPy),
    right: Math.max(0, maxPx - ww),
    bottom: Math.max(0, maxPy - hh),
  };
}
