/**
 * Binding Builder: display actions and action-binding events filtered by widget type.
 * Services listed per domain for action bindings (user sees only relevant options).
 */

export type DisplayAction = "label_text" | "slider_value" | "arc_value" | "bar_value" | "widget_checked" | "button_bg_color" | "button_white_temp" | "led_brightness";

/** Display target actions allowed per widget type (what property of the widget gets the HA value). */
export const DISPLAY_ACTIONS_BY_WIDGET_TYPE: Record<string, DisplayAction[]> = {
  label: ["label_text"],
  button: ["label_text", "widget_checked"],
  container: ["label_text", "widget_checked"],
  arc: ["arc_value"],
  arc_labeled: ["arc_value"],
  slider: ["slider_value", "label_text"],
  dropdown: ["label_text"],
  switch: ["widget_checked", "label_text"],
  checkbox: ["widget_checked", "label_text"],
  led: ["led_brightness"],
  image: [],
  bar: ["bar_value", "label_text"],
  spinner: [],
  roller: ["label_text"],
  spinbox: ["label_text"],
  textarea: ["label_text"],
  qrcode: ["label_text"],
  color_picker: ["button_bg_color", "label_text"],
  white_picker: ["button_white_temp", "label_text"],
  buttonmatrix: [],
};

/** Human-readable labels for display actions. */
export const DISPLAY_ACTION_LABELS: Record<DisplayAction, string> = {
  label_text: "Show as text",
  slider_value: "Set slider position",
  arc_value: "Set arc value",
  bar_value: "Set bar value",
  widget_checked: "Set on/off state",
  button_bg_color: "Set button colour",
  button_white_temp: "Set white temperature",
  led_brightness: "Set brightness (0–100)",
};

/** Events that can trigger an action binding, per widget type (ESPHome event names). */
export const EVENTS_BY_WIDGET_TYPE: Record<string, string[]> = {
  button: ["on_click"],
  container: ["on_click"],
  arc: ["on_release", "on_value"],
  arc_labeled: ["on_release", "on_value"],
  slider: ["on_release", "on_value"],
  dropdown: ["on_value", "on_change"],
  switch: ["on_change"],
  checkbox: ["on_change"],
  label: [],
  led: [],
  image: [],
  bar: ["on_release", "on_value"],
  spinner: [],
  roller: ["on_change"],
  spinbox: ["on_change"],
  textarea: ["on_value", "on_ready", "on_focus", "on_defocus"],
  qrcode: [],
  color_picker: ["on_click", "on_apply"],
  white_picker: ["on_click", "on_apply"],
  buttonmatrix: ["on_value"],
  keyboard: ["on_value"],
};

/** Event key -> human label. */
export const EVENT_LABELS: Record<string, string> = {
  on_click: "On click",
  on_release: "On release",
  on_value: "On value change",
  on_change: "On change",
  on_ready: "On ready",
  on_focus: "On focus",
  on_defocus: "On defocus",
  on_apply: "On apply",
};

/** Services relevant to each HA domain (for action binding service dropdown). */
export const SERVICES_BY_DOMAIN: Record<string, { service: string; label: string }[]> = {
  switch: [
    { service: "switch.toggle", label: "Toggle" },
    { service: "switch.turn_on", label: "Turn on" },
    { service: "switch.turn_off", label: "Turn off" },
  ],
  light: [
    { service: "light.toggle", label: "Toggle" },
    { service: "light.turn_on", label: "Turn on" },
    { service: "light.turn_off", label: "Turn off" },
  ],
  climate: [
    { service: "climate.set_temperature", label: "Set temperature" },
    { service: "climate.set_hvac_mode", label: "Set HVAC mode" },
    { service: "climate.set_preset_mode", label: "Set preset mode" },
    { service: "climate.set_fan_mode", label: "Set fan mode" },
  ],
  cover: [
    { service: "cover.open_cover", label: "Open" },
    { service: "cover.close_cover", label: "Close" },
    { service: "cover.stop_cover", label: "Stop" },
    { service: "cover.set_cover_position", label: "Set position" },
  ],
  fan: [
    { service: "fan.toggle", label: "Toggle" },
    { service: "fan.turn_on", label: "Turn on" },
    { service: "fan.turn_off", label: "Turn off" },
    { service: "fan.set_percentage", label: "Set percentage" },
  ],
  lock: [
    { service: "lock.lock", label: "Lock" },
    { service: "lock.unlock", label: "Unlock" },
  ],
  media_player: [
    { service: "media_player.media_play_pause", label: "Play/Pause" },
    { service: "media_player.media_previous_track", label: "Previous" },
    { service: "media_player.media_next_track", label: "Next" },
    { service: "media_player.volume_set", label: "Set volume" },
  ],
  input_boolean: [
    { service: "input_boolean.toggle", label: "Toggle" },
  ],
  number: [
    { service: "number.set_value", label: "Set value" },
  ],
  input_number: [
    { service: "input_number.set_value", label: "Set value" },
  ],
  script: [
    { service: "script.turn_on", label: "Run" },
  ],
  esptoolkit: [
    { service: "set_light_rgb", label: "Set light RGB (colour picker)" },
    { service: "set_light_color_temp", label: "Set light white temp (white picker)" },
  ],
};

