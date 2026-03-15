
export type BindingKind = "state" | "attribute_number" | "attribute_text" | "binary";

export type BindingSpec = {
  entity_id: string;
  kind: BindingKind;
  attribute?: string;
  note?: string;
};

export type DomainPreset = {
  domain: string;
  title: string;
  recommended: Omit<BindingSpec, "entity_id">[];
};

export const DOMAIN_PRESETS: DomainPreset[] = [
  { domain: "light", title: "Light", recommended: [
    { kind: "state", note: "state (on/off)" },
    { kind: "attribute_number", attribute: "brightness", note: "brightness (0-255)" },
    { kind: "attribute_text", attribute: "rgb_color", note: "rgb_color" },
    { kind: "attribute_number", attribute: "color_temp", note: "color_temp (mireds)" },
  ]},
  { domain: "switch", title: "Switch", recommended: [
    { kind: "state", note: "state (on/off)" },
  ]},
  { domain: "cover", title: "Cover", recommended: [
    { kind: "state", note: "state" },
    { kind: "attribute_number", attribute: "current_position", note: "current_position (0-100)" },
  ]},
  { domain: "climate", title: "Thermostat (climate)", recommended: [
    { kind: "state", note: "hvac mode/state" },
    { kind: "attribute_number", attribute: "current_temperature", note: "current temp" },
    { kind: "attribute_number", attribute: "temperature", note: "setpoint" },
  ]},
  { domain: "media_player", title: "Media Player", recommended: [
    { kind: "state", note: "state" },
    { kind: "attribute_text", attribute: "media_title", note: "media_title" },
    { kind: "attribute_number", attribute: "volume_level", note: "volume_level (0-1)" },
  ]},
  { domain: "fan", title: "Fan", recommended: [
    { kind: "state", note: "on/off" },
    { kind: "attribute_number", attribute: "percentage", note: "percentage (0-100)" },
  ]},
  { domain: "lock", title: "Lock", recommended: [
    { kind: "state", note: "locked/unlocked" },
  ]},
  { domain: "vacuum", title: "Vacuum", recommended: [
    { kind: "state", note: "state" },
    { kind: "attribute_number", attribute: "battery_level", note: "battery_level" },
  ]},
  { domain: "alarm_control_panel", title: "Alarm Panel", recommended: [
    { kind: "state", note: "state" },
  ]},
];
