/**
 * bindingConfig: display actions, events, services, and entity_id parsing.
 */
import { describe, it, expect } from "vitest";
import {
  getDisplayActionsForType,
  getEventsForType,
  getServicesForDomain,
  domainFromEntityId,
  formatDisplayBindingSummary,
  formatActionBindingSummary,
  displayActionRequiresNumericSource,
  NUMERIC_ONLY_DISPLAY_ACTIONS,
  DISPLAY_ACTIONS_BY_WIDGET_TYPE,
  EVENTS_BY_WIDGET_TYPE,
} from "./bindingConfig";

describe("bindingConfig", () => {
  describe("domainFromEntityId", () => {
    it("extracts domain from entity_id", () => {
      expect(domainFromEntityId("light.living")).toBe("light");
      expect(domainFromEntityId("sensor.temperature")).toBe("sensor");
      expect(domainFromEntityId("climate.thermostat")).toBe("climate");
    });
    it("returns empty string when no dot", () => {
      expect(domainFromEntityId("")).toBe("");
      expect(domainFromEntityId("nodot")).toBe("");
    });
  });

  describe("displayActionRequiresNumericSource", () => {
    it("returns true for arc_value, bar_value, slider_value", () => {
      expect(displayActionRequiresNumericSource("arc_value")).toBe(true);
      expect(displayActionRequiresNumericSource("bar_value")).toBe(true);
      expect(displayActionRequiresNumericSource("slider_value")).toBe(true);
    });
    it("returns false for label_text, widget_checked", () => {
      expect(displayActionRequiresNumericSource("label_text")).toBe(false);
      expect(displayActionRequiresNumericSource("widget_checked")).toBe(false);
    });
    it("NUMERIC_ONLY_DISPLAY_ACTIONS matches", () => {
      expect(NUMERIC_ONLY_DISPLAY_ACTIONS).toContain("arc_value");
      expect(NUMERIC_ONLY_DISPLAY_ACTIONS).toContain("bar_value");
      expect(NUMERIC_ONLY_DISPLAY_ACTIONS).toContain("slider_value");
    });
  });

  describe("getDisplayActionsForType", () => {
    it("returns label_text for label", () => {
      expect(getDisplayActionsForType("label")).toEqual(["label_text"]);
    });
    it("returns only arc_value for arc (no text; default ESPHome arc has no label)", () => {
      expect(getDisplayActionsForType("arc")).toEqual(["arc_value"]);
    });
    it("returns default label_text for unknown type", () => {
      expect(getDisplayActionsForType("unknown")).toEqual(["label_text"]);
    });
    it("is case-insensitive", () => {
      expect(getDisplayActionsForType("LABEL")).toEqual(["label_text"]);
    });
  });

  describe("getEventsForType", () => {
    it("returns on_click for button", () => {
      expect(getEventsForType("button")).toEqual(["on_click"]);
    });
    it("returns on_release and on_value for arc", () => {
      expect(getEventsForType("arc")).toEqual(["on_release", "on_value"]);
    });
    it("returns empty array for unknown type", () => {
      expect(getEventsForType("unknown")).toEqual([]);
    });
  });

  describe("getServicesForDomain", () => {
    it("returns services for light", () => {
      const svc = getServicesForDomain("light");
      expect(svc.length).toBeGreaterThan(0);
      expect(svc.some((s) => s.service === "light.toggle")).toBe(true);
    });
    it("returns empty array for unknown domain", () => {
      expect(getServicesForDomain("unknown_domain")).toEqual([]);
    });
  });

  describe("DISPLAY_ACTIONS_BY_WIDGET_TYPE coverage", () => {
    it("has entries for label, button, arc, slider, bar, switch, checkbox, led", () => {
      const types = ["label", "button", "arc", "slider", "bar", "switch", "checkbox", "led"];
      for (const t of types) {
        expect(DISPLAY_ACTIONS_BY_WIDGET_TYPE[t], `missing ${t}`).toBeDefined();
        expect(Array.isArray(DISPLAY_ACTIONS_BY_WIDGET_TYPE[t])).toBe(true);
      }
    });
  });

  describe("EVENTS_BY_WIDGET_TYPE coverage", () => {
    it("has entries for button, arc, slider, switch", () => {
      const types = ["button", "arc", "slider", "switch"];
      for (const t of types) {
        expect(EVENTS_BY_WIDGET_TYPE[t], `missing ${t}`).toBeDefined();
        expect(Array.isArray(EVENTS_BY_WIDGET_TYPE[t])).toBe(true);
      }
    });
  });

  describe("formatDisplayBindingSummary (§4.3)", () => {
    const entities = [
      { entity_id: "sensor.living_room_temp", friendly_name: "Living room temperature" },
      { entity_id: "light.shed", friendly_name: "Shed" },
    ];
    it("returns human summary with friendly_name when entity is in list", () => {
      const ln = { source: { entity_id: "sensor.living_room_temp", attribute: "" }, target: { action: "label_text" } };
      expect(formatDisplayBindingSummary(ln, entities)).toContain("Living room temperature");
      expect(formatDisplayBindingSummary(ln, entities)).toContain("sensor.living_room_temp");
      expect(formatDisplayBindingSummary(ln, entities)).toContain("Show as text");
    });
    it("falls back to entity_id when entity not in list", () => {
      const ln = { source: { entity_id: "sensor.unknown" }, target: { action: "label_text" } };
      const s = formatDisplayBindingSummary(ln, entities);
      expect(s).toContain("sensor.unknown");
    });
    it("handles no entity", () => {
      expect(formatDisplayBindingSummary({ source: {} }, entities)).toBe("Shows (no entity)");
    });
  });

  describe("formatActionBindingSummary (§4.3)", () => {
    const entities = [
      { entity_id: "light.shed", friendly_name: "Shed" },
    ];
    it("returns event label and service label with entity_id", () => {
      const ab = { event: "on_click", call: { domain: "light", service: "light.toggle", entity_id: "light.shed" } };
      const s = formatActionBindingSummary(ab, entities);
      expect(s).toContain("On click");
      expect(s).toContain("Toggle");
      expect(s).toContain("light.shed");
    });
    it("handles missing call", () => {
      const s = formatActionBindingSummary({ event: "on_click" }, entities);
      expect(s).toContain("On click");
      expect(s).toContain("?");
    });
  });
});
