export type DeviceSummary = {
  device_id: string;
  slug: string;
  name: string;
  hardware_recipe_id?: string | null;
  api_key?: string | null;
};

export type WidgetSchemaIndexItem = {
  type: string;
  title: string;
  description?: string;
};

export type WidgetSchema = {
  type: string;
  title: string;
  description?: string;
  props?: Record<string, any>;
  style?: Record<string, any>;
  events?: Record<string, any>;
};

/** One action binding: when widget fires event, call HA service. Optional yaml_override: if set, compiler uses this instead of generating from call. */
export type ActionBinding = {
  widget_id: string;
  event: string; // e.g. on_click, on_release, on_value
  call: { domain: string; service: string; entity_id?: string; data?: Record<string, unknown> };
  yaml_override?: string; // when set, compiler uses this; editor shows "custom" indicator
};

export type ProjectModel = {
  model_version: number;
  pages: Array<{ page_id: string; name: string; widgets: any[] }>;
  // Optional project-level HA bindings + live update links.
  // These are consumed by the backend compiler.
  bindings?: any[];
  links?: any[];
  /** Action bindings: widget event -> HA service call. Compiler uses yaml_override when set, else generates from call. */
  action_bindings?: ActionBinding[];
  palette?: Record<string, string>;
  // Optional runtime/device metadata used by the designer UI.
  // The backend stores this as part of the project model.
  device?: {
    hardware_recipe_id?: string;
    screen?: { width?: number; height?: number };
  };
  ui?: {
    gridSize?: number;
    showGrid?: boolean;
  };
  /** LVGL display background color (disp_bg_color). Hex string e.g. "#1a1a2e". Injected under lvgl: when set. */
  disp_bg_color?: string;
  /** LVGL top-level config: main (disp_bg_color, buffer_size), style_definitions, theme, gradients, top_layer. */
  lvgl_config?: {
    main?: { disp_bg_color?: string; buffer_size?: string; [k: string]: unknown };
    style_definitions?: Array<{ id: string; [k: string]: unknown }>;
    theme?: Record<string, Record<string, unknown>>;
    gradients?: Array<{ id: string; direction?: string; stops?: Array<{ color?: string; position?: number }> }>;
    top_layer?: { widgets?: any[] };
  };
};

export type ApiOk<T> = T & { ok: true };
export type ApiErr = { ok: false; error: string };

const DOMAIN = "esptoolkit";

function url(path: string, entryId?: string) {
  const u = new URL(`/api/${DOMAIN}/${path}`, window.location.origin);
  if (entryId) u.searchParams.set("entry_id", entryId);
  return u.toString();
}

export async function getContext(): Promise<ApiOk<{ entry_id: string; addon_base_url?: string }> | ApiErr> {
  const res = await fetch(url("context"), { credentials: "include" });
  return res.json();
}

export async function listDevices(entryId: string): Promise<ApiOk<{ devices: DeviceSummary[] }> | ApiErr> {
  const res = await fetch(url("devices", entryId));
  return res.json();
}

export async function upsertDevice(
  entryId: string,
  payload: { device_id: string; name?: string; slug?: string; hardware_recipe_id?: string | null; api_key?: string | null }
): Promise<ApiOk<{}> | ApiErr> {
  const res = await fetch(url("devices", entryId), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function deleteDevice(entryId: string, deviceId: string): Promise<ApiOk<{}> | ApiErr> {
  const u = new URL(url("devices", entryId));
  u.searchParams.set("device_id", deviceId);
  const res = await fetch(u.toString(), { method: "DELETE" });
  return res.json();
}

export async function getProject(entryId: string, deviceId: string): Promise<ApiOk<{ project: ProjectModel }> | ApiErr> {
  const res = await fetch(url(`devices/${encodeURIComponent(deviceId)}/project`, entryId));
  return res.json();
}

export async function putProject(entryId: string, deviceId: string, project: ProjectModel): Promise<ApiOk<{}> | ApiErr> {
  const res = await fetch(url(`devices/${encodeURIComponent(deviceId)}/project`, entryId), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project }),
  });
  return res.json();
}

export async function listWidgetSchemas(): Promise<ApiOk<{ schemas: WidgetSchemaIndexItem[] }> | ApiErr> {
  const res = await fetch(url("schemas/widgets"));
  return res.json();
}

export async function getWidgetSchema(widgetType: string): Promise<ApiOk<{ schema: WidgetSchema }> | ApiErr> {
  const res = await fetch(url(`schemas/widgets/${encodeURIComponent(widgetType)}`));
  return res.json();
}

