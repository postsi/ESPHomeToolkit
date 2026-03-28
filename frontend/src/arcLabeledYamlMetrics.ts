/**
 * Same geometry as api/views.py::_arc_labeled_layout_metrics (YAML wrapper vs model w×h).
 * Used for canvas preview parity and selection footprints.
 */
import { valueToAngle } from "./arcGeometry";
import { fontPxFromId } from "./fontMetrics";

function applyAlignLvgl(
  xVal: number,
  yVal: number,
  wVal: number,
  hVal: number,
  align: string,
  parentW: number | null,
  parentH: number | null
): { x: number; y: number } {
  const a = String(align || "TOP_LEFT").trim().toUpperCase();
  if (!a || a === "TOP_LEFT" || parentW == null || parentH == null) return { x: xVal, y: yVal };
  const pw = Math.floor(parentW);
  const ph = Math.floor(parentH);
  const pw2 = Math.floor(pw / 2);
  const ph2 = Math.floor(ph / 2);
  const wv = Math.floor(wVal);
  const hv = Math.floor(hVal);
  const w2 = Math.floor(wVal / 2);
  const h2 = Math.floor(hVal / 2);
  if (a === "CENTER") return { x: xVal + w2 - pw2, y: yVal + h2 - ph2 };
  if (a === "TOP_MID") return { x: xVal + w2 - pw2, y: yVal };
  if (a === "TOP_RIGHT") return { x: xVal + wv - pw, y: yVal };
  if (a === "LEFT_MID") return { x: xVal, y: yVal + h2 - ph2 };
  if (a === "RIGHT_MID") return { x: xVal + wv - pw, y: yVal + h2 - ph2 };
  if (a === "BOTTOM_LEFT") return { x: xVal, y: yVal + hv - ph };
  if (a === "BOTTOM_MID") return { x: xVal + w2 - pw2, y: yVal + hv - ph };
  if (a === "BOTTOM_RIGHT") return { x: xVal + wv - pw, y: yVal + hv - ph };
  return { x: xVal, y: yVal };
}

export type ArcLabeledYamlMetrics = {
  x_val: number;
  y_val: number;
  w_val: number;
  h_val: number;
  container_w: number;
  container_h: number;
  arc_off_x: number;
  arc_off_y: number;
};

