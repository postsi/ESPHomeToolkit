import { describe, expect, it } from "vitest";
import {
  fitContainerToDirectChildrenBounds,
  normalizeWidgetsForEntityWidgetExport,
} from "./entityWidgetLayout";

describe("fitContainerToDirectChildrenBounds", () => {
  it("sizes container to children and normalizes child origin", () => {
    const widgets: any[] = [
      { id: "r", type: "container", x: 0, y: 0, w: 999, h: 999 },
      { id: "a", type: "label", parent_id: "r", x: 10, y: 8, w: 50, h: 20 },
      { id: "b", type: "label", parent_id: "r", x: 10, y: 40, w: 100, h: 30 },
    ];
    fitContainerToDirectChildrenBounds(widgets, "r");
    const r = widgets.find((w) => w.id === "r");
    expect(r.w).toBe(100);
    expect(r.h).toBe(62);
    expect(widgets.find((w) => w.id === "a")).toMatchObject({ x: 0, y: 0 });
    expect(widgets.find((w) => w.id === "b")).toMatchObject({ x: 0, y: 32 });
  });
});

describe("normalizeWidgetsForEntityWidgetExport", () => {
  it("tightens a single root container to its direct children", () => {
    const widgets = [
      { id: "r", type: "container", x: 10, y: 20, w: 200, h: 200 },
      { id: "a", type: "label", parent_id: "r", x: 0, y: 0, w: 40, h: 20 },
    ];
    const out = normalizeWidgetsForEntityWidgetExport(widgets);
    expect(out[0]).toMatchObject({ id: "r", w: 40, h: 20 });
    expect(out[1]).toMatchObject({ id: "a", x: 0, y: 0 });
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
