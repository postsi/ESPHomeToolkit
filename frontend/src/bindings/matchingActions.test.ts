/**
 * matchingActions: getMatchingActionBindings for display→action binding creation.
 */
import { describe, it, expect } from "vitest";
import {
  getMatchingActionBindings,
  INPUT_WIDGET_TYPES,
  OPTION_SELECT_WIDGET_TYPES,
  CLICK_TOGGLE_WIDGET_TYPES,
  SELECT_OPTION_TEXT_SENTINEL,
} from "./matchingActions";

describe("matchingActions", () => {
  describe("constants", () => {
    it("INPUT_WIDGET_TYPES includes arc, slider, bar, spinbox, switch, checkbox", () => {
      expect(INPUT_WIDGET_TYPES).toContain("arc");
      expect(INPUT_WIDGET_TYPES).toContain("slider");
      expect(INPUT_WIDGET_TYPES).toContain("bar");
      expect(INPUT_WIDGET_TYPES).toContain("switch");
    });
    it("OPTION_SELECT_WIDGET_TYPES includes dropdown and roller", () => {
      expect(OPTION_SELECT_WIDGET_TYPES).toContain("dropdown");
      expect(OPTION_SELECT_WIDGET_TYPES).toContain("roller");
    });
    it("CLICK_TOGGLE_WIDGET_TYPES includes button and container", () => {
      expect(CLICK_TOGGLE_WIDGET_TYPES).toContain("button");
      expect(CLICK_TOGGLE_WIDGET_TYPES).toContain("container");
    });
    it("SELECT_OPTION_TEXT_SENTINEL is defined for compiler", () => {
      expect(SELECT_OPTION_TEXT_SENTINEL).toBeDefined();
      expect(typeof SELECT_OPTION_TEXT_SENTINEL).toBe("string");
    });
  });

  describe("getMatchingActionBindings", () => {
    it("returns light turn_on with brightness for arc + light.brightness", () => {
      const out = getMatchingActionBindings(
        "arc",
        "light.desk",
        "attribute_number",
        "brightness"
      );
      expect(out.length).toBeGreaterThan(0);
      expect(out[0].call.domain).toBe("light");
      expect(out[0].call.service).toBe("turn_on");
      expect(out[0].event).toBe("on_release");
    });

    it("returns climate set_temperature for slider + climate.temperature", () => {
      const out = getMatchingActionBindings(
        "slider",
        "climate.thermostat",
        "attribute_number",
        "temperature"
      );
      expect(out.length).toBeGreaterThan(0);
      expect(out[0].call.domain).toBe("climate");
      expect(out[0].call.service).toBe("set_temperature");
    });

    it("returns switch toggle for button + binary/state", () => {
      const out = getMatchingActionBindings(
        "button",
        "switch.plug",
        "binary",
        ""
      );
      expect(out.length).toBeGreaterThan(0);
      expect(out[0].call.domain).toBe("switch");
      expect(out[0].call.service).toBe("toggle");
      expect(out[0].event).toBe("on_click");
    });

    it("returns empty for unsupported combination", () => {
      const out = getMatchingActionBindings(
        "label",
        "sensor.temp",
        "state",
        ""
      );
      expect(out).toEqual([]);
    });

    it("returns dropdown climate set_hvac_mode for state", () => {
      const out = getMatchingActionBindings(
        "dropdown",
        "climate.room",
        "state",
        ""
      );
      expect(out.length).toBeGreaterThan(0);
      expect(out[0].call.service).toBe("set_hvac_mode");
      expect(out[0].call.data?.hvac_mode).toBe(SELECT_OPTION_TEXT_SENTINEL);
    });

    it("returns dropdown select.select_option for select entity", () => {
      const out = getMatchingActionBindings(
        "dropdown",
        "select.mode",
        "state",
        ""
      );
      expect(out.length).toBe(1);
      expect(out[0].event).toBe("on_change");
      expect(out[0].call.domain).toBe("select");
      expect(out[0].call.service).toBe("select_option");
      expect(out[0].call.data?.option).toBe(SELECT_OPTION_TEXT_SENTINEL);
    });

    it("returns roller input_select.select_option for input_select entity", () => {
      const out = getMatchingActionBindings(
        "roller",
        "input_select.scene",
        "state",
        ""
      );
      expect(out.length).toBe(1);
      expect(out[0].event).toBe("on_change");
      expect(out[0].call.domain).toBe("input_select");
      expect(out[0].call.service).toBe("select_option");
      expect(out[0].call.data?.option).toBe(SELECT_OPTION_TEXT_SENTINEL);
    });
  });
});