/** Port of views.py::_arc_labeled_layout_metrics (numeric fields only). */
export function arcLabeledYamlMetrics(w: WidgetLikeArc, parentW: number | null, parentH: number | null): ArcLabeledYamlMetrics {
  let xVal = Math.floor(Number(w.x ?? 0));
  let yVal = Math.floor(Number(w.y ?? 0));
  const wVal = Math.floor(Number(w.w ?? 100));
  const hVal = Math.floor(Number(w.h ?? 50));
  const props = w.props || {};
  const style = w.style || {};
  const align = String(props.align ?? "TOP_LEFT").trim().toUpperCase();
  const adj = applyAlignLvgl(xVal, yVal, wVal, hVal, align, parentW, parentH);
  xVal = adj.x;
  yVal = adj.y;

  const rot = Number(props.rotation ?? 0);
  const startAngle = Number(props.start_angle ?? 135);
  const endAngle = Number(props.end_angle ?? 45);
  const mode = String(props.mode ?? "NORMAL").trim().toUpperCase() as "NORMAL" | "REVERSE" | "SYMMETRICAL";
  const minVal = Number(props.min_value ?? 0);
  const maxVal = Number(props.max_value ?? 100);
  const tickInterval = Math.max(1, Number(style.tick_interval ?? props.tick_interval ?? 1));
  const labelInterval = Math.max(1, Number(style.label_interval ?? props.label_interval ?? 2));
  const labelFontRaw = String(style.label_text_font ?? style.text_font ?? props.font ?? "").trim();
  const labelFont = labelFontRaw || null;

  const cx = wVal / 2;
  const cy = hVal / 2;
  const arcWidthProp = Math.floor(Number(props.arc_width ?? 0));
  const trackW =
    arcWidthProp > 0
      ? Math.max(1, Math.min(16, arcWidthProp))
      : Math.max(4, Math.min(16, Math.floor(Math.min(wVal, hVal) / 8)));
  const half = Math.min(wVal, hVal) / 2;
  const rMid = Math.max(trackW / 2 + 1, half - trackW / 2 - 2);
  const outerR = rMid + trackW / 2;
  const tickLenAuto = Math.max(2, Math.min(6, Math.min(wVal, hVal) / 40));
  const tickLengthStyle = Math.max(0, Math.floor(Number(style.tick_length ?? 0)));
  const tickLen = tickLengthStyle > 0 ? Math.max(2, Math.min(48, tickLengthStyle)) : tickLenAuto;
  const tickWidth = Math.max(1, Math.min(16, Number(style.tick_width ?? 0) || 3));
  const labelOffset = Math.max(4, Math.min(20, Math.min(wVal, hVal) / 10));
  const labelR = outerR + labelOffset;
  const minInt = Math.ceil(minVal);
  const maxInt = Math.floor(maxVal);
  const tickValues: number[] = [];
  for (let v = minInt; v <= maxInt; v++) {
    if ((v - minInt) % tickInterval === 0) tickValues.push(v);
  }
  const labelValues: number[] = [];
  for (let v = minInt; v <= maxInt; v++) {
    if ((v - minInt) % labelInterval === 0) labelValues.push(v);
  }
  const configuredFontPx = fontPxFromId(labelFont, 14);
  const labelFontSizeExplicit = Math.floor(Number(style.label_font_size ?? 0));
  const labelFontSize = Math.max(8, Math.min(28, labelFontSizeExplicit || configuredFontPx));
  const labelH = labelFontSize + Math.max(10, Math.ceil(labelFontSize * 0.5));

  type Box = { lx: number; ly: number; box: number; lh: number };
  const labelBoxes: Box[] = [];
  for (const value of labelValues) {
    const angleDeg = valueToAngle(rot, startAngle, endAngle, mode, minVal, maxVal, value);
    const angleRad = (angleDeg * Math.PI) / 180;
    const lx = cx + labelR * Math.cos(angleRad);
    const ly = cy + labelR * Math.sin(angleRad);
    const text = String(value);
    const box = Math.max(28, Math.ceil(text.length * labelFontSize * 0.78) + 12);
    const half = box / 2;
    const lxInt = Math.round(lx - half);
    const lyInt = Math.round(ly - labelH / 2);
    labelBoxes.push({ lx: lxInt, ly: lyInt, box, lh: labelH });
  }

  let minX = 0;
  let maxX = wVal;
  let minY = 0;
  let maxY = hVal;
  for (const lb of labelBoxes) {
    minX = Math.min(minX, lb.lx);
    maxX = Math.max(maxX, lb.lx + lb.box);
    minY = Math.min(minY, lb.ly);
    maxY = Math.max(maxY, lb.ly + lb.lh);
  }
  const tw2 = Math.max(1, Math.floor((tickWidth + 1) / 2));
  for (const value of tickValues) {
    const angleDeg = valueToAngle(rot, startAngle, endAngle, mode, minVal, maxVal, value);
    const angleRad = (angleDeg * Math.PI) / 180;
    const c = Math.cos(angleRad);
    const sm = Math.sin(angleRad);
    const x1 = cx + (outerR - tickLen) * c;
    const y1 = cy + (outerR - tickLen) * sm;
    const x2 = cx + (outerR + tickLen) * c;
    const y2 = cy + (outerR + tickLen) * sm;
    for (const [px, py] of [
      [x1, y1],
      [x2, y2],
    ] as const) {
      const ix0 = Math.floor(px - tw2);
      const iy0 = Math.floor(py - tw2);
      const ix1 = Math.ceil(px + tw2);
      const iy1 = Math.ceil(py + tw2);
      minX = Math.min(minX, ix0);
      maxX = Math.max(maxX, ix1);
      minY = Math.min(minY, iy0);
      maxY = Math.max(maxY, iy1);
    }
  }
  const pad = 22;
  const containerW = Math.max(wVal, maxX - minX + 2 * pad);
  const containerH = Math.max(hVal, maxY - minY + 2 * pad);
  const ox = pad - minX;
  const oy = pad - minY;
  const arcOffX = Math.round(ox);
  const arcOffY = Math.round(oy);

  return {
    x_val: xVal,
    y_val: yVal,
    w_val: wVal,
    h_val: hVal,
    container_w: containerW,
    container_h: containerH,
    arc_off_x: arcOffX,
    arc_off_y: arcOffY,
  };
}

type WidgetLikeArc = {
  x?: number;
  y?: number;
  w?: number;
  h?: number;
  props?: Record<string, unknown>;
  style?: Record<string, unknown>;
};
