/**
 * Simulate using the UI to place canvas items (drop widget, drop prebuilt, move/resize).
 * Ensures the same logic the UI uses produces the expected project state.
 */
import { describe, it, expect, beforeEach } from "vitest";
import {
  defaultProject,
  resetSimulationIdCounter,
  simulateDropWidget,
  simulateDropPrebuilt,
  simulateChangeMany,
  widgetCount,
  findWidgetByType,
} from "./uiSimulation";

describe("uiSimulation", () => {
  beforeEach(() => {
    resetSimulationIdCounter();
  });

  describe("defaultProject", () => {
    it("returns one page with empty widgets", () => {
      const p = defaultProject();
      expect(p.pages).toHaveLength(1);
      expect(p.pages[0].page_id).toBe("main");
      expect(p.pages[0].widgets).toEqual([]);
    });
  });

  describe("simulateDropWidget", () => {
    it("adds one widget with correct type and position", () => {
      const p = defaultProject();
      const next = simulateDropWidget(p, "label", 20, 30);
      expect(widgetCount(next)).toBe(1);
      const w = next.pages[0].widgets[0];
      expect(w.type).toBe("label");
      expect(w.x).toBe(20);
      expect(w.y).toBe(30);
      expect(w.id).toBeDefined();
      expect(w.props).toEqual({});
      expect(w.style).toEqual({});
      expect(w.events).toEqual({});
    });

    it("adds multiple widgets when called in sequence", () => {
      let p = defaultProject();
      p = simulateDropWidget(p, "label", 10, 10);
      p = simulateDropWidget(p, "button", 100, 50);
      p = simulateDropWidget(p, "switch", 200, 80);
      expect(widgetCount(p)).toBe(3);
      expect(p.pages[0].widgets[0].type).toBe("label");
      expect(p.pages[0].widgets[0].x).toBe(10);
      expect(p.pages[0].widgets[1].type).toBe("button");
      expect(p.pages[0].widgets[1].x).toBe(100);
      expect(p.pages[0].widgets[2].type).toBe("switch");
      expect(p.pages[0].widgets[2].x).toBe(200);
    });

    it("does not mutate the original project", () => {
      const p = defaultProject();
      simulateDropWidget(p, "label", 0, 0);
      expect(widgetCount(p)).toBe(0);
    });

    it("gives color_picker and white_picker correct size and props", () => {
      let p = defaultProject();
      p = simulateDropWidget(p, "color_picker", 50, 50);
      const cp = p.pages[0].widgets[0];
      expect(cp.w).toBe(80);
      expect(cp.h).toBe(36);
      expect(cp.props.value).toBe(0x4080ff);
      expect(cp.style.bg_color).toBe(0x4080ff);

      p = simulateDropWidget(p, "white_picker", 150, 50);
      const wp = p.pages[0].widgets[1];
      expect(wp.w).toBe(80);
      expect(wp.h).toBe(36);
      expect(wp.props.value).toBe(326);
    });
  });

  describe("simulateDropPrebuilt", () => {
    it("adds multiple widgets for a prebuilt at (x, y)", () => {
      const p = defaultProject();
      const next = simulateDropPrebuilt(p, "prebuilt_battery", 40, 60);
      expect(widgetCount(next)).toBeGreaterThan(1);
      const root = next.pages[0].widgets[0];
      expect(root.x).toBe(40);
      expect(root.y).toBe(60);
    });

    it("prebuilt_spinbox_buttons adds container + spinbox + buttons", () => {
      const p = defaultProject();
      const next = simulateDropPrebuilt(p, "prebuilt_spinbox_buttons", 10, 20);
      const types = next.pages[0].widgets.map((w: any) => w.type);
      expect(types).toContain("container");
      expect(types).toContain("spinbox");
      expect(types.filter((t: string) => t === "button").length).toBe(2);
    });

    it("does not mutate the original project", () => {
      const p = defaultProject();
      simulateDropPrebuilt(p, "prebuilt_battery", 0, 0);
      expect(widgetCount(p)).toBe(0);
    });
  });

  describe("simulateChangeMany", () => {
    it("updates widget position after drag", () => {
      let p = defaultProject();
      p = simulateDropWidget(p, "label", 10, 10);
      const id = p.pages[0].widgets[0].id;
      p = simulateChangeMany(p, [{ id, patch: { x: 100, y: 200 } }]);
      expect(p.pages[0].widgets[0].x).toBe(100);
      expect(p.pages[0].widgets[0].y).toBe(200);
    });

    it("updates size after resize", () => {
      let p = defaultProject();
      p = simulateDropWidget(p, "label", 0, 0);
      const id = p.pages[0].widgets[0].id;
      p = simulateChangeMany(p, [{ id, patch: { w: 200, h: 80 } }]);
      expect(p.pages[0].widgets[0].w).toBe(200);
      expect(p.pages[0].widgets[0].h).toBe(80);
    });
  });

  describe("findWidgetByType", () => {
    it("returns first widget of given type", () => {
      let p = defaultProject();
      p = simulateDropWidget(p, "label", 0, 0);
      p = simulateDropWidget(p, "button", 50, 50);
      expect(findWidgetByType(p, "label")?.x).toBe(0);
      expect(findWidgetByType(p, "button")?.x).toBe(50);
      expect(findWidgetByType(p, "switch")).toBeUndefined();
    });
  });

  describe("simulated canvas flow", () => {
    it("drop label, then button, then move label — matches expected project shape", () => {
      let p = defaultProject();
      p = simulateDropWidget(p, "label", 20, 30);
      p = simulateDropWidget(p, "button", 120, 80);
      expect(widgetCount(p)).toBe(2);
      const labelId = findWidgetByType(p, "label").id;
      p = simulateChangeMany(p, [{ id: labelId, patch: { x: 40, y: 50 } }]);
      const label = findWidgetByType(p, "label");
      expect(label.x).toBe(40);
      expect(label.y).toBe(50);
      expect(findWidgetByType(p, "button").x).toBe(120);
    });
  });
});
