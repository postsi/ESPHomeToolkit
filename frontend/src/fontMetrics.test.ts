import { describe, it, expect } from "vitest";
import { fontPxFromId } from "./fontMetrics";

describe("fontPxFromId (parity with views.py::_font_px_from_id)", () => {
  it("defaults when empty", () => {
    expect(fontPxFromId(undefined)).toBe(14);
    expect(fontPxFromId("")).toBe(14);
    expect(fontPxFromId("   ")).toBe(14);
  });

  it("parses montserrat_NN suffix", () => {
    expect(fontPxFromId("montserrat_14")).toBe(14);
    expect(fontPxFromId("montserrat_24")).toBe(24);
  });

  it("parses asset:TTF:NN", () => {
    expect(fontPxFromId("asset:Foo.ttf:18")).toBe(18);
  });

  it("clamps suffix range", () => {
    expect(fontPxFromId("x_5")).toBe(6);
    expect(fontPxFromId("x_96")).toBe(96);
    expect(fontPxFromId("x_200")).toBe(96);
  });
});
