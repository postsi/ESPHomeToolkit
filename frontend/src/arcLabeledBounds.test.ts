import { describe, expect, it } from "vitest";
import { arcLabeledVisualOverflowPad } from "./arcLabeledBounds";

describe("arcLabeledVisualOverflowPad", () => {
  it("returns non-zero padding when scale labels extend past the 120×120 box (matches prebuilt arc)", () => {
    const pad = arcLabeledVisualOverflowPad({
      type: "arc_labeled",
      w: 120,
      h: 120,
      props: {
        min_value: 0,
        max_value: 100,
        start_angle: 135,
        end_angle: 45,
        rotation: 0,
        mode: "NORMAL",
      },
      style: {
        tick_length: 0,
        tick_width: 3,
        label_font_size: 0,
        label_text_font: "",
      },
    });
    const sum = pad.left + pad.top + pad.right + pad.bottom;
    expect(sum).toBeGreaterThan(8);
  });

  it("returns zero padding for non-arc_labeled", () => {
    expect(arcLabeledVisualOverflowPad({ type: "label", w: 50, h: 20 })).toEqual({
      left: 0,
      top: 0,
      right: 0,
      bottom: 0,
    });
  });
});
