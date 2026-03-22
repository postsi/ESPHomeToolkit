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
  formatLinkSourceRef,
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
    it("summarizes local_switch without HA entity_id", () => {
      const ln = {
        source: { type: "local_switch", switch_id: "heat_relay", state: "on" },
        target: { action: "widget_checked" },
      };
      const s = formatDisplayBindingSummary(ln, entities);
      expect(s).toContain("heat_relay");
      expect(s).toContain("Device switch");
    });
    it("summarizes local_climate", () => {
      const ln = {
        source: { type: "local_climate", climate_id: "main_thermostat", state: "HEAT" },
        target: { yaml_override: "foo: bar" },
      };
      const s = formatDisplayBindingSummary(ln, entities);
      expect(s).toContain("main_thermostat");
      expect(s).toContain("Device climate");
      expect(s).toContain("custom YAML");
    });
    it("local_climate includes display action when target.action is set", () => {
      const ln = {
        source: { type: "local_climate", climate_id: "c1", state: "HEAT" },
        target: { action: "arc_value", yaml_override: "then:\n  - x" },
      };
      const s = formatDisplayBindingSummary(ln, entities);
      expect(s).toContain("Set arc value");
      expect(s).toContain("ESPHome YAML");
    });
    it("summarizes interval link", () => {
      const ln = {
        source: { type: "interval", interval_seconds: 30, updates: [{ widget_id: "a" }, { widget_id: "b" }] },
        target: {},
      };
      expect(formatDisplayBindingSummary(ln, entities)).toContain("30s");
      expect(formatDisplayBindingSummary(ln, entities)).toContain("2 widget");
    });
    it("interval link includes display_hint snippets from updates", () => {
      const ln = {
        source: {
          type: "interval",
          interval_seconds: 1,
          updates: [{ widget_id: "arc_all", display_hint: "ESPHome climate `climate_all` · setpoint (not an HA entity link)" }],
        },
        target: {},
      };
      expect(formatDisplayBindingSummary(ln, entities)).toContain("ESPHome climate");
    });
  });

  describe("formatLinkSourceRef", () => {
    it("returns entity_id and optional attribute", () => {
      expect(formatLinkSourceRef({ source: { entity_id: "sensor.a", attribute: "temp" } })).toBe("sensor.a [temp]");
      expect(formatLinkSourceRef({ source: { entity_id: "light.k" } })).toBe("light.k");
    });
    it("returns device-local refs", () => {
      expect(formatLinkSourceRef({ source: { type: "local_switch", switch_id: "sw1" } })).toBe("device:switch:sw1");
      expect(formatLinkSourceRef({ source: { type: "local_climate", climate_id: "cl1" } })).toBe("device:climate:cl1");
      expect(formatLinkSourceRef({ source: { type: "interval", interval_seconds: 5 } })).toBe("interval:5s");
    });
    it("returns em dash when unknown", () => {
      expect(formatLinkSourceRef({ source: {} })).toBe("—");
    });
  });

  describe("formatActionBindingSummary (§4.3)", () => {
    const entities = [
      { entity_id: "light.shed", friendly_name: "Shed" },
    ];
    it("summarizes ESPHome yaml_override climate.control", () => {
      const ab = {
        event: "on_release",
        yaml_override: "then:\n  - climate.control:\n      id: climate_all\n",
      };
      expect(formatActionBindingSummary(ab, entities)).toContain("climate.control");
      expect(formatActionBindingSummary(ab, entities)).toContain("ESPHome");
    });
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
