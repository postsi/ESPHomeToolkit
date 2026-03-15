/**
 * Tests for arc geometry. LVGL: draw from start to end in clockwise direction (no "short arc").
 * 0°=right, 90°=bottom, 180°=left, 270°=top; angles increase clockwise.
 */
import { describe, it, expect } from "vitest";
import { computeArcBackground, pointerAngleToValue, valueToAngle } from "./arcGeometry";

describe("arcGeometry", () => {
  describe("computeArcBackground", () => {
    it("rotation=0, start=270, end=0 → quarter circle top to right (90° clockwise)", () => {
      const bg = computeArcBackground(0, 270, 0);
      expect(bg.sweepCw).toBe(90);
      expect(bg.bgSweep).toBe(90);
      expect(bg.bgClockwise).toBe(true);
      expect(bg.bgStartDeg).toBe(270);
      expect(bg.bgEndDeg).toBe(0);
      expect(bg.anticlockwise).toBe(false);
    });

    it("rotation=0, start=270, end=180 → three-quarter circle top via right/bottom to left (270° clockwise)", () => {
      const bg = computeArcBackground(0, 270, 180);
      expect(bg.sweepCw).toBe(270);
      expect(bg.bgSweep).toBe(270);
      expect(bg.bgClockwise).toBe(true);
      expect(bg.bgStartDeg).toBe(270);
      expect(bg.bgEndDeg).toBe(180);
      expect(bg.anticlockwise).toBe(false);
    });

    it("rotation=0, start=90, end=0 → three-quarter circle 6 o'clock to 3 o'clock (270° clockwise)", () => {
      const bg = computeArcBackground(0, 90, 0);
      expect(bg.sweepCw).toBe(270);
      expect(bg.bgSweep).toBe(270);
      expect(bg.bgStartDeg).toBe(90);
      expect(bg.bgEndDeg).toBe(0);
      expect(bg.anticlockwise).toBe(false);
    });

    it("rotation=0, start=270, end=90 → semicircle top to bottom (180°)", () => {
      const bg = computeArcBackground(0, 270, 90);
      expect(bg.sweepCw).toBe(180);
      expect(bg.bgSweep).toBe(180);
      expect(bg.bgClockwise).toBe(true);
      expect(bg.bgStartDeg).toBe(270);
      expect(bg.bgEndDeg).toBe(90);
      expect(bg.anticlockwise).toBe(false);
    });

    it("rotation=90, start=270, end=0 → quarter rotated (effective start=0, end=90)", () => {
      const bg = computeArcBackground(90, 270, 0);
      expect(bg.sweepCw).toBe(90);
      expect(bg.bgSweep).toBe(90);
      expect(bg.bgStartDeg).toBe(0);
      expect(bg.bgEndDeg).toBe(90);
    });

    it("start=135, end=45 → 270° clockwise arc (135→180→270→0→45)", () => {
      const bg = computeArcBackground(0, 135, 45);
      expect(bg.sweepCw).toBe(270);
      expect(bg.bgSweep).toBe(270);
      expect(bg.bgClockwise).toBe(true);
      expect(bg.bgStartDeg).toBe(135);
      expect(bg.bgEndDeg).toBe(45);
      expect(bg.anticlockwise).toBe(false);
    });
  });

  describe("pointerAngleToValue (simulator)", () => {
    const min = 0;
    const max = 100;

    it("NORMAL: pointer at start → min, at end → max", () => {
      // Arc 270°→0° (90° clockwise)
      expect(pointerAngleToValue(0, 270, 0, "NORMAL", min, max, 270)).toBe(0);
      expect(pointerAngleToValue(0, 270, 0, "NORMAL", min, max, 0)).toBe(100);
    });

    it("NORMAL: pointer at 50% along arc → value 50", () => {
      // 270→0°, 90° arc; 50% = 315°
      const v = pointerAngleToValue(0, 270, 0, "NORMAL", min, max, 315);
      expect(Math.round(v)).toBe(50);
    });

    it("NORMAL: 270° arc (90→0): pointer at 6 o'clock → 0, at 3 o'clock → 100", () => {
      expect(pointerAngleToValue(0, 90, 0, "NORMAL", min, max, 90)).toBe(0);
      expect(pointerAngleToValue(0, 90, 0, "NORMAL", min, max, 0)).toBe(100);
    });

    it("REVERSE: pointer at start → max, at end → min", () => {
      expect(pointerAngleToValue(0, 270, 0, "REVERSE", min, max, 270)).toBe(100);
      expect(pointerAngleToValue(0, 270, 0, "REVERSE", min, max, 0)).toBe(0);
    });

    it("SYMMETRICAL: pointer at mid → min, at end → max", () => {
      // 270→0°, mid = 315°, end = 0°
      expect(pointerAngleToValue(0, 270, 0, "SYMMETRICAL", min, max, 315)).toBe(0);
      expect(pointerAngleToValue(0, 270, 0, "SYMMETRICAL", min, max, 0)).toBe(100);
    });

    it("with rotation: effective start/end rotated", () => {
      // rotation=90, start=270 → effective start 0°; end 0 → effective end 90°
      expect(pointerAngleToValue(90, 270, 0, "NORMAL", min, max, 0)).toBe(0);
      expect(pointerAngleToValue(90, 270, 0, "NORMAL", min, max, 90)).toBe(100);
    });
  });

  describe("valueToAngle (tick labels)", () => {
    const min = 0;
    const max = 100;

    it("NORMAL: value min → start angle, value max → end angle", () => {
      expect(valueToAngle(0, 270, 0, "NORMAL", min, max, 0)).toBe(270);
      expect(valueToAngle(0, 270, 0, "NORMAL", min, max, 100)).toBe(0);
    });

    it("NORMAL: value 50 → mid angle", () => {
      const a = valueToAngle(0, 270, 0, "NORMAL", min, max, 50);
      expect(Math.round(a)).toBe(315);
    });

    it("round-trip: valueToAngle then pointerAngleToValue recovers value", () => {
      for (const v of [0, 25, 50, 75, 100]) {
        const angle = valueToAngle(0, 135, 45, "NORMAL", min, max, v);
        const back = pointerAngleToValue(0, 135, 45, "NORMAL", min, max, angle);
        expect(Math.round(back)).toBe(v);
      }
    });
  });
});