export async function deploy(entryId: string, deviceId: string): Promise<ApiOk<{ path: string }> | ApiErr> {
  const res = await fetch(url("deploy", entryId), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device_id: deviceId }),
  });
  return res.json();
}


async function apiGet<T = any>(path: string): Promise<T> {
  const res = await fetch(path, { credentials: "include" });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error || `Request failed: ${res.status}`);
  return data;
}

async function apiPost<T = any>(path: string, body: object): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = [data?.error, data?.detail].filter(Boolean).join(": ") || `Request failed: ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

const API_BASE = "/api/esptoolkit";

export async function listAssets(): Promise<{ name: string; size: number }[]> {
  const data = await apiGet<{ name: string; size: number }[] | unknown>(`${API_BASE}/assets`);
  return Array.isArray(data) ? data : [];
}

export async function uploadAsset(name: string, dataBase64: string) {
  return apiPost(`${API_BASE}/assets/upload`, { name, data_base64: dataBase64 });
}

export async function validateRecipe(recipe_id: string) {
  return apiPost(`${API_BASE}/recipes/validate`, { recipe_id });
}

/** Batch fetch HA entity states for live design-time preview. */
export async function fetchStateBatch(entity_ids: string[]): Promise<Record<string, { state: string; attributes: Record<string, any> }>> {
  if (!entity_ids?.length) return {};
  const res = await fetch(`${API_BASE}/state/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entity_ids }),
    credentials: "include",
  });
  if (!res.ok) return {};
  let data: any;
  try {
    data = await res.json();
  } catch {
    return {};
  }
  return (data?.states && typeof data.states === "object") ? data.states : {};
}

/** Call a Home Assistant service (simulator: widget action → HA). */
export async function callService(
  domain: string,
  service: string,
  data: Record<string, unknown> = {}
): Promise<{ ok: boolean; error?: string }> {
  const url = `${API_BASE}/call_service`;
  console.log("[Simulator] fetch", url, { domain, service, data });
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ domain, service, data }),
  });
  const out = await res.json().catch(() => ({}));
  console.log("[Simulator] fetch response", res.status, out);
  if (!res.ok) return { ok: false, error: out?.error || `HTTP ${res.status}` };
  return out?.ok === true ? { ok: true } : { ok: false, error: out?.error || "unknown" };
}

export async function exportDeviceYaml(device_id: string) {
  return apiPost(`${API_BASE}/devices/${encodeURIComponent(device_id)}/export`, {});
}

export async function getEntityCapabilities(entity_id: string) {
  return apiGet(`${API_BASE}/ha/entities/${encodeURIComponent(entity_id)}/capabilities`);
}

export async function listPlugins() {
  return apiGet(`${API_BASE}/plugins`);
}

export async function exportDeviceYamlPreview(device_id: string, entry_id: string) {
  const u = new URL(`${API_BASE}/devices/${encodeURIComponent(device_id)}/export/preview`, window.location.origin);
  u.searchParams.set("entry_id", entry_id);
  return apiPost(u.toString(), {});
}

export async function exportDeviceYamlWithExpectedHash(device_id: string, expected_hash: string, entry_id: string) {
  const u = new URL(`${API_BASE}/devices/${encodeURIComponent(device_id)}/export`, window.location.origin);
  u.searchParams.set("entry_id", entry_id);
  return apiPost(u.toString(), { expected_hash });
}

/** Run ESPHome build and upload via the configured add-on (reads YAML from exported file). */
export async function deployBuild(device_id: string, entry_id: string) {
  const u = new URL(`${API_BASE}/deploy_build`, window.location.origin);
  u.searchParams.set("entry_id", entry_id);
  return apiPost(u.toString(), { device_id });
}

/** Write compiled YAML to esphome/ then run add-on config-check (validate). */
export async function validateExport(device_id: string, entry_id: string): Promise<{ ok: boolean; stdout?: string; stderr?: string }> {
  const u = new URL(`${API_BASE}/devices/${encodeURIComponent(device_id)}/validate_export`, window.location.origin);
  u.searchParams.set("entry_id", entry_id);
  return apiPost(u.toString(), {});
}

/** Write compiled YAML to esphome/ then run add-on upload (deploy). */
export async function deployExport(device_id: string, entry_id: string): Promise<{ ok: boolean; path?: string; result?: string; error?: string; detail?: string }> {
  const u = new URL(`${API_BASE}/devices/${encodeURIComponent(device_id)}/deploy_export`, window.location.origin);
  u.searchParams.set("entry_id", entry_id);
  return apiPost(u.toString(), {});
}
