/**
 * Tests for canvas helpers: resize/drag clamping, snap, colors, layout, selection.
 * Catches regressions like the resize-handle bug (negative width/height from Konva).
 */
import { describe, it, expect } from "vitest";
import {
  snap,
  toFillColor,
  fontSizeFromFontId,
  textLayoutFromWidget,
  safeWidgets,
  computeLayoutPositions,
  clampResizeBox,
  clampDragPosition,
  clampDragPositionCentered,
  widgetsInSelectionRect,
  parentInfo,
  absPos,
  type WidgetLike,
} from "./canvasUtils";

describe("canvasUtils", () => {
  describe("snap", () => {
    it("returns n when grid is 0 or 1", () => {
      expect(snap(47, 0)).toBe(47);
      expect(snap(47, 1)).toBe(47);
    });
    it("snaps to grid", () => {
      expect(snap(0, 10)).toBe(0);
      expect(snap(4, 10)).toBe(0);
      expect(snap(5, 10)).toBe(10);
      expect(snap(14, 10)).toBe(10);
      expect(snap(15, 10)).toBe(20);
      expect(snap(23, 10)).toBe(20);
    });
    it("handles negative values", () => {
      expect(snap(-4, 10) + 0).toBe(0); // +0 normalizes -0
      expect(snap(-6, 10)).toBe(-10);
    });
  });

  describe("toFillColor", () => {
    it("converts numeric 0xrrggbb to #hex", () => {
      expect(toFillColor(0x1a1a2e, "#000")).toBe("#1a1a2e");
      expect(toFillColor(0x10b981, "#000")).toBe("#10b981");
      expect(toFillColor(0, "#000")).toBe("#000000");
      expect(toFillColor(0xffffff, "#000")).toBe("#ffffff");
    });
    it("accepts string hex with or without #", () => {
      expect(toFillColor("#3b82f6", "#000")).toBe("#3b82f6");
      expect(toFillColor("3b82f6", "#000")).toBe("#3b82f6");
    });
    it("returns fallback for invalid input", () => {
      expect(toFillColor(null, "#fallback")).toBe("#fallback");
      expect(toFillColor("nothex", "#fallback")).toBe("#fallback");
      expect(toFillColor(0x1000000, "#fallback")).toBe("#fallback");
    });
  });

  describe("fontSizeFromFontId", () => {
    it("parses montserrat_14 style", () => {
      expect(fontSizeFromFontId("montserrat_14")).toBe(14);
      expect(fontSizeFromFontId("roboto_18")).toBe(18);
    });
    it("parses asset:file:size style", () => {
      expect(fontSizeFromFontId("asset:myfont.ttf:16")).toBe(16);
      expect(fontSizeFromFontId("asset:file.ttf:24")).toBe(24);
    });
    it("returns null for invalid", () => {
      expect(fontSizeFromFontId(null)).toBe(null);
      expect(fontSizeFromFontId("")).toBe(null);
      expect(fontSizeFromFontId("nospace")).toBe(null);
    });
  });

  describe("textLayoutFromWidget", () => {
    it("applies padding and defaults to left/top", () => {
      const r = textLayoutFromWidget(10, 20, 100, 50, {}, { pad_left: 4, pad_top: 8 });
      expect(r.x).toBe(14);
      expect(r.y).toBe(28);
      expect(r.width).toBe(96);
      expect(r.height).toBe(42);
      expect(r.align).toBe("left");
      expect(r.verticalAlign).toBe("top");
    });
    it("respects text_align LEFT, CENTER, RIGHT, AUTO", () => {
      expect(textLayoutFromWidget(0, 0, 100, 50, {}, { text_align: "LEFT" }).align).toBe("left");
      expect(textLayoutFromWidget(0, 0, 100, 50, {}, { text_align: "CENTER" }).align).toBe("center");
      expect(textLayoutFromWidget(0, 0, 100, 50, {}, { text_align: "RIGHT" }).align).toBe("right");
      expect(textLayoutFromWidget(0, 0, 100, 50, {}, { text_align: "AUTO" }).align).toBe("left");
    });
    it("uses align for vertical placement (TOP_LEFT -> top, CENTER -> middle, BOTTOM_* -> bottom)", () => {
      expect(textLayoutFromWidget(0, 0, 100, 50, {}, { align: "TOP_LEFT" }).verticalAlign).toBe("top");
      expect(textLayoutFromWidget(0, 0, 100, 50, {}, { align: "CENTER" }).verticalAlign).toBe("middle");
      expect(textLayoutFromWidget(0, 0, 100, 50, {}, { align: "BOTTOM_RIGHT" }).verticalAlign).toBe("bottom");
    });
  });

  describe("safeWidgets", () => {
    it("filters out null/undefined and items without id", () => {
      const list = [
        { id: "a", x: 0, y: 0 },
        null,
        { id: "b", x: 10, y: 10 },
        undefined,
        {} as WidgetLike,
        { id: "c", x: 20, y: 20 },
      ];
      const out = safeWidgets(list);
      expect(out).toHaveLength(3);
      expect(out.map((w) => w.id)).toEqual(["a", "b", "c"]);
    });
    it("handles null/undefined list", () => {
      expect(safeWidgets(null)).toEqual([]);
      expect(safeWidgets(undefined)).toEqual([]);
    });
  });

  describe("computeLayoutPositions", () => {
    it("returns empty map for no widgets or no flex parents", () => {
      expect(computeLayoutPositions([]).size).toBe(0);
      expect(computeLayoutPositions([{ id: "a", x: 0, y: 0, w: 100, h: 50 }]).size).toBe(0);
    });
    it("computes flex_row positions", () => {
      const widgets: WidgetLike[] = [
        { id: "p", x: 0, y: 0, w: 200, h: 100, props: { layout: "flex_row", gap: 8 } },
        { id: "c1", x: 0, y: 0, w: 40, h: 30, parent_id: "p" },
        { id: "c2", x: 0, y: 0, w: 50, h: 30, parent_id: "p" },
      ];
      const pos = computeLayoutPositions(widgets);
      expect(pos.get("c1")).toEqual({ x: 0, y: 0 });
      expect(pos.get("c2")).toEqual({ x: 40 + 8, y: 0 });
    });
    it("computes flex_col positions", () => {
      const widgets: WidgetLike[] = [
        { id: "p", x: 10, y: 20, w: 100, h: 150, props: { layout: "flex_col", gap: 4 }, style: { pad_left: 6 } },
        { id: "c1", x: 0, y: 0, w: 80, h: 30, parent_id: "p" },
        { id: "c2", x: 0, y: 0, w: 80, h: 40, parent_id: "p" },
      ];
      const pos = computeLayoutPositions(widgets);
      expect(pos.get("c1")).toEqual({ x: 10 + 6, y: 20 });
      expect(pos.get("c2")).toEqual({ x: 16, y: 20 + 30 + 4 });
    });
  });

  describe("clampResizeBox (resize handle / Transformer)", () => {
    const cw = 800;
    const ch = 600;
    const min = 20;

    it("leaves box unchanged when inside canvas and positive size", () => {
      const { box, clamped } = clampResizeBox({ x: 50, y: 50, width: 200, height: 100 }, cw, ch, min);
      expect(box).toEqual({ x: 50, y: 50, width: 200, height: 100 });
      expect(clamped).toBe(false);
    });

    it("normalizes negative width (Konva passes when handle dragged past left edge)", () => {
      const { box, clamped } = clampResizeBox({ x: 150, y: 50, width: -100, height: 80 }, cw, ch, min);
      expect(box.x).toBe(50);
      expect(box.width).toBe(100);
      expect(box.y).toBe(50);
      expect(box.height).toBe(80);
      expect(clamped).toBe(false);
    });

    it("normalizes negative height (handle dragged past top edge)", () => {
      const { box } = clampResizeBox({ x: 50, y: 120, width: 100, height: -80 }, cw, ch, min);
      expect(box.x).toBe(50);
      expect(box.y).toBe(40);
      expect(box.width).toBe(100);
      expect(box.height).toBe(80);
    });

    it("normalizes both negative width and height", () => {
      const { box } = clampResizeBox({ x: 200, y: 150, width: -150, height: -100 }, cw, ch, min);
      expect(box.x).toBe(50);
      expect(box.y).toBe(50);
      expect(box.width).toBe(150);
      expect(box.height).toBe(100);
    });

    it("does not produce (0,0) tiny box when resizing from valid position (regression for resize bug)", () => {
      const { box } = clampResizeBox({ x: 100, y: 100, width: -1000, height: -1000 }, cw, ch, min);
      expect(box.width).toBeGreaterThanOrEqual(min);
      expect(box.height).toBeGreaterThanOrEqual(min);
      expect(box.x).toBe(0);
      expect(box.y).toBe(0);
      expect(box.width).toBe(800 - 0);
      expect(box.height).toBe(600 - 0);
    });

    it("enforces min size", () => {
      const { box } = clampResizeBox({ x: 50, y: 50, width: 5, height: 5 }, cw, ch, min);
      expect(box.width).toBe(min);
      expect(box.height).toBe(min);
    });

    it("clamps position and size to canvas bounds", () => {
      const { box, clamped } = clampResizeBox({ x: 700, y: 50, width: 200, height: 100 }, cw, ch, min);
      expect(box.x).toBe(700);
      expect(box.width).toBe(100);
      expect(box.y).toBe(50);
      expect(box.height).toBe(100);
      expect(clamped).toBe(true);
    });

    it("sets clamped only when actually clamped", () => {
      expect(clampResizeBox({ x: 0, y: 0, width: 100, height: 100 }, cw, ch, min).clamped).toBe(false);
      expect(clampResizeBox({ x: -10, y: 0, width: 100, height: 100 }, cw, ch, min).clamped).toBe(true);
    });
  });

  describe("clampDragPosition", () => {
    const cw = 800;
    const ch = 600;

    it("allows position when widget fits", () => {
      const r = clampDragPosition(100, 100, 50, 50, cw, ch);
      expect(r.x).toBe(100);
      expect(r.y).toBe(100);
      expect(r.atLimit).toBe(false);
    });

    it("clamps to stay on canvas", () => {
      const r = clampDragPosition(760, 560, 50, 50, cw, ch);
      expect(r.x).toBe(750);
      expect(r.y).toBe(550);
      expect(r.atLimit).toBe(true);
    });

    it("clamps negative to 0", () => {
      const r = clampDragPosition(-10, -20, 50, 50, cw, ch);
      expect(r.x).toBe(0);
      expect(r.y).toBe(0);
      expect(r.atLimit).toBe(true);
    });
  });

  describe("clampDragPositionCentered", () => {
    it("keeps center inside canvas", () => {
      const r = clampDragPositionCentered(400, 300, 100, 80, 800, 600);
      expect(r.x).toBe(400);
      expect(r.y).toBe(300);
      expect(r.atLimit).toBe(false);
    });
    it("clamps when center would go past edge", () => {
      const r = clampDragPositionCentered(800, 300, 100, 80, 800, 600);
      expect(r.x).toBe(750);
      expect(r.atLimit).toBe(true);
    });
  });

  describe("widgetsInSelectionRect", () => {
    it("returns ids that overlap the box", () => {
      const items = [
        { id: "a", ax: 10, ay: 10, w: 50, h: 50 },
        { id: "b", ax: 70, ay: 10, w: 50, h: 50 },
        { id: "c", ax: 10, ay: 70, w: 50, h: 50 },
      ];
      const ids = widgetsInSelectionRect(0, 60, 0, 60, items);
      expect(ids).toContain("a");
      expect(ids).not.toContain("b");
      expect(ids).not.toContain("c");
    });

    it("returns multiple when box spans several", () => {
      const items = [
        { id: "a", ax: 0, ay: 0, w: 40, h: 40 },
        { id: "b", ax: 50, ay: 0, w: 40, h: 40 },
        { id: "c", ax: 25, ay: 25, w: 40, h: 40 },
      ];
      const ids = widgetsInSelectionRect(10, 80, 10, 60, items);
      expect(ids.sort()).toEqual(["a", "b", "c"]);
    });

    it("returns empty when box does not overlap any", () => {
      const items = [{ id: "a", ax: 100, ay: 100, w: 20, h: 20 }];
      expect(widgetsInSelectionRect(0, 50, 0, 50, items)).toEqual([]);
    });
  });

  describe("parentInfo and absPos", () => {
    const byId = new Map<string, WidgetLike>();
    const w = 800;
    const h = 600;

    it("root widget has parentInfo at origin with canvas size", () => {
      const root: WidgetLike = { id: "r", x: 0, y: 0, w: 100, h: 50 };
      byId.set("r", root);
      const info = parentInfo(root, byId, w, h);
      expect(info).toEqual({ ax: 0, ay: 0, pw: w, ph: h });
    });

    it("TOP_LEFT child position is parent ax+ay + x,y", () => {
      const root: WidgetLike = { id: "r", x: 0, y: 0, w: 200, h: 100 };
      const child: WidgetLike = { id: "c", x: 10, y: 20, w: 50, h: 30, parent_id: "r" };
      byId.set("r", root);
      byId.set("c", child);
      const info = parentInfo(child, byId, w, h);
      expect(info.ax).toBe(0);
      expect(info.ay).toBe(0);
      expect(info.pw).toBe(200);
      expect(info.ph).toBe(100);
      const pos = absPos(child, byId, w, h);
      expect(pos).toEqual({ ax: 10, ay: 20 });
    });

    it("CENTER align uses parent position and child size for placement", () => {
      const root: WidgetLike = { id: "r", x: 100, y: 100, w: 200, h: 100 };
      const child: WidgetLike = { id: "c", x: 0, y: 0, w: 80, h: 40, parent_id: "r", props: { align: "CENTER" } };
      byId.set("r", root);
      byId.set("c", child);
      const pos = absPos(child, byId, w, h);
      expect(pos.ax).toBe(100);
      expect(pos.ay).toBe(100);
    });
  });
});
