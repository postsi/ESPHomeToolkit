/**
 * Test harness for Spinbox +/- prebuilt (single spinbox2 widget).
 */
import { describe, it, expect } from "vitest";
import { PREBUILT_WIDGETS } from "./index";

describe("Spinbox +/- prebuilt", () => {
  const prebuilt = PREBUILT_WIDGETS.find((p) => p.id === "prebuilt_spinbox_buttons");
  if (!prebuilt) {
    it("prebuilt_spinbox_buttons exists in PREBUILT_WIDGETS", () => {
      expect(prebuilt).toBeDefined();
    });
    return;
  }

  it("has correct title and description", () => {
    expect(prebuilt.title).toBe("Spinbox +/-");
    expect(prebuilt.description).toMatch(/spinbox2|step|Spinbox2/i);
  });

  it("build() returns one spinbox2 at (x, y)", () => {
    const { widgets } = prebuilt.build({ x: 10, y: 20 });
    expect(widgets.length).toBe(1);
    const w = widgets[0];
    expect(w.type).toBe("spinbox2");
    expect(w.x).toBe(10);
    expect(w.y).toBe(20);
    expect(w.w).toBe(200);
    expect(w.h).toBe(48);
    const props = w.props as Record<string, unknown>;
    expect(props.value).toBe(15);
    expect(props.min_value).toBe(5);
    expect(props.max_value).toBe(30);
    expect(props.step).toBe(1);
    expect(props.decimal_places).toBe(1);
    expect(props.minus_text).toBe("-");
    expect(props.plus_text).toBe("+");
  });
});