/** Display actions that accept only numeric values (arc, bar, slider). Do not offer state (text) for these. */
export const NUMERIC_ONLY_DISPLAY_ACTIONS: DisplayAction[] = ["arc_value", "bar_value", "slider_value"];

export function displayActionRequiresNumericSource(action: string): boolean {
  return NUMERIC_ONLY_DISPLAY_ACTIONS.includes(action as DisplayAction);
}

export function getDisplayActionsForType(widgetType: string): DisplayAction[] {
  const t = String(widgetType ?? "").toLowerCase();
  return DISPLAY_ACTIONS_BY_WIDGET_TYPE[t] ?? ["label_text"];
}

export function getEventsForType(widgetType: string): string[] {
  const t = String(widgetType ?? "").toLowerCase();
  return EVENTS_BY_WIDGET_TYPE[t] ?? [];
}

export function getServicesForDomain(domain: string): { service: string; label: string }[] {
  return SERVICES_BY_DOMAIN[domain] ?? [];
}

export function domainFromEntityId(entityId: string): string {
  const dot = String(entityId || "").indexOf(".");
  return dot > 0 ? String(entityId).slice(0, dot) : "";
}

type EntityLike = { entity_id?: string; friendly_name?: string };

/** Human summary for a display binding (link): "Shows Living room temp (sensor.living_room_temp)" */
export function formatDisplayBindingSummary(
  ln: { source?: Record<string, unknown>; target?: { action?: string; yaml_override?: string } },
  entities: EntityLike[]
): string {
  const src = (ln?.source || {}) as Record<string, unknown>;
  const ent = String(src.entity_id || "").trim();
  const srcType = String(src.type || "").trim();
  const action = String(ln?.target?.action || "").trim();
  const actionLabel = action ? (DISPLAY_ACTION_LABELS[action as DisplayAction] || action) : "";

  // ESPHome device-local sources (no HA entity_id on the link)
  if (srcType === "local_switch") {
    const sid = String(src.switch_id || "").trim();
    const st = String(src.state || "").trim();
    const tail = actionLabel || (ln?.target?.yaml_override ? "custom YAML" : "widget update");
    return `Device switch "${sid || "?"}" (${st || "?"}) → ${tail}`;
  }
  if (srcType === "local_climate") {
    const cid = String(src.climate_id || "").trim();
    const st = String(src.state || "").trim();
    const tail = ln?.target?.yaml_override ? "custom YAML" : "widget update";
    return `Device climate "${cid || "?"}" (${st || "?"}) → ${tail}`;
  }
  if (srcType === "interval") {
    const sec = src.interval_seconds != null ? String(src.interval_seconds) : "?";
    const updates = Array.isArray(src.updates) ? src.updates.length : 0;
    return `Interval every ${sec}s → ${updates} widget update(s)`;
  }

  const attr = String(src.attribute || "").trim();
  const label = ent ? (entities.find((e) => e?.entity_id === ent)?.friendly_name || ent) : "";
  if (!ent) return "Shows (no entity)";
  const part = label || ent;
  const attrPart = attr ? ` · ${attr}` : "";
  return `Shows ${part} (${ent})${attrPart}${actionLabel ? ` → ${actionLabel}` : ""}`;
}

/** Short right-hand label for link row (entity id or device-local source). */
export function formatLinkSourceRef(ln: { source?: Record<string, unknown> }): string {
  const src = (ln?.source || {}) as Record<string, unknown>;
  const ent = String(src.entity_id || "").trim();
  if (ent) {
    const attr = String(src.attribute || "").trim();
    return attr ? `${ent} [${attr}]` : ent;
  }
  const t = String(src.type || "").trim();
  if (t === "local_switch") return `device:switch:${String(src.switch_id || "").trim() || "?"}`;
  if (t === "local_climate") return `device:climate:${String(src.climate_id || "").trim() || "?"}`;
  if (t === "interval") return `interval:${src.interval_seconds != null ? String(src.interval_seconds) : "?"}s`;
  return "—";
}

/** Human summary for an action binding: "On click → Toggle (light.shed)" */
export function formatActionBindingSummary(
  ab: { event?: string; call?: { domain?: string; service?: string; entity_id?: string } },
  entities: EntityLike[]
): string {
  const ev = String(ab?.event || "").trim();
  const call = ab?.call || {};
  const domain = String(call?.domain || "").trim();
  const service = String(call?.service || "").trim();
  const entityId = String(call?.entity_id || "").trim();
  const eventLabel = ev ? (EVENT_LABELS[ev] || ev) : "?";
  const opts = getServicesForDomain(domain);
  const serviceLabel = opts.find((o) => o.service === service)?.label || service;
  const entityLabel = entityId ? (entities.find((e) => e?.entity_id === entityId)?.friendly_name || entityId) : "";
  const target = !service && !entityId ? "?" : (entityId ? `${serviceLabel || service || "?"} (${entityId})` : (serviceLabel || service || "?"));
  return `${eventLabel} → ${target}`;
}
