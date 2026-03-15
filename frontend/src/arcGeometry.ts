/**
 * Pure arc geometry for LVGL-style arcs.
 * LVGL: 0°=right, 90°=bottom, 180°=left, 270°=top; angles increase clockwise.
 * The arc is drawn from start_angle to end_angle in the clockwise direction (no "short arc").
 */

export interface ArcBackground {
  /** Clockwise angular span from start to end [1, 360]. */
  sweepCw: number;
  /** Same as sweepCw: we draw the full clockwise arc. */
  bgSweep: number;
  /** Always true: we draw clockwise from start to end. */
  bgClockwise: boolean;
  /** Start angle in degrees [0,360) for drawing (includes rotation). */
  bgStartDeg: number;
  /** End angle in degrees [0,360) for drawing; 0 is stored as 0 (we use 2π in rad). */
  bgEndDeg: number;
  bgStartRad: number;
  bgEndRad: number;
  /** Canvas arc(..., anticlockwise): false = draw clockwise. */
  anticlockwise: boolean;
}

export interface ArcIndicator {
  indStart: number;
  indSweep: number;
  endDeg: number;
  indFromDeg: number;
  indToDeg: number;
  indClockwise: boolean;
}

export function computeArcBackground(
  rotation: number,
  startAngle: number,
  endAngle: number
): ArcBackground {
  const rot = rotation;
  const bgStart = startAngle;
  const bgEnd = endAngle;
  // Clockwise angular distance from start to end; draw this full arc (LVGL convention).
  const sweepCw = (bgEnd - bgStart + 360) % 360 || 360;
  const bgSweep = sweepCw;
  const bgClockwise = true;
  const bgStartDeg = (rot + bgStart + 720) % 360;
  const bgEndDeg = (rot + bgStart + sweepCw + 720) % 360;
  const toRad = (deg: number) => ((deg % 360 + 360) % 360) * (Math.PI / 180);
  const bgStartRad = toRad(bgStartDeg);
  const bgEndRad = bgEndDeg === 0 ? 2 * Math.PI : toRad(bgEndDeg);
  const anticlockwise = false; // always draw clockwise
  return {
    sweepCw,
    bgSweep,
    bgClockwise,
    bgStartDeg,
    bgEndDeg,
    bgStartRad,
    bgEndRad,
    anticlockwise,
  };
}

export function computeArcIndicator(
  rotation: number,
  startAngle: number,
  endAngle: number,
  bg: ArcBackground,
  mode: "NORMAL" | "REVERSE" | "SYMMETRICAL",
  minVal: number,
  maxVal: number,
  value: number
): ArcIndicator {
  const { sweepCw } = bg;
  const bgStart = startAngle;
  const bgEnd = endAngle;
  const t = maxVal > minVal ? (value - minVal) / (maxVal - minVal) : 0.5;
  let indStart = bgStart;
  let indSweep = 0;
  if (maxVal > minVal) {
    if (mode === "SYMMETRICAL") {
      const mid = bgStart + sweepCw / 2;
      indStart = mid;
      indSweep = t * (sweepCw / 2); // from mid toward end (clockwise)
    } else if (mode === "REVERSE") {
      indStart = bgEnd;
      indSweep = -t * sweepCw; // from end back to start (counter-clockwise)
    } else {
      indSweep = t * sweepCw; // from start toward end (clockwise)
    }
  }
  const endDeg = indStart + indSweep;
  const indFromDeg = (rotation + (indSweep >= 0 ? indStart : endDeg) + 720) % 360;
  const indToDeg = (rotation + (indSweep >= 0 ? endDeg : indStart) + 720) % 360;
  return {
    indStart,
    indSweep,
    endDeg,
    indFromDeg,
    indToDeg,
    indClockwise: indSweep >= 0,
  };
}

/** Normalise angle to [0, 360). */
export function normDeg(deg: number): number {
  return ((deg % 360) + 360) % 360;
}

/**
 * Simulator: map pointer angle (degrees [0,360), 0=right, 90=bottom) to arc value.
 * Must match the drawn arc (clockwise from start to end) and mode.
 */
export function pointerAngleToValue(
  rotation: number,
  startAngle: number,
  endAngle: number,
  mode: "NORMAL" | "REVERSE" | "SYMMETRICAL",
  minVal: number,
  maxVal: number,
  pointerAngleDeg: number
): number {
  const sweepCw = (endAngle - startAngle + 360) % 360 || 360;
  const startAngleWorld = (rotation + startAngle + 720) % 360;
  const a = normDeg(pointerAngleDeg);
  const norm = Math.max(0, Math.min(1, ((a - startAngleWorld + 360) % 360) / sweepCw));
  if (mode === "REVERSE") {
    return minVal + (1 - norm) * (maxVal - minVal);
  }
  if (mode === "SYMMETRICAL") {
    const midAngle = (startAngleWorld + sweepCw / 2) % 360;
    const normSym = Math.max(0, Math.min(1, ((a - midAngle + 360) % 360) / (sweepCw / 2)));
    return minVal + normSym * (maxVal - minVal);
  }
  return minVal + norm * (maxVal - minVal);
}

/**
 * Map a value to world angle (degrees [0, 360)) for label placement.
 * Inverse of pointerAngleToValue: value → angle so that labels sit at the correct arc position.
 */
export function valueToAngle(
  rotation: number,
  startAngle: number,
  endAngle: number,
  mode: "NORMAL" | "REVERSE" | "SYMMETRICAL",
  minVal: number,
  maxVal: number,
  value: number
): number {
  const sweepCw = (endAngle - startAngle + 360) % 360 || 360;
  const t = maxVal > minVal ? (value - minVal) / (maxVal - minVal) : 0.5;
  const clampedT = Math.max(0, Math.min(1, t));
  let arcDeg: number;
  if (mode === "REVERSE") {
    arcDeg = startAngle + (1 - clampedT) * sweepCw;
  } else if (mode === "SYMMETRICAL") {
    const mid = startAngle + sweepCw / 2;
    arcDeg = mid + clampedT * (sweepCw / 2);
  } else {
    arcDeg = startAngle + clampedT * sweepCw;
  }
  return (rotation + arcDeg + 720) % 360;
}
