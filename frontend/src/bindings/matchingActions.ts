/**
 * Opt-in "create matching action bindings": when user adds a display binding to an input widget,
 * we can create the corresponding action binding(s) so the widget sends value/state to HA.
 * Step for increment/decrement widgets (e.g. spinbox) comes from widget props (decimal_places);
 * the action sends the new value (x) from the event — no read-add-set in the action.
 *
 * For dropdown/roller, the device event passes selected index (x). We use a sentinel in data
 * so the compiler expands it to a lambda that maps index -> option string (e.g. for set_hvac_mode).
 */

import { domainFromEntityId } from "./bindingConfig";

/** Sentinel for action binding data: compiler replaces with lambda mapping selected index x to option text. */
export const SELECT_OPTION_TEXT_SENTINEL = "!lambda SELECT_OPTION_TEXT";

export const INPUT_WIDGET_TYPES = ["arc", "slider", "bar", "spinbox", "switch", "checkbox"] as const;

/** Widgets that send selected option (index) and can have matching actions for text-based services (e.g. climate HVAC mode). */
export const OPTION_SELECT_WIDGET_TYPES = ["dropdown", "roller"] as const;

/** Widgets that act as a click/tap and can toggle binary entities (on_click → toggle). */
export const CLICK_TOGGLE_WIDGET_TYPES = ["button", "container"] as const;

export type MatchingActionBinding = {
  event: string;
  call: { domain: string; service: string; entity_id?: string; data?: Record<string, unknown> };
};

/**
 * Returns action bindings to create when user opts in to "also create action bindings"
 * for a display binding. widgetType, entity_id, domain, kind (state | attribute_number | attribute_text | binary), attribute (e.g. temperature, brightness).
 * Returns [] if no matching action is defined for this combination.
 */
