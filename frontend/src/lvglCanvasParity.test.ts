import { describe, expect, it } from "vitest";
import { layoutInt } from "./canvasUtils";
import { effectiveLongMode, konvaLongModeTextProps } from "./lvglCanvasParity";

describe("effectiveLongMode", () => {
  it("uses schema default CLIP for label when omitted", () => {
    expect(effectiveLongMode("label", {}, {})).toBe("CLIP");
  });

  it("respects explicit long_mode", () => {
    expect(effectiveLongMode("label", { long_mode: "WRAP" }, {})).toBe("WRAP");
    expect(effectiveLongMode("label", {}, { long_mode: "DOT" })).toBe("DOT");
  });

  it("defaults textarea to WRAP", () => {
    expect(effectiveLongMode("textarea", {}, {})).toBe("WRAP");
  });

  it("textarea still respects explicit CLIP", () => {
    expect(effectiveLongMode("textarea", { long_mode: "CLIP" }, {})).toBe("CLIP");
  });
});

describe("layoutInt", () => {
  it("rounds geometry for preview", () => {
    expect(layoutInt(10.4)).toBe(10);
    expect(layoutInt(10.6)).toBe(11);
  });
});

describe("konvaLongModeTextProps", () => {
  it("maps WRAP and CLIP", () => {
    expect(konvaLongModeTextProps("WRAP")).toEqual({ wrap: "word", ellipsis: false });
    expect(konvaLongModeTextProps("CLIP")).toEqual({ ellipsis: false });
  });

  it("uses ellipsis for DOT and scroll modes", () => {
    expect(konvaLongModeTextProps("DOT")).toEqual({ ellipsis: true });
    expect(konvaLongModeTextProps("SCROLL")).toEqual({ ellipsis: true });
    expect(konvaLongModeTextProps("SCROLL_CIRCULAR")).toEqual({ ellipsis: true });
  });
});
