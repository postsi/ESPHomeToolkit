import { describe, expect, it } from "vitest";
import { normalizeWidgetsForEntityWidgetExport } from "./entityWidgetLayout";

describe("normalizeWidgetsForEntityWidgetExport", () => {
  it("leaves a single-root tree unchanged", () => {
    const widgets = [
      { id: "r", type: "container", x: 10, y: 20, w: 100, h: 50 },
      { id: "a", type: "label", parent_id: "r", x: 5, y: 5, w: 40, h: 20 },
    ];
    const out = normalizeWidgetsForEntityWidgetExport(widgets);
    expect(out).toEqual(widgets);
  });

  it("wraps multiple top-level widgets in a new root", () => {
    const widgets = [
      { id: "a", type: "label", x: 10, y: 10, w: 20, h: 20 },
      { id: "b", type: "label", x: 50, y: 10, w: 20, h: 20 },
    ];
    const out = normalizeWidgetsForEntityWidgetExport(widgets);
    expect(out.length).toBe(3);
    const root = out[0];
    expect(root.type).toBe("container");
    expect(root.x).toBe(10);
    expect(root.y).toBe(10);
    expect(root.w).toBe(60);
    expect(root.h).toBe(20);
    expect(out[1]).toMatchObject({ id: "a", parent_id: root.id, x: 0, y: 0 });
    expect(out[2]).toMatchObject({ id: "b", parent_id: root.id, x: 40, y: 0 });
  });
});