export function getMatchingActionBindings(
  widgetType: string,
  entity_id: string,
  kind: string,
  attribute: string,
  preferredEvent?: "on_release" | "on_value" | "on_change"
): MatchingActionBinding[] {
  const domain = domainFromEntityId(entity_id);
  const type = String(widgetType).toLowerCase();

  // Numeric value widgets: arc, slider, bar, spinbox — event passes value as x
  const numericValueEvents: Record<string, string> = {
    arc: preferredEvent === "on_value" ? "on_value" : "on_release",
    slider: preferredEvent === "on_value" ? "on_value" : "on_release",
    bar: preferredEvent === "on_value" ? "on_value" : "on_release",
    spinbox: "on_change",
  };
  const eventForValue = numericValueEvents[type];
  if (eventForValue && (kind === "attribute_number" || (kind === "state" && domain === "number"))) {
    if (domain === "climate" && attribute === "temperature") {
      return [
        {
          event: eventForValue,
          call: {
            domain: "climate",
            service: "set_temperature",
            entity_id,
            data: { temperature: "!lambda return (float)x;" },
          },
        },
      ];
    }
    if (domain === "light" && (attribute === "brightness" || !attribute)) {
      return [
        {
          event: eventForValue,
          call: {
            domain: "light",
            service: "turn_on",
            entity_id,
            data: { brightness: "!lambda return (int)x;" },
          },
        },
      ];
    }
    if (domain === "number") {
      return [
        {
          event: eventForValue,
          call: {
            domain: "number",
            service: "set_value",
            entity_id,
            data: { value: "!lambda return (float)x;" },
          },
        },
      ];
    }
    if (domain === "input_number") {
      return [
        {
          event: eventForValue,
          call: {
            domain: "input_number",
            service: "set_value",
            entity_id,
            data: { value: "!lambda return (float)x;" },
          },
        },
      ];
    }
    if (domain === "cover" && (attribute === "current_position" || attribute === "position" || !attribute)) {
      return [
        {
          event: eventForValue,
          call: {
            domain: "cover",
            service: "set_cover_position",
            entity_id,
            data: { position: "!lambda return (int)x;" },
          },
        },
      ];
    }
    if (domain === "fan" && (attribute === "percentage" || !attribute)) {
      return [
        {
          event: eventForValue,
          call: {
            domain: "fan",
            service: "set_percentage",
            entity_id,
            data: { percentage: "!lambda return (int)x;" },
          },
        },
      ];
    }
    if (domain === "media_player" && (attribute === "volume_level" || !attribute)) {
      return [
        {
          event: eventForValue,
          call: {
            domain: "media_player",
            service: "volume_set",
            entity_id,
            data: { volume_level: "!lambda return (float)x / 100.0;" },
          },
        },
      ];
    }
  }

  // Option-select widgets: dropdown, roller — event passes selected index (x); compiler maps index -> option text
  if ((type === "dropdown" || type === "roller") && (kind === "state" || kind === "attribute_text")) {
    const eventForOption = type === "dropdown" ? "on_change" : "on_change";
    if (domain === "climate") {
      if (attribute === "hvac_mode" || (!attribute && kind === "state")) {
        return [
          {
            event: eventForOption,
            call: {
              domain: "climate",
              service: "set_hvac_mode",
              entity_id,
              data: { hvac_mode: SELECT_OPTION_TEXT_SENTINEL },
            },
          },
        ];
      }
      if (attribute === "preset_mode") {
        return [
          {
            event: eventForOption,
            call: {
              domain: "climate",
              service: "set_preset_mode",
              entity_id,
              data: { preset_mode: SELECT_OPTION_TEXT_SENTINEL },
            },
          },
        ];
      }
      if (attribute === "fan_mode") {
        return [
          {
            event: eventForOption,
            call: {
              domain: "climate",
              service: "set_fan_mode",
              entity_id,
              data: { fan_mode: SELECT_OPTION_TEXT_SENTINEL },
            },
          },
        ];
      }
    }
    if (domain === "fan" && attribute === "preset_mode") {
      return [
        {
          event: eventForOption,
          call: {
            domain: "fan",
            service: "set_preset_mode",
            entity_id,
            data: { preset_mode: SELECT_OPTION_TEXT_SENTINEL },
          },
        },
      ];
    }
    if (domain === "select" && (kind === "state" || !attribute)) {
      return [
        {
          event: eventForOption,
          call: {
            domain: "select",
            service: "select_option",
            entity_id,
            data: { option: SELECT_OPTION_TEXT_SENTINEL },
          },
        },
      ];
    }
    if (domain === "input_select" && (kind === "state" || !attribute)) {
      return [
        {
          event: eventForOption,
          call: {
            domain: "input_select",
            service: "select_option",
            entity_id,
            data: { option: SELECT_OPTION_TEXT_SENTINEL },
          },
        },
      ];
    }
  }

  // Binary widgets: switch, checkbox — event passes checked state; we use toggle
  if ((type === "switch" || type === "checkbox") && kind === "binary") {
    if (domain === "switch") {
      return [{ event: "on_change", call: { domain: "switch", service: "toggle", entity_id } }];
    }
    if (domain === "light") {
      return [{ event: "on_change", call: { domain: "light", service: "toggle", entity_id } }];
    }
    if (domain === "input_boolean") {
      return [{ event: "on_change", call: { domain: "input_boolean", service: "toggle", entity_id } }];
    }
  }

  // Click widgets: button, container — on_click → toggle (e.g. show switch state on button, tap to toggle)
  if ((type === "button" || type === "container") && kind === "binary") {
    if (domain === "switch") {
      return [{ event: "on_click", call: { domain: "switch", service: "toggle", entity_id } }];
    }
    if (domain === "light") {
      return [{ event: "on_click", call: { domain: "light", service: "toggle", entity_id } }];
    }
    if (domain === "input_boolean") {
      return [{ event: "on_click", call: { domain: "input_boolean", service: "toggle", entity_id } }];
    }
  }

  return [];
}
