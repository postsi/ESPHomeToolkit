/**
 * Tests for project.sections helpers: collectWidgetIds, updateSectionsWidgetRef.
 */
import { describe, it, expect } from "vitest";
import {
  collectWidgetIds,
  updateSectionsWidgetRef,
  SECTION_KEYS_WITH_WIDGET_REF,
} from "./projectSections";

describe("projectSections", () => {
  describe("collectWidgetIds", () => {
    it("returns empty set for empty list", () => {
      expect(collectWidgetIds([])).toEqual(new Set());
    });

    it("collects ids from flat widgets", () => {
      const list = [{ id: "a" }, { id: "b" }, { type: "label" }];
      expect(collectWidgetIds(list)).toEqual(new Set(["a", "b"]));
    });

    it("collects ids from nested widgets", () => {
      const list = [
        { id: "root", widgets: [{ id: "child1" }, { id: "child2", widgets: [{ id: "grand" }] }] },
      ];
      expect(collectWidgetIds(list)).toEqual(new Set(["root", "child1", "child2", "grand"]));
    });

    it("ignores null/undefined and non-objects", () => {
      expect(collectWidgetIds([null, undefined, { id: "x" }])).toEqual(new Set(["x"]));
    });
  });

  describe("updateSectionsWidgetRef", () => {
    it("replaces widget: oldId with widget: newId in switch section", () => {
      const sections: Record<string, string> = {
        switch:
          "switch:\n  - platform: lvgl\n    id: my_sw\n    widget: btn1\n    name: My Switch\n",
      };
      updateSectionsWidgetRef(sections, "btn1", "btn_renamed");
      expect(sections.switch).toContain("widget: btn_renamed");
      expect(sections.switch).not.toContain("widget: btn1");
    });

    it("replaces id: oldId with id: newId in same block", () => {
      const sections: Record<string, string> = {
        switch:
          "switch:\n  - platform: lvgl\n    id: btn1\n    widget: btn1\n    name: X\n",
      };
      updateSectionsWidgetRef(sections, "btn1", "btn_renamed");
      expect(sections.switch).toContain("id: btn_renamed");
      expect(sections.switch).toContain("widget: btn_renamed");
      expect(sections.switch).not.toContain("btn1");
    });

    it("updates only the matching key; leaves other sections unchanged", () => {
      const sections: Record<string, string> = {
        switch: "switch:\n  - platform: lvgl\n    widget: w1\n",
        sensor: "sensor:\n  - platform: lvgl\n    widget: w2\n",
      };
      updateSectionsWidgetRef(sections, "w1", "w1_new");
      expect(sections.switch).toContain("widget: w1_new");
      expect(sections.sensor).toContain("widget: w2");
    });

    it("does nothing when oldId === newId", () => {
      const sections: Record<string, string> = {
        switch: "switch:\n  - platform: lvgl\n    widget: x\n",
      };
      const before = sections.switch;
      updateSectionsWidgetRef(sections, "x", "x");
      expect(sections.switch).toBe(before);
    });

    it("does nothing when section has no matching widget ref", () => {
      const sections: Record<string, string> = {
        switch: "switch:\n  - platform: lvgl\n    widget: other\n",
      };
      const before = sections.switch;
      updateSectionsWidgetRef(sections, "missing", "new_id");
      expect(sections.switch).toBe(before);
    });
  });

  describe("SECTION_KEYS_WITH_WIDGET_REF", () => {
    it("includes switch, sensor, and other LVGL component section keys", () => {
      expect(SECTION_KEYS_WITH_WIDGET_REF).toContain("switch");
      expect(SECTION_KEYS_WITH_WIDGET_REF).toContain("sensor");
      expect(SECTION_KEYS_WITH_WIDGET_REF).toContain("number");
      expect(SECTION_KEYS_WITH_WIDGET_REF).toContain("text_sensor");
      expect(SECTION_KEYS_WITH_WIDGET_REF).toContain("binary_sensor");
      expect(SECTION_KEYS_WITH_WIDGET_REF).toContain("light");
      expect(SECTION_KEYS_WITH_WIDGET_REF).toContain("select");
    });
  });
});
