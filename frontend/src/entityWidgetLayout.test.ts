import { describe, expect, it } from "vitest";
import {
  fitDescendantContainerTrees,
  fitContainerToDirectChildrenBounds,
  fitContainerTreeToDescendantBounds,
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

  it("expands container for arc_labeled visual overflow (labels/ticks outside w×h)", () => {
    const widgets: any[] = [
      { id: "r", type: "container", x: 0, y: 0, w: 200, h: 200 },
      {
        id: "arc",
        type: "arc_labeled",
        parent_id: "r",
        x: 0,
        y: 0,
        w: 120,
        h: 120,
        props: {
          min_value: 0,
          max_value: 100,
          start_angle: 135,
          end_angle: 45,
          mode: "NORMAL",
        },
        style: { tick_length: 0, tick_width: 3, label_font_size: 0 },
      },
    ];
    fitContainerToDirectChildrenBounds(widgets, "r");
    const r = widgets.find((w) => w.id === "r");
    expect(r!.w).toBeGreaterThan(120);
    expect(r!.h).toBeGreaterThan(120);
  });
});

describe("fitContainerTreeToDescendantBounds", () => {
  it("fits nested containers bottom-up so inner clipping bounds grow first", () => {
    const widgets: any[] = [
      { id: "root", type: "container", x: 0, y: 0, w: 300, h: 300 },
      { id: "inner", type: "container", parent_id: "root", x: 20, y: 20, w: 80, h: 80 },
      { id: "lbl", type: "label", parent_id: "inner", x: 70, y: 10, w: 60, h: 20 },
    ];
    fitContainerTreeToDescendantBounds(widgets, "root");
    const inner = widgets.find((w) => w.id === "inner");
    const root = widgets.find((w) => w.id === "root");
    expect(inner).toMatchObject({ x: 0, y: 0, w: 60, h: 20 });
    expect(root).toMatchObject({ w: 60, h: 20 });
  });
});

describe("fitDescendantContainerTrees", () => {
  it("fits nested descendants but leaves selected root shell untouched", () => {
    const widgets: any[] = [
      { id: "root", type: "container", x: 0, y: 0, w: 220, h: 220 },
      { id: "inner", type: "container", parent_id: "root", x: 20, y: 20, w: 40, h: 40 },
      { id: "lbl", type: "label", parent_id: "inner", x: 70, y: 10, w: 60, h: 20 },
    ];
    fitDescendantContainerTrees(widgets, "root");
    const root = widgets.find((w) => w.id === "root");
    const inner = widgets.find((w) => w.id === "inner");
    expect(root).toMatchObject({ w: 220, h: 220 });
    expect(inner).toMatchObject({ w: 60, h: 20 });
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

  it("recursively tightens nested container trees", () => {
    const widgets = [
      { id: "root", type: "container", x: 0, y: 0, w: 200, h: 200 },
      { id: "inner", type: "container", parent_id: "root", x: 20, y: 20, w: 40, h: 40 },
      { id: "lbl", type: "label", parent_id: "inner", x: 70, y: 10, w: 60, h: 20 },
    ];
    const out = normalizeWidgetsForEntityWidgetExport(widgets);
    const root = out.find((w: any) => w.id === "root");
    const inner = out.find((w: any) => w.id === "inner");
    expect(inner).toMatchObject({ w: 60, h: 20 });
    expect(root).toMatchObject({ w: 60, h: 20 });
  });
});
