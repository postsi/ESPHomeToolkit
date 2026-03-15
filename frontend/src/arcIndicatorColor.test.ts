/**
 * Tests for arc indicator (filled part) color on the canvas.
 * Ensures WiFi-fan-style arcs (dark track, no indicator.bg_color) render with a visible fill,
 * not the same as the track (which would be invisible).
 */
import { describe, it, expect } from "vitest";
import { toFillColor } from "./canvasUtils";

/** Rule used in Canvas for arc indicator stroke: indicator.bg_color only, default #10b981 (never style.bg_color). */
function getArcIndicatorStrokeColor(indicatorBgColor: unknown): string {
  return toFillColor(indicatorBgColor, "#10b981");
}

describe("arc indicator color (canvas)", () => {
  it("uses visible default when indicator.bg_color is unset (WiFi fan)", () => {
    const indStroke = getArcIndicatorStrokeColor(undefined);
    expect(indStroke).toBe("#10b981");
  });

  it("uses visible default when indicator is missing (WiFi fan arcs have no indicator)", () => {
    const w = { style: { bg_color: 0x1e1e1e } };
    const indicatorBg = (w as { indicator?: { bg_color?: number } }).indicator?.bg_color;
    expect(getArcIndicatorStrokeColor(indicatorBg)).toBe("#10b981");
  });

  it("does not use style.bg_color for indicator (would make fill same as track = invisible)", () => {
    const styleBg = 0x1e1e1e;
    const wrongFormula = toFillColor(styleBg, "#10b981");
    expect(wrongFormula).toBe("#1e1e1e");
    expect(wrongFormula).not.toBe("#10b981");
    // So Canvas must use (w.indicator || {}).bg_color with default "#10b981", never ?? s.bg_color
  });

  it("uses indicator.bg_color when set", () => {
    expect(getArcIndicatorStrokeColor(0x3b82f6)).toBe("#3b82f6");
    expect(getArcIndicatorStrokeColor("#22c55e")).toBe("#22c55e");
  });
});
