import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import packageJson from "../package.json";
import Canvas from "./Canvas";
import { resolveDeviceScreen } from "./deviceScreen";
import { usePreviewFontResolver } from "./usePreviewFontResolver";
import {
  listRecipes,
  compileYaml,
  parseYamlSyntax,
  listEntities,
  getEntity,
  importRecipe,
  updateRecipeLabel,
  deleteRecipe,
  cloneRecipe,
  exportRecipe,
  listSavedEntityWidgets,
  getSavedEntityWidget,
  saveEntityWidget,
  deleteSavedEntityWidget,
  previewWidgetYaml,
  type LayoutAuditResult,
} from "./lib/api";
import { collectWidgetIds, updateSectionsWidgetRef } from "./projectSections";
import { CONTROL_TEMPLATES, type ControlTemplate } from "./controls";
import { PREBUILT_WIDGETS, type PrebuiltWidget } from "./prebuiltWidgets";
import {
  ENTITY_WIDGET_TITLE_PREFIX,
  isEntityWidgetTemplateTitle,
  isSavedEntityWidgetTemplateId,
  savedEntityWidgetStorageId,
  SAVED_ENTITY_WIDGET_PREFIX,
} from "./entityWidgetTitles";
import {
  fitDescendantContainerTrees,
  fitContainerToDirectChildrenBounds,
  fitContainerTreeToDescendantBounds,
  normalizeWidgetsForEntityWidgetExport,
} from "./entityWidgetLayout";
import { DOMAIN_PRESETS } from "./bindings/domains";
import {
  getDisplayActionsForType,
  getEventsForType,
  getServicesForDomain,
  domainFromEntityId,
  DISPLAY_ACTION_LABELS,
  EVENT_LABELS,
  formatDisplayBindingSummary,
  formatLinkSourceRef,
  formatActionBindingSummary,
  displayActionRequiresNumericSource,
} from "./bindings/bindingConfig";
import { displayLinkRowsForWidget } from "./bindings/widgetLinks";
import { entityMatchesBindingSearch } from "./bindings/entitySearch";
import { getMatchingActionBindings, INPUT_WIDGET_TYPES, OPTION_SELECT_WIDGET_TYPES, CLICK_TOGGLE_WIDGET_TYPES } from "./bindings/matchingActions";
import {
  deleteDevice,
  deploy,
  deployExport,
  enqueueMacSim,
  listEsphomePorts,
  exportDeviceYamlPreview,
  exportDeviceYamlWithExpectedHash,
  getVersion,
  validateExport,
  callService,
  fetchStateBatch,
  getContext,
  getProject,
  getWidgetSchema,
  importFromYaml,
  listAssets,
  listDevices,
  listWidgetSchemas,
  putProject,
  uploadAsset,
  upsertDevice,
  validateRecipe,
  type DeviceSummary,
  type ProjectModel,
  type WidgetSchema,
  type WidgetSchemaIndexItem,
} from "./api";
import LvglSettingsModal, { type LvglConfig } from "./LvglSettingsModal";
import ComponentsPanelLoader from "./ComponentsPanelLoader";
import WorkflowStepper, { type WorkflowStep } from "./WorkflowStepper";
import WelcomePanel from "./WelcomePanel";
import ManageDevicesModal from "./ManageDevicesModal";
import OpenDevicePickerModal from "./OpenDevicePickerModal";
import YamlEditor from "./YamlEditor";

type Toast = { type: "ok" | "error"; msg: string };

const INTEGRATION_NOT_CONFIGURED_MSG =
  "Designer isn't connected yet. If you've set the API token in the EspToolkit add-on (Settings → Add-ons → EspToolkit → Configuration), restart the add-on and Home Assistant, then refresh this page.";

function uid(prefix: string) {
  return `${prefix}_${Math.random().toString(16).slice(2, 10)}`;
}

function friendlyToId(s: string): string {
  return s
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    || "device";
}

function clone<T>(x: T): T {
  return JSON.parse(JSON.stringify(x));
}

/** Widget IDs referenced in a YAML block (e.g. "widget: my_switch"). Used to remove esphome_components when a widget is deleted. */
const WIDGET_REF_RE = /widget:\s*["']?([a-zA-Z0-9_]+)["']?/g;
function getWidgetRefsInYaml(yamlStr: string): string[] {
  const refs: string[] = [];
  let m: RegExpExecArray | null;
  WIDGET_REF_RE.lastIndex = 0;
  while ((m = WIDGET_REF_RE.exec(yamlStr)) !== null) refs.push(m[1]);
  return refs;
}

/** True if project has a Create Component block (esphome_components) that references this widget (widget: id). */
function widgetHasCreateComponent(project: any, widgetId: string): boolean {
  const comps = project?.esphome_components;
  if (!Array.isArray(comps) || !widgetId) return false;
  for (const c of comps) {
    const yaml = typeof c === "string" ? c : (c?.yaml ?? "");
    if (getWidgetRefsInYaml(yaml).includes(widgetId)) return true;
  }
  return false;
}

/** Hex #RRGGBB to HSV: h 0–360, s 0–100, v 0–100. */
function hexToHsv(hex: string): { h: number; s: number; v: number } {
  const m = /^#?([0-9a-fA-F]{6})$/.exec(hex);
  if (!m) return { h: 0, s: 0, v: 100 };
  const r = parseInt(m[1].slice(0, 2), 16) / 255;
  const g = parseInt(m[1].slice(2, 4), 16) / 255;
  const b = parseInt(m[1].slice(4, 6), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const v = max * 100;
  const d = max - min;
  const s = max === 0 ? 0 : (d / max) * 100;
  let h = 0;
  if (d !== 0) {
    if (max === r) h = 60 * (((g - b) / d) % 6);
    else if (max === g) h = 60 * ((b - r) / d + 2);
    else h = 60 * ((r - g) / d + 4);
    if (h < 0) h += 360;
  }
  return { h: Math.round(h), s: Math.round(s), v: Math.round(v) };
}

/** HSV to #RRGGBB. h 0–360, s 0–100, v 0–100. */
function hsvToHex(h: number, s: number, v: number): string {
  s /= 100; v /= 100;
  const c = v * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = v - c;
  let r = 0, g = 0, b = 0;
  if (h < 60) { r = c; g = x; }
  else if (h < 120) { r = x; g = c; }
  else if (h < 180) { g = c; b = x; }
  else if (h < 240) { g = x; b = c; }
  else if (h < 300) { r = x; b = c; }
  else { r = c; b = x; }
  const R = Math.round((r + m) * 255);
  const G = Math.round((g + m) * 255);
  const B = Math.round((b + m) * 255);
  return "#" + [R, G, B].map((n) => n.toString(16).padStart(2, "0")).join("");
}

/** Derive a friendly widget id from entity_id + attribute (e.g. climate.living_room + friendly_name → living_room_friendly_name). */
function friendlyWidgetIdFromBinding(entity_id: string, attribute: string, usedIds: Set<string>): string {
  const parts = String(entity_id || "").trim().split(".");
  const slug = parts.length > 1 ? (parts[1] || parts[0]) : (parts[0] || "entity");
  const attr = String(attribute || "state").trim() || "state";
  const base = friendlyToId(slug) + "_" + friendlyToId(attr);
  if (!base) return uid("w");
  let id = base;
  let n = 1;
  while (usedIds.has(id)) {
    id = base + "_" + (++n);
  }
  return id;
}

/** Legacy: container that grouped a native spinbox with +/- buttons; return the spinbox child id if present. */
function getSpinboxChildId(project: any, containerId: string): string | null {
  const page = project?.pages?.[0];
  const list = page?.widgets;
  if (!Array.isArray(list)) return null;
  const spinbox = list.find((w: any) => w?.parent_id === containerId && (w?.type === "spinbox"));
  return spinbox?.id ?? null;
}

function findWidgetById(list: any[], id: string): any | null {
  for (const w of list || []) {
    if (w?.id === id) return w;
    const child = findWidgetById((w as any).widgets || [], id);
    if (child) return child;
  }
  return null;
}

function updateParentIds(list: any[], oldId: string, newId: string): void {
  for (const w of list || []) {
    if (w?.parent_id === oldId) w.parent_id = newId;
    updateParentIds((w as any).widgets || [], oldId, newId);
  }
}

/** Rename a widget id everywhere in the project (page.widgets including nested, links, parent_id, sections). Returns updated project. */
function renameWidgetInProject(
  proj: any,
  pageIndex: number,
  oldId: string,
  newId: string
): { project: any; ok: boolean; newId?: string; error?: string } {
  if (!oldId || !newId || oldId === newId) return { project: proj, ok: false };
  const sanitized = newId.replace(/[^a-zA-Z0-9_]/g, "_").replace(/^_+|_+$/g, "") || null;
  if (!sanitized) return { project: proj, ok: false, error: "Invalid id" };
  const p2 = clone(proj);
  const page = p2?.pages?.[pageIndex];
  if (!page?.widgets) return { project: proj, ok: false };
  const existingIds = collectWidgetIds(page.widgets);
  if (existingIds.has(sanitized) && sanitized !== oldId) return { project: proj, ok: false, error: "Id already in use" };
  const w = findWidgetById(page.widgets, oldId);
  if (!w) return { project: proj, ok: false };
  w.id = sanitized;
  const links = (p2 as any).links;
  if (Array.isArray(links)) {
    for (const l of links) {
      if (l?.target?.widget_id === oldId) l.target = { ...l.target, widget_id: sanitized };
    }
  }
  const actionBindings = (p2 as any).action_bindings;
  if (Array.isArray(actionBindings)) {
    for (const ab of actionBindings) {
      if (ab?.widget_id === oldId) ab.widget_id = sanitized;
    }
  }
  updateParentIds(page.widgets, oldId, sanitized);
  // Sync widget refs in project.sections (LVGL platform blocks)
  const sections = (p2 as any).sections;
  if (sections && typeof sections === "object") {
    updateSectionsWidgetRef(sections, oldId, sanitized);
  }
  return { project: p2, ok: true, newId: sanitized };
}

/** LVGL platform component types: key -> { section_key, label }. */
const LVGL_COMPONENT_TYPES: Record<string, { section: string; label: string }> = {
  switch: { section: "switch", label: "Switch" },
  light: { section: "light", label: "Light" },
  sensor: { section: "sensor", label: "Sensor" },
  number: { section: "number", label: "Number" },
  select: { section: "select", label: "Select" },
  text_sensor: { section: "text_sensor", label: "Text sensor" },
  binary_sensor: { section: "binary_sensor", label: "Binary sensor" },
};

/** Widget type -> allowed LVGL component types and default. */
const WIDGET_TO_LVGL_COMPONENTS: Record<string, { types: string[]; default: string }> = {
  button: { types: ["switch", "binary_sensor"], default: "switch" },
  switch: { types: ["switch"], default: "switch" },
  checkbox: { types: ["switch"], default: "switch" },
  led: { types: ["light"], default: "light" },
  arc: { types: ["sensor", "number"], default: "number" },
  bar: { types: ["sensor", "number"], default: "number" },
  slider: { types: ["sensor", "number"], default: "number" },
  spinbox: { types: ["sensor", "number"], default: "number" },
  spinbox2: { types: ["sensor", "number"], default: "number" },
  dropdown: { types: ["select"], default: "select" },
  roller: { types: ["select"], default: "select" },
  label: { types: ["text_sensor"], default: "text_sensor" },
  textarea: { types: ["text_sensor"], default: "text_sensor" },
};

function getLvglComponentsForWidget(widgetType: string): { types: string[]; default: string } | null {
  return WIDGET_TO_LVGL_COMPONENTS[widgetType] ?? null;
}

function canCreateNativeComponentForWidget(widgetType: string): boolean {
  const c = getLvglComponentsForWidget(widgetType);
  return !!c && c.types.length > 0;
}


function useHistory<T>(initial: T) {
  const [present, setPresent] = useState<T>(initial);
  const [past, setPast] = useState<T[]>([]);
  const [future, setFuture] = useState<T[]>([]);

  const set = useCallback((next: T, commit = true) => {
    if (!commit) {
      setPresent(next);
      return;
    }
    setPresent((prev) => {
      setPast((p) => [...p, prev]);
      setFuture([]);
      return next;
    });
  }, []);

  const undo = () => {
    setPast((p) => {
      if (p.length === 0) return p;
      const prev = p[p.length - 1];
      setFuture((f) => [present, ...f]);
      setPresent(prev);
      return p.slice(0, -1);
    });
  };

  const redo = () => {
    setFuture((f) => {
      if (f.length === 0) return f;
      const next = f[0];
      setPast((p) => [...p, present]);
      setPresent(next);
      return f.slice(1);
    });
  };

  const canUndo = past.length > 0;
  const canRedo = future.length > 0;

  return { present, set, undo, redo, canUndo, canRedo };
}

export default function App() {
  const [entryId, setEntryId] = useState<string>("");
  const [versionInfo, setVersionInfo] = useState<{ integration: string; addon: string | null } | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>("");

  // Hardware recipes are loaded once for pickers and metadata display.
  const [recipes, setRecipes] = useState<any[]>([]);
  const setRecipesRef = useRef(setRecipes);
  setRecipesRef.current = setRecipes;
  const [recipeValidateBusy, setRecipeValidateBusy] = useState(false);
  const [recipeValidateErr, setRecipeValidateErr] = useState<string>("");
  const [recipeValidateRes, setRecipeValidateRes] = useState<any>(null);

  const [devices, setDevices] = useState<DeviceSummary[]>([]);
  const [newDeviceId, setNewDeviceId] = useState("");
  const [newDeviceName, setNewDeviceName] = useState("");
  const [newDeviceSlug, setNewDeviceSlug] = useState("");
  const [newDeviceApiKey, setNewDeviceApiKey] = useState("");

  const RECENT_DEVICES_KEY = "esptoolkit_recent_devices";
  const [recentDeviceIds, setRecentDeviceIds] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem(RECENT_DEVICES_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  });

  // New device wizard: hardware-first flow
  const [editDeviceModalOpen, setEditDeviceModalOpen] = useState(false);
  const [manageDevicesOpen, setManageDevicesOpen] = useState(false);
  const [openDevicePickerOpen, setOpenDevicePickerOpen] = useState(false);
  const [newDeviceWizardOpen, setNewDeviceWizardOpen] = useState(false);
  const [newDeviceWizardStep, setNewDeviceWizardStep] = useState<1 | 2>(1);
  const [newDeviceWizardRecipe, setNewDeviceWizardRecipe] = useState<{ id: string; label: string } | null>(null);
  const [newDeviceWizardId, setNewDeviceWizardId] = useState("");
  const [newDeviceWizardName, setNewDeviceWizardName] = useState("");
  const [newDeviceWizardSlug, setNewDeviceWizardSlug] = useState("");
  const [newDeviceWizardApiKey, setNewDeviceWizardApiKey] = useState("");
  const [newDeviceWizardOtaPassword, setNewDeviceWizardOtaPassword] = useState("");
  const [newDeviceWizardWifiSsid, setNewDeviceWizardWifiSsid] = useState("");
  const [newDeviceWizardWifiPassword, setNewDeviceWizardWifiPassword] = useState("");

  const [editDeviceRecipeId, setEditDeviceRecipeId] = useState<string>("");
  const [newDeviceOtaPassword, setNewDeviceOtaPassword] = useState("");
  const [newDeviceWifiSsid, setNewDeviceWifiSsid] = useState("");
  const [newDeviceWifiPassword, setNewDeviceWifiPassword] = useState("");

  const [selectedDevice, setSelectedDevice] = useState<string>("");
  const projectHist = useHistory<ProjectModel | null>(null);
  const project = projectHist.present;
  const setProject = projectHist.set;
  const haBindingCounts = useMemo(() => {
    const p = project;
    return {
      entities: ((p as any)?.bindings || []).length,
      links: ((p as any)?.links || []).length,
      actions: ((p as any)?.action_bindings || []).length,
    };
  }, [project]);
  const [projectDirty, setProjectDirty] = useState(false);
  /** URL-driven parity mode (?etd_parity=1&etd_fixture=name) for PNG compare vs simulator. */
  const [parityMode, setParityMode] = useState(false);
  const [parityError, setParityError] = useState<string | null>(null);

  const [schemaIndex, setSchemaIndex] = useState<WidgetSchemaIndexItem[]>([]);
  const [newWidgetType, setNewWidgetType] = useState("label");
  const [selectedWidgetIds, setSelectedWidgetIds] = useState<string[]>([]);
  const selectedWidgetId = selectedWidgetIds[0] || "";
  const [selectedSchema, setSelectedSchema] = useState<WidgetSchema | null>(null);

  const [currentPageIndex, setCurrentPageIndex] = useState(0);
  const LAST_DEVICE_KEY = "esptoolkit_last_device";
  const draftKeyForDevice = (deviceId: string) => `esptoolkit_project_draft:${deviceId}`;

  // Derived before any hooks that reference them (avoids TDZ: "Cannot access 'safePageIndex' before initialization").
  const pages = project?.pages ?? [];
  const safePageIndex = Math.max(0, Math.min(currentPageIndex, Math.max(0, pages.length - 1)));

  useEffect(() => {
    if (typeof window === "undefined") return;
    const p = new URLSearchParams(window.location.search);
    if (p.get("etd_parity") !== "1") return;
    const name = (p.get("etd_fixture") || "").trim();
    if (!/^[a-z0-9_-]+$/i.test(name)) {
      setParityError("Invalid etd_fixture (use letters, digits, underscore, hyphen).");
      return;
    }
    const base = import.meta.env.BASE_URL || "/";
    fetch(`${base}parity-fixtures/${name}.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`fixture HTTP ${r.status}`);
        return r.json() as Promise<ProjectModel>;
      })
      .then((data) => {
        setProject(data, false);
        setParityMode(true);
        setCurrentPageIndex(0);
      })
      .catch((e) => setParityError(String((e as Error)?.message ?? e)));
  }, [setProject]);

  // Clipboard for copy/paste (v0.19). Stored as raw widget JSON fragments.
  const [clipboard, setClipboard] = useState<any[] | null>(null);

  // v0.22: Post-drop wizard for HA control templates.
  const [tmplWizard, setTmplWizard] = useState<null | { template_id: string; x: number; y: number }>(null);
  const [tmplEntity, setTmplEntity] = useState<string>("");
  const [tmplLabel, setTmplLabel] = useState<string>("");
  // v0.34: entity capabilities (supported_features/attrs) shown in the wizard.
  const [tmplCaps, setTmplCaps] = useState<any>(null);
  // v0.36: allow explicit selection of a variant, otherwise auto-pick based on capabilities.
  const [tmplVariant, setTmplVariant] = useState<string>("auto");

  // v0.60: Entity widget wizard options (shared post-drop wizard for multi-widget templates).
  const [tmplTapAction, setTmplTapAction] = useState<string>("toggle");
  const [tmplService, setTmplService] = useState<string>("");
  const [tmplServiceData, setTmplServiceData] = useState<string>("");
  const [tmplEntities, setTmplEntities] = useState<string[]>([]);

  // v0.68: Conditional entity widget wizard builder
  const [tmplCondOp, setTmplCondOp] = useState<string>("equals");
  const [tmplCondValue, setTmplCondValue] = useState<string>("on");
  const [tmplCondNumeric, setTmplCondNumeric] = useState<boolean>(false);

  // v0.61: Richer entity widget wizard options
  // Thermostat
  const [tmplThMin, setTmplThMin] = useState<number>(5);
  const [tmplThMax, setTmplThMax] = useState<number>(35);
  const [tmplThStep, setTmplThStep] = useState<number>(1);

  // Media entity widget
  const [tmplMediaShowTransport, setTmplMediaShowTransport] = useState<boolean>(true);
  const [tmplMediaShowVolume, setTmplMediaShowVolume] = useState<boolean>(true);
  const [tmplMediaShowMute, setTmplMediaShowMute] = useState<boolean>(true);
  const [tmplMediaShowSource, setTmplMediaShowSource] = useState<boolean>(true);
  const [tmplMediaDefaultSource, setTmplMediaDefaultSource] = useState<string>("");

  // Cover entity widget
  const [tmplCoverShowTilt, setTmplCoverShowTilt] = useState<boolean>(true);

  // Multi-entity layouts (glance/grid template ids)
  const [tmplGlanceRows, setTmplGlanceRows] = useState<number>(4);
  const [tmplGridSize, setTmplGridSize] = useState<"2x2" | "3x2" | "3x3">("2x2");


  // v0.24: Design-time entity list snapshot for template wizard + linting.
  const [entities, setEntities] = useState<any[]>([]);
  // Entity combobox: show dropdown when open; filter list by domain (from template) + typed search.
  const [tmplEntityDropdownOpen, setTmplEntityDropdownOpen] = useState(false);

  // Binding Builder: entity picker search + bind target fields.
  const [entityQuery, setEntityQuery] = useState<string>("");
  const [bindEntity, setBindEntity] = useState<string>("");
  const [bindAttr, setBindAttr] = useState<string>("");
  const [bindAction, setBindAction] = useState<string>("label_text");
  const [bindFormat, setBindFormat] = useState<string>("%.1f");
  const [createMatchingActions, setCreateMatchingActions] = useState<boolean>(true);
  const [bindScale, setBindScale] = useState<number>(1);
  const [builderMode, setBuilderMode] = useState<"display" | "action">("display");
  const [bindingsListExpanded, setBindingsListExpanded] = useState<Record<string, boolean>>({});
  const [builderEntityDropdownOpen, setBuilderEntityDropdownOpen] = useState(false);
  // Action binding form
  const [actionEvent, setActionEvent] = useState<string>("on_click");
  const [actionService, setActionService] = useState<string>("");
  const [actionEntity, setActionEntity] = useState<string>("");
  const [actionEntityDropdownOpen, setActionEntityDropdownOpen] = useState(false);
  const [editingLinkOverride, setEditingLinkOverride] = useState<{
    linkIndex: number;
    forWidgetId: string;
    intervalUpdateIndex?: number;
  } | null>(null);
  const [editingOverrideYaml, setEditingOverrideYaml] = useState<string>("");
  /** Fetched entity details for Binding Builder attribute list (so dropdown has full attributes e.g. temperature, current_temperature). */
  const [bindingEntityDetails, setBindingEntityDetails] = useState<{ entity_id: string; attributes?: Record<string, unknown> } | null>(null);

  // Create native component (LVGL platform): dialog state
  const [createNativeComponentOpen, setCreateNativeComponentOpen] = useState(false);
  const [createNativeComponentType, setCreateNativeComponentType] = useState<string>("");
  const [createNativeComponentId, setCreateNativeComponentId] = useState<string>("");
  const [createNativeComponentName, setCreateNativeComponentName] = useState<string>("");
  const [createNativeComponentTypeFilter, setCreateNativeComponentTypeFilter] = useState<string>("");
  const [createNativeComponentDropdownOpen, setCreateNativeComponentDropdownOpen] = useState(false);

  // v0.35: Plugin controls (loaded from API)
  const [pluginControls, setPluginControls] = useState<ControlTemplate[]>([]);

  // v0.24: Lint output shown in the UI (best-effort, purely advisory).
  // --- Assets panel (v0.27) ---
const [assets, setAssets] = React.useState<{name:string; size:number}[]>([]);
const [assetError, setAssetError] = React.useState<string | null>(null);

async function refreshAssets() {
  try {
    const items = await listAssets();
    setAssets(items);
    setAssetError(null);
  } catch (e: any) {
    const msg = String(e?.message || e);
    setAssetError(msg.includes("404") || msg.includes("no_active_entry") ? INTEGRATION_NOT_CONFIGURED_MSG : msg);
  }
}

async function onUploadAssetFile(file: File) {
  try {
    const buf = await file.arrayBuffer();
    const b64 = btoa(String.fromCharCode(...new Uint8Array(buf)));
    await uploadAsset(file.name, b64);
    await refreshAssets();
  } catch (e: any) {
    const msg = String(e?.message || e);
    setAssetError(msg.includes("404") || msg.includes("no_active_entry") ? INTEGRATION_NOT_CONFIGURED_MSG : msg);
  }
}

  const [lintOpen, setLintOpen] = useState<boolean>(false);
  const [paletteTab, setPaletteTab] = useState<"basic" | "prebuilt" | "entity">("basic");
  const [inspectorTab, setInspectorTab] = useState<"properties" | "bindings" | "builder" | "yaml" | "importlog">("properties");
  const [editingWidgetId, setEditingWidgetId] = useState<string>("");
  useEffect(() => {
    setEditingWidgetId("");
  }, [selectedWidgetIds.join(",")]);
  const [compileModalOpen, setCompileModalOpen] = useState(false);
  const [compiledYaml, setCompiledYaml] = useState<string>("");
  const [compileErr, setCompileErr] = useState<string>("");
  const [compileWarnings, setCompileWarnings] = useState<Array<{ type: string; section?: string; widget_id?: string }>>([]);
  const [autoCompile, setAutoCompile] = useState<boolean>(true);
  const [compileBusy, setCompileBusy] = useState<boolean>(false);
  const [layoutAuditBusy, setLayoutAuditBusy] = useState<boolean>(false);
  const [layoutAudit, setLayoutAudit] = useState<LayoutAuditResult | null>(null);
  const [layoutAuditErr, setLayoutAuditErr] = useState<string>("");
  const [validateYamlBusy, setValidateYamlBusy] = useState<boolean>(false);
  const [validateYamlResult, setValidateYamlResult] = useState<{ ok: boolean; stdout?: string; stderr?: string; error?: string } | null>(null);
  const [exportBusy, setExportBusy] = useState<boolean>(false);
  const [exportPreview, setExportPreview] = useState<any>(null);
  const [exportPreviewErr, setExportPreviewErr] = useState<string>("");
  const [exportResult, setExportResult] = useState<any>(null);
  const [exportErr, setExportErr] = useState<string>("");

  // Full YAML: view full compiled output in CodeMirror (read-only)
  const [fullYamlOpen, setFullYamlOpen] = useState<boolean>(false);
  const [fullYamlContent, setFullYamlContent] = useState<string>("");
  const [fullYamlBusy, setFullYamlBusy] = useState<boolean>(false);
  const [fullYamlError, setFullYamlError] = useState<string>("");

  // About / licenses modal
  const [aboutOpen, setAboutOpen] = useState<boolean>(false);

  // Deploy target prompt (USB vs OTA)
  const [deployTargetOpen, setDeployTargetOpen] = useState(false);
  const [deployTargetPorts, setDeployTargetPorts] = useState<string[]>([]);
  const [deployTargetChoice, setDeployTargetChoice] = useState<string>("ota"); // "ota" or "usb:<port>"
  const deployTargetResolveRef = useRef<((choice: string | null) => void) | null>(null);

  // v0.62: Built-in self-check (verification suite) — runs backend checks without deploying.
  const [selfCheckBusy, setSelfCheckBusy] = useState<boolean>(false);
  const [selfCheckResult, setSelfCheckResult] = useState<any>(null);
  const [selfCheckErr, setSelfCheckErr] = useState<string>("");

  // Simulator: live interactive preview
  const [simulationOpen, setSimulationOpen] = useState<boolean>(false);
  const [macSimBusy, setMacSimBusy] = useState<boolean>(false);
  const [simOverrides, setSimOverrides] = useState<Record<string, { value?: number; checked?: boolean; selected_index?: number; text?: string }>>({});
  const [colorPickerModal, setColorPickerModal] = useState<{ widgetId: string; initialHex: string; fromSimulator?: boolean } | null>(null);
  const [colorPickerHue, setColorPickerHue] = useState(0);
  const [colorPickerSat, setColorPickerSat] = useState(0);
  const [whitePickerModal, setWhitePickerModal] = useState<{ widgetId: string; mireds: number } | null>(null);
  const [textareaModal, setTextareaModal] = useState<{ widgetId: string; text: string } | null>(null);

  // v0.64: Hardware recipe importer (Product Mode)
  const [recipeImportOpen, setRecipeImportOpen] = useState<boolean>(false);
  const [recipeImportYaml, setRecipeImportYaml] = useState<string>("");
  const [recipeImportLabel, setRecipeImportLabel] = useState<string>("");
  const [recipeImportId, setRecipeImportId] = useState<string>("");
  const [recipeImportBusy, setRecipeImportBusy] = useState<boolean>(false);
  const [recipeImportErr, setRecipeImportErr] = useState<string>("");
  const [recipeImportOk, setRecipeImportOk] = useState<any>(null);

  const [lvglSettingsOpen, setLvglSettingsOpen] = useState<boolean>(false);
  // v0.70.138: Components panel (section-based: categories → sections → section_overrides)
  const [componentsOpen, setComponentsOpen] = useState<boolean>(false);
  // Widget YAML tab: full preview from compiler (props, style, action bindings)
  const [widgetYamlPreview, setWidgetYamlPreview] = useState<string | null>(null);
  const [widgetYamlEventSnippets, setWidgetYamlEventSnippets] = useState<Record<string, { yaml: string; source: string }>>({});
  const [widgetYamlPreviewLoading, setWidgetYamlPreviewLoading] = useState<boolean>(false);
  const [widgetYamlPreviewError, setWidgetYamlPreviewError] = useState<string | null>(null);
  const [widgetEventDrafts, setWidgetEventDrafts] = useState<Record<string, string>>({});
  const [widgetEventError, setWidgetEventError] = useState<string | null>(null);
  // When user changes bound entity on an action that has custom YAML: prompt Keep or Reset
  const [actionEntityChangePending, setActionEntityChangePending] = useState<{ widgetId: string; event: string; newEntityId: string } | null>(null);

  // YAML import: modal + Import log tab
  const [importYamlOpen, setImportYamlOpen] = useState<boolean>(false);
  const [importYamlText, setImportYamlText] = useState<string>("");
  const [importYamlNameOverride, setImportYamlNameOverride] = useState<string>("");
  const [importYamlBusy, setImportYamlBusy] = useState<boolean>(false);
  const [importYamlErr, setImportYamlErr] = useState<string>("");
  const [importLogLines, setImportLogLines] = useState<string[]>([]);

  // Live HA state for design-time preview (bound widgets show current HA values).
  const [liveEntityStates, setLiveEntityStates] = useState<Record<string, { state: string; attributes: Record<string, any> }>>({});

  // v0.69: Recipe Manager (Product Mode)
  const [recipeMgrOpen, setRecipeMgrOpen] = useState<boolean>(false);
  const [recipeMgrEdits, setRecipeMgrEdits] = useState<Record<string, string>>({});
  const [recipeMgrBusy, setRecipeMgrBusy] = useState<boolean>(false);
  const [recipeMgrErr, setRecipeMgrErr] = useState<string>("");

  // User-saved entity widgets (snapshot of current page)
  const [customEntityWidgets, setCustomEntityWidgets] = useState<
    { id: string; name: string; description: string; device_types: string[] }[]
  >([]);
  const [customEntityWidgetsError, setCustomEntityWidgetsError] = useState<string | null>(null);
  const [saveEntityWidgetOpen, setSaveEntityWidgetOpen] = useState<boolean>(false);
  const [saveEntityWidgetName, setSaveEntityWidgetName] = useState<string>("");
  const [saveEntityWidgetDescription, setSaveEntityWidgetDescription] = useState<string>("");
  const [saveEntityWidgetDeviceType, setSaveEntityWidgetDeviceType] = useState<string>("climate");
  const [saveEntityWidgetBusy, setSaveEntityWidgetBusy] = useState<boolean>(false);
  const [saveEntityWidgetErr, setSaveEntityWidgetErr] = useState<string>("");
  const [entityWidgetContextMenu, setEntityWidgetContextMenu] = useState<{
    x: number;
    y: number;
    entityWidgetId: string;
    entityWidgetName: string;
  } | null>(null);
  const [pageTabContextMenu, setPageTabContextMenu] = useState<{ x: number; y: number; pageIndex: number } | null>(null);

  async function refreshCustomEntityWidgets() {
    try {
      const items = await listSavedEntityWidgets();
      setCustomEntityWidgets(items);
      setCustomEntityWidgetsError(null);
    } catch (e: any) {
      setCustomEntityWidgets([]);
      const msg = String(e?.message || e);
      setCustomEntityWidgetsError(
        msg.includes("404") || msg.includes("no_active_entry") ? INTEGRATION_NOT_CONFIGURED_MSG : msg
      );
    }
  }
  useEffect(() => {
    if (paletteTab === "entity") refreshCustomEntityWidgets();
  }, [paletteTab]);

  async function doImportRecipe() {
    setRecipeImportBusy(true);
    setRecipeImportErr("");
    setRecipeImportOk(null);
    try {
      const res = await importRecipe(recipeImportYaml, recipeImportLabel || undefined, recipeImportId || undefined);
      setRecipeImportOk(res);
    } catch (e: any) {
      const errMsg = String(e?.message || e);
      setRecipeImportErr(errMsg.includes("404") || errMsg.includes("no_active_entry") ? INTEGRATION_NOT_CONFIGURED_MSG : errMsg);
    } finally {
      setRecipeImportBusy(false);
    }
  }

  async function doImportYaml() {
    setImportYamlBusy(true);
    setImportYamlErr("");
    try {
      const result = await importFromYaml(importYamlText, importYamlNameOverride.trim() || undefined, entryId || undefined);
      const logLines = Array.isArray(result.log) ? result.log : [];
      setImportLogLines(logLines);
      if (result.ok) {
        setImportYamlOpen(false);
        setImportYamlText("");
        setImportYamlNameOverride("");
        const deviceId = (result as any).device_id as string | undefined;
        if (entryId && deviceId) {
          const listRes = await listDevices(entryId);
          if (listRes.ok) setDevices(listRes.devices);
          try {
            localStorage.removeItem(draftKeyForDevice(deviceId));
          } catch {}
          setSelectedDevice(deviceId);
          await loadDevice(deviceId, { saveAfterLoad: true });
        } else {
          setToast({ type: "ok", msg: `Imported device: ${deviceId ?? "ok"}` });
          if (entryId) {
            const listRes = await listDevices(entryId);
            if (listRes.ok) setDevices(listRes.devices);
          }
        }
      } else {
        const err = (result as any).error ?? "Import failed";
        const detail = String((result as any).detail || "").trim();
        setImportYamlErr(detail ? `${err}: ${detail}` : err);
      }
    } catch (e: any) {
      setImportYamlErr(String(e?.message ?? e));
      setImportLogLines([]);
    } finally {
      setImportYamlBusy(false);
    }
  }

  async function refresh() {
    if (!entryId) {
      setDevices([]);
      return;
    }
    const res = await listDevices(entryId);
    if (!res.ok) return setToast({ type: "error", msg: res.error });
    setDevices(res.devices);
  }

  const refreshRecipes = useCallback(async () => {
    try {
      const rs = await listRecipes();
      setRecipesRef.current(rs);
    } catch (e: any) {
      setError(String(e?.message || e));
    }
  }, []);

  useEffect(() => {
    void refreshAssets();
    refreshRecipes();
    (async () => {
      let ctx = await getContext();
      if (!ctx.ok) return setToast({ type: "error", msg: ctx.error });
      let eid = ctx.entry_id ?? "";
      if (!eid) {
        await new Promise((r) => setTimeout(r, 2000));
        ctx = await getContext();
        if (ctx.ok) eid = ctx.entry_id ?? "";
        if (!eid) {
          await new Promise((r) => setTimeout(r, 3000));
          ctx = await getContext();
          if (ctx.ok) eid = ctx.entry_id ?? "";
        }
      }
      setEntryId(eid);

      const si = await listWidgetSchemas();
      if (si.ok) setSchemaIndex(si.schemas);

      if (eid) {
        const res = await listDevices(eid);
        if (res.ok) setDevices(res.devices);
      } else {
        setDevices([]);
      }
    })();
  }, []);

  useEffect(() => {
    if (!entryId) {
      setVersionInfo(null);
      return;
    }
    getVersion(entryId)
      .then(setVersionInfo)
      .catch(() => setVersionInfo(null));
  }, [entryId]);

  // Persist the last selected device so returning to Designer resumes work.
  useEffect(() => {
    try {
      if (selectedDevice) localStorage.setItem(LAST_DEVICE_KEY, selectedDevice);
    } catch {}
  }, [selectedDevice]);

  // Auto-restore last device after refresh / panel remount.
  useEffect(() => {
    if (!entryId) return;
    if (selectedDevice) return;
    if (!devices.length) return;
    try {
      const last = localStorage.getItem(LAST_DEVICE_KEY) || "";
      if (last && devices.some((d) => d.device_id === last)) {
        // eslint-disable-next-line @typescript-eslint/no-floating-promises
        loadDevice(last);
      }
    } catch {}
    // Intentionally do not depend on loadDevice identity (defined inline).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entryId, devices.length, selectedDevice]);

  const selectedDeviceObj = useMemo(() => devices.find((d) => d.device_id === selectedDevice) || null, [devices, selectedDevice]);
  const selectedRecipeId = selectedDeviceObj?.hardware_recipe_id || null;

  const recipeLabels = useMemo(() => {
    const m: Record<string, string> = {};
    (recipes || []).forEach((r: any) => { m[r.id] = r.label || r.id; });
    return m;
  }, [recipes]);

  const totalWidgetCount = useMemo(() => project?.pages?.reduce((acc: number, p: any) => acc + (p?.widgets?.length ?? 0), 0) ?? 0, [project]);
  const bindingCount = (haBindingCounts.entities + haBindingCounts.links + haBindingCounts.actions) || 0;
  const { currentWorkflowStep, completedWorkflowSteps, stepGuidance, nextStepLabel } = useMemo(() => {
    const completed = new Set<WorkflowStep>();
    let current: WorkflowStep = 1;
    if (selectedDevice) {
      completed.add(1);
      if (project) {
        completed.add(2);
        if (totalWidgetCount > 0) completed.add(3);
        if (bindingCount > 0) completed.add(4);
        if (totalWidgetCount === 0) current = 3;
        else if (bindingCount === 0) current = 4;
        else current = 5;
      } else {
        current = 2;
      }
    } else {
      current = 1;
    }
    const guidance: Record<WorkflowStep, string> = {
      1: "Select the ESPHome device you want to design screens for.",
      2: "Load this device's UI, or add a new device using a hardware recipe.",
      3: "Arrange widgets on your pages. Use the palette on the left and the properties panel on the right.",
      4: "Connect widgets to Home Assistant entities and actions so they show data and control devices.",
      5: "Interact with the screen in the simulator to verify layout and behaviour before deploying.",
      6: "Export YAML and deploy to your device.",
    };
    const nextLabels: Record<WorkflowStep, string | null> = {
      1: "Select device",
      2: "Load or add device",
      3: "Add widgets to your pages",
      4: "Set up bindings",
      5: "Test in simulator",
      6: null,
    };
    return {
      currentWorkflowStep: current,
      completedWorkflowSteps: completed,
      stepGuidance: guidance[current],
      nextStepLabel: nextLabels[current],
    };
  }, [selectedDevice, project, totalWidgetCount, bindingCount]);

  const showAdvancedToolsProminent = project != null && totalWidgetCount > 0;

  // v0.68: Validate and display hardware recipe metadata + issues.
  useEffect(() => {
    if (!selectedRecipeId) {
      setRecipeValidateRes(null);
      setRecipeValidateErr("");
      return;
    }
    let cancelled = false;
    (async () => {
      setRecipeValidateBusy(true);
      setRecipeValidateErr("");
      try {
        const r: any = await validateRecipe(selectedRecipeId);
        if (cancelled) return;
        setRecipeValidateRes(r);
      } catch (e: any) {
        if (cancelled) return;
        const raw = String(e?.message || e);
        const is404 = raw.includes("404") || raw.includes("Not Found");
        setRecipeValidateErr(is404
          ? "Recipe validation unavailable (update integration to v0.70.61+ and restart HA)."
          : raw);
        setRecipeValidateRes(null);
      } finally {
        if (!cancelled) setRecipeValidateBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedRecipeId]);

useEffect(() => {
  // Design-time entity picker (poll-free): fetch snapshot when panel opens.
  listEntities()
    .then((x) => setEntities(Array.isArray(x) ? x : []))
    .catch(() => setEntities([]));
}, []);

  // Widget YAML tab: fetch full preview from compiler when tab is active and one widget selected
  useEffect(() => {
    if (inspectorTab !== "yaml" || selectedWidgetIds.length !== 1 || !project) {
      setWidgetYamlPreview(null);
      setWidgetYamlPreviewError(null);
      return;
    }
    const widgetId = selectedWidgetIds[0];
    let cancelled = false;
    setWidgetYamlPreviewLoading(true);
    setWidgetYamlPreviewError(null);
    previewWidgetYaml(project, widgetId, safePageIndex)
      .then(({ yaml, event_snippets }) => {
        if (!cancelled) {
          setWidgetYamlPreview(yaml);
          setWidgetYamlEventSnippets(event_snippets ?? {});
          setWidgetYamlPreviewError(null);
        }
      })
      .catch((e: any) => {
        if (!cancelled) {
          setWidgetYamlPreview(null);
          setWidgetYamlPreviewError(String(e?.message || e));
        }
      })
      .finally(() => {
        if (!cancelled) setWidgetYamlPreviewLoading(false);
      });
    return () => { cancelled = true; };
  }, [inspectorTab, selectedWidgetIds.join(","), project, safePageIndex]);

useEffect(() => {
  // Binding Builder: when user selects an entity, fetch its full details so the Attribute dropdown has all keys (e.g. temperature, current_temperature).
  if (!bindEntity || !bindEntity.includes(".")) {
    setBindingEntityDetails(null);
    return;
  }
  let cancelled = false;
  getEntity(bindEntity)
    .then((data: any) => {
      if (!cancelled && data && data.entity_id === bindEntity)
        setBindingEntityDetails({ entity_id: data.entity_id, attributes: data.attributes ?? {} });
    })
    .catch(() => {
      if (!cancelled) setBindingEntityDetails(null);
    });
  return () => { cancelled = true; };
}, [bindEntity]);

useEffect(() => {
  // v0.35: load plugin controls (best-effort)
  (async () => {
    try {
      const r = await fetch("/api/esptoolkit/plugins");
      const j = await r.json();
      const pc: ControlTemplate[] = Array.isArray(j?.controls)
        ? j.controls
            .filter((c: any) => c && c.id && Array.isArray(c.widgets))
            .map((c: any) => ({
              id: String(c.id),
              title: String(c.title || c.id),
              description: String(c.description || "Plugin control"),
              build: (_args: any) => ({ widgets: c.widgets || [], bindings: c.bindings || [], links: c.links || [] }),
            }))
        : [];
      setPluginControls(pc);
    } catch (e) {
      setPluginControls([]);
    }
  })();
}, []);

useEffect(() => {
  // v0.34: when the template wizard has an entity, fetch its capabilities.
  (async () => {
    try {
      if (!tmplWizard) return setTmplCaps(null);
      const eid = (tmplEntity || "").trim();
      if (!eid || !eid.includes(".")) return setTmplCaps(null);
      const r = await fetch(`/api/esptoolkit/ha/entities/${encodeURIComponent(eid)}/capabilities`);
      if (!r.ok) return setTmplCaps(null);
      const j = await r.json();
      setTmplCaps(j);
    } catch {
      setTmplCaps(null);
    }
  })();
}, [tmplWizard, tmplEntity]);

// Live HA state for design-time preview: WebSocket + polling fallback (polling ensures updates when WS is unavailable).
useEffect(() => {
  const links = (project as any)?.links;
  if (!Array.isArray(links) || links.length === 0) {
    setLiveEntityStates({});
    return;
  }
  const entityIds = Array.from(
    new Set(
      links
        .map((l: any) => l?.source?.entity_id)
        .filter((e: any) => e && typeof e === "string" && e.includes("."))
    )
  ) as string[];
  if (entityIds.length === 0) return;
  let cancelled = false;

  const applyBatch = (states: Record<string, { state: string; attributes: Record<string, any> }>) => {
    if (cancelled) return;
    setLiveEntityStates((prev) => ({ ...prev, ...states }));
  };

  // WebSocket for real-time updates when supported
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${proto}//${window.location.host}/api/esptoolkit/state/ws`;
  let ws: WebSocket | null = null;
  const connect = () => {
    if (cancelled) return;
    try {
      ws = new WebSocket(wsUrl);
      ws.onopen = () => {
        if (cancelled || !ws) return;
        ws.send(JSON.stringify({ type: "subscribe", entity_ids: entityIds }));
      };
      ws.onmessage = (event) => {
        if (cancelled) return;
        try {
          const data = JSON.parse(event.data);
          if (data?.type === "state" && data?.entity_id) {
            applyBatch({ [data.entity_id]: { state: data.state ?? "", attributes: data.attributes ?? {} } });
          }
        } catch (_) {}
      };
      ws.onerror = () => {};
      ws.onclose = () => {
        ws = null;
        if (!cancelled) setTimeout(connect, 2000);
      };
    } catch (_) {}
  };
  connect();

  // Polling fallback: initial fetch + interval so canvas gets HA state even when WebSocket fails or isn't supported
  const poll = () => {
    if (cancelled) return;
    fetchStateBatch(entityIds).then(applyBatch).catch(() => {});
  };
  const t0 = setTimeout(poll, 500);
  const iv = setInterval(poll, 8000);

  return () => {
    cancelled = true;
    clearTimeout(t0);
    clearInterval(iv);
    if (ws) try { ws.close(); } catch (_) {}
  };
}, [project]);

useEffect(() => {
  // v0.61: prefill entity widget options from capabilities when available.
  if (!tmplWizard || !tmplCaps) return;
  try {
    if (tmplWizard.template_id === "thermostat_card") {
      const a = tmplCaps?.attributes || {};
      if (typeof a.min_temp === "number") setTmplThMin(a.min_temp);
      if (typeof a.max_temp === "number") setTmplThMax(a.max_temp);
      if (typeof a.target_temp_step === "number") setTmplThStep(a.target_temp_step);
    }
    if (tmplWizard.template_id === "media_control_card") {
      // Default: only show source row if there is a source_list.
      const a = tmplCaps?.attributes || {};
      if (!Array.isArray(a.source_list) || a.source_list.length === 0) setTmplMediaShowSource(false);
      // Default source if provided.
      if (Array.isArray(a.source_list) && a.source_list.length > 0 && !tmplMediaDefaultSource) {
        setTmplMediaDefaultSource(String(a.source_list[0]));
      }
    }
  } catch {}
}, [tmplCaps, tmplWizard]);

  function templateDomain(template_id: string): string {
    if (isSavedEntityWidgetTemplateId(template_id || "")) {
      const sid = savedEntityWidgetStorageId(template_id);
      const c = customEntityWidgets.find((cc) => cc.id === sid);
      return (c?.device_types?.[0] || "").toLowerCase();
    }
    const m = /^ha_([a-z0-9]+)_/i.exec(template_id || "");
    return (m?.[1] || "").toLowerCase();
  }

  const allTemplatesForWizard = [...CONTROL_TEMPLATES, ...(pluginControls ?? [])];
  const wizardTemplate = tmplWizard
    ? (isSavedEntityWidgetTemplateId(tmplWizard.template_id)
        ? (() => {
            const c = customEntityWidgets.find(
              (cc) => SAVED_ENTITY_WIDGET_PREFIX + cc.id === tmplWizard.template_id
            );
            return c
              ? {
                  id: tmplWizard.template_id,
                  title: ENTITY_WIDGET_TITLE_PREFIX + c.name,
                  entityDomain: c.device_types?.[0] || "climate",
                  description: c.description || "Saved entity widget",
                }
              : allTemplatesForWizard.find((t) => t?.id === tmplWizard.template_id) ?? null;
          })()
        : allTemplatesForWizard.find((t) => t?.id === tmplWizard.template_id) ?? null)
    : null;
  const wizardIsEntityWidget = !!(wizardTemplate && isEntityWidgetTemplateTitle((wizardTemplate as any).title));
  const wizardIsMultiEntity = !!(tmplWizard && (tmplWizard.template_id.startsWith("glance_card") || tmplWizard.template_id.startsWith("grid_card_")));
  const wizardWantsTapAction = !!(tmplWizard && (tmplWizard.template_id === "entity_card" || tmplWizard.template_id === "tile_card" || tmplWizard.template_id.startsWith("glance_card") || tmplWizard.template_id.startsWith("grid_card_")));
  const wizardEntitySlots = (() => {
    if (!tmplWizard) return 1;
    if (tmplWizard.template_id.startsWith("glance_card")) return tmplGlanceRows || 4;
    if (tmplWizard.template_id.startsWith("grid_card_")) {
      if (tmplGridSize === "3x3") return 9;
      if (tmplGridSize === "3x2") return 6;
      return 4;
    }
    return 1;
  })();

  function lintProject(p: ProjectModel | null) {
    const res: { level: "error" | "warn"; msg: string }[] = [];
    if (!p) return res;
    const pages = p.pages || [];
    const allWidgets: any[] = [];
    for (const pg of pages) {
      if (!pg) continue;
      for (const w of (pg.widgets || []).filter((w: any) => w && typeof w === "object" && w.id != null)) {
        allWidgets.push(w);
      }
    }
    const widgetIds = new Set(allWidgets.map((w) => w.id).filter(Boolean));

    const bindings = ((p as any).bindings || []).filter((b: any) => b && typeof b === "object");
    const links = ((p as any).links || []).filter((l: any) => l && typeof l === "object");

    for (const b of bindings) {
      const eid = String(b?.entity_id || "").trim();
      if (!eid) res.push({ level: "warn", msg: "Binding has empty entity_id (will compile to nothing)." });
      else if (!eid.includes(".")) res.push({ level: "warn", msg: `Binding entity_id looks invalid: ${eid}` });
    }

    for (const ln of links) {
      const wid = String(ln?.target?.widget_id || "").trim();
      const eid = String(ln?.source?.entity_id || "").trim();
      if (wid && !widgetIds.has(wid)) res.push({ level: "error", msg: `Link targets missing widget id: ${wid}` });
      if (eid && !eid.includes(".")) res.push({ level: "warn", msg: `Link source entity_id looks invalid: ${eid}` });
      if (!eid) res.push({ level: "warn", msg: "Link source has empty entity_id (live updates will not work)." });
      if (!wid) res.push({ level: "warn", msg: "Link target has empty widget_id (live updates will not work)." });
    }

    const entitySet = new Set((entities || []).map((e) => e?.entity_id).filter(Boolean));
    for (const b of bindings) {
      const eid = String(b?.entity_id || "").trim();
      if (eid && entitySet.size > 0 && !entitySet.has(eid)) {
        res.push({ level: "warn", msg: `Binding entity_id not found in current HA snapshot: ${eid}` });
      }
    }

    return res;
  }

  function openTemplateWizard(template_id: string, x: number, y: number) {
    setTmplWizard({ template_id, x, y });
    setTmplEntity("");
    setTmplLabel("");
    setTmplCaps(null);
    setTmplVariant("auto");

    // v0.60: entity widget wizard extras
    setTmplTapAction(template_id === "entity_card" ? "more-info" : template_id === "tile_card" ? "toggle" : "toggle");
    setTmplService("");
    setTmplServiceData("");
    setTmplEntities([]);

    // v0.61: defaults for richer entity widget options
    setTmplThMin(5); setTmplThMax(35); setTmplThStep(1);
    setTmplMediaShowTransport(true); setTmplMediaShowVolume(true); setTmplMediaShowMute(true); setTmplMediaShowSource(true); setTmplMediaDefaultSource("");
    setTmplCoverShowTilt(true);
    setTmplGlanceRows(4);
    setTmplGridSize("2x2");
  }

  function pickCapabilityVariant(baseTemplateId: string, caps: any | null, chosen: string): string {
    // v0.36: capability-driven variants for HA controls.
    if (chosen && chosen !== "auto") return chosen;
    const dom = templateDomain(baseTemplateId);
    if (dom === "light") {
      const modes = caps?.attributes?.supported_color_modes;
      if (Array.isArray(modes) && modes.includes("color_temp")) return "ha_light_ct";
      // Default to brightness + toggle, which is widely supported.
      return "ha_light_full";
    }
    if (dom === "cover") {
      // Heuristic: if HA exposes tilt position attributes, prefer the tilt control.
      const hasTilt = caps?.attributes && (caps.attributes.current_tilt_position !== undefined || caps.attributes.tilt_position !== undefined);
      if (hasTilt) return "ha_cover_tilt";
      return "ha_cover_basic";
    }
    if (dom === "media_player") {
      // If HA provides media metadata, prefer the richer template when available.
      const a = caps?.attributes || {};
      const hasMeta = a.media_title !== undefined || a.media_artist !== undefined || a.source_list !== undefined;
      if (hasMeta) return "ha_media_player_full";
      return "ha_media_basic";
    }
    // (Future) climate/cover/media variants.
    return baseTemplateId;
  }

  async function applyTemplateWizard() {
    if (!project || !tmplWizard) {
      if (!project) setToast({ type: "error", msg: "No project loaded. Select a device and open a project first." });
      return;
    }
    const entity_id = tmplEntity.trim();
    const label = tmplLabel.trim() || undefined;
    let built: { widgets?: any[]; bindings?: any[]; links?: any[]; action_bindings?: any[]; scripts?: any[] } | undefined;
    try {
    const p2 = clone(project);
    const allTemplates = [...CONTROL_TEMPLATES, ...(pluginControls || [])].filter((t) => t != null && typeof t === "object");
    let baseId = tmplWizard.template_id;

// v0.61: grid size selector allows choosing a variant at insert time.
if (baseId.startsWith("grid_card_")) {
  if (tmplGridSize === "3x2") baseId = "grid_card_3x2";
  else if (tmplGridSize === "3x3") baseId = "grid_card_3x3";
  else baseId = "grid_card_2x2";
}

// v0.61: glance rows selector chooses a specific template id.
if (baseId.startsWith("glance_card")) {
  if (tmplGlanceRows === 6) baseId = "glance_card_6";
  else if (tmplGlanceRows === 3) baseId = "glance_card_3";
  else if (tmplGlanceRows === 2) baseId = "glance_card_2";
  else baseId = "glance_card";
}

// ha_auto returns empty widgets; must resolve to real template from entity domain + caps
    // Built-in Entity widget templates are never resolved via pickCapabilityVariant (that's for ha_* only)
    const isBuiltInEntityTemplate = (tid: string) => {
      const t = allTemplates.find((x) => x?.id === tid);
      return t && isEntityWidgetTemplateTitle((t as any).title ?? "");
    };
    let resolvedId = baseId;
    if (isSavedEntityWidgetTemplateId(baseId)) {
      resolvedId = baseId;
    } else if (isBuiltInEntityTemplate(baseId)) {
      resolvedId = baseId;
    } else if (baseId === "ha_auto") {
      const dom = entity_id.split(".")[0]?.toLowerCase() || "";
      const caps = tmplCaps;
      if (dom === "light") resolvedId = pickCapabilityVariant("ha_light_full", caps, tmplVariant);
      else if (dom === "cover") resolvedId = pickCapabilityVariant("ha_cover_basic", caps, tmplVariant);
      else if (dom === "media_player") resolvedId = pickCapabilityVariant("ha_media_basic", caps, tmplVariant);
      else if (dom === "climate") {
        const modes = caps?.attributes?.hvac_modes;
        if (Array.isArray(modes) && (modes.includes("cool") || modes.includes("heat_cool"))) resolvedId = "ha_climate_heat_cool";
        else if (Array.isArray(modes) && modes.includes("heat")) resolvedId = "ha_climate_heat_only";
        else resolvedId = "ha_climate_full";
      }
      else if (dom === "switch") resolvedId = "ha_switch_parity";
      else if (dom === "lock") resolvedId = "ha_lock_parity";
      else if (dom === "fan") resolvedId = "ha_fan_parity";
      else if (dom === "alarm_control_panel") resolvedId = "ha_alarm_parity";
      else if (dom === "select") resolvedId = "ha_select_parity";
      else if (dom === "number") resolvedId = "ha_number_parity";
      else if (dom === "input_boolean") resolvedId = "ha_input_boolean";
      else if (dom === "input_number") resolvedId = "ha_input_number";
      else if (dom === "input_select") resolvedId = "ha_input_select";
      else if (dom === "input_text") resolvedId = "ha_input_text";
      else if (dom === "sensor") resolvedId = "ha_sensor_tile";
      else { setToast({ type: "error", msg: `No template for domain: ${dom || "(enter entity_id)"}` }); return; }
    } else {
      resolvedId = pickCapabilityVariant(baseId, tmplCaps, tmplVariant);
    }
    if (isSavedEntityWidgetTemplateId(resolvedId)) {
      const storageId = savedEntityWidgetStorageId(resolvedId);
      try {
        const def = await getSavedEntityWidget(storageId);
        const domain = (def.device_types && def.device_types[0]) || "climate";
        const placeholder = domain + ".example";
        built = {
          widgets: JSON.parse(JSON.stringify(def.widgets || [])),
          bindings: [] as any[],
          links: (def.links || []).map((l: any) => ({ ...l, source: { ...l.source, entity_id: entity_id || placeholder } })),
          action_bindings: (def.action_bindings || []).map((ab: any) => ({
            ...ab,
            call: ab.call ? { ...ab.call, entity_id: ab.call.entity_id ? (entity_id || placeholder) : ab.call.entity_id } : ab.call,
          })),
          scripts: (def.scripts || []).map((s: any) => ({ ...s, entity_id: s.entity_id ? (entity_id || placeholder) : s.entity_id })),
        };
        const seen = new Set<string>();
        for (const l of built.links!) {
          const s = l.source;
          if (!s) continue;
          const key = `${s.entity_id}|${s.kind}|${s.attribute || ""}`;
          if (seen.has(key)) continue;
          seen.add(key);
          built.bindings!.push({ entity_id: s.entity_id, kind: s.kind, attribute: s.attribute || undefined });
        }
      } catch (e: any) {
        setToast({ type: "error", msg: String(e?.message || e) });
        return;
      }
    } else {
      const tmpl = allTemplates.find((t) => t && t.id === resolvedId);
      if (!tmpl) {
        setToast({ type: "error", msg: `Template not found: ${resolvedId}` });
        return;
      }
      built = tmpl.build({
        entity_id,
        entities: tmplEntities,
        x: tmplWizard.x,
        y: tmplWizard.y,
        label,
        tap_action: tmplTapAction,
        service: tmplService,
        service_data: tmplServiceData,
        caps: tmplCaps,

        condition: (() => {
          if (baseId !== "conditional_card") return undefined;
          const v = String(tmplCondValue || "").trim();
          if (!v) return 'x == "on"';
          if (tmplCondNumeric) {
            const num = Number(v);
            if (Number.isFinite(num)) {
              const f = `atof(x.c_str())`;
              if (tmplCondOp === "gt") return `${f} > ${num}`;
              if (tmplCondOp === "lt") return `${f} < ${num}`;
              if (tmplCondOp === "neq") return `${f} != ${num}`;
              return `${f} == ${num}`;
            }
          }
          const esc = v.replaceAll('"', '\\"');
          if (tmplCondOp === "contains") return `x.find(\"${esc}\") != std::string::npos`;
          if (tmplCondOp === "neq") return `x != \"${esc}\"`;
          return `x == \"${esc}\"`;
        })(),

        th_min: tmplThMin,
        th_max: tmplThMax,
        th_step: tmplThStep,

        media_show_transport: tmplMediaShowTransport,
        media_show_volume: tmplMediaShowVolume,
        media_show_mute: tmplMediaShowMute,
        media_show_source: tmplMediaShowSource,
        media_default_source: tmplMediaDefaultSource,

        cover_show_tilt: tmplCoverShowTilt,
      });
    }

    // v0.35: best-effort placeholder substitution for plugin templates.
    const replaceEntity = (s: string) => {
      if (!entity_id) return s;
      return s
        .replaceAll("${entity_id}", entity_id)
        .replaceAll("light.example", entity_id)
        .replaceAll("climate.example", entity_id)
        .replaceAll("cover.example", entity_id)
        .replaceAll("media_player.example", entity_id)
        .replaceAll("switch.example", entity_id);
    };
    for (const w of (built.widgets || []).filter((w: any) => w && typeof w === "object")) {
      if (w.events) {
        for (const k of Object.keys(w.events)) {
          if (typeof w.events[k] === "string") w.events[k] = replaceEntity(w.events[k]);
        }
      }
      if (label && w.props?.text && typeof w.props.text === "string") {
        w.props.text = String(w.props.text).replaceAll("${label}", label);
      }
    }
    for (const b of (built.bindings || []).filter((x: any) => x && typeof x === "object")) {
      if (entity_id && (!b.entity_id || String(b.entity_id).endsWith(".example"))) b.entity_id = entity_id;
    }
    for (const l of (built.links || []).filter((x: any) => x && typeof x === "object")) {
      if (entity_id && l.source && (!l.source.entity_id || String(l.source.entity_id).endsWith(".example"))) l.source.entity_id = entity_id;
    }
    const rawWidgets = (built.widgets || []).filter((w: any) => w != null && typeof w === "object");
    if (rawWidgets.length === 0) {
      setToast({ type: "error", msg: "Template returned no widgets." });
      return;
    }
    const validLinksForInsert = (built.links || []).filter((l: any) => l && typeof l === "object");
    const usedIds = new Set<string>((p2?.pages?.[safePageIndex]?.widgets || []).map((x: any) => x?.id).filter(Boolean));
    const ws: any[] = [];
    const idMap = new Map<string, string>();
    for (let i = 0; i < rawWidgets.length; i++) {
      const w = rawWidgets[i];
      const linkToThis = validLinksForInsert.find((l: any) => l?.target?.widget_id === w.id);
      const newId = linkToThis?.source?.entity_id
        ? friendlyWidgetIdFromBinding(
            linkToThis.source.entity_id,
            linkToThis.source.attribute ?? "",
            usedIds
          )
        : uid(w.type || "w");
      usedIds.add(newId);
      const obj = { ...w, id: newId };
      if (obj.id == null) {
        console.warn("[Insert] Widget at index", i, "had no id after spread:", w);
        continue;
      }
      ws.push(obj);
      if (w.id != null) idMap.set(String(w.id), newId);
    }
    if (ws.length === 0) {
      setToast({ type: "error", msg: "Template returned no valid widgets (check console)." });
      return;
    }
    const validLinks = (built.links || []).filter((l: any) => l && typeof l === "object");
    const links = validLinks.map((l: any) => {
      const wid = l?.target?.widget_id;
      if (wid && idMap.has(wid)) {
        return { ...l, target: { ...l.target, widget_id: idMap.get(wid) } };
      }
      return l;
    });

    const insertX = tmplWizard.x;
    const insertY = tmplWizard.y;
    const isEntityBundleTemplate =
      /_card$/.test(tmplWizard.template_id) || isSavedEntityWidgetTemplateId(tmplWizard.template_id);

    if (isEntityBundleTemplate && ws.length > 0) {
      const ids = new Set(ws.map((w: any) => w?.id).filter(Boolean));
      const roots = ws.filter((w: any) => w && (!w.parent_id || !ids.has(w.parent_id)));
      if (roots.length === 1 && roots[0].type === "container") {
        const root = roots[0];
        root.x = insertX;
        root.y = insertY;
      } else {
        let minX = Infinity,
          minY = Infinity,
          maxX = -Infinity,
          maxY = -Infinity;
        for (const w of ws) {
          const x = Number(w.x ?? 0),
            y = Number(w.y ?? 0),
            ww = Number(w.w ?? 0),
            hh = Number(w.h ?? 0);
          minX = Math.min(minX, x);
          minY = Math.min(minY, y);
          maxX = Math.max(maxX, x + ww);
          maxY = Math.max(maxY, y + hh);
        }
        const gw = Math.max(1, maxX - minX),
          gh = Math.max(1, maxY - minY);
        const firstIsContainer = ws[0].type === "container";
        if (firstIsContainer) {
          ws[0].x = insertX;
          ws[0].y = insertY;
          ws[0].w = gw;
          ws[0].h = gh;
          for (let i = 1; i < ws.length; i++) {
            ws[i].parent_id = ws[0].id;
            ws[i].x = Number(ws[i].x ?? 0) - minX;
            ws[i].y = Number(ws[i].y ?? 0) - minY;
          }
        } else {
          const groupId = uid("group");
          const groupWidget = {
            id: groupId,
            type: "container",
            x: insertX,
            y: insertY,
            w: gw,
            h: gh,
            props: {},
            style: { bg_color: 0x1e1e1e, radius: 10 },
          };
          for (const w of ws) {
            w.parent_id = groupId;
            w.x = Number(w.x ?? 0) - minX;
            w.y = Number(w.y ?? 0) - minY;
          }
          ws.unshift(groupWidget as any);
        }
      }
    } else {
      for (const w of ws) {
        w.x = Number(w.x ?? 0) + insertX;
        w.y = Number(w.y ?? 0) + insertY;
      }
    }

    // Entity palette templates use a fixed card size; shrink container trees to descendant bounds
    // so nested clipping containers do not keep stale sizes.
    if (isEntityBundleTemplate && ws.length > 0) {
      const idSet = new Set(ws.map((w: any) => w?.id).filter(Boolean));
      const roots = ws.filter((w: any) => w && (!w.parent_id || !idSet.has(w.parent_id)));
      if (roots.length === 1 && (roots[0].type === "container" || roots[0].type === "obj")) {
        const hasKids = ws.some((w: any) => w && w.parent_id === roots[0].id);
        if (hasKids) fitContainerTreeToDescendantBounds(ws, roots[0].id);
      }
    }

    // Ensure pages structure exists (defensive for edge-case project shapes)
    if (!Array.isArray(p2.pages) || p2.pages.length === 0) {
      p2.pages = [{ page_id: uid("page"), name: "Main", widgets: [] }];
    }
    const page = p2.pages[safePageIndex] ?? p2.pages[0];
    if (!page) return setToast({ type: "error", msg: "No page to add widgets to" });
    if (!Array.isArray(page.widgets)) page.widgets = [];
    // Strip any null/undefined from existing page.widgets so next render never sees them
    const beforeLen = page.widgets.length;
    page.widgets = page.widgets.filter((w: any) => w != null && typeof w === "object" && w.id != null);
    if (page.widgets.length < beforeLen) {
      console.warn("[Insert] Removed", beforeLen - page.widgets.length, "invalid widget(s) from current page (existing data).");
    }
    page.widgets.push(...ws);
    (p2 as any).bindings = Array.isArray((p2 as any).bindings) ? (p2 as any).bindings : [];
    (p2 as any).links = Array.isArray((p2 as any).links) ? (p2 as any).links : [];
    (p2 as any).bindings.push(
      ...(built.bindings || []).filter((b: any) => b && typeof b === "object")
    );
    (p2 as any).links.push(...links.filter((l: any) => l && typeof l === "object"));
    if (Array.isArray((built as any).scripts) && (built as any).scripts.length > 0) {
      (p2 as any).scripts = Array.isArray((p2 as any).scripts) ? (p2 as any).scripts : [];
      const rootId = ws[0]?.id ?? null;
      for (const s of (built as any).scripts) {
        if (s && typeof s === "object" && s.id && s.entity_id) {
          let scriptEntity = s.entity_id;
          if (entity_id && (String(scriptEntity || "").endsWith(".example") || !scriptEntity)) scriptEntity = entity_id;
          (p2 as any).scripts.push({ ...s, entity_id: scriptEntity, _source_root_id: rootId });
        }
      }
    }
    if (Array.isArray((built as any).action_bindings) && (built as any).action_bindings.length > 0) {
      (p2 as any).action_bindings = Array.isArray((p2 as any).action_bindings) ? (p2 as any).action_bindings : [];
      for (const ab of (built as any).action_bindings) {
        if (ab && typeof ab === "object" && ab.widget_id) {
          const newWid = idMap.get(ab.widget_id);
          (p2 as any).action_bindings.push({
            ...ab,
            widget_id: newWid != null ? newWid : ab.widget_id,
          });
        }
      }
    }

    setProject(p2, true);
    setProjectDirty(true);
    if (ws[0]?.id) {
      setSelectedWidgetIds([ws[0].id]);
      setInspectorTab("properties");
      getWidgetSchema(ws[0].type).then((sr) => { if (sr.ok) setSelectedSchema(sr.schema); });
    }
    setTmplWizard(null);
    setToast({ type: "ok", msg: `Added ${ws.length} widget(s) to canvas` });
    } catch (err) {
      try {
        const msg = String(err instanceof Error ? err.message : err ?? "unknown");
        setToast({ type: "error", msg: `Insert failed: ${msg}` });
        console.error("[Insert] applyTemplateWizard failed:", msg, "template_id:", tmplWizard?.template_id);
        if (typeof built !== "undefined") {
          const w = (built as any).widgets;
          console.error("[Insert] built.widgets:", Array.isArray(w) ? w.length + " items" : typeof w, Array.isArray(w) ? w.slice(0, 10).map((x: any, i: number) => (x != null && x.id != null ? x.id : "null/undefined@" + i)) : []);
        }
      } catch (_) {
        setToast({ type: "error", msg: "Insert failed (see console)." });
      }
      console.error(err);
    }
  }

  async function saveEditedDevice() {
    if (!selectedDevice || !newDeviceName.trim()) return;
    if (!entryId) {
      setToast({ type: "error", msg: INTEGRATION_NOT_CONFIGURED_MSG });
      return;
    }
    setBusy(true);
    try {
      const res = await upsertDevice(entryId, {
        device_id: selectedDevice,
        name: newDeviceName.trim(),
        slug: newDeviceSlug.trim() || undefined,
        api_key: newDeviceApiKey.trim() || undefined,
        ota_password: newDeviceOtaPassword.trim() || undefined,
        device_settings: {
          ...((selectedDeviceObj as any)?.device_settings || {}),
          wifi_ssid: newDeviceWifiSsid.trim() || "",
          wifi_password: newDeviceWifiPassword.trim() || "",
        },
        hardware_recipe_id: editDeviceRecipeId.trim() || undefined,
      });
      if (!res.ok) return setToast({ type: "error", msg: res.error });
      setToast({ type: "ok", msg: "Device updated" });
      setEditDeviceModalOpen(false);
      setNewDeviceId(""); setNewDeviceName(""); setNewDeviceSlug(""); setNewDeviceApiKey(""); setNewDeviceOtaPassword(""); setEditDeviceRecipeId(""); setNewDeviceWifiSsid(""); setNewDeviceWifiPassword("");
      await refresh();
    } finally { setBusy(false); }
  }

  function regenerateApiKey() {
    const arr = new Uint8Array(32);
    crypto.getRandomValues(arr);
    const base64 = btoa(String.fromCharCode(...arr));
    setNewDeviceApiKey(base64);
  }

  async function createNewDeviceFromWizard() {
    if (!newDeviceWizardRecipe || !newDeviceWizardId.trim()) return;
    if (!entryId) {
      setToast({ type: "error", msg: INTEGRATION_NOT_CONFIGURED_MSG });
      return;
    }
    const did = newDeviceWizardId.trim();
    setBusy(true);
    try {
      const res = await upsertDevice(entryId, {
        device_id: did,
        name: newDeviceWizardName.trim() || did,
        slug: newDeviceWizardSlug.trim() || undefined,
        hardware_recipe_id: newDeviceWizardRecipe.id,
        api_key: newDeviceWizardApiKey.trim() || undefined,
        ota_password: newDeviceWizardOtaPassword.trim() || undefined,
        device_settings: {
          wifi_ssid: newDeviceWizardWifiSsid.trim() || "",
          wifi_password: newDeviceWizardWifiPassword.trim() || "",
        },
      });
      if (!res.ok) return setToast({ type: "error", msg: res.error });
      setToast({ type: "ok", msg: "Device created" });
      setNewDeviceWizardOpen(false);
      setNewDeviceWizardStep(1);
      setNewDeviceWizardRecipe(null);
      setNewDeviceWizardId("");
      setNewDeviceWizardName("");
      setNewDeviceWizardSlug("");
      setNewDeviceWizardApiKey("");
      setNewDeviceWizardOtaPassword("");
      setNewDeviceWizardWifiSsid("");
      setNewDeviceWizardWifiPassword("");
      await refresh();
      await loadDevice(did);
    } finally { setBusy(false); }
  }

  function openEditDeviceModal() {
    if (!selectedDeviceObj) return;
    setNewDeviceId(selectedDeviceObj.device_id);
    setNewDeviceName(selectedDeviceObj.name || "");
    setNewDeviceSlug(selectedDeviceObj.slug || selectedDeviceObj.device_id || "");
    setNewDeviceApiKey(selectedDeviceObj.api_key ?? "");
    setNewDeviceOtaPassword(selectedDeviceObj.ota_password ?? "");
    setNewDeviceWifiSsid(String((selectedDeviceObj as any)?.device_settings?.wifi_ssid ?? ""));
    setNewDeviceWifiPassword(String((selectedDeviceObj as any)?.device_settings?.wifi_password ?? ""));
    setEditDeviceRecipeId(selectedDeviceObj.hardware_recipe_id ?? "");
    setEditDeviceModalOpen(true);
  }

  function openNewDeviceWizard() {
    setNewDeviceWizardOpen(true);
    setNewDeviceWizardStep(1);
    setNewDeviceWizardRecipe(null);
    setNewDeviceWizardId("");
    setNewDeviceWizardName("");
    setNewDeviceWizardSlug("");
    setNewDeviceWizardApiKey("");
    setNewDeviceWizardOtaPassword("");
    setNewDeviceWizardWifiSsid("");
    setNewDeviceWizardWifiPassword("");
    refreshRecipes(); // Refetch recipes when wizard opens (handles late load or retry)
  }

  function regenerateWizardApiKey() {
    const arr = new Uint8Array(32);
    crypto.getRandomValues(arr);
    setNewDeviceWizardApiKey(btoa(String.fromCharCode(...arr)));
  }

  function wizardSelectRecipe(r: { id: string; label: string }) {
    setNewDeviceWizardRecipe(r);
    const derived = friendlyToId(r.label || r.id);
    setNewDeviceWizardName(r.label || r.id);
    setNewDeviceWizardId(derived);
    setNewDeviceWizardSlug(derived);
    const arr = new Uint8Array(32);
    crypto.getRandomValues(arr);
    setNewDeviceWizardApiKey(btoa(String.fromCharCode(...arr)));
    setNewDeviceWizardStep(2);
  }

  async function removeDevice(id: string) {
    if (!entryId) {
      setToast({ type: "error", msg: INTEGRATION_NOT_CONFIGURED_MSG });
      return;
    }
    setBusy(true);
    try {
      const res = await deleteDevice(entryId, id);
      if (!res.ok) return setToast({ type: "error", msg: res.error });
      setToast({ type: "ok", msg: "Device deleted" });
      if (selectedDevice === id) { setSelectedDevice(""); setProject(null); }
      setRecentDeviceIds((prev) => {
        const next = prev.filter((x) => x !== id);
        try {
          localStorage.setItem(RECENT_DEVICES_KEY, JSON.stringify(next));
        } catch {}
        return next;
      });
      await refresh();
    } finally { setBusy(false); }
  }

  async function copyDevice(sourceId: string, newName: string, newSlug: string) {
    if (!entryId) {
      setToast({ type: "error", msg: INTEGRATION_NOT_CONFIGURED_MSG });
      return;
    }
    setBusy(true);
    try {
      const projRes = await getProject(entryId, sourceId);
      if (!projRes.ok) return setToast({ type: "error", msg: projRes.error });
      const source = devices.find((d) => d.device_id === sourceId);
      const newDeviceId = friendlyToId(newSlug) || friendlyToId(newName) || "device_copy";
      const upsertRes = await upsertDevice(entryId, {
        device_id: newDeviceId,
        name: newName,
        slug: newSlug,
        hardware_recipe_id: source?.hardware_recipe_id ?? null,
        ota_password: source?.ota_password ?? null,
      });
      if (!upsertRes.ok) return setToast({ type: "error", msg: upsertRes.error });
      const putRes = await putProject(entryId, newDeviceId, projRes.project);
      if (!putRes.ok) return setToast({ type: "error", msg: putRes.error });
      setToast({ type: "ok", msg: `Device "${newName}" created` });
      await refresh();
      setManageDevicesOpen(false);
      await loadDevice(newDeviceId);
    } finally { setBusy(false); }
  }

  async function loadDevice(id: string, opts?: { saveAfterLoad?: boolean }) {
    if (!entryId) {
      setToast({ type: "error", msg: INTEGRATION_NOT_CONFIGURED_MSG });
      return;
    }
    setBusy(true);
    try {
      const res = await getProject(entryId, id);
      if (!res.ok) return setToast({ type: "error", msg: res.error });
      setSelectedDevice(id);
      // If we have a local draft (e.g. user navigated away), offer to restore it.
      let nextProject = res.project;
      let restoredPageIndex: number | null = null;
      try {
        const rawDraft = localStorage.getItem(draftKeyForDevice(id));
        if (rawDraft) {
          const draft = JSON.parse(rawDraft) as { project?: any; pageIndex?: number; ts?: number };
          const draftProj = draft?.project;
          const differs = draftProj && JSON.stringify(draftProj) !== JSON.stringify(res.project);
          if (differs && window.confirm("Unsaved changes were found for this device. Restore them?")) {
            nextProject = draftProj;
            restoredPageIndex = typeof draft?.pageIndex === "number" ? draft.pageIndex : null;
            setProjectDirty(true);
          } else {
            setProjectDirty(false);
          }
        } else {
          setProjectDirty(false);
        }
      } catch {
        setProjectDirty(false);
      }
      setProject(nextProject);
      setSelectedWidgetIds([]);
      setSelectedSchema(null);
      setCurrentPageIndex(restoredPageIndex != null ? restoredPageIndex : 0);
      setRecentDeviceIds((prev) => {
        const next = [id, ...prev.filter((x) => x !== id)].slice(0, 4);
        try {
          localStorage.setItem(RECENT_DEVICES_KEY, JSON.stringify(next));
        } catch {}
        return next;
      });
      if (opts?.saveAfterLoad) {
        const putRes = await putProject(entryId, id, nextProject);
        if (!putRes.ok) {
          setToast({ type: "error", msg: `Loaded project but save failed: ${putRes.error}` });
          setProjectDirty(true);
        } else {
          setProjectDirty(false);
          try {
            localStorage.removeItem(draftKeyForDevice(id));
          } catch {}
          setToast({ type: "ok", msg: "Imported device — project saved" });
        }
      } else {
        setToast({ type: "ok", msg: `Loaded device` });
      }
    } finally { setBusy(false); }
  }

  const widgets = useMemo(
    () => {
      const raw = pages?.[safePageIndex]?.widgets ?? [];
      const filtered = raw.filter((w: any) => w && typeof w === "object" && w.id != null);
      console.log('[ETD widgets useMemo] safePageIndex:', safePageIndex, 'raw:', raw.length, 'filtered:', filtered.length);
      return filtered;
    },
    [pages, safePageIndex]
  );

  // Persist a local draft so navigating away from the HA sidebar doesn't lose work.
  useEffect(() => {
    if (!selectedDevice || !project) return;
    if (!projectDirty) return;
    const t = window.setTimeout(() => {
      try {
        localStorage.setItem(
          draftKeyForDevice(selectedDevice),
          JSON.stringify({ ts: Date.now(), project, pageIndex: currentPageIndex })
        );
      } catch {}
    }, 300);
    return () => window.clearTimeout(t);
  }, [selectedDevice, project, projectDirty, currentPageIndex]);

  const widgetsFlat = useMemo(() => {
    const out: any[] = [];
    function collect(list: any[]) {
      for (const w of list || []) {
        if (!w || typeof w !== "object" || w.id == null) continue;
        out.push(w);
        if (Array.isArray((w as any).widgets)) collect((w as any).widgets);
      }
    }
    collect(pages?.[safePageIndex]?.widgets ?? []);
    return out.length ? out : widgets;
  }, [pages, safePageIndex, widgets]);

  const { resolvePreviewFont, fontPreviewBanner } = usePreviewFontResolver(widgetsFlat, assets);

  // Live overrides for canvas: from links + liveEntityStates, compute per-widget display values.
  const liveOverrides = useMemo(() => {
    const links = (project as any)?.links ?? [];
    const pages = (project as any)?.pages ?? [];
    const overrides: Record<string, { text?: string; value?: number; checked?: boolean }> = {};
    const widgetTypeById: Record<string, string> = {};
    const containerToSpinboxChildId: Record<string, string> = {};
    for (const page of pages) {
      for (const w of page?.widgets ?? []) {
        if (w?.id) widgetTypeById[w.id] = w.type ?? "label";
        if ((w as any)?.parent_id && (w as any)?.type === "spinbox" && w?.id) containerToSpinboxChildId[(w as any).parent_id] = w.id;
      }
    }
    for (const ln of links) {
      const src = ln?.source;
      const tgt = ln?.target;
      const rawWidgetId = typeof tgt?.widget_id === "object" && tgt?.widget_id != null && "id" in tgt?.widget_id
        ? (tgt.widget_id as { id: string }).id
        : (Array.isArray(tgt?.widget_id) ? tgt?.widget_id?.[0] : tgt?.widget_id);
      const widgetId = typeof rawWidgetId === "string" ? rawWidgetId : (rawWidgetId && typeof (rawWidgetId as any)?.id === "string" ? (rawWidgetId as any).id : String(rawWidgetId ?? ""));
      const entityId = src?.entity_id;
      const kind = src?.kind || "state";
      const attr = src?.attribute ?? "";
      const action = tgt?.action || "";
      const fmt = (tgt?.format != null && String(tgt.format).trim() !== "") ? String(tgt.format).trim() : "%.1f";
      const scale = typeof tgt?.scale === "number" ? tgt.scale : 1;
      if (!widgetId || !entityId) continue;
      const data = liveEntityStates[entityId];
      if (!data) continue;
      let raw: any = data.state;
      if (kind === "attribute_number" && attr) {
        const v = data.attributes?.[attr];
        if (v != null && typeof v === "number" && !Number.isNaN(v)) raw = v;
        else if (v != null && typeof v === "string") raw = parseFloat(v);
        else raw = NaN;
        if (Number.isNaN(raw) && typeof data.state === "string") raw = parseFloat(data.state);
      } else if (kind === "attribute_text" && attr) {
        raw = data.attributes?.[attr] ?? "";
        if (raw === "" && typeof data.state === "string") raw = data.state;
      } else if (kind === "binary") {
        raw = (data.state || "").toLowerCase() === "on";
      }
      if (action === "label_text") {
        const displayTargetId = widgetTypeById[widgetId] === "container" && containerToSpinboxChildId[widgetId]
          ? containerToSpinboxChildId[widgetId]
          : widgetId;
        if (typeof raw === "number" && !Number.isNaN(raw)) {
          const n = raw * scale;
          const s = fmt.replace("%.2f", n.toFixed(2)).replace("%.1f", n.toFixed(1)).replace("%.0f", String(Math.round(n)));
          overrides[displayTargetId] = { ...overrides[displayTargetId], text: s };
          if (widgetTypeById[displayTargetId] === "spinbox") overrides[displayTargetId] = { ...overrides[displayTargetId], value: n };
        } else {
          const fallback = kind === "attribute_number" ? "--" : String(raw ?? "");
          const existing = overrides[displayTargetId]?.text ?? "";
          if (fallback !== "" || existing === "") overrides[displayTargetId] = { ...overrides[displayTargetId], text: fallback || existing || "" };
        }
      } else if (action === "label_number") {
        if (typeof raw === "number" && !Number.isNaN(raw)) {
          const n = raw * scale;
          overrides[widgetId] = { ...overrides[widgetId], text: String(Math.round(n)) };
        }
      } else if (action === "arc_value" || action === "slider_value" || action === "bar_value") {
        const num = typeof raw === "number" ? raw : parseFloat(String(raw));
        if (!Number.isNaN(num)) overrides[widgetId] = { ...overrides[widgetId], value: num * scale };
      } else if (action === "spinbox2_value") {
        if (widgetTypeById[widgetId] === "spinbox2") {
          const num = typeof raw === "number" ? raw : parseFloat(String(raw ?? ""));
          if (!Number.isNaN(num)) {
            const n = num * scale;
            const s = fmt.replace("%.2f", n.toFixed(2)).replace("%.1f", n.toFixed(1)).replace("%.0f", String(Math.round(n)));
            overrides[widgetId] = { ...overrides[widgetId], value: n, text: s };
          }
        }
      } else if (action === "widget_checked") {
        overrides[widgetId] = { ...overrides[widgetId], checked: !!raw };
      } else if (action === "button_bg_color") {
        const rgb = data.attributes?.rgb_color;
        if (Array.isArray(rgb) && rgb.length >= 3) {
          const r = Math.max(0, Math.min(255, Number(rgb[0]) || 0));
          const g = Math.max(0, Math.min(255, Number(rgb[1]) || 0));
          const b = Math.max(0, Math.min(255, Number(rgb[2]) || 0));
          overrides[widgetId] = { ...overrides[widgetId], value: (r << 16) | (g << 8) | b };
        }
      } else if (action === "button_white_temp") {
        const mireds = typeof raw === "number" && !Number.isNaN(raw) ? raw : Number(data.attributes?.color_temp);
        if (mireds != null && !Number.isNaN(mireds)) {
          overrides[widgetId] = { ...overrides[widgetId], value: Math.max(153, Math.min(500, mireds)) };
        }
      } else if (action === "led_brightness") {
        const v = typeof raw === "number" && !Number.isNaN(raw) ? raw * scale : (raw ? 100 : 0);
        overrides[widgetId] = { ...overrides[widgetId], value: Math.max(0, Math.min(100, v)) };
      }
    }
    return overrides;
  }, [project, liveEntityStates]);

  const handleSimulatorAction = useCallback(
    (widgetId: string, event: string, payload?: { value?: number; checked?: boolean; selected_index?: number; text?: string }) => {
      const actionBindings = (project as any)?.action_bindings || [];
      const ab = actionBindings.find((a: any) => String(a?.widget_id) === widgetId && String(a?.event) === event);
      const call = ab?.call;
      if (!call?.domain || !call?.service) {
        setToast({ type: "error", msg: `No action binding for ${event}. Add one in Binding Builder (Action tab) or add a display binding with "Also create action bindings" checked.` });
        return;
      }
      const cur = simOverrides[widgetId];
      const value = payload?.value ?? cur?.value;
      const checked = payload?.checked ?? cur?.checked;
      const selected_index = payload?.selected_index ?? cur?.selected_index;
      const text = payload?.text ?? cur?.text;
      const entityId = call.entity_id || (call.data && (call.data as any).entity_id);
      const serviceData: Record<string, unknown> = entityId ? { entity_id: entityId } : {};
      const data = call.data || {};
      for (const [k, v] of Object.entries(data)) {
        if (k === "entity_id") continue;
        const isLambda = typeof v === "string" && (String(v).startsWith("!lambda") || String(v).includes("return"));
        if (isLambda) {
          if (k === "volume_level" && (value != null || value === 0)) serviceData[k] = Number(value) / 100;
          else if (typeof value === "number") serviceData[k] = value;
          else if (typeof checked === "boolean") serviceData[k] = checked;
          else if (typeof selected_index === "number") serviceData[k] = selected_index;
          else if (typeof text === "string") serviceData[k] = text;
          else serviceData[k] = value ?? 0;
        } else {
          serviceData[k] = v;
        }
      }
      callService(call.domain, call.service, serviceData).then((res) => {
        if (res.ok) setToast({ type: "ok", msg: `Action: ${event} → ${call.domain}.${call.service}` });
        else setToast({ type: "error", msg: res.error || "Service call failed" });
      }).catch((err) => setToast({ type: "error", msg: String(err?.message || err) }));
    },
    [project, simOverrides, callService]
  );

  /** Physical display size only — from saved project device.screen (API fills from recipe) or WxH in recipe id. No invented defaults. */
  const screenSize = useMemo(
    () => resolveDeviceScreen(project, selectedDeviceObj?.hardware_recipe_id ?? null),
    [project, selectedDeviceObj?.hardware_recipe_id],
  );

  const handleMacSim = useCallback(async () => {
    if (!entryId || !selectedDevice || !project) {
      setToast({ type: "error", msg: "Mac sim: select a device and load a project." });
      return;
    }
    if (!screenSize) {
      setToast({
        type: "error",
        msg: "Mac sim: display size is unknown. Reload the device (project includes size from the hardware recipe) or use a recipe id with resolution (e.g. 1024x600).",
      });
      return;
    }
    setMacSimBusy(true);
    try {
      const res = await enqueueMacSim(entryId, {
        device_id: selectedDevice,
        project,
        hardware_recipe_id: selectedDeviceObj?.hardware_recipe_id ?? (project as any)?.device?.hardware_recipe_id,
        screen: { width: screenSize.width, height: screenSize.height },
      });
      const extra =
        res.mac_sim_api_key_generated && res.mac_sim_api_key_hint
          ? ` ${res.mac_sim_api_key_hint}`
          : "";
      setToast({
        type: "ok",
        msg: `Mac sim: host/SDL YAML sent to your connected Mac agent (ESPHome window should open there).${extra}`,
      });
    } catch (e: any) {
      setToast({ type: "error", msg: `Mac sim: ${e?.message || e}` });
    } finally {
      setMacSimBusy(false);
    }
  }, [
    entryId,
    selectedDevice,
    project,
    selectedDeviceObj?.hardware_recipe_id,
    screenSize,
  ]);

  function _findWidget(id: string) {
    return widgets.find((w: any) => w && w.id === id);
  }

  function _childrenOf(parentId: string) {
    return widgets.filter((w: any) => w && w.parent_id === parentId);
  }

  function _absPos(w: any): { ax: number; ay: number } {
    let ax = Number(w.x || 0);
    let ay = Number(w.y || 0);
    let p = w.parent_id ? _findWidget(w.parent_id) : null;
    let guard = 0;
    while (p && guard++ < 10) {
      ax += Number(p.x || 0);
      ay += Number(p.y || 0);
      p = p.parent_id ? _findWidget(p.parent_id) : null;
    }
    return { ax, ay };
  }

  // v0.18: Grouping as a container widget (children become parent-relative).
  function groupSelected() {
    if (!project) return;
    if (selectedWidgetIds.length < 2) return;
    const sel = selectedWidgetIds.map(_findWidget).filter(Boolean) as any[];
    if (sel.length < 2) return;
    // Only group widgets with the same parent (simple rule for now)
    const parentId = sel[0].parent_id || "";
    if (!sel.every((w) => (w.parent_id || "") === parentId)) {
      setToast({ type: "error", msg: "Grouping currently requires all selected widgets to share the same parent." });
      return;
    }

    const abs = sel.map((w) => ({ w, ..._absPos(w) }));
    const minX = Math.min(...abs.map((x) => x.ax));
    const minY = Math.min(...abs.map((x) => x.ay));
    const maxX = Math.max(...abs.map((x) => x.ax + (x.w.w || 0)));
    const maxY = Math.max(...abs.map((x) => x.ay + (x.w.h || 0)));

    const parentWidget = parentId ? _findWidget(parentId) : null;
    const parentAbs = parentWidget ? _absPos(parentWidget) : { ax: 0, ay: 0 };
    const containerId = uid("container");
    const container = {
      id: containerId,
      type: "container",
      x: minX - parentAbs.ax,
      y: minY - parentAbs.ay,
      w: Math.max(40, maxX - minX),
      h: Math.max(40, maxY - minY),
      parent_id: parentId || undefined,
      props: { clickable: false, scrollable: false, layout: "NONE" },
      style: { border_width: 1, border_color: "#10b981", bg_color: "#00000000" },
      events: {},
    };

    const p2 = clone(project);
    const page = (p2 as any).pages?.[safePageIndex];
    if (!page?.widgets) return;
    const list = page.widgets as any[];
    // Insert container just before the first selected widget to keep approximate z-order.
    const firstIdx = Math.min(...sel.map((w) => list.findIndex((x) => x && x.id === w.id)).filter((i) => i >= 0));
    list.splice(firstIdx >= 0 ? firstIdx : list.length, 0, container);

    // Re-parent selected widgets under container with relative coords.
    for (const entry of abs) {
      const w = list.find((x) => x && x.id === entry.w.id);
      if (!w) continue;
      w.parent_id = containerId;
      w.x = entry.ax - minX;
      w.y = entry.ay - minY;
    }

    setProject(p2, true);
    setProjectDirty(true);
    setSelectedWidgetIds([containerId]);
  }

  // v0.18: Ungroup (only works when selecting a container).
  function ungroupSelected() {
    if (!project) return;
    if (selectedWidgetIds.length !== 1) return;
    const w0 = _findWidget(selectedWidgetIds[0]);
    if (!w0 || String(w0.type).toLowerCase() !== "container") return;
    const kids = _childrenOf(w0.id);

    const p2 = clone(project);
    const page = (p2 as any).pages?.[safePageIndex];
    if (!page?.widgets) return;
    const list = page.widgets as any[];
    const container = list.find((x) => x && x.id === w0.id);
    if (!container) return;
    const parentId = container.parent_id || "";
    const containerAbs = _absPos(container);
    const parentWidget = parentId ? _findWidget(parentId) : null;
    const parentAbs = parentWidget ? _absPos(parentWidget) : { ax: 0, ay: 0 };

    for (const k of kids) {
      const kk = list.find((x) => x && x.id === k.id);
      if (!kk) continue;
      // Convert from container-relative -> parent-relative (or top-level absolute)
      const absKx = containerAbs.ax + Number(kk.x || 0);
      const absKy = containerAbs.ay + Number(kk.y || 0);
      kk.parent_id = parentId || undefined;
      kk.x = absKx - parentAbs.ax;
      kk.y = absKy - parentAbs.ay;
    }

    // Remove container
    const idx = list.findIndex((x) => x && x.id === container.id);
    if (idx >= 0) list.splice(idx, 1);
    setProject(p2, true);
    setProjectDirty(true);
    setSelectedWidgetIds(kids.map((k) => k.id));
  }

  // v0.18: Z-order within the current page list (only within same parent). List order = draw order (first = back, last = front).
  // Back = send selection to very back of sibling group; Front = bring to very front (one click reveals/hides correctly).
  function moveZ(direction: "front" | "back") {
    if (!project) return;
    if (!selectedWidgetIds.length) return;
    const p2 = clone(project);
    const page = (p2 as any).pages?.[safePageIndex];
    if (!page?.widgets) return;
    const list = page.widgets as any[];
    const sel = selectedWidgetIds.map((id) => list.find((x) => x && x.id === id)).filter(Boolean) as any[];
    if (!sel.length) return;
    const parentId = sel[0].parent_id || "";
    if (!sel.every((w) => (w.parent_id || "") === parentId)) {
      setToast({ type: "error", msg: "Z-order moves currently require all selected widgets to share the same parent." });
      return;
    }
    const idxs = sel.map((w) => list.findIndex((x) => x && x.id === w.id)).filter((i) => i >= 0).sort((a, b) => a - b);
    if (!idxs.length) return;
    const block = idxs.map((i) => list[i]);
    // Remove selected from list (back to front so indices stay valid)
    for (let i = idxs.length - 1; i >= 0; i--) list.splice(idxs[i], 1);
    // Siblings = same parent_id in the list after removal; insert so selection goes to very back or very front
    const siblingIndices = list
      .map((w, i) => (w && (w.parent_id || "") === parentId ? i : -1))
      .filter((i) => i >= 0);
    if (direction === "back") {
      const insertAt = siblingIndices.length > 0 ? siblingIndices[0] : 0;
      list.splice(insertAt, 0, ...block);
    } else {
      const insertAt = siblingIndices.length > 0 ? siblingIndices[siblingIndices.length - 1] + 1 : list.length;
      list.splice(insertAt, 0, ...block);
    }
    setProject(p2, true);
    setProjectDirty(true);
  }

  // v0.19: Copy/Paste selected widgets (within the active page).
  function copySelected() {
    if (!selectedWidgetIds.length) return;
    const sel = selectedWidgetIds.map(_findWidget).filter(Boolean);
    if (!sel.length) return;
    // Copy as deep-cloned fragments.
    setClipboard(sel.map((w) => clone(w)));
    setToast({ type: "ok", msg: `Copied ${sel.length} widget(s)` });
  }

  function pasteClipboard() {
    if (!project) return;
    if (!clipboard?.length) return;
    const p2 = clone(project);
    const page = (p2 as any).pages?.[safePageIndex];
    if (!page?.widgets) return;
    const list = page.widgets as any[];

    // Paste offset: 12px right/down each time.
    const offset = 12;
    const idMap = new Map<string, string>();
    const pasted: any[] = [];

    // Only paste widgets that either have no parent or whose parent also exists in the clipboard.
    const clipIds = new Set(clipboard.filter((w) => w && w.id).map((w) => w.id));
    const clipRoots = clipboard.filter((w) => w && w.id && (!w.parent_id || clipIds.has(w.parent_id)));

    for (const w0 of clipRoots) {
      const w = clone(w0);
      const newId = uid(w.type || "widget");
      idMap.set(w.id, newId);
      w.id = newId;
      // Update parent_id if parent in clipboard
      if (w.parent_id && idMap.has(w.parent_id)) w.parent_id = idMap.get(w.parent_id);
      // Apply offset in its own coordinate space.
      w.x = Number(w.x || 0) + offset;
      w.y = Number(w.y || 0) + offset;
      pasted.push(w);
    }

    // Second pass to fix parent_ids for children pasted after parents.
    for (const w of pasted) {
      if (w.parent_id && idMap.has(w.parent_id)) w.parent_id = idMap.get(w.parent_id);
    }

    // Copy and remap action_bindings for pasted widgets so the new widgets get the same bindings.
    const abs = (p2 as any).action_bindings || [];
    const toAdd: any[] = [];
    for (const ab of abs) {
      const wid = String(ab?.widget_id || "").trim();
      if (clipIds.has(wid) && idMap.has(wid)) {
        const cloned = clone(ab);
        cloned.widget_id = idMap.get(wid);
        toAdd.push(cloned);
      }
    }
    (p2 as any).action_bindings = abs.concat(toAdd);

    list.push(...pasted);
    setProject(p2, true);
    setProjectDirty(true);
    setSelectedWidgetIds(pasted.map((w) => w.id));
  }

  
function nudgeSelected(dx: number, dy: number, step: number) {
    if (!project) return;
    if (!selectedWidgetIds.length) return;
    const p2 = clone(project);
    const page = (p2 as any).pages?.[safePageIndex];
    if (!page?.widgets) return;
    const list = page.widgets as any[];
    const sel = selectedWidgetIds.map((id) => list.find((x) => x && x.id === id)).filter(Boolean) as any[];
    if (!sel.length) return;

    // Group by parent to keep relative semantics predictable.
    const byParent = new Map<string, any[]>();
    for (const w of sel) {
      const pid = String(w.parent_id || "");
      let arr = byParent.get(pid);
      if (!arr) { arr = []; byParent.set(pid, arr); }
      arr.push(w);
    }

    for (const [pid, items] of byParent.entries()) {
      for (const w of items) {
        w.x = (w.x || 0) + dx * step;
        w.y = (w.y || 0) + dy * step;
      }
    }

    setProject(p2, true);
    setProjectDirty(true);
  }

  function alignSelected(mode: "left"|"center"|"right"|"top"|"middle"|"bottom") {
    if (!project) return;
    if (selectedWidgetIds.length < 2) return;

    const p2 = clone(project);
    const page = (p2 as any).pages?.[safePageIndex];
    if (!page?.widgets) return;
    const list = page.widgets as any[];
    const sel = selectedWidgetIds.map((id) => list.find((x) => x && x.id === id)).filter(Boolean) as any[];
    if (sel.length < 2) return;

    // Align only within shared-parent groups (predictable for nested containers)
    const byParent = new Map<string, any[]>();
    for (const w of sel) {
      const pid = String(w.parent_id || "");
      let arr = byParent.get(pid);
      if (!arr) { arr = []; byParent.set(pid, arr); }
      arr.push(w);
    }

    for (const items of byParent.values()) {
      if (items.length < 2) continue;
      const left = Math.min(...items.map((w) => w.x || 0));
      const top = Math.min(...items.map((w) => w.y || 0));
      const right = Math.max(...items.map((w) => (w.x || 0) + (w.w || 0)));
      const bottom = Math.max(...items.map((w) => (w.y || 0) + (w.h || 0)));
      const cx = (left + right) / 2;
      const cy = (top + bottom) / 2;

      for (const w of items) {
        if (mode === "left") w.x = left;
        if (mode === "center") w.x = cx - (w.w || 0) / 2;
        if (mode === "right") w.x = right - (w.w || 0);
        if (mode === "top") w.y = top;
        if (mode === "middle") w.y = cy - (w.h || 0) / 2;
        if (mode === "bottom") w.y = bottom - (w.h || 0);
      }
    }

    setProject(p2, true);
    setProjectDirty(true);
  }

  function distributeSelected(axis: "h"|"v") {
    if (!project) return;
    if (selectedWidgetIds.length < 3) return;

    const p2 = clone(project);
    const page = (p2 as any).pages?.[safePageIndex];
    if (!page?.widgets) return;
    const list = page.widgets as any[];
    const sel = selectedWidgetIds.map((id) => list.find((x) => x && x.id === id)).filter(Boolean) as any[];
    if (sel.length < 3) return;

    const byParent = new Map<string, any[]>();
    for (const w of sel) {
      const pid = String(w.parent_id || "");
      let arr = byParent.get(pid);
      if (!arr) { arr = []; byParent.set(pid, arr); }
      arr.push(w);
    }

    for (const items of byParent.values()) {
      if (items.length < 3) continue;
      if (axis === "h") {
        const sorted = [...items].sort((a, b) => (a.x - b.x) || a.id.localeCompare(b.id));
        const left = sorted[0].x || 0;
        const right = (sorted[sorted.length - 1].x || 0) + (sorted[sorted.length - 1].w || 0);
        const totalW = sorted.reduce((acc, w) => acc + (w.w || 0), 0);
        const gap = (right - left - totalW) / (sorted.length - 1);
        let x = left;
        for (const w of sorted) {
          w.x = x;
          x += (w.w || 0) + gap;
        }
      } else {
        const sorted = [...items].sort((a, b) => (a.y - b.y) || a.id.localeCompare(b.id));
        const top = sorted[0].y || 0;
        const bottom = (sorted[sorted.length - 1].y || 0) + (sorted[sorted.length - 1].h || 0);
        const totalH = sorted.reduce((acc, w) => acc + (w.h || 0), 0);
        const gap = (bottom - top - totalH) / (sorted.length - 1);
        let y = top;
        for (const w of sorted) {
          w.y = y;
          y += (w.h || 0) + gap;
        }
      }
    }

    setProject(p2, true);
    setProjectDirty(true);
  }

/** Recompute project.bindings from current links so we only keep sensors for entities/widgets still on canvas. */
  function recomputeBindingsFromLinks(proj: any): void {
    const links = proj?.links;
    if (!Array.isArray(links)) return;
    const key = (b: { entity_id?: string; kind?: string; attribute?: string }) =>
      `${b.entity_id ?? ""}|${b.kind ?? "state"}|${b.attribute ?? ""}`;
    const seen = new Set<string>();
    const out: any[] = [];
    for (const l of links) {
      const src = l?.source;
      if (!src || !src.entity_id) continue;
      const k = key({ entity_id: src.entity_id, kind: src.kind, attribute: src.attribute });
      if (seen.has(k)) continue;
      seen.add(k);
      out.push({
        entity_id: src.entity_id,
        kind: src.kind ?? "state",
        attribute: src.attribute ?? undefined,
      });
    }
    (proj as any).bindings = out;
  }

  function deleteSelected() {
    if (!project) return;
    if (!selectedWidgetIds.length) return;
    const p2 = clone(project);
    const page = (p2 as any).pages?.[safePageIndex];
    if (!page?.widgets) return;
    const list = page.widgets as any[];
    const toDelete = new Set(selectedWidgetIds);
    // If a container is deleted, also delete its descendants.
    let changed = true;
    while (changed) {
      changed = false;
      for (const w of list) {
        if (!w || !w.id) continue;
        if (w.parent_id && toDelete.has(w.parent_id) && !toDelete.has(w.id)) {
          toDelete.add(w.id);
          changed = true;
        }
      }
    }
    const kept = list.filter((w) => w && w.id && !toDelete.has(w.id));
    page.widgets = kept;
    // Remove any links and action_bindings that reference deleted widget ids.
    const links = (p2 as any).links;
    if (Array.isArray(links)) {
      (p2 as any).links = links.filter((l: any) => !toDelete.has(String(l?.target?.widget_id || "")));
    }
    const actionBindings = (p2 as any).action_bindings;
    if (Array.isArray(actionBindings)) {
      (p2 as any).action_bindings = actionBindings.filter((ab: any) => !toDelete.has(String(ab?.widget_id || "")));
    }
    // Remove scripts that belonged to deleted entity-widget roots (e.g. thermostat inc/dec).
    const scripts = (p2 as any).scripts;
    if (Array.isArray(scripts)) {
      (p2 as any).scripts = scripts.filter((s: any) => !toDelete.has(String(s?._source_root_id ?? "")));
    }
    // Remove esphome_components: (1) prebuilt roots by _source_root_id, (2) Create-component blocks that reference deleted widget IDs.
    const comps = (p2 as any).esphome_components;
    if (Array.isArray(comps)) {
      (p2 as any).esphome_components = comps.filter((c: any) => {
        if (c == null) return false;
        if (typeof c === "object") {
          const rootId = c._source_root_id;
          if (rootId != null) return !toDelete.has(String(rootId)); // prebuilt: keep only if root not deleted
          const yamlStr = typeof c.yaml === "string" ? c.yaml : "";
          const refs = getWidgetRefsInYaml(yamlStr);
          if (refs.some((r: string) => toDelete.has(r))) return false;
          return true;
        }
        const refs = getWidgetRefsInYaml(String(c));
        if (refs.some((r: string) => toDelete.has(r))) return false;
        return true;
      });
    }
    recomputeBindingsFromLinks(p2);
    setProject(p2, true);
    setProjectDirty(true);
    setSelectedWidgetIds([]);
  }
  const selectedWidget = selectedWidgetId ? widgets.find((w: any) => w && w.id === selectedWidgetId) : null;

  function addPage() {
    if (!project) return;
    const p2 = clone(project);
    const pid = uid("page");
    p2.pages = p2.pages || [];
    p2.pages.push({ page_id: pid, name: `Page ${p2.pages.length + 1}`, widgets: [] } as any);
    setProject(p2);
    setProjectDirty(true);
    setCurrentPageIndex(p2.pages.length - 1);
    setSelectedWidgetIds([]);
  }

  function deletePage(pageIndex: number) {
    if (!project || !Array.isArray(project.pages) || project.pages.length <= 1) return;
    const name = project.pages[pageIndex]?.name || `Page ${pageIndex + 1}`;
    if (!window.confirm(`Delete "${name}"? This cannot be undone.`)) return;
    const p2 = clone(project);
    p2.pages = p2.pages.filter((_: any, i: number) => i !== pageIndex);
    setProject(p2);
    setProjectDirty(true);
    if (currentPageIndex >= p2.pages.length) setCurrentPageIndex(Math.max(0, p2.pages.length - 1));
    else if (currentPageIndex > pageIndex) setCurrentPageIndex(currentPageIndex - 1);
    setSelectedWidgetIds([]);
    setPageTabContextMenu(null);
  }

  async function addWidget() {
    if (!project) return;
    const sr = await getWidgetSchema(newWidgetType);
    if (!sr.ok) return setToast({ type: "error", msg: sr.error });
    const s = sr.schema;

    const props: any = {};
    const style: any = {};
    const events: any = {};
    // Only apply defaults when they are explicitly set and non-null.
    // This avoids generating YAML like `text: null` which ESPHome can reject.
    for (const [k, defAny] of Object.entries(s.props ?? {})) {
      const def = defAny as any;
      if (def.default !== undefined && def.default !== null) props[k] = def.default;
    }
    for (const [k, defAny] of Object.entries(s.style ?? {})) {
      const def = defAny as any;
      if (def.default !== undefined && def.default !== null) style[k] = def.default;
    }
    for (const [k, defAny] of Object.entries(s.events ?? {})) {
      const def = defAny as any;
      if (def.default !== undefined && def.default !== null) events[k] = def.default;
    }

    const w = { id: uid(newWidgetType), type: newWidgetType, x: 10, y: 10, w: 160, h: 60, props, style, events };

    const p2 = clone(project);
    const page = p2.pages?.[safePageIndex];
    if (!page?.widgets) return setToast({ type: "error", msg: "No page to add widget to" });
    page.widgets.push(w);
    setProject(p2);
    setProjectDirty(true);
    setSelectedWidgetIds([w.id]);
    setSelectedSchema(s);
  }

  async function selectWidget(id: string, additive = false) {
    if (!project) return;
    const w = widgets.find((x: any) => x && x.id === id);
    if (!w) return;
    setSelectedWidgetIds((prev) => {
      if (!additive) return [id];
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      return [...prev, id];
    });
    const sr = await getWidgetSchema(w.type);
    if (sr.ok) setSelectedSchema(sr.schema);
  }

  // v0.19: Editor keyboard shortcuts
  useEffect(() => {
    const isTypingTarget = (t: any) => {
      const tag = String(t?.tagName || "").toLowerCase();
      return tag === "input" || tag === "textarea" || tag === "select" || !!t?.isContentEditable;
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (isTypingTarget(e.target)) return;
      const ctrl = e.ctrlKey || e.metaKey;

      if (ctrl && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) projectHist.redo();
        else projectHist.undo();
        return;
      }
      if (ctrl && e.key.toLowerCase() === "y") {
        e.preventDefault();
        projectHist.redo();
        return;
      }
      if (ctrl && e.key.toLowerCase() === "c") {
        e.preventDefault();
        copySelected();
        return;
      }
      if (ctrl && e.key.toLowerCase() === "v") {
        e.preventDefault();
        pasteClipboard();
        return;
      }
      if (ctrl && e.key.toLowerCase() === "s") {
        e.preventDefault();
        saveProject();
        return;
      }
      if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        deleteSelected();
        return;
      }
      if (ctrl && e.key.toLowerCase() === "g") {
        e.preventDefault();
        if (e.shiftKey) ungroupSelected();
        else groupSelected();
        return;
      }
      // v0.62: Nudge selected widgets with arrow keys.
      if (e.key === "ArrowLeft" || e.key === "ArrowRight" || e.key === "ArrowUp" || e.key === "ArrowDown") {
        if (!selectedWidgetIds.length) return;
        e.preventDefault();
        const step = e.shiftKey ? 1 : (e.altKey ? 5 : ((project as any)?.ui?.gridSize || 10));
        const dx = e.key === "ArrowLeft" ? -1 : e.key === "ArrowRight" ? 1 : 0;
        const dy = e.key === "ArrowUp" ? -1 : e.key === "ArrowDown" ? 1 : 0;
        nudgeSelected(dx, dy, step);
        return;
      }
      if (ctrl && e.altKey) {
        if (e.key === "ArrowLeft") { e.preventDefault(); alignSelected("left"); return; }
        if (e.key === "ArrowRight") { e.preventDefault(); alignSelected("right"); return; }
        if (e.key === "ArrowUp") { e.preventDefault(); alignSelected("top"); return; }
        if (e.key === "ArrowDown") { e.preventDefault(); alignSelected("bottom"); return; }
      }
      if (ctrl && e.key === "]") {
        e.preventDefault();
        moveZ("front");
        return;
      }
      if (ctrl && e.key === "[") {
        e.preventDefault();
        moveZ("back");
        return;
      }
    };
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!projectDirty) return;
      // Required for modern browsers to show the "Leave site?" prompt.
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("beforeunload", onBeforeUnload);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedWidgetIds, clipboard, project, projectDirty]);

  // v0.57.2: Live compile preview — debounced when compile modal is open.
  useEffect(() => {
    if (!project || !selectedDevice) return;
    if (!compileModalOpen) return;
    if (!autoCompile) return;

    const t = window.setTimeout(async () => {
      setCompileBusy(true);
      setCompileErr("");
      try {
        const result = await compileYaml(selectedDevice, project as any);
        setCompiledYaml(result?.yaml ?? "");
        setCompileWarnings(result?.warnings ?? []);
      } catch (e: any) {
        setCompileErr(String(e?.message || e));
      } finally {
        setCompileBusy(false);
      }
    }, 500);

    return () => window.clearTimeout(t);
  }, [project, selectedDevice, compileModalOpen, autoCompile]);

  async function refreshCompile() {
    if (!project || !selectedDevice) return;
    setCompileBusy(true);
    setCompileErr("");
    setValidateYamlResult(null);
    try {
      const result = await compileYaml(selectedDevice, project as any);
      setCompiledYaml(result?.yaml ?? "");
      setCompileWarnings(result?.warnings ?? []);
    } catch (e: any) {
      setCompileErr(String(e?.message || e));
    } finally {
      setCompileBusy(false);
    }
  }

  async function runLayoutAudit() {
    if (!project || !selectedDevice) return;
    setLayoutAuditBusy(true);
    setLayoutAuditErr("");
    setLayoutAudit(null);
    try {
      const result = await compileYaml(selectedDevice, project as any, { includeLayoutAudit: true });
      setCompiledYaml(result?.yaml ?? "");
      setCompileWarnings(result?.warnings ?? []);
      setLayoutAudit(result.layout_audit ?? null);
    } catch (e: any) {
      setLayoutAuditErr(String(e?.message || e));
    } finally {
      setLayoutAuditBusy(false);
    }
  }

  // When Full YAML modal opens, compile and show result
  useEffect(() => {
    if (!fullYamlOpen) return;
    const device = selectedDevice;
    const proj = project;
    if (!device || !proj) {
      setFullYamlError("Select a device and load a project first.");
      setFullYamlBusy(false);
      return;
    }
    let cancelled = false;
    setFullYamlBusy(true);
    setFullYamlError("");
    compileYaml(device, proj as any)
      .then((result) => {
        if (!cancelled) setFullYamlContent(result?.yaml ?? "");
      })
      .catch((e: any) => {
        if (!cancelled) setFullYamlError(String(e?.message || e));
      })
      .finally(() => {
        if (!cancelled) setFullYamlBusy(false);
      });
    return () => { cancelled = true; };
  }, [fullYamlOpen]);

  async function previewExport() {
    if (!selectedDevice || !entryId) return;
    setExportBusy(true);
    setExportPreviewErr("");
    try {
      const res: any = await exportDeviceYamlPreview(selectedDevice, entryId);
      if (!res?.ok) throw new Error(res?.error || "preview_failed");
      setExportPreview(res);
    } catch (e: any) {
      setExportPreviewErr(String(e?.message || e));
    } finally {
      setExportBusy(false);
    }
  }

  async function doExport() {
    if (!selectedDevice || !entryId) return;
    setExportBusy(true);
    setExportErr("");
    try {
      const expected = exportPreview?.existing_hash || "";
      const res: any = await exportDeviceYamlWithExpectedHash(selectedDevice, expected, entryId);
      if (!res?.ok) throw new Error(res?.error || "export_failed");
      setExportResult(res);
      setToast({ type: "ok", msg: "Exported to /config/esphome/" });
      // Refresh preview so hashes/diff reflect latest write.
      await previewExport();
    } catch (e: any) {
      setExportErr(String(e?.message || e));
    } finally {
      setExportBusy(false);
    }
  }


  async function runSelfCheck() {
    setSelfCheckBusy(true);
    setSelfCheckErr("");
    setSelfCheckResult(null);
    try {
      const r = await fetch("/api/esptoolkit/self_check", { credentials: "include" });
      if (!r.ok) throw new Error(`self_check failed: ${r.status}`);
      const data = await r.json();
      setSelfCheckResult(data);
    } catch (e: any) {
      setSelfCheckErr(String(e?.message || e));
    } finally {
      setSelfCheckBusy(false);
    }
  }

  function updateField(section: string, key: string, value: any) {
    if (!project || !selectedWidgetId) return;
    const p2 = clone(project);
    const page = p2.pages?.[safePageIndex];
    if (!page?.widgets) return;
    const w = page.widgets.find((x: any) => x && x.id === selectedWidgetId);
    if (!w) return;
    w[section] = w[section] || {};
    // If the UI clears a field, remove it entirely so the compiler won't emit it.
    if (value === undefined) {
      delete w[section][key];
    } else {
      w[section][key] = value;
    }
    setProject(p2);
    setProjectDirty(true);
  }

  async function saveProject() {
    if (!project || !selectedDevice) return;
    setBusy(true);
    try {
      const res = await putProject(entryId, selectedDevice, project);
      if (!res.ok) return setToast({ type: "error", msg: res.error });
      setProjectDirty(false);
      try { localStorage.removeItem(draftKeyForDevice(selectedDevice)); } catch {}
      setToast({ type: "ok", msg: "Project saved" });
    } finally { setBusy(false); }
  }

  async function deploySelected() {
    if (!selectedDevice) return;
    setBusy(true);
    try {
      const res = await deploy(entryId, selectedDevice);
      if (!res.ok) return setToast({ type: "error", msg: res.error });
      setToast({ type: "ok", msg: `Deployed: ${res.path}` });
    } finally { setBusy(false); }
  }

  /** Write compiled YAML to /config/esphome/<slug>.yaml then run add-on run (deploy). */
  async function deployToConfig() {
    if (!selectedDevice || !entryId || !project) return;
    setBusy(true);
    try {
      if (projectDirty) {
        const res = await putProject(entryId, selectedDevice, project);
        if (!res.ok) {
          setToast({ type: "error", msg: `Save failed: ${res.error}` });
          return;
        }
        setProjectDirty(false);
      }
      // If USB serial ports are present, prompt for target (OTA vs a specific USB port).
      // For OTA we send device name as name.local so ESPHome targets the wireless device and does not use USB.
      let deviceOverride: string | undefined = undefined;
      try {
        const portsRes: any = await listEsphomePorts(entryId);
        const ports: string[] = portsRes?.ok && Array.isArray(portsRes?.ports) ? portsRes.ports : [];
        if (ports.length) {
          const choice = await new Promise<string | null>((resolve) => {
            deployTargetResolveRef.current = resolve;
            setDeployTargetPorts(ports);
            setDeployTargetChoice("ota");
            setDeployTargetOpen(true);
          });
          if (choice == null) return; // cancelled
          if (choice === "ota") {
            const name = (selectedDeviceObj?.slug || selectedDeviceObj?.device_id || selectedDevice || "").trim();
            deviceOverride = name ? `${name}.local` : undefined;
          } else if (choice.startsWith("usb:")) {
            deviceOverride = choice.slice("usb:".length);
          }
        }
      } catch {
        // If ports listing fails, fall back to legacy behaviour (OTA).
      }

      setBusy(false); // Release UI immediately; deploy continues in background.
      setToast({ type: "ok", msg: "Deploy started…" });
      void (async () => {
        try {
          const res: any = await deployExport(selectedDevice, entryId, deviceOverride);
          if (res?.ok) {
            setToast({ type: "ok", msg: res.path ? `Deployed: ${res.path}` : "Deployed" });
          } else {
            const msg = (res?.detail ?? res?.error ?? "Deploy failed").slice(0, 300);
            setToast({ type: "error", msg });
          }
        } catch (e: any) {
          setToast({ type: "error", msg: `Deploy failed: ${e?.message ?? "unknown error"}` });
        }
      })();
      return;
    } catch (e: any) {
      setToast({ type: "error", msg: `Deploy failed: ${e?.message ?? "unknown error"}` });
    } finally {
      setBusy(false);
    }
  }

  /** Deploy to a specific host: prompt for hostname then run add-on run with --device. */
  async function deployToHost() {
    if (!selectedDevice || !entryId || !project) return;
    const host = window.prompt("Deploy to host (hostname or IP):", "");
    if (host == null || !host.trim()) return;
    setBusy(true);
    try {
      if (projectDirty) {
        const res = await putProject(entryId, selectedDevice, project);
        if (!res.ok) {
          setToast({ type: "error", msg: `Save failed: ${res.error}` });
          return;
        }
        setProjectDirty(false);
      }
      setBusy(false); // Release UI immediately; deploy continues in background.
      setToast({ type: "ok", msg: `Deploy to ${host.trim()} started…` });
      void (async () => {
        try {
          const res: any = await deployExport(selectedDevice, entryId, host.trim());
          if (res?.ok) {
            setToast({ type: "ok", msg: res.path ? `Deployed to ${host.trim()}: ${res.path}` : `Deployed to ${host.trim()}` });
          } else {
            const msg = (res?.detail ?? res?.error ?? "Deploy failed").slice(0, 300);
            setToast({ type: "error", msg });
          }
        } catch (e: any) {
          setToast({ type: "error", msg: `Deploy failed: ${e?.message ?? "unknown error"}` });
        }
      })();
      return;
    } catch (e: any) {
      setToast({ type: "error", msg: `Deploy failed: ${e?.message ?? "unknown error"}` });
    } finally {
      setBusy(false);
    }
  }

  /** Write compiled YAML to esphome/ then run add-on config-check (validate). */
  async function validateExportYaml() {
    if (!selectedDevice || !entryId) return;
    setValidateYamlBusy(true);
    setValidateYamlResult(null);
    try {
      if (project && projectDirty) {
        const res = await putProject(entryId, selectedDevice, project);
        if (!res.ok) {
          setToast({ type: "error", msg: `Save failed: ${res.error}` });
          return;
        }
        setProjectDirty(false);
      }
      const result = await validateExport(selectedDevice, entryId);
      setValidateYamlResult(result);
      if (result.ok) {
        setToast({ type: "ok", msg: "Config valid" });
      } else {
        const msg = (result.stderr || result.stdout || "Validation failed").slice(0, 200);
        setToast({ type: "error", msg: `Validation failed: ${msg}` });
      }
    } catch (e: any) {
      setValidateYamlResult({ ok: false, stderr: String(e?.message || e) });
      setToast({ type: "error", msg: `Validation error: ${e?.message ?? "unknown"}` });
    } finally {
      setValidateYamlBusy(false);
    }
  }

  const parityScreen = parityMode && project ? resolveDeviceScreen(project, null) : null;
  const parityWidgets =
    parityMode && project
      ? ((project.pages?.[0]?.widgets ?? []).filter((w: any) => w && typeof w === "object" && w.id != null) as any[])
      : [];

  const parityView =
    parityError != null ? (
      <div className="app" data-etd-parity-root="1">
        <div style={{ padding: 24, fontFamily: "system-ui, sans-serif" }} data-etd-parity-error="1">
          {parityError}
        </div>
      </div>
    ) : parityMode && project && parityScreen ? (
      <div
        className="app"
        data-etd-parity-root="1"
        style={{ margin: 0, padding: 0, overflow: "hidden", width: parityScreen.width, height: parityScreen.height }}
      >
        <Canvas
          widgets={parityWidgets}
          selectedIds={[]}
          width={parityScreen.width}
          height={parityScreen.height}
          gridSize={8}
          showGrid={false}
          dispBgColor="#000000"
          liveOverrides={{}}
          onSelect={() => {}}
          onSelectNone={() => {}}
          onChangeMany={() => {}}
          parityCaptureMode
        />
      </div>
    ) : null;

  return (
    parityView ?? (
    <div className="app">
      <header className="header">
        <div>
          <h1>EspToolkit Designer</h1>
          <div className="muted">
            Designer v{versionInfo?.integration || packageJson.version}
            {versionInfo?.addon != null && versionInfo.addon !== "" ? ` · Add-on v${versionInfo.addon}` : ""}
          </div>
          {!entryId && (
            <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>If you just started Home Assistant, wait a few seconds and refresh the page.</div>
          )}
        </div>
        <div className="pill"><span className="muted">entry_id</span><code>{entryId || "…"}</code></div>
      </header>

      {toast && (
        <div className={toast.type === "ok" ? "toast ok" : "toast error"} onClick={() => setToast(null)}>
          {toast.msg} <span className="muted">(click to dismiss)</span>
        </div>
      )}

      {tmplWizard && (
        <div className="modalOverlay" onClick={() => setTmplWizard(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modalHeader">
              <div>
                <div className="title">{wizardIsEntityWidget ? "Add entity widget" : "Add Home Assistant control"}</div>
                <div className="muted">
                  Template: <code>{tmplWizard.template_id}</code>{wizardTemplate ? <span> • {String((wizardTemplate as any).title || "")}</span> : null}
                </div>
              </div>
              <button className="ghost" onClick={() => setTmplWizard(null)}>✕</button>
            </div>

            <div className="field">
              <div className="fieldLabel">{wizardIsMultiEntity ? "entities" : "Home Assistant Entity"}</div>
              {!wizardIsMultiEntity ? (
                <>
                  {/* Filterable dropdown: list comes from template entityDomain (or ha_<domain>_), filter by typing */}
                  <div style={{ position: "relative" }}>
                    <input
                      type="text"
                      placeholder={`Select or type… (${(wizardTemplate as any)?.entityDomain || templateDomain(tmplWizard.template_id) || "any"})`}
                      value={tmplEntity}
                      onChange={(e) => {
                        setTmplEntity(e.target.value);
                        setTmplEntityDropdownOpen(true);
                      }}
                      onFocus={() => setTmplEntityDropdownOpen(true)}
                      onBlur={() => setTimeout(() => setTmplEntityDropdownOpen(false), 150)}
                      autoComplete="off"
                      style={{ width: "100%", boxSizing: "border-box" }}
                    />
                    {tmplEntityDropdownOpen && (() => {
                      const dom = (wizardTemplate as any)?.entityDomain || templateDomain(tmplWizard.template_id);
                      const search = (tmplEntity || "").trim().toLowerCase();
                      const list = entities
                        .filter((e) => {
                          if (!e?.entity_id) return false;
                          if (dom && !String(e.entity_id).startsWith(dom + ".")) return false;
                          if (!search) return true;
                          const eid = String(e.entity_id).toLowerCase();
                          const name = String(e?.friendly_name || "").toLowerCase();
                          return eid.includes(search) || name.includes(search);
                        })
                        .slice(0, 300);
                      return (
                        <div
                          className="dropdownList"
                          style={{
                            position: "absolute",
                            left: 0,
                            right: 0,
                            top: "100%",
                            marginTop: 2,
                            maxHeight: 260,
                            overflow: "auto",
                            background: "var(--panel-bg, #1e1e1e)",
                            border: "1px solid rgba(255,255,255,0.12)",
                            borderRadius: 8,
                            zIndex: 1000,
                            boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
                          }}
                        >
                          {list.length === 0 ? (
                            <div style={{ padding: "10px 12px", color: "var(--muted, #888)" }}>
                              {entities.length === 0 ? "Loading entities…" : "No matching entities."}
                            </div>
                          ) : (
                            list.map((e) => (
                              <div
                                key={e.entity_id}
                                role="option"
                                onMouseDown={(ev) => {
                                  ev.preventDefault();
                                  setTmplEntity(e.entity_id);
                                  setTmplEntityDropdownOpen(false);
                                }}
                                style={{
                                  padding: "8px 12px",
                                  cursor: "pointer",
                                  borderBottom: "1px solid rgba(255,255,255,0.06)",
                                  whiteSpace: "nowrap",
                                  overflow: "hidden",
                                  textOverflow: "ellipsis",
                                }}
                                className="dropdownOption"
                              >
                                <span style={{ fontWeight: 500 }}>{e.entity_id}</span>
                                {e.friendly_name ? (
                                  <span style={{ color: "var(--muted, #888)", marginLeft: 8 }}>— {e.friendly_name}</span>
                                ) : null}
                              </div>
                            ))
                          )}
                        </div>
                      );
                    })()}
                  </div>
                  <div className="muted" style={{ marginTop: 6 }}>
                    List shows only entities for this template. Type to filter or pick from the list.
                  </div>
                </>
              ) : (
                <>
                  <div className="muted" style={{ marginTop: 6 }}>
                    Add up to 4 entities (you can paste/type, or pick from the list).
                  </div>
                  {Array.from({ length: wizardEntitySlots }).map((_, i) => (
                    <div key={i} style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 6 }}>
                      <input
                        list="ha_entities_any"
                        placeholder={`entity ${i + 1} (e.g. light.kitchen)`}
                        value={tmplEntities[i] || ""}
                        onChange={(e) => {
                          const v = e.target.value;
                          setTmplEntities((prev) => {
                            const p = Array.isArray(prev) ? [...prev] : [];
                            while (p.length < wizardEntitySlots) p.push("");
                            p[i] = v;
                            return p;
                          });
                        }}
                      />
                      <button
                        className="tiny secondary"
                        type="button"
                        onClick={() =>
                          setTmplEntities((prev) => {
                            const p = Array.isArray(prev) ? [...prev] : [];
                            while (p.length < wizardEntitySlots) p.push("");
                            p[i] = "";
                            return p;
                          })
                        }
                      >
                        clear
                      </button>
                    </div>
                  ))}
                  <datalist id="ha_entities_any">
                    {entities.slice(0, 800).map((e) => (
                      <option key={e.entity_id} value={e.entity_id}>
                        {(e.friendly_name || e.entity_id) as any}
                      </option>
                    ))}
                  </datalist>
                </>
              )}

              
              {wizardWantsTapAction && (
                <div style={{ marginTop: 12 }}>
                  <div className="fieldLabel">tap action</div>
                  <select value={tmplTapAction} onChange={(e) => setTmplTapAction(e.target.value)}>
                    <option value="toggle">toggle</option>
                    <option value="more-info">more-info</option>
                    <option value="call-service">call-service</option>
                  </select>

                  {tmplTapAction === "call-service" && (
                    <div style={{ marginTop: 10 }}>
                      <div className="fieldLabel">service</div>
                      <input
                        placeholder="e.g. script.some_action"
                        value={tmplService}
                        onChange={(e) => setTmplService(e.target.value)}
                      />
                      <div className="muted" style={{ marginTop: 6 }}>
                        Optional: service data YAML (will be merged under data:).
                      </div>
                      <YamlEditor value={tmplServiceData} onChange={setTmplServiceData} minHeight={100} placeholder="brightness_pct: 50\ntransition: 1" />
                    </div>
                  )}
                </div>
              )}

              {/* v0.68: Conditional card wizard builder */}
              {tmplWizard && tmplWizard.template_id === "conditional_card" && (
                <div style={{ marginTop: 12 }}>
                  <div className="fieldLabel">condition</div>
                  <div className="muted" style={{ marginTop: 6 }}>
                    Choose when the card should be shown. This generates a condition expression over <code>x</code> (the entity value).
                  </div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8, flexWrap: "wrap" }}>
                    <label className="muted" style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <input type="checkbox" checked={tmplCondNumeric} onChange={(e) => setTmplCondNumeric(e.target.checked)} /> numeric
                    </label>
                    <select value={tmplCondOp} onChange={(e) => setTmplCondOp(e.target.value)}>
                      {!tmplCondNumeric ? (
                        <>
                          <option value="equals">equals</option>
                          <option value="neq">not equals</option>
                          <option value="contains">contains</option>
                        </>
                      ) : (
                        <>
                          <option value="equals">=</option>
                          <option value="neq">≠</option>
                          <option value="gt">&gt;</option>
                          <option value="lt">&lt;</option>
                        </>
                      )}
                    </select>
                    <input
                      placeholder={tmplCondNumeric ? "e.g. 25" : "e.g. on"}
                      value={tmplCondValue}
                      onChange={(e) => setTmplCondValue(e.target.value)}
                      style={{ width: 180 }}
                    />
                  </div>
                  <div className="muted" style={{ marginTop: 8 }}>
                    Preview: <code>{(() => {
                      const v = String(tmplCondValue || "").trim() || "…";
                      if (tmplCondNumeric) {
                        const op = tmplCondOp === "gt" ? ">" : tmplCondOp === "lt" ? "<" : tmplCondOp === "neq" ? "!=" : "==";
                        return `atof(x.c_str()) ${op} ${v}`;
                      }
                      const esc = v.replaceAll('"', '\\"');
                      if (tmplCondOp === "contains") return `x.find(\"${esc}\") != std::string::npos`;
                      const op = tmplCondOp === "neq" ? "!=" : "==";
                      return `x ${op} \"${esc}\"`;
                    })()}</code>
                  </div>
                </div>
              )}

              {/* v0.61: Card-specific options */}
              {tmplWizard && tmplWizard.template_id === "thermostat_card" && (
                <div style={{ marginTop: 12 }}>
                  <div className="fieldLabel">thermostat setpoint range</div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <label className="muted">min
                      <input type="number" value={tmplThMin} onChange={(e)=>setTmplThMin(Number(e.target.value))} style={{ width: 80, marginLeft: 6 }} />
                    </label>
                    <label className="muted">max
                      <input type="number" value={tmplThMax} onChange={(e)=>setTmplThMax(Number(e.target.value))} style={{ width: 80, marginLeft: 6 }} />
                    </label>
                    <label className="muted">step
                      <input type="number" value={tmplThStep} onChange={(e)=>setTmplThStep(Math.max(0.1, Number(e.target.value)))} style={{ width: 80, marginLeft: 6 }} />
                    </label>
                  </div>
                  <div className="muted" style={{ marginTop: 6 }}>
                    Tip: if the entity exposes min_temp/max_temp/target_temp_step, we’ll prefill these when capabilities are loaded.
                  </div>
                </div>
              )}

              {tmplWizard && tmplWizard.template_id === "media_control_card" && (
                <div style={{ marginTop: 12 }}>
                  <div className="fieldLabel">media card sections</div>
                  <label className="muted" style={{ display: "block", marginTop: 6 }}>
                    <input type="checkbox" checked={tmplMediaShowTransport} onChange={(e)=>setTmplMediaShowTransport(e.target.checked)} /> transport controls
                  </label>
                  <label className="muted" style={{ display: "block", marginTop: 6 }}>
                    <input type="checkbox" checked={tmplMediaShowVolume} onChange={(e)=>setTmplMediaShowVolume(e.target.checked)} /> volume slider
                  </label>
                  <label className="muted" style={{ display: "block", marginTop: 6 }}>
                    <input type="checkbox" checked={tmplMediaShowMute} onChange={(e)=>setTmplMediaShowMute(e.target.checked)} /> mute + vol buttons
                  </label>
                  <label className="muted" style={{ display: "block", marginTop: 6 }}>
                    <input type="checkbox" checked={tmplMediaShowSource} onChange={(e)=>setTmplMediaShowSource(e.target.checked)} /> source row (best-effort)
                  </label>
                  {tmplMediaShowSource && (
                    <div style={{ marginTop: 8 }}>
                      <div className="fieldLabel">default source (optional)</div>
                      <input placeholder="e.g. HDMI 1" value={tmplMediaDefaultSource} onChange={(e)=>setTmplMediaDefaultSource(e.target.value)} />
                    </div>
                  )}
                </div>
              )}

              {tmplWizard && tmplWizard.template_id === "cover_card" && (
                <div style={{ marginTop: 12 }}>
                  <div className="fieldLabel">cover card options</div>
                  <label className="muted" style={{ display: "block", marginTop: 6 }}>
                    <input type="checkbox" checked={tmplCoverShowTilt} onChange={(e)=>setTmplCoverShowTilt(e.target.checked)} /> show tilt controls when available
                  </label>
                </div>
              )}

              {tmplWizard && tmplWizard.template_id.startsWith("glance_card") && (
                <div style={{ marginTop: 12 }}>
                  <div className="fieldLabel">glance rows</div>
                  <select value={tmplGlanceRows} onChange={(e)=>setTmplGlanceRows(Number(e.target.value) as any)}>
                    <option value={2}>2</option>
                    <option value={3}>3</option>
                    <option value={4}>4</option>
                    <option value={6}>6</option>
                  </select>
                </div>
              )}

              {tmplWizard && tmplWizard.template_id.startsWith("grid_card_") && (
                <div style={{ marginTop: 12 }}>
                  <div className="fieldLabel">grid size</div>
                  <select value={tmplGridSize} onChange={(e)=>setTmplGridSize(e.target.value as any)}>
                    <option value="2x2">2×2 (4 tiles)</option>
                    <option value="3x2">3×2 (6 tiles)</option>
                    <option value="3x3">3×3 (9 tiles)</option>
                  </select>
                  <div className="muted" style={{ marginTop: 6 }}>Adjust entity slots accordingly after choosing size.</div>
                </div>
              )}

{tmplCaps && (
                <div className="muted" style={{ marginTop: 10 }}>
                  <div><strong>Detected capabilities</strong></div>
                  <div>
                    domain: <code>{tmplCaps.domain}</code> • supported_features: <code>{String(tmplCaps.supported_features ?? "-")}</code>
                  </div>
                  {tmplCaps?.attributes?.supported_color_modes && (
                    <div>
                      supported_color_modes: <code>{String((tmplCaps.attributes.supported_color_modes || []).join(", ") || "-")}</code>
                    </div>
                  )}
                  {tmplCaps?.attributes?.hvac_modes && (
                    <div>
                      hvac_modes: <code>{String((tmplCaps.attributes.hvac_modes || []).join(", ") || "-")}</code>
                    </div>
                  )}

                  {/* v0.50: raw capability dump to help template debugging / parity work */}
                  <details style={{ marginTop: 8 }}>
                    <summary style={{ cursor: "pointer" }}>Raw capabilities</summary>
                    <pre style={{ whiteSpace: "pre-wrap", userSelect: "text" }}>{JSON.stringify(tmplCaps, null, 2)}</pre>
                  </details>
                </div>
              )}

              {templateDomain(tmplWizard.template_id) === "light" && (
                <div style={{ marginTop: 10 }}>
                  <div className="fieldLabel">Variant</div>
                  <select value={tmplVariant} onChange={(e) => setTmplVariant(e.target.value)}>
                    <option value="auto">Auto (recommended)</option>
                    <option value="ha_light_toggle">Toggle only</option>
                    <option value="ha_light_full">Toggle + Brightness</option>
                    <option value="ha_light_ct">Toggle + Brightness + Color Temp</option>
                  </select>
                  <div className="muted" style={{ marginTop: 6 }}>
                    Auto will pick the best match based on supported_color_modes.
                  </div>
                </div>
              )}
            </div>

            <div className="field">
              <div className="fieldLabel">label (optional)</div>
              <input
                placeholder="Override title text"
                value={tmplLabel}
                onChange={(e) => setTmplLabel(e.target.value)}
              />
            </div>

            <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
              <button className="ghost" onClick={() => setTmplWizard(null)}>Cancel</button>
              <button onClick={() => void applyTemplateWizard()} disabled={!project}>
                {wizardIsEntityWidget ? "Insert entity widget" : "Insert control"}
              </button>
            </div>
          </div>
        </div>
      )}


      {createNativeComponentOpen && selectedWidgetIds.length === 1 && project && (() => {
        const wid = selectedWidgetIds[0];
        const selWidget = widgetsFlat.find((w: any) => w?.id === wid) ?? widgets.find((w: any) => w?.id === wid);
        const widgetType = selWidget?.type || "";
        const mapping = getLvglComponentsForWidget(widgetType);
        const allowedTypes = mapping?.types ?? [];
        const filteredTypes = allowedTypes.filter((k) => {
          const lbl = LVGL_COMPONENT_TYPES[k]?.label ?? k;
          return !createNativeComponentTypeFilter || lbl.toLowerCase().includes(createNativeComponentTypeFilter.toLowerCase());
        });
        const currentMeta = LVGL_COMPONENT_TYPES[createNativeComponentType];
        const sectionKey = currentMeta?.section ?? "switch";
        return (
          <div className="modalOverlay" onClick={() => setCreateNativeComponentOpen(false)}>
            <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 420 }}>
              <h3>Create native component</h3>
              <div className="muted" style={{ marginTop: 4 }}>
                Add an ESPHome {sectionKey} bound to this {widgetType} widget. Bidirectional with HA.
              </div>
              <div className="field" style={{ marginTop: 12 }}>
                <div className="fieldLabel">Component type</div>
                <div style={{ position: "relative" }}>
                  <input
                    type="text"
                    value={createNativeComponentTypeFilter}
                    onChange={(e) => {
                      setCreateNativeComponentTypeFilter(e.target.value);
                      setCreateNativeComponentDropdownOpen(true);
                    }}
                    onFocus={() => setCreateNativeComponentDropdownOpen(true)}
                    onBlur={() => setTimeout(() => setCreateNativeComponentDropdownOpen(false), 150)}
                    placeholder="Select or type…"
                    style={{ width: "100%", fontFamily: "ui-monospace, monospace" }}
                  />
                  {createNativeComponentDropdownOpen && (
                    <ul style={{
                      position: "absolute", top: "100%", left: 0, right: 0, margin: 0, padding: 0, listStyle: "none",
                      background: "var(--ha-bg)", border: "1px solid var(--border)", borderRadius: 6, maxHeight: 180, overflow: "auto",
                      zIndex: 100
                    }}>
                      {filteredTypes.map((k) => {
                        const lbl = LVGL_COMPONENT_TYPES[k]?.label ?? k;
                        return (
                          <li
                            key={k}
                            style={{ padding: "8px 12px", cursor: "pointer", borderBottom: "1px solid rgba(255,255,255,0.06)" }}
                            onMouseDown={(e) => { e.preventDefault(); setCreateNativeComponentType(k); setCreateNativeComponentTypeFilter(lbl); setCreateNativeComponentDropdownOpen(false); }}
                          >
                            {lbl}
                          </li>
                        );
                      })}
                      {filteredTypes.length === 0 && <li style={{ padding: 8, color: "var(--muted)" }}>No match</li>}
                    </ul>
                  )}
                </div>
                <div className="muted" style={{ marginTop: 6 }}>Inferred from widget. Type to filter or pick another.</div>
              </div>
              <div className="field">
                <div className="fieldLabel">ID (YAML)</div>
                <input
                  type="text"
                  value={createNativeComponentId}
                  onChange={(e) => setCreateNativeComponentId(e.target.value)}
                  placeholder="e.g. kitchen_light"
                  style={{ width: "100%", fontFamily: "ui-monospace, monospace" }}
                />
                <div className="muted" style={{ marginTop: 6 }}>Also updates Widget ID in Properties if changed.</div>
              </div>
              <div className="field">
                <div className="fieldLabel">Name (HA entity)</div>
                <input
                  type="text"
                  value={createNativeComponentName}
                  onChange={(e) => setCreateNativeComponentName(e.target.value)}
                  placeholder="e.g. Kitchen Light"
                  style={{ width: "100%" }}
                />
              </div>
              <div className="row" style={{ justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
                <button className="ghost" onClick={() => setCreateNativeComponentOpen(false)}>Cancel</button>
                <button
                  onClick={async () => {
                    const rawId = createNativeComponentId.replace(/[^a-zA-Z0-9_]/g, "_").replace(/^_+|_+$/g, "").trim();
                    if (!rawId) { setToast({ type: "error", msg: "Invalid ID" }); return; }
                    if (!allowedTypes.includes(createNativeComponentType)) { setToast({ type: "error", msg: "Invalid component type for this widget" }); return; }
                    const meta = LVGL_COMPONENT_TYPES[createNativeComponentType];
                    if (!meta) return;
                    let p2 = clone(project);
                    const origWidgetId = String(selWidget?.id ?? "");
                    if (rawId !== origWidgetId) {
                      const result = renameWidgetInProject(p2, safePageIndex, origWidgetId, rawId);
                      if (!result.ok) { setToast({ type: "error", msg: result.error || "Cannot rename widget" }); return; }
                      p2 = result.project;
                      setSelectedWidgetIds([rawId]);
                    }
                    // ESPHome LVGL platform: use widget: to reference the widget; do not emit id (widget already defines it; duplicate causes "ID redefined").
                    const blockBody = `  - platform: lvgl
    widget: ${rawId}
    name: ${JSON.stringify((createNativeComponentName.trim() || "Component"))}
`;
                    const fullBlock = `${meta.section}:\n${blockBody.trim()}`;
                    p2.esphome_components = Array.isArray(p2.esphome_components) ? p2.esphome_components : [];
                    p2.esphome_components.push(fullBlock);
                    if (widgetType === "button" && createNativeComponentType === "switch") {
                      const pg = p2?.pages?.[safePageIndex];
                      const w = findWidgetById(pg?.widgets ?? [], rawId);
                      if (w) (w.props = w.props || {})["checkable"] = true;
                    }
                    setProject(p2, true);
                    setProjectDirty(true);
                    setCreateNativeComponentOpen(false);
                    setToast({ type: "ok", msg: `Added ${meta.label} to Components → ${meta.section}` });
                  }}
                  disabled={!createNativeComponentId.trim()}
                >
                  Create
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {recipeImportOpen && (
        <div className="modalOverlay" onClick={() => setRecipeImportOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Import hardware recipe</h3>
            <div className="muted" style={{ marginTop: 4 }}>
              Paste a full ESPHome device YAML. We will normalize it into a hardware-focused recipe and inject the LVGL marker.
            </div>

            <div className="field" style={{ marginTop: 12 }}>
              <div className="fieldLabel">label (optional)</div>
              <input value={recipeImportLabel} onChange={(e)=>setRecipeImportLabel(e.target.value)} placeholder="e.g. Sunton 8048S043 800×480" />
            </div>

            <div className="field">
              <div className="fieldLabel">id/slug (optional)</div>
              <input value={recipeImportId} onChange={(e)=>setRecipeImportId(e.target.value)} placeholder="e.g. sunton_8048s043_800x480" />
              <div className="muted" style={{ marginTop: 6 }}>If omitted, we derive a safe id from the label.</div>
            </div>

            <div className="field">
              <div className="fieldLabel">device YAML</div>
              <YamlEditor value={recipeImportYaml} onChange={setRecipeImportYaml} minHeight={220} placeholder="Paste YAML here…" />
            </div>

            {recipeImportErr && <div className="error" style={{ marginTop: 10 }}>{recipeImportErr}</div>}
            {recipeImportOk && (
              <div className="ok" style={{ marginTop: 10 }}>
                Imported as <code>{recipeImportOk.id}</code>
              </div>
            )}

            <div className="row" style={{ justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
              <button className="ghost" onClick={() => setRecipeImportOpen(false)}>Close</button>
              <button disabled={recipeImportBusy || !recipeImportYaml.trim()} onClick={doImportRecipe}>
                {recipeImportBusy ? "Importing…" : "Import"}
              </button>
            </div>
          </div>
        </div>
      )}

      {importYamlOpen && (
        <div className="modalOverlay" onClick={() => !importYamlBusy && setImportYamlOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Import device from YAML</h3>
            <div className="muted" style={{ marginTop: 4 }}>
              Paste full ESPHome device YAML. We match or create a hardware recipe and reverse the LVGL UI into the Designer.
            </div>
            <div className="field" style={{ marginTop: 12 }}>
              <div className="fieldLabel">Device name override (optional)</div>
              <input value={importYamlNameOverride} onChange={(e) => setImportYamlNameOverride(e.target.value)} placeholder="Leave empty to use esphome.name from YAML" />
            </div>
            <div className="field">
              <div className="fieldLabel">Device YAML</div>
              <YamlEditor value={importYamlText} onChange={setImportYamlText} minHeight={220} placeholder="Paste full ESPHome YAML here…" />
            </div>
            {importYamlErr && <div className="error" style={{ marginTop: 10 }}>{importYamlErr}</div>}
            <div className="row" style={{ justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
              <button className="ghost" onClick={() => !importYamlBusy && setImportYamlOpen(false)}>Close</button>
              <button disabled={importYamlBusy || !importYamlText.trim()} onClick={doImportYaml}>
                {importYamlBusy ? "Importing…" : "Import"}
              </button>
            </div>
          </div>
        </div>
      )}

      {recipeMgrOpen && (
        <div className="modalOverlay" onClick={() => setRecipeMgrOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Recipe Manager</h3>
            <div className="muted" style={{ marginTop: 4 }}>
              Rename or delete your custom hardware recipes. Built-in recipes cannot be edited.
            </div>

            {recipeMgrErr && <div className="error" style={{ marginTop: 10 }}>{recipeMgrErr}</div>}

            <div style={{ marginTop: 12, maxHeight: 420, overflow: "auto", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 10 }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ textAlign: "left" }}>
                    <th style={{ padding: "10px 12px" }}>Label</th>
                    <th style={{ padding: "10px 12px" }}>ID</th>
                    <th style={{ padding: "10px 12px" }}>Stored at</th>
                    <th style={{ padding: "10px 12px" }}></th>
                  </tr>
                </thead>
                <tbody>
                  
                  {recipes.map((r) => {
                    const val = recipeMgrEdits[r.id] ?? r.label ?? r.id;
                    const canEdit = !r.builtin;
                    return (
                      <tr key={r.id} style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                        <td style={{ padding: "10px 12px" }}>
                          {canEdit ? (
                            <input
                              value={val}
                              onChange={(e) => setRecipeMgrEdits((m) => ({ ...m, [r.id]: e.target.value }))}
                              style={{ width: "100%" }}
                            />
                          ) : (
                            <div>{r.label || r.id}</div>
                          )}
                        </td>
                        <td style={{ padding: "10px 12px", whiteSpace: "nowrap" }}><code>{r.id}</code></td>
                        <td style={{ padding: "10px 12px" }}>
                          <code style={{ fontSize: 12 }}>{r.path || ""}</code>
                        </td>
                        <td style={{ padding: "10px 12px", whiteSpace: "nowrap" }}>
                          <button
                            className="secondary"
                            disabled={recipeMgrBusy}
                            title="Download recipe.yaml + metadata as JSON"
                            onClick={async () => {
                              setRecipeMgrBusy(true);
                              setRecipeMgrErr("");
                              try {
                                const data = await exportRecipe(r.id);
                                const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
                                const url = URL.createObjectURL(blob);
                                const a = document.createElement('a');
                                a.href = url;
                                a.download = `${r.id}.recipe.json`;
                                a.click();
                                URL.revokeObjectURL(url);
                                setToast({ type: 'ok', msg: `Exported: ${r.id}` });
                              } catch (e: any) {
                                setRecipeMgrErr(String(e?.message || e));
                              } finally {
                                setRecipeMgrBusy(false);
                              }
                            }}
                          >Export</button>

                          <button
                            className="secondary"
                            style={{ marginLeft: 8 }}
                            disabled={recipeMgrBusy}
                            title="Clone this recipe into a custom (user) recipe so you can edit it"
                            onClick={async () => {
                              const newLabel = prompt('New recipe label (optional):', r.label || r.id) || '';
                              const newId = prompt('New recipe id/slug (optional):', '') || '';
                              setRecipeMgrBusy(true);
                              setRecipeMgrErr('');
                              try {
                                await cloneRecipe(r.id, newLabel || undefined, newId || undefined);
                                await refreshRecipes();
                                setToast({ type: 'ok', msg: `Cloned: ${r.id}` });
                              } catch (e: any) {
                                const errMsg = String(e?.message || e);
                                setRecipeMgrErr(errMsg.includes("404") || errMsg.includes("no_active_entry") ? INTEGRATION_NOT_CONFIGURED_MSG : errMsg);
                              } finally {
                                setRecipeMgrBusy(false);
                              }
                            }}
                          >Duplicate</button>

                          {canEdit && (
                            <>
                              <button
                                className="secondary"
                                style={{ marginLeft: 8 }}
                                disabled={recipeMgrBusy || val.trim() === (r.label || "").trim()}
                                onClick={async () => {
                                  setRecipeMgrBusy(true);
                                  setRecipeMgrErr("");
                                  try {
                                    await updateRecipeLabel(r.id, val);
                                    await refreshRecipes();
                                    setToast({ type: "ok", msg: `Updated label: ${r.id}` });
                                  } catch (e: any) {
                                    const errMsg = String(e?.message || e);
                                    setRecipeMgrErr(errMsg.includes("404") || errMsg.includes("no_active_entry") ? INTEGRATION_NOT_CONFIGURED_MSG : errMsg);
                                  } finally {
                                    setRecipeMgrBusy(false);
                                  }
                                }}
                              >Save</button>
                              <button
                                className="danger"
                                style={{ marginLeft: 8 }}
                                disabled={recipeMgrBusy}
                                onClick={async () => {
                                  if (!confirm(`Delete recipe "${r.label}"? This cannot be undone.`)) return;
                                  setRecipeMgrBusy(true);
                                  setRecipeMgrErr("");
                                  try {
                                    await deleteRecipe(r.id);
                                    await refreshRecipes();
                                    setToast({ type: "ok", msg: `Deleted recipe: ${r.id}` });
                                  } catch (e: any) {
                                    const errMsg = String(e?.message || e);
                                    setRecipeMgrErr(errMsg.includes("404") || errMsg.includes("no_active_entry") ? INTEGRATION_NOT_CONFIGURED_MSG : errMsg);
                                  } finally {
                                    setRecipeMgrBusy(false);
                                  }
                                }}
                              >Delete</button>
                            </>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {recipes.length === 0 && (
                    <tr>
                      <td colSpan={4} className="muted" style={{ padding: "12px" }}>
                        No recipes discovered.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="row" style={{ justifyContent: "space-between", gap: 8, marginTop: 12 }}>
              <button className="secondary" onClick={refreshRecipes} disabled={recipeMgrBusy}>Refresh</button>
              <button className="ghost" onClick={() => setRecipeMgrOpen(false)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {saveEntityWidgetOpen && (
        <div
          className="modalOverlay"
          onClick={() => !saveEntityWidgetBusy && setSaveEntityWidgetOpen(false)}
        >
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 420 }}>
            <div className="modalHeader">
              <div className="title">Save as entity widget</div>
              <button className="ghost" disabled={saveEntityWidgetBusy} onClick={() => setSaveEntityWidgetOpen(false)}>
                ✕
              </button>
            </div>
            <p className="muted" style={{ marginBottom: 12 }}>
              Saves the current page as a reusable entity widget. Layout is grouped under one root when needed. Home Assistant entity IDs are replaced with a placeholder for the chosen device type.
            </p>
            <label className="label">Name</label>
            <input
              value={saveEntityWidgetName}
              onChange={(e) => setSaveEntityWidgetName(e.target.value)}
              placeholder="e.g. My climate panel"
              style={{ width: "100%", marginBottom: 8 }}
            />
            <label className="label">Description (optional)</label>
            <input
              value={saveEntityWidgetDescription}
              onChange={(e) => setSaveEntityWidgetDescription(e.target.value)}
              placeholder="e.g. Thermostat with preset dropdown"
              style={{ width: "100%", marginBottom: 8 }}
            />
            <label className="label">Device type</label>
            <select
              value={saveEntityWidgetDeviceType}
              onChange={(e) => setSaveEntityWidgetDeviceType(e.target.value)}
              title="Entity domain (entity_id will be stripped to this type)"
              style={{ width: "100%", padding: "8px 10px", marginBottom: 12 }}
            >
              <option value="climate">climate</option>
              <option value="light">light</option>
              <option value="cover">cover</option>
              <option value="switch">switch</option>
              <option value="media_player">media_player</option>
              <option value="fan">fan</option>
              <option value="lock">lock</option>
              <option value="sensor">sensor</option>
              <option value="number">number</option>
              <option value="select">select</option>
            </select>
            {saveEntityWidgetErr && <div className="error" style={{ marginBottom: 8 }}>{saveEntityWidgetErr}</div>}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button className="ghost" disabled={saveEntityWidgetBusy} onClick={() => setSaveEntityWidgetOpen(false)}>
                Cancel
              </button>
              <button
                disabled={saveEntityWidgetBusy || !saveEntityWidgetName.trim()}
                onClick={async () => {
                  if (!project || !saveEntityWidgetName.trim()) return;
                  const page = project.pages?.[safePageIndex];
                  if (!page?.widgets?.length) return setSaveEntityWidgetErr("Current page has no widgets.");
                  const widgetIds = new Set((page.widgets || []).map((w: any) => w?.id).filter(Boolean));
                  const links = ((project as any).links || []).filter((l: any) => widgetIds.has(l?.target?.widget_id));
                  const action_bindings = ((project as any).action_bindings || []).filter((ab: any) =>
                    widgetIds.has(ab?.widget_id)
                  );
                  const placeholder = saveEntityWidgetDeviceType + ".example";
                  const strippedLinks = links.map((l: any) => ({
                    ...l,
                    source: l.source ? { ...l.source, entity_id: placeholder } : l.source,
                  }));
                  const strippedActions = action_bindings.map((ab: any) => ({
                    ...ab,
                    call: ab.call
                      ? { ...ab.call, entity_id: ab.call.entity_id ? placeholder : ab.call.entity_id }
                      : ab.call,
                  }));
                  const widgetsNorm = normalizeWidgetsForEntityWidgetExport(page.widgets || []);
                  const widgetsJson = JSON.stringify(widgetsNorm);
                  const allScripts = ((project as any).scripts || []).filter(Boolean);
                  const strippedScripts = allScripts
                    .filter((s: any) => s?.id && widgetsJson.includes(String(s.id)))
                    .map((s: any) => ({
                      ...s,
                      entity_id: s.entity_id ? placeholder : s.entity_id,
                    }));
                  const slug =
                    saveEntityWidgetName.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") ||
                    "entity_widget";
                  setSaveEntityWidgetBusy(true);
                  setSaveEntityWidgetErr("");
                  try {
                    await saveEntityWidget({
                      id: slug,
                      name: saveEntityWidgetName.trim(),
                      description: saveEntityWidgetDescription.trim() || undefined,
                      device_types: [saveEntityWidgetDeviceType],
                      widgets: widgetsNorm,
                      links: strippedLinks,
                      action_bindings: strippedActions,
                      scripts: strippedScripts,
                    });
                    setSaveEntityWidgetOpen(false);
                    await refreshCustomEntityWidgets();
                    setToast({ type: "ok", msg: `Saved entity widget: ${saveEntityWidgetName.trim()}` });
                    setPaletteTab("entity");
                  } catch (e: any) {
                    setSaveEntityWidgetErr(String(e?.message || e));
                  } finally {
                    setSaveEntityWidgetBusy(false);
                  }
                }}
              >
                {saveEntityWidgetBusy ? "Saving…" : "Save entity widget"}
              </button>
            </div>
          </div>
        </div>
      )}

      {entityWidgetContextMenu && (
        <div
          style={{ position: "fixed", inset: 0, zIndex: 9999 }}
          onClick={() => setEntityWidgetContextMenu(null)}
          onContextMenu={(e) => {
            e.preventDefault();
            setEntityWidgetContextMenu(null);
          }}
        >
          <div
            style={{
              position: "absolute",
              left: entityWidgetContextMenu.x,
              top: entityWidgetContextMenu.y,
              background: "#2a2a2a",
              border: "1px solid #444",
              borderRadius: 6,
              boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
              minWidth: 140,
              overflow: "hidden",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ padding: "8px 12px", fontSize: 11, color: "#888", borderBottom: "1px solid #444" }}>
              {entityWidgetContextMenu.entityWidgetName}
            </div>
            <button
              type="button"
              style={{
                display: "block",
                width: "100%",
                padding: "10px 12px",
                textAlign: "left",
                background: "transparent",
                border: "none",
                color: "#ef4444",
                cursor: "pointer",
                fontSize: 13,
              }}
              onMouseOver={(e) => (e.currentTarget.style.background = "#3a3a3a")}
              onMouseOut={(e) => (e.currentTarget.style.background = "transparent")}
              onClick={async () => {
                const ewid = entityWidgetContextMenu.entityWidgetId;
                const nm = entityWidgetContextMenu.entityWidgetName;
                setEntityWidgetContextMenu(null);
                if (!confirm(`Delete saved entity widget "${nm}"?\n\nThis cannot be undone.`)) return;
                try {
                  await deleteSavedEntityWidget(ewid);
                  await refreshCustomEntityWidgets();
                  setToast({ type: "ok", msg: `Deleted: ${nm}` });
                } catch (e: any) {
                  setToast({ type: "error", msg: `Failed to delete: ${e?.message || e}` });
                }
              }}
            >
              🗑 Delete
            </button>
          </div>
        </div>
      )}

      {/* Context menu for page tab (delete page) */}
      {pageTabContextMenu && (
        <div
          style={{ position: "fixed", inset: 0, zIndex: 9999 }}
          onClick={() => setPageTabContextMenu(null)}
          onContextMenu={(e) => { e.preventDefault(); setPageTabContextMenu(null); }}
        >
          <div
            style={{
              position: "absolute",
              left: pageTabContextMenu.x,
              top: pageTabContextMenu.y,
              background: "#2a2a2a",
              border: "1px solid #444",
              borderRadius: 6,
              boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
              minWidth: 140,
              overflow: "hidden",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              style={{
                display: "block",
                width: "100%",
                padding: "10px 12px",
                textAlign: "left",
                background: "transparent",
                border: "none",
                color: "#ef4444",
                cursor: "pointer",
                fontSize: 13,
              }}
              onMouseOver={(e) => (e.currentTarget.style.background = "#3a3a3a")}
              onMouseOut={(e) => (e.currentTarget.style.background = "transparent")}
              onClick={() => {
                const idx = pageTabContextMenu.pageIndex;
                setPageTabContextMenu(null);
                deletePage(idx);
              }}
            >
              🗑 Delete page
            </button>
          </div>
        </div>
      )}

      <LvglSettingsModal
        open={lvglSettingsOpen}
        onClose={() => setLvglSettingsOpen(false)}
        config={project?.lvgl_config}
        onSave={(config: LvglConfig) => {
          if (project) {
            setProject({ ...project, lvgl_config: config });
            setProjectDirty(true);
          }
          setLvglSettingsOpen(false);
        }}
      />

      <OpenDevicePickerModal
        open={openDevicePickerOpen}
        onClose={() => setOpenDevicePickerOpen(false)}
        devices={devices}
        recipeLabels={recipeLabels}
        onSelect={(id) => loadDevice(id)}
      />

      <ManageDevicesModal
        open={manageDevicesOpen}
        onClose={() => setManageDevicesOpen(false)}
        devices={devices}
        recipeLabels={recipeLabels}
        busy={busy}
        onOpen={(id) => { loadDevice(id); setManageDevicesOpen(false); }}
        onRename={async (id, payload) => {
          if (!entryId) {
            setToast({ type: "error", msg: INTEGRATION_NOT_CONFIGURED_MSG });
            return;
          }
          const dev = devices.find((d) => d.device_id === id);
          const res = await upsertDevice(entryId, { device_id: id, name: payload.name, slug: payload.slug, hardware_recipe_id: dev?.hardware_recipe_id ?? null });
          if (!res.ok) return setToast({ type: "error", msg: res.error });
          setToast({ type: "ok", msg: "Device renamed" });
          await refresh();
        }}
        onCopy={copyDevice}
        onDelete={removeDevice}
      />

      {deployTargetOpen && (
        <div
          className="modalOverlay"
          onClick={() => {
            setDeployTargetOpen(false);
            const r = deployTargetResolveRef.current;
            deployTargetResolveRef.current = null;
            r?.(null);
          }}
        >
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 520 }}>
            <div className="modalHeader">
              <div className="title">Deploy target</div>
              <button
                className="ghost"
                onClick={() => {
                  setDeployTargetOpen(false);
                  const r = deployTargetResolveRef.current;
                  deployTargetResolveRef.current = null;
                  r?.(null);
                }}
              >
                ✕
              </button>
            </div>
            <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="muted" style={{ fontSize: 12 }}>
                USB serial device(s) detected on the Home Assistant host. Choose how to upload firmware.
              </div>
              <label style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                <input
                  type="radio"
                  name="deployTarget"
                  value="ota"
                  checked={deployTargetChoice === "ota"}
                  onChange={() => setDeployTargetChoice("ota")}
                  style={{ marginTop: 3 }}
                />
                <div>
                  <div style={{ fontWeight: 600 }}>OTA (wireless)</div>
                  <div className="muted" style={{ fontSize: 12 }}>Default ESPHome behaviour. No device override.</div>
                </div>
              </label>
              <div style={{ height: 1, background: "rgba(255,255,255,0.08)", margin: "6px 0" }} />
              <div style={{ fontSize: 12, fontWeight: 600 }}>USB serial</div>
              {(deployTargetPorts || []).map((p) => (
                <label key={p} style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  <input
                    type="radio"
                    name="deployTarget"
                    value={`usb:${p}`}
                    checked={deployTargetChoice === `usb:${p}`}
                    onChange={() => setDeployTargetChoice(`usb:${p}`)}
                  />
                  <code style={{ fontSize: 12 }}>{p}</code>
                </label>
              ))}
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 6 }}>
                <button
                  className="secondary"
                  onClick={() => {
                    setDeployTargetOpen(false);
                    const r = deployTargetResolveRef.current;
                    deployTargetResolveRef.current = null;
                    r?.(null);
                  }}
                >
                  Cancel
                </button>
                <button
                  className="primary"
                  onClick={() => {
                    setDeployTargetOpen(false);
                    const r = deployTargetResolveRef.current;
                    deployTargetResolveRef.current = null;
                    r?.(deployTargetChoice);
                  }}
                >
                  Continue
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {editDeviceModalOpen && selectedDeviceObj && (
        <div className="modalOverlay" onClick={() => setEditDeviceModalOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 420 }}>
            <div className="modalHeader">
              <div className="title">Device details</div>
              <button className="ghost" onClick={() => setEditDeviceModalOpen(false)}>✕</button>
            </div>
            <div className="muted" style={{ marginBottom: 12 }}><code>{selectedDeviceObj.device_id}</code></div>
            <label className="label">Friendly name</label>
            <input
              value={newDeviceName}
              onChange={(e) => setNewDeviceName(e.target.value)}
              placeholder="e.g. Living Room Display"
            />
            <label className="label">Filename</label>
            <input
              value={newDeviceSlug}
              onChange={(e) => setNewDeviceSlug(e.target.value)}
              placeholder="Used for .yaml export"
            />
            <label className="label">Hardware recipe</label>
            <select
              value={editDeviceRecipeId}
              onChange={(e) => setEditDeviceRecipeId(e.target.value)}
              title="Recipe = base YAML for this device (display, touch, pins). One recipe per device."
              style={{ width: "100%", padding: "8px 10px" }}
            >
              <option value="">(none)</option>
              {recipes.map((r) => (
                <option key={r.id} value={r.id}>{r.label || r.id}</option>
              ))}
            </select>
            <div className="muted" style={{ marginTop: 4, fontSize: 11 }}>Recipe = base device YAML (display, touch, pins). Defines resolution and hardware.</div>
            <label className="label">API key</label>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="text"
                autoComplete="off"
                value={newDeviceApiKey}
                onChange={(e) => setNewDeviceApiKey(e.target.value)}
                placeholder={newDeviceApiKey ? "" : "No key—click Regenerate to create one"}
                style={{ flex: 1, fontFamily: "monospace", fontSize: 12 }}
              />
              <button type="button" className="secondary" onClick={regenerateApiKey} title="Generate new API key">Regenerate</button>
              <button type="button" className="secondary" disabled={!newDeviceApiKey} onClick={() => newDeviceApiKey && navigator.clipboard.writeText(newDeviceApiKey)} title="Copy to clipboard">Copy</button>
            </div>
            <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
              Required for Home Assistant API. Visible for debugging. Saves with device; paste into ESPHome secrets or ensure it matches configuration.yaml.
            </div>
            <label className="label">WiFi SSID</label>
            <input
              type="text"
              autoComplete="off"
              value={newDeviceWifiSsid}
              onChange={(e) => setNewDeviceWifiSsid(e.target.value)}
              placeholder="Optional; blank = !secret wifi_ssid"
            />
            <label className="label">WiFi password</label>
            <input
              type="text"
              autoComplete="off"
              value={newDeviceWifiPassword}
              onChange={(e) => setNewDeviceWifiPassword(e.target.value)}
              placeholder="Optional; blank = !secret wifi_password"
            />
            <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
              Stored per-device. If password is blank, compiler uses <code>!secret wifi_password</code>.
            </div>
            <label className="label">OTA password</label>
            <input
              type="text"
              autoComplete="off"
              value={newDeviceOtaPassword}
              onChange={(e) => setNewDeviceOtaPassword(e.target.value)}
              placeholder="Optional; blank = no OTA password"
            />
            <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
              Optional. When set, compiler writes this into the top-level <code>ota:</code> block.
            </div>
            {!entryId && (
              <div className="muted" style={{ marginTop: 6 }}>
                Integration not ready.
                <div style={{ marginTop: 4, fontSize: 11 }}>If you just started Home Assistant, wait a few seconds and refresh the page.</div>
              </div>
            )}
            <div style={{ display: "flex", gap: 8, marginTop: 16, justifyContent: "flex-end" }}>
              <button className="ghost" onClick={() => setEditDeviceModalOpen(false)}>Cancel</button>
              <button disabled={busy || !newDeviceName.trim()} onClick={saveEditedDevice}>Save</button>
            </div>
          </div>
        </div>
      )}

      {/* Components Panel: section-based (categories → sections → section_overrides); loaded on open to keep main bundle small */}
      {componentsOpen && project && (
        <ComponentsPanelLoader
          project={project}
          setProject={setProject}
          setProjectDirty={setProjectDirty}
          onClose={() => setComponentsOpen(false)}
          deviceId={selectedDevice || null}
          entryId={entryId || null}
          onSaveAndPersist={
            entryId && selectedDevice
              ? async (updatedProject) => {
                  setBusy(true);
                  try {
                    const res = await putProject(entryId, selectedDevice, updatedProject);
                    if (!res.ok) {
                      setToast({ type: "error", msg: res.error });
                      return;
                    }
                    setProjectDirty(false);
                    setToast({ type: "ok", msg: "Project saved" });
                    // Refetch from server so app state matches stored project (section_overrides etc.).
                    const getRes = await getProject(entryId, selectedDevice);
                    if (getRes?.ok && getRes.project) setProject(getRes.project, true);
                  } finally {
                    setBusy(false);
                  }
                }
              : undefined
          }
        />
      )}

      {newDeviceWizardOpen && (
        <div className="modalOverlay">
          <div className="modal" style={{ maxWidth: 520 }} onClick={(e) => e.stopPropagation()}>
            <div className="modalHeader">
              <div>
                <div className="title">Add device</div>
                <div className="muted">
                  {newDeviceWizardStep === 1 ? "Step 1: Choose a hardware profile" : "Step 2: Device details"}
                </div>
              </div>
              <button className="ghost" onClick={() => setNewDeviceWizardOpen(false)}>✕</button>
            </div>
            {newDeviceWizardStep === 1 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div className="muted" style={{ fontSize: 13 }}>
                  Select the hardware recipe for this device. The canvas size will match the recipe resolution.
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 8, maxHeight: 320, overflowY: "auto" }}>
                  {recipes.map((r: any) => (
                    <button
                      key={r.id}
                      type="button"
                      className={newDeviceWizardRecipe?.id === r.id ? "" : "secondary"}
                      style={{ textAlign: "left", padding: 12 }}
                      onClick={() => wizardSelectRecipe({ id: r.id, label: String(r.label || r.id) })}
                    >
                      <div className="title" style={{ fontSize: 14 }}>{r.label || r.id}</div>
                      <div className="muted" style={{ fontSize: 12 }}><code>{r.id}</code></div>
                    </button>
                  ))}
                </div>
                {recipes.length === 0 && (
                  <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                    <div className="muted">No recipes found. The integration ships with built-in recipes — if none appear, try Refresh or check the Home Assistant logs.</div>
                    <button className="secondary" onClick={refreshRecipes}>Refresh</button>
                  </div>
                )}
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div className="muted" style={{ fontSize: 13 }}>
                  Profile: <strong>{newDeviceWizardRecipe?.label}</strong>
                </div>
                <label className="label">Friendly name</label>
                <input
                  value={newDeviceWizardName}
                  onChange={(e) => {
                    const name = e.target.value;
                    setNewDeviceWizardName(name);
                    const derived = friendlyToId(name);
                    setNewDeviceWizardId(derived);
                    setNewDeviceWizardSlug(derived);
                  }}
                  placeholder="e.g. Living Room Display"
                />
                <label className="label">device_id</label>
                <input value={newDeviceWizardId} onChange={(e) => { setNewDeviceWizardId(e.target.value); setNewDeviceWizardSlug(e.target.value); }} placeholder="Derived from name" />
                <label className="label">Filename</label>
                <input value={newDeviceWizardSlug} onChange={(e) => setNewDeviceWizardSlug(e.target.value)} placeholder="Defaults to device_id, used for .yaml file" />
                <label className="label">API key</label>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input
                    type="text"
                    autoComplete="off"
                    value={newDeviceWizardApiKey}
                    onChange={(e) => setNewDeviceWizardApiKey(e.target.value)}
                    placeholder="32-byte base64 (auto-generated)"
                    style={{ flex: 1, fontFamily: "monospace", fontSize: 12 }}
                  />
                  <button type="button" className="secondary" onClick={regenerateWizardApiKey} title="Generate new API key">Regenerate</button>
                  <button type="button" className="secondary" disabled={!newDeviceWizardApiKey} onClick={() => newDeviceWizardApiKey && navigator.clipboard.writeText(newDeviceWizardApiKey)} title="Copy to clipboard">Copy</button>
                </div>
                <label className="label">WiFi SSID</label>
                <input
                  type="text"
                  autoComplete="off"
                  value={newDeviceWizardWifiSsid}
                  onChange={(e) => setNewDeviceWizardWifiSsid(e.target.value)}
                  placeholder="Optional; blank = !secret wifi_ssid"
                />
                <label className="label">WiFi password</label>
                <input
                  type="text"
                  autoComplete="off"
                  value={newDeviceWizardWifiPassword}
                  onChange={(e) => setNewDeviceWizardWifiPassword(e.target.value)}
                  placeholder="Optional; blank = !secret wifi_password"
                />
                <label className="label">OTA password</label>
                <input
                  type="text"
                  autoComplete="off"
                  value={newDeviceWizardOtaPassword}
                  onChange={(e) => setNewDeviceWizardOtaPassword(e.target.value)}
                  placeholder="Optional; blank = no OTA password"
                />
                <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                  <button
                    className="secondary"
                    onClick={() => { setNewDeviceWizardStep(1); setNewDeviceWizardRecipe(null); }}
                  >
                    Back
                  </button>
                  <button
                    disabled={busy || !newDeviceWizardName.trim()}
                    onClick={createNewDeviceFromWizard}
                  >
                    Create device
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {compileModalOpen && (
        <div className="modalOverlay" onClick={() => setCompileModalOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 900, maxHeight: "90vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div className="modalHeader">
              <div className="title">Compile</div>
              <button className="ghost" onClick={() => setCompileModalOpen(false)}>Close</button>
            </div>
            <div style={{ flex: 1, overflowY: "auto", paddingRight: 8 }}>
              {!selectedDevice || !project ? (
                <div className="muted">Select a device first.</div>
              ) : (
                <>
                  <div className="section">
                    <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8, flexWrap: "wrap" }}>
                      <button className="secondary" disabled={compileBusy || !project} onClick={refreshCompile}>{compileBusy ? "Compiling…" : "Refresh"}</button>
                      <button
                        type="button"
                        className="secondary"
                        disabled={layoutAuditBusy || compileBusy || !project}
                        title="Compare model boxes to YAML footprints (arc_labeled wrapper, spinbox2 height) and list overlaps"
                        onClick={runLayoutAudit}
                      >
                        {layoutAuditBusy ? "Auditing…" : "Layout audit"}
                      </button>
                      <button className="secondary" disabled={!compiledYaml} onClick={async () => {
                          if (!compiledYaml) return;
                          try {
                            if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
                              await navigator.clipboard.writeText(compiledYaml);
                              setToast({ type: "ok", msg: "Copied to clipboard" });
                              return;
                            }
                          } catch {}
                          const textarea = document.createElement("textarea");
                          textarea.value = compiledYaml;
                          textarea.style.position = "fixed";
                          textarea.style.left = "-9999px";
                          textarea.setAttribute("readonly", "");
                          document.body.appendChild(textarea);
                          textarea.select();
                          try {
                            if (document.execCommand("copy")) {
                              setToast({ type: "ok", msg: "Copied to clipboard" });
                            } else {
                              setToast({ type: "error", msg: "Copy failed (check permissions)" });
                            }
                          } catch {
                            setToast({ type: "error", msg: "Copy failed (check permissions)" });
                          }
                          document.body.removeChild(textarea);
                        }}>Copy</button>
                      <button
                        disabled={exportBusy || !entryId || !selectedDevice}
                        onClick={async () => {
                          if (!entryId || !selectedDevice) return;
                          if (!exportPreview && !exportPreviewErr) await previewExport();
                          await doExport();
                        }}
                      >
                        {exportBusy ? "Exporting…" : "Export to /config/esphome/"}
                      </button>
                    </div>
                    {compileErr && <div className="toast error" style={{ marginBottom: 8 }}>Compile error: {compileErr}</div>}
                    {layoutAuditErr && <div className="toast error" style={{ marginBottom: 8 }}>Layout audit: {layoutAuditErr}</div>}
                    {layoutAudit && layoutAudit.overlaps && layoutAudit.overlaps.length > 0 && (
                      <div className="toast error" style={{ marginBottom: 8 }}>
                        <strong>YAML footprint overlaps ({layoutAudit.overlaps.length})</strong>
                        <ul style={{ margin: "8px 0 0 18px", padding: 0 }}>
                          {layoutAudit.overlaps.map((o) => (
                            <li key={`${o.a}-${o.b}`}>
                              {o.a} ↔ {o.b} — {o.intersection_px}px²
                            </li>
                          ))}
                        </ul>
                        <div className="muted" style={{ marginTop: 6 }}>
                          Pairs use page-absolute rectangles as emitted (padding, align, arc_labeled wrapper size, spinbox2 row height). Overlap here usually matches on-device stacking.
                        </div>
                      </div>
                    )}
                    {layoutAudit && (!layoutAudit.overlaps || layoutAudit.overlaps.length === 0) && !layoutAudit.error && (
                      <div className="toast" style={{ marginBottom: 8, background: "rgba(80,200,120,0.12)", border: "1px solid rgba(80,200,120,0.35)" }}>
                        Layout audit: no 2D overlaps between emitted widget footprints on this page.
                      </div>
                    )}
                    {layoutAudit && (
                      <div className="section" style={{ marginBottom: 12 }}>
                        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
                          <span className="muted">Audit JSON</span>
                          <button
                            type="button"
                            className="secondary"
                            onClick={async () => {
                              try {
                                await navigator.clipboard.writeText(JSON.stringify(layoutAudit, null, 2));
                                setToast({ type: "ok", msg: "Layout audit copied" });
                              } catch {
                                setToast({ type: "error", msg: "Copy failed" });
                              }
                            }}
                          >
                            Copy JSON
                          </button>
                        </div>
                        <pre
                          style={{
                            margin: 0,
                            maxHeight: 220,
                            overflow: "auto",
                            fontSize: 11,
                            padding: 8,
                            background: "var(--etd-panel-bg, #111)",
                            borderRadius: 6,
                          }}
                        >
                          {JSON.stringify(layoutAudit, null, 2)}
                        </pre>
                      </div>
                    )}
                    {compileWarnings.length > 0 && (
                      <div className="toast" style={{ marginBottom: 8, background: "rgba(250,200,80,0.15)", border: "1px solid rgba(250,200,80,0.4)" }}>
                        Component references missing widgets: {compileWarnings.map((w) => w.section && w.widget_id ? `${w.section} → widget "${w.widget_id}"` : w.type).join("; ")}. Remove or fix in Components, or delete the block.
                      </div>
                    )}
                    {exportErr && <div className="toast error" style={{ marginBottom: 8 }}>Export error: {exportErr}</div>}
                    <div style={{ minHeight: 200, maxHeight: 400 }}>
                      <YamlEditor readOnly value={compiledYaml || (compileBusy ? "Compiling…" : "No YAML yet.")} minHeight={200} maxHeight={400} />
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {fullYamlOpen && (
        <div className="modalOverlay" onClick={() => setFullYamlOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 960, maxHeight: "90vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div className="modalHeader">
              <div className="title">Full YAML</div>
              <button className="ghost" onClick={() => setFullYamlOpen(false)}>Close</button>
            </div>
            <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column", padding: 12 }}>
              {fullYamlError && <div className="toast error" style={{ marginBottom: 8 }}>{fullYamlError}</div>}
              {fullYamlBusy && <div className="muted" style={{ marginBottom: 8 }}>Compiling…</div>}
              <div style={{ flex: 1, minHeight: 300 }}>
                <YamlEditor
                  readOnly
                  value={fullYamlBusy ? "Compiling…" : fullYamlContent}
                  minHeight={300}
                  maxHeight="75vh"
                />
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                <button
                  className="secondary"
                  disabled={!fullYamlContent || fullYamlBusy}
                  onClick={async () => {
                    if (!fullYamlContent) return;
                    try {
                      if (navigator.clipboard?.writeText) {
                        await navigator.clipboard.writeText(fullYamlContent);
                        setToast({ type: "ok", msg: "Copied to clipboard" });
                      } else {
                        const ta = document.createElement("textarea");
                        ta.value = fullYamlContent;
                        ta.style.position = "fixed";
                        ta.style.left = "-9999px";
                        document.body.appendChild(ta);
                        ta.select();
                        document.execCommand("copy");
                        document.body.removeChild(ta);
                        setToast({ type: "ok", msg: "Copied to clipboard" });
                      }
                    } catch {
                      setToast({ type: "error", msg: "Copy failed" });
                    }
                  }}
                >
                  Copy
                </button>
                <button className="secondary" onClick={() => setFullYamlOpen(false)}>Close</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {aboutOpen && (
        <div className="modalOverlay" onClick={() => setAboutOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <div className="modalHeader">
              <div className="title">About</div>
              <button className="ghost" onClick={() => setAboutOpen(false)}>Close</button>
            </div>
            <div style={{ padding: 16 }}>
              <p style={{ marginBottom: 12 }}><strong>EspToolkit Designer</strong> — A Lovelace-style UI designer for ESP32 LVGL touch screens. Compiles designs into ESPHome YAML and deploys through Home Assistant.</p>
              <p className="muted" style={{ fontSize: 12, marginBottom: 12 }}>The canvas matches project pixel geometry at 1:1. Fonts: Montserrat in the browser aligns with common ESPHome defaults; uploaded TTF/OTF assets load when present. Final text metrics on the device can still differ slightly.</p>
              <p className="muted" style={{ fontSize: 12, marginBottom: 16 }}>YAML editing in this app uses CodeMirror 6.</p>
              <div style={{ borderTop: "1px solid rgba(255,255,255,0.1)", paddingTop: 12 }}>
                <div style={{ fontSize: 12, marginBottom: 8 }}><strong>CodeMirror 6</strong></div>
                <p className="muted" style={{ fontSize: 11, margin: 0 }}>Copyright (c) 2018–2024 by Marijn Haverbeke and others. Licensed under the MIT License. <a href="https://codemirror.net/" target="_blank" rel="noopener noreferrer" style={{ color: "rgba(100,180,255,0.9)" }}>codemirror.net</a></p>
              </div>
            </div>
          </div>
        </div>
      )}

      {simulationOpen && selectedDevice && project && screenSize && (
        <div className="modalOverlay" onClick={() => setSimulationOpen(false)} style={{ zIndex: 10001 }}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: "none", width: "auto", maxHeight: "95vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div className="modalHeader">
              <div className="title">Simulator</div>
              <button className="ghost" onClick={() => setSimulationOpen(false)}>Close</button>
            </div>
            <div style={{ padding: 12, overflow: "auto", display: "flex", flexDirection: "column", alignItems: "flex-start" }}>
              <p className="muted" style={{ marginBottom: 8, fontSize: 12 }}>Click and drag widgets to try controls. Buttons and actions show a toast.</p>
              <div style={{ outline: "2px solid rgba(16, 185, 129, 0.4)", borderRadius: 12 }}>
                <Canvas
                  widgets={widgets}
                  selectedIds={[]}
                  width={screenSize.width}
                  height={screenSize.height}
                  gridSize={(project as any)?.ui?.gridSize || 10}
                  showGrid={false}
                  dispBgColor={(project as any)?.disp_bg_color}
                  resolvePreviewFont={resolvePreviewFont}
                  liveOverrides={liveOverrides}
                  simulationMode={true}
                  simOverrides={simOverrides}
                  onSimulateUpdate={(widgetId, updates) => setSimOverrides((prev) => ({ ...prev, [widgetId]: { ...prev[widgetId], ...updates } }))}
                  onSimulateAction={handleSimulatorAction}
                  onOpenColorPicker={(widgetId, currentHex) => {
                    const { h, s } = hexToHsv(currentHex);
                    setColorPickerHue(h);
                    setColorPickerSat(s);
                    setColorPickerModal({ widgetId, initialHex: currentHex, fromSimulator: true });
                  }}
                  onOpenWhitePicker={(widgetId, currentMireds) => {
                    setWhitePickerModal({ widgetId, mireds: Math.max(153, Math.min(500, currentMireds)) });
                  }}
                  onOpenTextarea={(widgetId, currentText) => {
                    setTextareaModal({ widgetId, text: currentText || "" });
                  }}
                  onSelect={() => {}}
                  onSelectNone={() => {}}
                  onDropCreate={() => {}}
                  onChangeMany={() => {}}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {colorPickerModal && (() => {
        const { widgetId } = colorPickerModal;
        const currentHex = hsvToHex(colorPickerHue, colorPickerSat, 100);
        return (
          <div className="modalOverlay" style={{ zIndex: 10002 }} onClick={() => setColorPickerModal(null)}>
            <div className="modal" style={{ width: 320 }} onClick={(e) => e.stopPropagation()}>
              <div className="modalHeader">
                <div className="title">Pick colour</div>
                <button type="button" className="ghost" onClick={() => setColorPickerModal(null)}>×</button>
              </div>
              <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                <div style={{ height: 24, borderRadius: 6, background: "linear-gradient(to right, #ff0000, #ffff00, #00ff00, #00ffff, #0000ff, #ff00ff, #ff0000)", cursor: "pointer" }} title="Hue (tap to set)"
                  onClick={(e) => {
                    const rect = (e.target as HTMLElement).getBoundingClientRect();
                    const x = (e.clientX - rect.left) / rect.width;
                    setColorPickerHue(Math.round(x * 360) % 360);
                  }}
                />
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <label className="muted" style={{ width: 48, fontSize: 12 }}>Hue</label>
                  <input type="range" min={0} max={360} value={colorPickerHue} onChange={(e) => setColorPickerHue(Number(e.target.value))} style={{ flex: 1 }} />
                  <span style={{ fontSize: 12, minWidth: 36 }}>{colorPickerHue}°</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <label className="muted" style={{ width: 48, fontSize: 12 }}>Sat</label>
                  <input type="range" min={0} max={100} value={colorPickerSat} onChange={(e) => setColorPickerSat(Number(e.target.value))} style={{ flex: 1 }} />
                  <span style={{ fontSize: 12, minWidth: 36 }}>{colorPickerSat}%</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 8, background: currentHex, border: "1px solid rgba(255,255,255,.3)" }} />
                  <code style={{ fontSize: 12 }}>{currentHex}</code>
                </div>
                <p className="muted" style={{ fontSize: 11, margin: 0 }}>Use the sliders to choose a colour. Done updates the widget; use action bindings to drive lights or entities.</p>
                <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                  <button type="button" className="secondary" onClick={() => setColorPickerModal(null)}>Cancel</button>
                  <button type="button" className="primary" onClick={() => {
                    if (!project) return;
                    const hexNum = parseInt(currentHex.slice(1), 16);
                    if (colorPickerModal?.fromSimulator) {
                      setSimOverrides((prev) => ({ ...prev, [widgetId]: { ...prev[widgetId], value: hexNum } }));
                      handleSimulatorAction(widgetId, "on_apply", { value: hexNum });
                    }
                    const p2 = clone(project);
                    const pg = p2?.pages?.[safePageIndex];
                    const w = pg?.widgets?.find((x: any) => x?.id === widgetId);
                    if (w) {
                      if (!w.props) w.props = {};
                      w.props.value = hexNum;
                      if (!w.style) w.style = {};
                      w.style.bg_color = hexNum;
                      setProject(p2, true);
                      setProjectDirty(true);
                    }
                    setColorPickerModal(null);
                  }}>Done</button>
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      {whitePickerModal && (() => {
        const { widgetId, mireds } = whitePickerModal;
        const m = Math.max(153, Math.min(500, mireds));
        const t = (m - 153) / (500 - 153);
        const r = 255;
        const g = Math.round(255 - 75 * t);
        const b = Math.round(255 - 135 * t);
        const previewHex = `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${b.toString(16).padStart(2, "0")}`;
        return (
          <div className="modalOverlay" style={{ zIndex: 10002 }} onClick={() => setWhitePickerModal(null)}>
            <div className="modal" style={{ width: 320 }} onClick={(e) => e.stopPropagation()}>
              <div className="modalHeader">
                <div className="title">White temperature</div>
                <button type="button" className="ghost" onClick={() => setWhitePickerModal(null)}>×</button>
              </div>
              <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <label className="muted" style={{ width: 80, fontSize: 12 }}>Mireds</label>
                  <input
                    type="range"
                    min={153}
                    max={500}
                    value={mireds}
                    onChange={(e) => setWhitePickerModal((prev) => (prev ? { ...prev, mireds: Number(e.target.value) } : null))}
                    style={{ flex: 1 }}
                  />
                  <span style={{ fontSize: 12, minWidth: 36 }}>{mireds}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 8, background: previewHex, border: "1px solid rgba(255,255,255,.3)" }} />
                  <span className="muted" style={{ fontSize: 11 }}>Cool (153) ← → Warm (500)</span>
                </div>
                <p className="muted" style={{ fontSize: 11, margin: 0 }}>Apply sends this value to the bound light via action binding (on_apply).</p>
                <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                  <button type="button" className="secondary" onClick={() => setWhitePickerModal(null)}>Cancel</button>
                  <button
                    type="button"
                    className="primary"
                    onClick={() => {
                      setSimOverrides((prev) => ({ ...prev, [widgetId]: { ...prev[widgetId], value: mireds } }));
                      handleSimulatorAction(widgetId, "on_apply", { value: mireds });
                      setWhitePickerModal(null);
                    }}
                  >
                    Apply
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      {textareaModal && (() => {
        const { widgetId, text } = textareaModal;
        return (
          <div className="modalOverlay" style={{ zIndex: 10002 }} onClick={() => setTextareaModal(null)}>
            <div className="modal" style={{ width: 360 }} onClick={(e) => e.stopPropagation()}>
              <div className="modalHeader">
                <div className="title">Textarea (simulator)</div>
                <button type="button" className="ghost" onClick={() => setTextareaModal(null)}>×</button>
              </div>
              <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                <label className="muted" style={{ fontSize: 12 }}>Text</label>
                <textarea
                  value={text}
                  onChange={(e) => setTextareaModal((prev) => (prev ? { ...prev, text: e.target.value } : null))}
                  rows={4}
                  style={{ width: "100%", boxSizing: "border-box", resize: "vertical", padding: 8, background: "var(--panel-bg, #1e1e1e)", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 8, color: "inherit" }}
                />
                <p className="muted" style={{ fontSize: 11, margin: 0 }}>Apply updates the widget in simulator and fires on_value so action bindings can use the text.</p>
                <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                  <button type="button" className="secondary" onClick={() => setTextareaModal(null)}>Cancel</button>
                  <button
                    type="button"
                    className="primary"
                    onClick={() => {
                      setSimOverrides((prev) => ({ ...prev, [widgetId]: { ...prev[widgetId], text } }));
                      handleSimulatorAction(widgetId, "on_value", { text });
                      setTextareaModal(null);
                    }}
                  >
                    Apply
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      <WorkflowStepper
        currentStep={currentWorkflowStep}
        completedWorkflowSteps={completedWorkflowSteps}
        deviceName={selectedDeviceObj?.name || selectedDevice || null}
        stepGuidance={stepGuidance}
        nextStepLabel={nextStepLabel}
      />
      <nav className="bar" style={{ padding: "10px 16px", gap: 12, flexWrap: "wrap", alignItems: "center", borderBottom: "1px solid var(--color-border, #333)" }}>
        {/* Group: Device (when loaded) */}
        {selectedDevice && project && (
          <>
            <button
              type="button"
              className="ghost"
              onClick={() => {
                if (projectDirty && !window.confirm("You have unsaved changes. Go to device list anyway? Changes will be lost.")) return;
                try { localStorage.removeItem(LAST_DEVICE_KEY); } catch {}
                setSelectedDevice("");
                setProject(null, true);
                setSelectedWidgetIds([]);
                setSelectedSchema(null);
              }}
              title="Back to device list (recent, open, add, manage)"
            >
              Device list
            </button>
            <button className="secondary" disabled={busy || !selectedDevice} onClick={openEditDeviceModal} title="View or edit device name, slug, API key, recipe">Device details</button>
            <span className="muted" style={{ marginRight: 4 }}>|</span>
          </>
        )}
        {/* Group: Device & deploy */}
        <button className={projectDirty ? "primary" : "secondary"} disabled={busy || !selectedDevice || !project} onClick={saveProject} title="Save project to server (Ctrl+S)">{projectDirty ? "Save (unsaved)" : "Save"}</button>
        <button className="secondary" disabled={validateYamlBusy || !selectedDevice || !project} onClick={validateExportYaml} title="Validate exported YAML (add-on or local ESPHome CLI)">{validateYamlBusy ? "Validating…" : "Validate YAML"}</button>
        <button className="secondary" disabled={busy || !selectedDevice || !project} onClick={deployToConfig} title="Save compiled YAML to /config/esphome/ then run add-on (validate + compile + upload)">Deploy</button>
        <button className="secondary" disabled={busy || !selectedDevice || !project} onClick={deployToHost} title="Deploy to a specific host (hostname or IP)">Deploy to Host</button>
        <button className="secondary" disabled={busy || !selectedDevice || !project} onClick={() => setFullYamlOpen(true)} title="View full compiled ESPHome YAML">Full YAML</button>
        <button
          className="secondary"
          disabled={!project || !project.pages?.[safePageIndex]?.widgets?.length}
          onClick={() => {
            setSaveEntityWidgetOpen(true);
            setSaveEntityWidgetErr("");
            setSaveEntityWidgetName("");
            setSaveEntityWidgetDescription("");
            setSaveEntityWidgetDeviceType("climate");
          }}
          title="Save current page as a reusable entity widget (drop onto other projects from the Entity palette)"
        >
          Save as entity widget
        </button>
        <span className="muted" style={{ marginRight: 4 }}>|</span>
        {/* Group: Advanced */}
        <span style={{ display: "inline-flex", gap: 8, alignItems: "center", opacity: showAdvancedToolsProminent ? 1 : 0.7 }}>
          <button className="ghost" disabled={!project} onClick={() => setLvglSettingsOpen(true)} title="Theme, style definitions, gradients, main LVGL config">LVGL settings</button>
          <button className="ghost" disabled={!project} onClick={() => setComponentsOpen(true)} title="Edit ESPHome top-level sections (wifi, sensor, lvgl, etc.)">Components</button>
          <button className="ghost" onClick={() => setAboutOpen(true)} title="About and third-party licenses">About</button>
        </span>
      </nav>

      <main
        className="designerLayout"
        style={
          selectedDevice && project
            ? screenSize
              ? { gridTemplateColumns: `200px ${12 + 36 + screenSize.width + 12}px minmax(260px, 1fr)`, gap: 20 }
              : { gridTemplateColumns: "200px minmax(360px, 1fr) minmax(260px, 1fr)", gap: 20 }
            : undefined
        }
      >
        <aside className="designerPanel designerPanelLeft" style={{ minWidth: 200, maxWidth: 220 }}>
          <div className="panelTabs">
            <button type="button" className={`panelTab ${paletteTab === "basic" ? "active" : ""}`} onClick={() => setPaletteTab("basic")}>Basic</button>
            <button type="button" className={`panelTab ${paletteTab === "prebuilt" ? "active" : ""}`} onClick={() => setPaletteTab("prebuilt")}>Prebuilt</button>
            <button type="button" className={`panelTab ${paletteTab === "entity" ? "active" : ""}`} onClick={() => setPaletteTab("entity")}>Entity</button>
          </div>
          <div className="panelContent">
            {paletteTab === "basic" && (
              <>
                <div className="sectionTitle">Basic widgets</div>
                <div className="palette">
                  {(schemaIndex ?? []).filter(Boolean).map((s) => (
                    <div key={s?.type ?? ""} className="paletteItem" draggable onDragStart={(e) => { console.log('[ETD DragStart] widget:', s?.type); e.dataTransfer.setData("application/x-esphome-widget-type", s?.type ?? ""); e.dataTransfer.effectAllowed = "copy"; }} title={`Drag ${s?.title ?? s?.type ?? ""} onto canvas`}>
                      {s?.title ?? s?.type ?? ""}
                    </div>
                  ))}
                </div>
              </>
            )}
            {paletteTab === "prebuilt" && (
              <>
                <div className="sectionTitle">Prebuilt widgets</div>
                <div className="palette">
                  {PREBUILT_WIDGETS.map((pw) => (
                    <div
                      key={pw.id}
                      className="paletteItem"
                      draggable
                      onDragStart={(e) => { console.log('[ETD DragStart] prebuilt:', pw.id); e.dataTransfer.setData("application/x-esphome-prebuilt-widget", pw.id); e.dataTransfer.effectAllowed = "copy"; }}
                      onClick={() => {
                        if (!project) return;
                        if (!screenSize) {
                          setToast({ type: "error", msg: "Display size unknown; reload the device or set a hardware recipe with resolution." });
                          return;
                        }
                        const p2 = clone(project);
                        const pg = p2.pages?.[safePageIndex];
                        if (!pg?.widgets) return;
                        const NAV_BAR_W = 200;
                        const NAV_BAR_H = 44;
                        const placeX = pw.id === "prebuilt_nav_bar"
                          ? (screenSize.width - NAV_BAR_W) / 2
                          : 80;
                        const placeY = pw.id === "prebuilt_nav_bar"
                          ? screenSize.height - NAV_BAR_H
                          : 80;
                        const built = pw.build({ x: placeX, y: placeY });
                        const widgets = built.widgets || [];
                        for (const w of widgets) pg.widgets.push(w);
                        const rootId = widgets[0]?.id ?? null;
                        if (Array.isArray(built.action_bindings) && built.action_bindings.length > 0) {
                          (p2 as any).action_bindings = Array.isArray((p2 as any).action_bindings) ? (p2 as any).action_bindings : [];
                          for (const ab of built.action_bindings) (p2 as any).action_bindings.push(ab);
                        }
                        if (Array.isArray(built.scripts) && built.scripts.length > 0) {
                          (p2 as any).scripts = Array.isArray((p2 as any).scripts) ? (p2 as any).scripts : [];
                          for (const s of built.scripts) (p2 as any).scripts.push({ ...s, _source_root_id: rootId });
                        }
                        // v0.70.136: merge esphome_components for native prebuilt functionality (tag for delete cleanup)
                        if (Array.isArray(built.esphome_components) && built.esphome_components.length > 0) {
                          (p2 as any).esphome_components = Array.isArray((p2 as any).esphome_components) ? (p2 as any).esphome_components : [];
                          for (const c of built.esphome_components) {
                            const yaml = typeof c === "string" ? c : (c?.yaml ?? "");
                            (p2 as any).esphome_components.push({ yaml, _source_root_id: rootId });
                          }
                        }
                        setProject(p2, true);
                        setProjectDirty(true);
                        setSelectedWidgetIds(widgets.length ? [widgets[0].id] : []);
                        setInspectorTab("properties");
                      }}
                      title={pw.description ? `${pw.description} (drag or click to add)` : "Drag or click to add"}
                      style={{ display: "flex", alignItems: "center", minWidth: 0 }}
                    >
                      <span style={{ flex: 1, minWidth: 0 }}>{pw.title}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
            {paletteTab === "entity" && (
              <>
                <div
                  className="sectionTitle"
                  title="Multi-widget layouts bound to Home Assistant entities. Built-in templates or your saved entity widgets."
                >
                  Entity widgets
                </div>
                <div className="muted" style={{ fontSize: 10, marginBottom: 8 }}>
                  Built-in or saved layouts. Drop onto the canvas, then pick an entity in the wizard.
                </div>
                {customEntityWidgetsError && (
                  <div className="error" style={{ marginBottom: 8 }}>{customEntityWidgetsError}</div>
                )}
                <div className="palette">
                  {[...(CONTROL_TEMPLATES || []), ...(pluginControls || [])]
                    .filter((t: any) => t && isEntityWidgetTemplateTitle((t as any).title))
                    .map((t: any) => (
                      <div
                        key={t.id}
                        className="paletteItem"
                        draggable
                        onDragStart={(e) => {
                          console.log("[ETD DragStart] entity template:", t.id);
                          e.dataTransfer.setData("application/x-esphome-control-template", t.id);
                          e.dataTransfer.effectAllowed = "copy";
                        }}
                        onClick={() => {
                          if (project && selectedDevice) openTemplateWizard(t.id, 80, 80);
                          else setToast({ type: "error", msg: "Select a device first, then add an entity widget." });
                        }}
                        title={String((t as any).description ?? "") + " (click or drag onto canvas)"}
                      >
                        {t.title ?? t.id}
                      </div>
                    ))}
                  {customEntityWidgets.map((c) => (
                    <div
                      key={SAVED_ENTITY_WIDGET_PREFIX + c.id}
                      className="paletteItem"
                      draggable
                      onDragStart={(e) => {
                        console.log("[ETD DragStart] saved entity widget:", c.id);
                        e.dataTransfer.setData(
                          "application/x-esphome-control-template",
                          SAVED_ENTITY_WIDGET_PREFIX + c.id
                        );
                        e.dataTransfer.effectAllowed = "copy";
                      }}
                      onClick={() => {
                        if (project && selectedDevice)
                          openTemplateWizard(SAVED_ENTITY_WIDGET_PREFIX + c.id, 80, 80);
                        else setToast({ type: "error", msg: "Select a device first, then add an entity widget." });
                      }}
                      onContextMenu={(e) => {
                        e.preventDefault();
                        setEntityWidgetContextMenu({
                          x: e.clientX,
                          y: e.clientY,
                          entityWidgetId: c.id,
                          entityWidgetName: c.name,
                        });
                      }}
                      title={(c.description || "") + " (click or drag • right-click to delete)"}
                    >
                      {c.name}{" "}
                      <span className="muted" style={{ fontSize: 10 }}>
                        (saved)
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}
            <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
              Drag onto canvas. <code>ALT</code> disables snapping. Resize a group: hold <code>Shift</code> to change only the container (children stay same size/position).
            </div>
          </div>
        </aside>

        <div className="designerPanelCenter">
          {!selectedDevice || !project ? (
            <WelcomePanel
              devices={devices}
              recentDeviceIds={recentDeviceIds}
              recipeLabels={recipeLabels}
              busy={busy}
              onLoadDevice={loadDevice}
              onOpenDevicePicker={() => setOpenDevicePickerOpen(true)}
              onAddDevice={openNewDeviceWizard}
              onManageDevices={() => setManageDevicesOpen(true)}
              onImportYaml={() => { setImportYamlOpen(true); setImportYamlText(""); setImportYamlNameOverride(""); setImportYamlErr(""); setImportLogLines([]); }}
              onCopyDevice={copyDevice}
              onDeleteDevice={removeDevice}
            />
          ) : (
            <>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 8 }}>
                {/* Page tabs */}
                <div style={{ display: "inline-flex", alignItems: "center", gap: 0, border: "1px solid var(--color-border, #333)", borderRadius: 8, overflow: "hidden" }}>
                  {pages.map((p, idx) => (
                    <button
                      key={p?.page_id ?? `page-${idx}`}
                      type="button"
                      className={safePageIndex === idx ? "primary" : "ghost"}
                      style={{
                        padding: "6px 12px",
                        borderRadius: 0,
                        borderRight: idx < pages.length - 1 ? "1px solid var(--color-border, #333)" : "none",
                        fontWeight: safePageIndex === idx ? 600 : 400,
                      }}
                      onClick={() => { setCurrentPageIndex(idx); setSelectedWidgetIds([]); setSelectedSchema(null); }}
                      onContextMenu={(e) => {
                        e.preventDefault();
                        if (pages.length > 1) setPageTabContextMenu({ x: e.clientX, y: e.clientY, pageIndex: idx });
                      }}
                      title={pages.length > 1 ? `Page ${idx + 1} (right-click to delete)` : `Page ${idx + 1}`}
                    >
                      {p?.name || `Page ${idx + 1}`}
                    </button>
                  ))}
                  <button
                    type="button"
                    className="ghost"
                    style={{ padding: "6px 10px", borderRadius: 0, borderLeft: "1px solid var(--color-border, #333)" }}
                    disabled={busy}
                    onClick={addPage}
                    title="Add page"
                  >
                    + Page
                  </button>
                </div>
                <span className="muted">|</span>
                <button className="secondary" disabled={!projectHist.canUndo} onClick={projectHist.undo}>Undo</button>
                <button className="secondary" disabled={!projectHist.canRedo} onClick={projectHist.redo}>Redo</button>
                <span className="muted">|</span>
                <button className="secondary" disabled={selectedWidgetIds.length < 2} onClick={() => alignSelected("left")}>Align L</button>
                <button className="secondary" disabled={selectedWidgetIds.length < 2} onClick={() => alignSelected("center")}>C</button>
                <button className="secondary" disabled={selectedWidgetIds.length < 2} onClick={() => alignSelected("right")}>R</button>
                <button className="secondary" disabled={selectedWidgetIds.length < 2} onClick={() => alignSelected("top")}>T</button>
                <button className="secondary" disabled={selectedWidgetIds.length < 2} onClick={() => alignSelected("middle")}>M</button>
                <button className="secondary" disabled={selectedWidgetIds.length < 2} onClick={() => alignSelected("bottom")}>B</button>
                <button className="secondary" disabled={selectedWidgetIds.length < 3} onClick={() => distributeSelected("h")}>Dist H</button>
                <button className="secondary" disabled={selectedWidgetIds.length < 3} onClick={() => distributeSelected("v")}>Dist V</button>
                <span className="muted">|</span>
                <button className="secondary" disabled={!selectedWidgetIds.length} onClick={() => moveZ("front")} title="Bring forward (Ctrl+])">Front</button>
                <button className="secondary" disabled={!selectedWidgetIds.length} onClick={() => moveZ("back")} title="Send backward (Ctrl+[)">Back</button>
                <span className="muted">|</span>
                <button className="secondary" disabled={!clipboard?.length} onClick={pasteClipboard}>Paste</button>
                <button className="secondary" disabled={!selectedWidgetIds.length} onClick={copySelected}>Copy</button>
                <button className="secondary" disabled={!selectedWidgetIds.length} onClick={deleteSelected}>Del</button>
              </div>
              {/* Physical screen dimensions - from device / recipe only (no generic defaults) */}
              <div style={{
                marginBottom: 12,
                padding: "10px 14px",
                background: screenSize ? "rgba(16, 185, 129, 0.12)" : "rgba(245, 158, 11, 0.14)",
                border: screenSize ? "1px solid rgba(16, 185, 129, 0.4)" : "1px solid rgba(245, 158, 11, 0.45)",
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 600,
                color: "var(--ha-text-primary)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                flexWrap: "wrap",
                gap: 8,
              }}>
                <span style={{ flex: "1 1 220px" }}>
                  <span style={{ marginRight: 8 }}>Physical screen:</span>
                  {screenSize ? (
                    <>
                      <span>{screenSize.width} × {screenSize.height} px</span>
                      <span className="muted" style={{ marginLeft: 8, fontSize: 12, fontWeight: 400 }}>({screenSize.source})</span>
                    </>
                  ) : (
                    <span className="muted" style={{ fontSize: 13, fontWeight: 500 }}>
                      Unknown — open this device again from the list (project loads size from the hardware recipe), or ensure the recipe id includes resolution (e.g. 1024x600).
                    </span>
                  )}
                </span>
                <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button
                    type="button"
                    className="primary"
                    disabled={!screenSize}
                    onClick={() => {
                      if (!screenSize) return;
                      setSimOverrides({});
                      setSimulationOpen(true);
                    }}
                    title="Open live interactive simulator"
                  >
                    Simulate
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    disabled={!entryId || !selectedDevice || !project || !screenSize || macSimBusy}
                    onClick={() => void handleMacSim()}
                    title="Compile for host/SDL and send to Mac agent (EspToolkit integration options: Mac sim token; run ha_agent_client.py on the Mac)"
                  >
                    {macSimBusy ? "Mac sim…" : "Mac sim"}
                  </button>
                </span>
              </div>
              {!screenSize ? (
                <div className="muted" style={{ fontSize: 13, marginBottom: 16, padding: 14, background: "rgba(245, 158, 11, 0.08)", borderRadius: 8, border: "1px solid rgba(245, 158, 11, 0.25)", maxWidth: 560, lineHeight: 1.45 }}>
                  Canvas is hidden until display width and height are known. That normally comes from <strong>device.screen</strong> on the project (filled when you load a device that has a hardware recipe with resolution metadata) or from a <strong>W×H</strong> pattern in the hardware recipe id.
                </div>
              ) : (
                <>
              {fontPreviewBanner && (
                <div className="muted" style={{ fontSize: 11, marginBottom: 8, maxWidth: screenSize.width + 48, lineHeight: 1.4 }}>
                  {fontPreviewBanner}
                </div>
              )}
              <div className="muted" style={{ fontSize: 11, marginBottom: 8, maxWidth: screenSize.width + 48, lineHeight: 1.4 }}>
                Canvas is 1 logical project pixel per screen pixel (no zoom). Long mode: WRAP/CLIP/DOT are approximated; SCROLL / SCROLL_CIRCULAR show as static ellipsis here, not animated. Typography may still differ from firmware (hinting, bitmap fonts).
              </div>
              <div className="canvasAxis" style={{ alignSelf: "flex-start" }}>
                <div style={{
                  display: "grid",
                  gridTemplateColumns: "36px " + screenSize.width + "px",
                  gridTemplateRows: screenSize.height + "px 28px",
                  alignItems: "stretch",
                  justifyItems: "stretch",
                }}>
                  <div className="canvasAxisY" style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", paddingTop: 10, paddingBottom: 10, paddingRight: 6, fontSize: 11, lineHeight: 1.2, color: "var(--muted)", textAlign: "right", overflow: "visible", minHeight: 0 }}>
                    {(() => {
                      const ticks: number[] = [];
                      for (let v = 0; v <= screenSize.height; v += 100) ticks.push(v);
                      if (ticks[ticks.length - 1] !== screenSize.height) ticks.push(screenSize.height);
                      return ticks.map((y) => <span key={y}>{y}</span>);
                    })()}
                  </div>
                  <div style={{ minWidth: 0, flexShrink: 0, width: screenSize.width, height: screenSize.height, outline: "2px solid rgba(16, 185, 129, 0.4)", borderRadius: 12, overflow: "hidden" }}>
                    <Canvas
                  widgets={widgets}
                  selectedIds={selectedWidgetIds}
                  width={screenSize.width}
                  height={screenSize.height}
                  gridSize={(project as any)?.ui?.gridSize || 10}
                  showGrid={((project as any)?.ui?.showGrid ?? true) as any}
                  dispBgColor={(project as any)?.disp_bg_color}
                  resolvePreviewFont={resolvePreviewFont}
                  liveOverrides={liveOverrides}
                  onSelect={(id, additive) => selectWidget(id, additive)}
                  onSelectNone={() => setSelectedWidgetIds([])}
                  onDropCreate={(type, x, y) => {
                    console.log('[ETD onDropCreate] type:', type, 'x:', x, 'y:', y, 'project:', !!project, 'safePageIndex:', safePageIndex);
                    if (!project) { console.log('[ETD onDropCreate] No project, aborting'); return; }
                    const p2 = clone(project);
                    const pg = p2.pages?.[safePageIndex];
                    console.log('[ETD onDropCreate] pg:', !!pg, 'pg.widgets:', pg?.widgets?.length ?? 'undefined');
                    // Ensure page has widgets array
                    if (pg && !Array.isArray(pg.widgets)) {
                      console.log('[ETD onDropCreate] Initializing pg.widgets array');
                      pg.widgets = [];
                    }
                    // Prebuilt widgets: insert directly without wizard
                    if (String(type).startsWith("prebuilt:")) {
                      const prebuiltId = String(type).slice(9);
                      const pw = PREBUILT_WIDGETS.find((p) => p.id === prebuiltId);
                      console.log('[ETD onDropCreate] Prebuilt:', prebuiltId, 'found:', !!pw);
                      if (pw && pg) {
                        if (prebuiltId === "prebuilt_nav_bar" && !screenSize) {
                          setToast({ type: "error", msg: "Display size unknown; reload the device or set a hardware recipe with resolution." });
                          return;
                        }
                        const NAV_BAR_W = 200;
                        const NAV_BAR_H = 44;
                        const placeX = prebuiltId === "prebuilt_nav_bar" && screenSize
                          ? (screenSize.width - NAV_BAR_W) / 2
                          : x;
                        const placeY = prebuiltId === "prebuilt_nav_bar" && screenSize
                          ? screenSize.height - NAV_BAR_H
                          : y;
                        const built = pw.build({ x: placeX, y: placeY });
                        const widgets = built.widgets || [];
                        console.log('[ETD onDropCreate] Built widgets:', widgets.length, widgets.map((w: any) => ({ id: w.id, type: w.type, parent_id: w.parent_id })));
                        for (const w of widgets) pg.widgets.push(w);
                        console.log('[ETD onDropCreate] After push, pg.widgets:', pg.widgets.length);
                        const rootId = widgets[0]?.id ?? null;
                        if (Array.isArray(built.action_bindings) && built.action_bindings.length > 0) {
                          (p2 as any).action_bindings = Array.isArray((p2 as any).action_bindings) ? (p2 as any).action_bindings : [];
                          for (const ab of built.action_bindings) (p2 as any).action_bindings.push(ab);
                        }
                        if (Array.isArray(built.scripts) && built.scripts.length > 0) {
                          (p2 as any).scripts = Array.isArray((p2 as any).scripts) ? (p2 as any).scripts : [];
                          for (const s of built.scripts) (p2 as any).scripts.push({ ...s, _source_root_id: rootId });
                        }
                        // v0.70.136: merge esphome_components for native prebuilt functionality (tag for delete cleanup)
                        if (Array.isArray(built.esphome_components) && built.esphome_components.length > 0) {
                          (p2 as any).esphome_components = Array.isArray((p2 as any).esphome_components) ? (p2 as any).esphome_components : [];
                          for (const c of built.esphome_components) {
                            const yaml = typeof c === "string" ? c : (c?.yaml ?? "");
                            (p2 as any).esphome_components.push({ yaml, _source_root_id: rootId });
                          }
                        }
                        console.log('[ETD onDropCreate] Calling setProject');
                        setProject(p2, true);
                        setProjectDirty(true);
                        const firstId = widgets.length ? widgets[0].id : null;
                        console.log('[ETD onDropCreate] Prebuilt done, firstId:', firstId);
                        requestAnimationFrame(() => {
                          requestAnimationFrame(() => {
                            if (firstId) setSelectedWidgetIds([firstId]);
                            setInspectorTab("properties");
                          });
                        });
                      }
                      return;
                    }
                    // v0.21: allow dropping either a raw widget type OR a control template (tmpl:<id>)
                    if (String(type).startsWith("tmpl:")) {
                      const tid = String(type).slice(5);
                      console.log('[ETD onDropCreate] Template:', tid);
                      // v0.22: open a post-drop wizard so we can capture entity_id/label.
                      openTemplateWizard(tid, x, y);
                      return;
                    }

                    const id = uid(type);
                    const isColorPicker = String(type).toLowerCase() === "color_picker";
                    const isWhitePicker = String(type).toLowerCase() === "white_picker";
                    const isSpinbox2 = String(type).toLowerCase() === "spinbox2";
                    const w = {
                      id,
                      type,
                      x,
                      y,
                      w: isColorPicker || isWhitePicker ? 80 : isSpinbox2 ? 200 : 120,
                      h: isColorPicker || isWhitePicker ? 36 : 48,
                      props: isColorPicker
                        ? { value: 0x4080FF }
                        : isWhitePicker
                          ? { value: 326 }
                          : isSpinbox2
                            ? {
                                value: 15,
                                min_value: 5,
                                max_value: 30,
                                step: 1,
                                decimal_places: 1,
                                minus_text: "-",
                                plus_text: "+",
                              }
                            : {},
                      style: isColorPicker
                        ? { bg_color: 0x4080FF, radius: 8 }
                        : isWhitePicker
                          ? { bg_color: 0xFFD9BC, radius: 8 }
                          : isSpinbox2
                            ? { bg_color: 0x1e293b, border_width: 1, border_color: 0x475569, radius: 6, text_color: 0xe2e8f0 }
                            : {},
                      events: {},
                    };
                    if (!pg) { console.log('[ETD onDropCreate] No page, aborting'); return; }
                    pg.widgets.push(w as any);
                    console.log('[ETD onDropCreate] Widget pushed, total widgets:', pg.widgets.length);
                    setProject(p2, true);
                    setProjectDirty(true);
                    setSelectedWidgetIds([id]);
                    setInspectorTab("properties");
                    getWidgetSchema(type).then((sr) => { if (sr.ok) setSelectedSchema(sr.schema); });
                  }}
                  onChangeMany={(patches, commit) => {
                    if (!project) return;
                    const p2 = clone(project);
                    const pg = (p2 as any).pages?.[safePageIndex];
                    if (!pg?.widgets) return;
                    const byId = new Map<string, any>((pg.widgets || []).filter((w: any) => w && w.id).map((w: any) => [String(w.id), w]));
                    for (const { id, patch } of patches) {
                      const w = pg.widgets.find((x: any) => x && x.id === id);
                      if (!w) continue;
                      Object.assign(w, patch);
                    }
                    // Frame-only resize updates a single container shell; keep descendant clipping
                    // containers (common in saved entity widgets) fit to their own children.
                    if (patches.length === 1) {
                      const p0 = patches[0];
                      const w0 = byId.get(String(p0.id));
                      const t0 = String(w0?.type || "").toLowerCase();
                      const resized = !!p0.patch && (Object.prototype.hasOwnProperty.call(p0.patch, "w") || Object.prototype.hasOwnProperty.call(p0.patch, "h"));
                      if (resized && (t0 === "container" || t0 === "obj")) {
                        fitDescendantContainerTrees(pg.widgets, String(p0.id));
                      }
                    }
                    setProject(p2, commit ?? true);
                    setProjectDirty(true);
                  }}
                />
                  </div>
                  <div />
                  <div className="canvasAxisX" style={{ display: "flex", justifyContent: "space-between", alignSelf: "start", width: screenSize.width, paddingLeft: 6, paddingRight: 6, boxSizing: "border-box", fontSize: 11, lineHeight: 1.2, color: "var(--muted)", direction: "ltr", overflow: "visible" }}>
                    {(() => {
                      const ticks: number[] = [];
                      for (let v = 0; v <= screenSize.width; v += 100) ticks.push(v);
                      if (ticks[ticks.length - 1] !== screenSize.width) ticks.push(screenSize.width);
                      return ticks.map((x) => <span key={x} style={{ flex: "0 0 auto" }}>{x}</span>);
                    })()}
                  </div>
                </div>
              </div>
                </>
              )}
            </>
          )}
        </div>

        <aside className="designerPanel designerPanelRight" style={{ minWidth: 260 }}>
          <div className="panelTabs">
            <button type="button" className={`panelTab ${inspectorTab === "properties" ? "active" : ""}`} onClick={() => setInspectorTab("properties")}>Properties</button>
            <button type="button" className={`panelTab ${inspectorTab === "builder" ? "active" : ""}`} onClick={() => setInspectorTab("builder")}>Binding Builder</button>
            <button type="button" className={`panelTab ${inspectorTab === "bindings" ? "active" : ""}`} onClick={() => setInspectorTab("bindings")}>HA Bindings</button>
            <button type="button" className={`panelTab ${inspectorTab === "yaml" ? "active" : ""}`} onClick={() => setInspectorTab("yaml")}>YAML</button>
            <button type="button" className={`panelTab ${inspectorTab === "importlog" ? "active" : ""}`} onClick={() => setInspectorTab("importlog")} title="Import and debug log">Import log</button>
          </div>
          <div className="panelContent">
            {selectedWidgetIds.length === 0 && (
              <div style={{ marginBottom: 12, padding: 14, background: "rgba(255,255,255,.06)", borderRadius: 8, border: "1px solid rgba(255,255,255,.12)", textAlign: "center" }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", marginBottom: 4 }}>Nothing selected</div>
                <div className="muted" style={{ fontSize: 12 }}>Select a widget on the canvas to edit properties and bindings.</div>
              </div>
            )}
            {project && (
              <div style={{ marginBottom: 12, padding: 10, background: "rgba(255,255,255,.04)", borderRadius: 8, border: "1px solid rgba(255,255,255,.08)" }}>
                <div className="sectionTitle" style={{ fontSize: 12, marginBottom: 8 }}>Canvas background</div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <input
                    type="color"
                    value={/^#[0-9a-fA-F]{6}$/.test((project as any).disp_bg_color || "") ? (project as any).disp_bg_color : "#0b0f14"}
                    onChange={(e) => {
                      const hex = e.target.value;
                      setProject({ ...project, disp_bg_color: hex }, true);
                      setProjectDirty(true);
                    }}
                    style={{ width: 42, height: 28, padding: 0, border: "none", background: "transparent", cursor: "pointer" }}
                  />
                  <input
                    type="text"
                    value={(project as any).disp_bg_color || ""}
                    onChange={(e) => {
                      const v = e.target.value.trim();
                      setProject({ ...project, disp_bg_color: v || undefined }, true);
                      setProjectDirty(true);
                    }}
                    placeholder="None (device default)"
                    style={{ flex: 1, fontSize: 12, fontFamily: "ui-monospace, monospace" }}
                  />
                  {((project as any).disp_bg_color) && (
                    <button
                      type="button"
                      className="secondary"
                      style={{ fontSize: 11 }}
                      onClick={() => {
                        const { disp_bg_color: _, ...rest } = project as any;
                        setProject(rest, true);
                        setProjectDirty(true);
                      }}
                    >
                      Clear
                    </button>
                  )}
                </div>
                <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>Sets disp_bg_color and page bg_color in LVGL. Recipe must have display: auto_clear_enabled: false.</div>
              </div>
            )}
            {inspectorTab === "properties" && (
              <div>
                <div className="muted">Properties</div>
                {selectedWidgetIds.length === 1 && selectedWidget && (
                  <>
                    <div className="inspectorWidgetId" style={{ marginBottom: 12, padding: "10px 12px", background: "rgba(255,255,255,.06)", borderRadius: 8, border: "1px solid rgba(255,255,255,.1)" }}>
                      <div className="inspectorWidgetIdLabel">Widget ID (YAML)</div>
                      <input
                        type="text"
                        value={editingWidgetId !== "" ? editingWidgetId : selectedWidget.id}
                        onChange={(e) => setEditingWidgetId(e.target.value)}
                        onBlur={() => {
                          const raw = editingWidgetId !== "" ? editingWidgetId : selectedWidget.id;
                          const next = raw.replace(/[^a-zA-Z0-9_]/g, "_").replace(/^_+|_+$/g, "").trim();
                          if (next && next !== selectedWidget.id) {
                            const result = renameWidgetInProject(project, safePageIndex, selectedWidget.id, next);
                            if (result.ok && result.newId) {
                              setProject(result.project, true);
                              setProjectDirty(true);
                              setSelectedWidgetIds([result.newId]);
                            } else {
                              setToast({ type: "error", msg: result.error || "Cannot rename" });
                            }
                          }
                          setEditingWidgetId("");
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                        }}
                        placeholder="e.g. living_room_temperature"
                        style={{ width: "100%", marginTop: 6, fontSize: 13, fontFamily: "ui-monospace, monospace" }}
                      />
                    </div>
                    <div className="section" style={{ marginBottom: 12 }}>
                      <div className="sectionTitle" style={{ fontSize: 12 }}>Group</div>
                      {selectedWidget.parent_id ? (
                        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                          <span className="muted">Parent:</span>
                          <code>{selectedWidget.parent_id}</code>
                          <button
                            type="button"
                            className="secondary"
                            onClick={() => {
                              if (!project) return;
                              const p2 = clone(project);
                              const pg = (p2 as any).pages?.[safePageIndex];
                              const w = pg?.widgets?.find((x: any) => x?.id === selectedWidget.id);
                              if (w) { w.parent_id = undefined; delete w.parent_id; }
                              setProject(p2, true);
                              setProjectDirty(true);
                            }}
                          >
                            Remove from group
                          </button>
                        </div>
                      ) : (
                        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                          <span className="muted">Parent: None</span>
                          <select
                            value=""
                            onChange={(e) => {
                              const parentId = e.target.value;
                              if (!parentId || !project) return;
                              const p2 = clone(project);
                              const pg = (p2 as any).pages?.[safePageIndex];
                              const w = pg?.widgets?.find((x: any) => x?.id === selectedWidget.id);
                              if (w) w.parent_id = parentId;
                              setProject(p2, true);
                              setProjectDirty(true);
                              e.target.value = "";
                            }}
                          >
                            <option value="">Add to group…</option>
                            {widgets.filter((w: any) => w?.type === "container" && w?.id !== selectedWidget?.id).map((w: any) => (
                              <option key={w.id} value={w.id}>{w.id}</option>
                            ))}
                          </select>
                        </div>
                      )}
                      {selectedWidget.type === "container" && (
                        <div className="muted" style={{ marginTop: 4, fontSize: 12 }}>
                          Children: {widgets.filter((w: any) => w?.parent_id === selectedWidget.id).length}
                        </div>
                      )}
                    </div>
                    {(() => {
                      const screensaverWidget =
                        selectedWidget?.id && String(selectedWidget.id).startsWith("screensaver_")
                          ? selectedWidget
                          : (widgets as any[]).find(
                              (w: any) =>
                                w?.parent_id === selectedWidget?.id &&
                                String(w?.id ?? "").startsWith("screensaver_")
                            );
                      const screensaverOnChange = (section: string, key: string, value: any) => {
                        if (!project || !screensaverWidget?.id) return;
                        const targetId = screensaverWidget.id;
                        if (targetId === selectedWidgetId) {
                          updateField(section, key, value);
                          return;
                        }
                        const p2 = clone(project);
                        const page = p2.pages?.[safePageIndex];
                        const w = page?.widgets?.find((x: any) => x?.id === targetId);
                        if (!w) return;
                        w[section] = w[section] || {};
                        if (value === undefined) delete w[section][key];
                        else w[section][key] = value;
                        setProject(p2);
                        setProjectDirty(true);
                      };
                      return screensaverWidget ? (
                        <ScreensaverInspector widget={screensaverWidget} onChange={screensaverOnChange} />
                      ) : selectedSchema ? (
                        <Inspector widget={selectedWidget} schema={selectedSchema} onChange={updateField} assets={assets} assetError={assetError} />
                      ) : (
                        <div className="muted">No schema for this widget type.</div>
                      );
                    })()}
                  </>
                )}
                {selectedWidgetIds.length > 1 && (
                  <MultiSelectProperties
                    widgetIds={selectedWidgetIds}
                    widgets={widgets}
                    project={project}
                    setProject={setProject}
                    setProjectDirty={setProjectDirty}
                    safePageIndex={safePageIndex}
                    clone={clone}
                    assets={assets}
                  />
                )}
              </div>
            )}
            {inspectorTab === "bindings" && (
              <div className="section">
                <div className="sectionTitle">Home Assistant Bindings</div>
                <div className="muted">Generates ESPHome homeassistant sensors.</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                  <select value={(window as any).__bindDomain || ""} onChange={(e)=>{ (window as any).__bindDomain = e.target.value; setProject(JSON.parse(JSON.stringify(project || {}))); }}>
                    <option value="">(domain)</option>
                    {DOMAIN_PRESETS.map((d)=> <option key={d.domain} value={d.domain}>{d.title}</option>)}
                  </select>
                  <input placeholder="entity_id (e.g. light.kitchen)" value={(window as any).__bindEntity || ""} onChange={(e)=>{ (window as any).__bindEntity = e.target.value; setProject(JSON.parse(JSON.stringify(project || {}))); }} />
                  <button onClick={() => {
                    if (!project) return;
                    const domain = (window as any).__bindDomain || "";
                    const entity_id = (window as any).__bindEntity || "";
                    const preset = DOMAIN_PRESETS.find((x)=>x.domain===domain);
                    if (!preset || !entity_id) return;
                    const p2 = JSON.parse(JSON.stringify(project));
                    (p2 as any).bindings = (p2 as any).bindings || [];
                    for (const b of preset.recommended) { (p2 as any).bindings.push({ ...b, entity_id }); }
                    setProject(p2);
                  }}>Add recommended</button>
                <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>Recommended: adds common bindings for the selected domain (e.g. state, brightness for light).</div>
                </div>
                {(() => {
                  const bindings = (project as any)?.bindings || [];
                  const links = (project as any)?.links || [];
                  const actionBindings = (project as any)?.action_bindings || [];
                  return (
                    <>
                <div
                  className="muted"
                  style={{ marginTop: 8 }}
                  title="Entities = project.bindings[] (YAML import homeassistant sensors, or Add recommended). Links = display sources (HA entity, device switch/climate, or interval). Actions = Binding Builder."
                >
                  Entities: {haBindingCounts.entities} • Links: {haBindingCounts.links} • Actions: {haBindingCounts.actions}
                </div>
                {(() => {
                  const haBindingsExpanded = bindingsListExpanded["ha-entity-bindings"] ?? false;
                  return (
                    <div style={{ marginTop: 10, border: "1px solid var(--divider-color, rgba(0,0,0,0.12))", borderRadius: 6, overflow: "hidden" }}>
                      <button
                        type="button"
                        onClick={() => setBindingsListExpanded((prev) => ({ ...prev, ["ha-entity-bindings"]: !prev["ha-entity-bindings"] }))}
                        style={{
                          width: "100%",
                          padding: "8px 10px",
                          textAlign: "left",
                          background: "rgba(255,255,255,.04)",
                          border: "none",
                          cursor: "pointer",
                          fontSize: 12,
                          fontWeight: 600,
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                        }}
                      >
                        <span>HA entity bindings (compile → homeassistant)</span>
                        <span className="muted" style={{ fontSize: 11 }}>{bindings.length} row{bindings.length !== 1 ? "s" : ""}</span>
                        <span style={{ transform: haBindingsExpanded ? "rotate(180deg)" : "none" }}>▼</span>
                      </button>
                      {haBindingsExpanded && (
                        <div style={{ padding: "8px 10px 10px", fontSize: 12, maxHeight: 220, overflowY: "auto" }}>
                          {bindings.length === 0 ? (
                            <div className="muted">None yet. YAML import with <code>sensor:</code> / <code>text_sensor:</code> <code>platform: homeassistant</code> fills this; or use Add recommended above.</div>
                          ) : (
                            <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.65, listStyle: "disc" }}>
                              {bindings.map((b: any, i: number) => {
                                const eid = String(b?.entity_id || "").trim();
                                const kind = String(b?.kind || "").trim();
                                const attr = String(b?.attribute || "").trim();
                                return (
                                  <li key={`hb-${i}`}>
                                    <code title={eid}>{eid || "(missing entity_id)"}</code>
                                    <span className="muted" style={{ fontSize: 11 }}>
                                      {" "}
                                      · {kind || "?"}
                                      {attr ? ` [${attr}]` : ""}
                                    </span>
                                  </li>
                                );
                              })}
                            </ul>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })()}
                {(() => {
                  const widgetType = (wid: string) => widgets.find((w: any) => w?.id === wid)?.type || "container";
                  const byTypeLinks: Record<string, { index: number; ln: any }[]> = {};
                  const byTypeActions: Record<string, { index: number; ab: any }[]> = {};
                  links.forEach((ln: any, idx: number) => {
                    const wid = String(ln?.target?.widget_id || "").trim();
                    const type = widgetType(wid) || "other";
                    if (!byTypeLinks[type]) byTypeLinks[type] = [];
                    byTypeLinks[type].push({ index: idx, ln });
                  });
                  actionBindings.forEach((ab: any, idx: number) => {
                    const type = widgetType(String(ab?.widget_id || "")) || "other";
                    if (!byTypeActions[type]) byTypeActions[type] = [];
                    byTypeActions[type].push({ index: idx, ab });
                  });
                  const typeOrder = ["label", "button", "arc", "slider", "dropdown", "switch", "checkbox", "container", "other"];
                  const sortTypes = (keys: string[]) => keys.sort((a, b) => {
                    const ia = typeOrder.indexOf(a);
                    const ib = typeOrder.indexOf(b);
                    if (ia >= 0 && ib >= 0) return ia - ib;
                    if (ia >= 0) return -1;
                    if (ib >= 0) return 1;
                    return a.localeCompare(b);
                  });
                  const linkTypes = sortTypes(Object.keys(byTypeLinks));
                  const actionTypes = sortTypes(Object.keys(byTypeActions));
                  if (linkTypes.length === 0 && actionTypes.length === 0) return <div className="muted" style={{ marginTop: 12, fontSize: 12 }}>No display or action bindings yet.</div>;
                  return (
                    <div style={{ marginTop: 12, maxHeight: 400, overflowY: "auto", overflowX: "hidden" }}>
                      <div className="sectionTitle" style={{ fontSize: 13 }}>Display bindings (links)</div>
                      {linkTypes.length === 0 ? <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>None. Add via Binding Builder → Display.</div> : linkTypes.map((type) => {
                        const group = byTypeLinks[type];
                        const expanded = bindingsListExpanded[`links:${type}`] ?? false;
                        return (
                          <div key={`l-${type}`} style={{ marginBottom: 6, border: "1px solid var(--divider-color, rgba(0,0,0,0.12))", borderRadius: 6, overflow: "hidden" }}>
                            <button type="button" onClick={() => setBindingsListExpanded((prev) => ({ ...prev, [`links:${type}`]: !prev[`links:${type}`] }))} style={{ width: "100%", padding: "8px 10px", textAlign: "left", background: "rgba(255,255,255,.04)", border: "none", cursor: "pointer", fontSize: 12, fontWeight: 600, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <span>{type}</span>
                              <span className="muted" style={{ fontSize: 11 }}>{group.length} link{group.length !== 1 ? "s" : ""}</span>
                              <span style={{ transform: expanded ? "rotate(180deg)" : "none" }}>▼</span>
                            </button>
                            {expanded && (
                              <ul style={{ margin: 0, padding: "6px 10px 10px 22px", fontSize: 12, lineHeight: 1.6, listStyle: "disc" }}>
                                {group.map(({ index, ln }) => {
                                  const tgt = ln?.target || {}; const wid = String(tgt?.widget_id || "").trim();
                                  const isSelected = selectedWidgetIds.includes(wid); const hasOverride = !!tgt?.yaml_override;
                                  const summary = formatDisplayBindingSummary(ln, entities);
                                  const srcRef = formatLinkSourceRef(ln);
                                  return (
                                    <li key={`l-${index}`} style={isSelected ? { fontWeight: 600 } : {}}>
                                      {hasOverride && <span title="Custom YAML">✎ </span>}
                                      <span title={summary}>{summary}</span>
                                      <span className="muted" style={{ fontSize: 11 }}> — <code>{wid || "(no widget)"}</code> ← <code>{srcRef}</code></span>
                                      {tgt?.import_orphan_widget ? (
                                        <span className="muted" style={{ fontSize: 10, marginLeft: 6 }} title="Widget id not found on canvas after import; fix ids or LVGL tree, then re-import.">
                                          (orphan)
                                        </span>
                                      ) : null}
                                    </li>
                                  );
                                })}
                              </ul>
                            )}
                          </div>
                        );
                      })}
                      <div className="sectionTitle" style={{ fontSize: 13, marginTop: 14 }}>Action bindings</div>
                      {actionTypes.length === 0 ? <div className="muted" style={{ fontSize: 12 }}>None. Add via Binding Builder → Action.</div> : actionTypes.map((type) => {
                        const group = byTypeActions[type];
                        const expanded = bindingsListExpanded[`actions:${type}`] ?? false;
                        return (
                          <div key={`a-${type}`} style={{ marginBottom: 6, border: "1px solid var(--divider-color, rgba(0,0,0,0.12))", borderRadius: 6, overflow: "hidden" }}>
                            <button type="button" onClick={() => setBindingsListExpanded((prev) => ({ ...prev, [`actions:${type}`]: !prev[`actions:${type}`] }))} style={{ width: "100%", padding: "8px 10px", textAlign: "left", background: "rgba(255,255,255,.04)", border: "none", cursor: "pointer", fontSize: 12, fontWeight: 600, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <span>{type}</span>
                              <span className="muted" style={{ fontSize: 11 }}>{group.length} action{group.length !== 1 ? "s" : ""}</span>
                              <span style={{ transform: expanded ? "rotate(180deg)" : "none" }}>▼</span>
                            </button>
                            {expanded && (
                              <ul style={{ margin: 0, padding: "6px 10px 10px 22px", fontSize: 12, lineHeight: 1.6, listStyle: "disc" }}>
                                {group.map(({ index, ab }) => {
                                  const wid = String(ab?.widget_id || "").trim(); const call = ab?.call || {};
                                  const isSelected = selectedWidgetIds.includes(wid); const hasOverride = !!ab?.yaml_override;
                                  const summary = formatActionBindingSummary(ab, entities);
                                  return (
                                    <li key={`a-${index}`} style={isSelected ? { fontWeight: 600 } : {}}>
                                      {hasOverride && <span title="Custom YAML">✎ </span>}
                                      <span>{summary}</span>
                                      <span className="muted" style={{ fontSize: 11 }}> — <code>{wid}</code></span>
                                    </li>
                                  );
                                })}
                              </ul>
                            )}
                          </div>
                        );
                      })}
                      {selectedWidgetIds.length > 0 && (
                        <div className="muted" style={{ marginTop: 6, fontSize: 11 }}>Selected widget(s) highlighted. ✎ = custom YAML.</div>
                      )}
                    </div>
                  );
                })()}
                    </>
                  );
                })()}
              </div>
            )}
            {inspectorTab === "builder" && (() => {
              const hasCreateComponent = selectedWidgetIds.length === 1 && project && widgetHasCreateComponent(project, selectedWidgetIds[0]);
              return (
              <div className="section">
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                  <div className="sectionTitle" style={{ marginBottom: 0 }}>Binding Builder</div>
                  {hasCreateComponent ? (
                    <span className="muted" style={{ fontSize: 12 }} title="This widget already has an ESPHome component (switch/light/sensor etc.); no display/action bindings needed — linkage is automatic in ESPHome.">
                      Component created
                    </span>
                  ) : null}
                  <button
                    type="button"
                    className="secondary"
                    style={{ fontSize: 12, padding: "6px 10px" }}
                    disabled={
                      selectedWidgetIds.length !== 1
                      || !project
                      || hasCreateComponent
                      || !canCreateNativeComponentForWidget((() => {
                        const wid = selectedWidgetIds[0];
                        const w = widgetsFlat.find((x: any) => x?.id === wid) ?? widgets.find((x: any) => x?.id === wid);
                        return w?.type || "";
                      })())
                    }
                    title={hasCreateComponent ? "This widget already has a component." : "Create ESPHome component (switch, light, sensor, etc.) bound to this widget — bidirectional with HA"}
                    onClick={() => {
                      if (selectedWidgetIds.length !== 1 || !project) return;
                      const wid = selectedWidgetIds[0];
                      const w = widgetsFlat.find((x: any) => x?.id === wid) ?? widgets.find((x: any) => x?.id === wid);
                      const wtype = w?.type || "";
                      const mapping = getLvglComponentsForWidget(wtype);
                      if (!mapping) return;
                      setCreateNativeComponentType(mapping.default);
                      setCreateNativeComponentTypeFilter(LVGL_COMPONENT_TYPES[mapping.default]?.label ?? mapping.default);
                      setCreateNativeComponentId(String(w?.id ?? ""));
                      setCreateNativeComponentName(String(w?.id ?? "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) || "Component");
                      setCreateNativeComponentDropdownOpen(false);
                      setCreateNativeComponentOpen(true);
                    }}
                  >
                    Create component…
                  </button>
                </div>
                <div className="muted">Bind selected widget to HA entity (display or action).</div>
                {selectedWidgetIds.length !== 1 ? (
                  <div className="muted" style={{ marginTop: 10, fontSize: 12 }}>Select a single widget on the canvas to see its bindings and add new ones.</div>
                ) : (() => {
                  const widgetId = selectedWidgetIds[0];
                  const selWidget = widgetsFlat.find((w: any) => w?.id === widgetId) ?? widgets.find((w: any) => w?.id === widgetId);
                  const widgetType = selWidget?.type || "container";
                  const spinboxChildId = (widgetType === "container" && project) ? getSpinboxChildId(project, widgetId) : null;
                  const allProjectLinks = ((project as any)?.links || []) as any[];
                  const linkRowsForWidget = displayLinkRowsForWidget(allProjectLinks, widgetId);
                  const actionsForWidget = ((project as any)?.action_bindings || []).filter(
                    (ab: any) => {
                      const abWid = String(ab?.widget_id || "").trim();
                      return abWid === widgetId || (spinboxChildId != null && abWid === spinboxChildId);
                    }
                  );
                  const actionBindingMatches = (a: any, evt: string) =>
                    (String(a?.widget_id) === widgetId || (spinboxChildId != null && String(a?.widget_id) === spinboxChildId)) && a?.event === evt;
                  const displayActions = getDisplayActionsForType(widgetType);
                  const eventOptions = spinboxChildId ? getEventsForType("spinbox") : getEventsForType(widgetType);
                  const bindDomain = domainFromEntityId(bindEntity || actionEntity || "");
                  const serviceOptions = getServicesForDomain(bindDomain);
                  const filteredEntities = entities.filter(
                    (e) => e?.entity_id && entityMatchesBindingSearch(e, entityQuery)
                  ).slice(0, 200);
                  const effectiveDisplayAction = displayActions.includes(bindAction as any) ? bindAction : (displayActions[0] || "label_text");
                  const requiresNumeric = displayActionRequiresNumericSource(effectiveDisplayAction);
                  const numericEntityAllowsState =
                    requiresNumeric && ["number", "input_number"].includes(bindDomain);
                  const selectedEntityAttrs = (() => {
                      if (!bindEntity) return [];
                      const attrs = bindingEntityDetails?.entity_id === bindEntity
                        ? bindingEntityDetails?.attributes
                        : entities.find((x) => x && x.entity_id === bindEntity)?.attributes;
                      if (!attrs) return [];
                      const keys = Object.keys(attrs).sort();
                      if (!requiresNumeric) return keys;
                      const valueNumeric = keys.filter((k) => {
                        const v = attrs[k];
                        if (typeof v === "number" && !Number.isNaN(v)) return true;
                        if (typeof v === "string" && v.trim() !== "" && !Number.isNaN(Number(v))) return true;
                        return false;
                      });
                      const domain = domainFromEntityId(bindEntity);
                      const preset = DOMAIN_PRESETS.find((p) => p.domain === domain);
                      const knownNumeric = (preset?.recommended ?? [])
                        .filter((r) => r.kind === "attribute_number" && r.attribute && attrs.hasOwnProperty(r.attribute))
                        .map((r) => r.attribute as string);
                      return [...new Set([...valueNumeric, ...knownNumeric])].sort();
                    })();
                  return (
                    <>
                      <div className="panelTabs" style={{ marginTop: 10, padding: "8px 8px 0", borderBottom: "1px solid var(--border)", background: "rgba(0,0,0,.2)" }}>
                        <button type="button" className={`panelTab ${builderMode === "display" ? "active" : ""}`} style={{ padding: "8px 12px", fontSize: 13 }} onClick={() => setBuilderMode("display")}>Display</button>
                        <button type="button" className={`panelTab ${builderMode === "action" ? "active" : ""}`} style={{ padding: "8px 12px", fontSize: 13 }} onClick={() => setBuilderMode("action")}>Action</button>
                      </div>
                      <div style={{ marginTop: 10, marginBottom: 10, padding: 8, borderRadius: 4, border: "1px solid var(--divider-color, rgba(0,0,0,0.12))" }}>
                        <div className="sectionTitle" style={{ fontSize: 12, marginBottom: 4 }}>{builderMode === "display" ? "Display bindings for this widget" : "Action bindings for this widget"}</div>
                        {builderMode === "display" ? (
                          <div className="muted" style={{ fontSize: 11, marginBottom: 8 }}>This widget will show a value from Home Assistant (entity or attribute) in this widget.</div>
                        ) : (
                          <div className="muted" style={{ fontSize: 11, marginBottom: 8 }}>When the user does an action (e.g. tap, release), call a Home Assistant service.</div>
                        )}
                        {builderMode === "display" ? (linkRowsForWidget.length === 0 ? (
                          <div className="muted" style={{ fontSize: 12 }}>No display bindings. Use the form below to add one.</div>
                        ) : (
                          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, lineHeight: 1.6 }}>
                            {linkRowsForWidget.map((row, idx: number) => {
                              const ln = row.link as any;
                              const globalIndex = row.globalIndex;
                              const intervalUpdateIndex = row.intervalUpdateIndex;
                              const tgt = ln?.target || {};
                              const src = ln?.source || {};
                              const upd =
                                intervalUpdateIndex != null && Array.isArray(src?.updates)
                                  ? src.updates[intervalUpdateIndex]
                                  : null;
                              const yamlFromTarget = String(tgt?.yaml_override || "").trim();
                              const yamlFromUpdate = upd && typeof upd === "object" ? String((upd as any).yaml_override || "").trim() : "";
                              const hasOverride = !!(yamlFromTarget || yamlFromUpdate);
                              const actionRaw = String((upd as any)?.action || tgt?.action || "").trim();
                              const actionHuman = actionRaw ? (DISPLAY_ACTION_LABELS[actionRaw as keyof typeof DISPLAY_ACTION_LABELS] || actionRaw) : "";
                              const summary = formatDisplayBindingSummary(ln, entities);
                              const srcRef = formatLinkSourceRef(ln);
                              const isEditing =
                                editingLinkOverride?.forWidgetId === widgetId
                                && editingLinkOverride.linkIndex === globalIndex
                                && (editingLinkOverride.intervalUpdateIndex ?? -1) === (intervalUpdateIndex ?? -1);
                              const rowKey = `dl-${globalIndex}-${intervalUpdateIndex ?? "t"}`;
                              return (
                                <li key={rowKey}>
                                  {hasOverride && <span title="Custom YAML">✎ </span>}
                                  <span title={summary}>{summary}</span>
                                  <span className="muted" style={{ fontSize: 11 }}>
                                    {" "}
                                    — <code>{srcRef}</code>
                                    {actionHuman ? ` → ${actionHuman}` : ""}
                                    {intervalUpdateIndex != null ? (
                                      <span title="Part of an interval: block; delete removes the whole interval for all widgets."> (interval)</span>
                                    ) : null}
                                  </span>
                                  <button
                                    type="button"
                                    className="secondary"
                                    style={{ marginLeft: 6, fontSize: 10 }}
                                    onClick={() => {
                                      if (isEditing) {
                                        setEditingLinkOverride(null);
                                        setEditingOverrideYaml("");
                                        return;
                                      }
                                      const yaml =
                                        intervalUpdateIndex != null && upd && typeof upd === "object"
                                          ? String((upd as any).yaml_override || "")
                                          : String(tgt?.yaml_override || "");
                                      setEditingLinkOverride({ linkIndex: globalIndex, forWidgetId: widgetId, intervalUpdateIndex });
                                      setEditingOverrideYaml(yaml);
                                    }}
                                  >
                                    {isEditing ? "Cancel" : "Edit YAML"}
                                  </button>
                                  <button
                                    type="button"
                                    className="danger"
                                    style={{ marginLeft: 4, fontSize: 10 }}
                                    onClick={() => {
                                      if (!project) return;
                                      const p2 = clone(project);
                                      const links2 = (p2 as any).links || [];
                                      if (globalIndex >= 0 && globalIndex < links2.length) {
                                        links2.splice(globalIndex, 1);
                                        (p2 as any).links = links2;
                                        setProject(p2, true);
                                        setProjectDirty(true);
                                        setEditingLinkOverride(null);
                                      }
                                    }}
                                    title="Delete this display link (entire interval block if marked interval)"
                                  >
                                    Delete
                                  </button>
                                </li>
                              );
                            })}
                          </ul>
                        )) : (actionsForWidget.length === 0 ? (
                          <div className="muted" style={{ fontSize: 12 }}>No action bindings. Use the form below to add one.</div>
                        ) : (
                          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, lineHeight: 1.6 }}>
                            {actionsForWidget.map((ab: any, idx: number) => {
                              const call = ab?.call || {};
                              const hasOverride = !!ab?.yaml_override;
                              const ev = String(ab?.event || "");
                              const currentEnt = String(call?.entity_id || "").trim();
                              const pending = actionEntityChangePending?.widgetId === widgetId && actionEntityChangePending?.event === ev ? actionEntityChangePending : null;
                              return (
                                <li key={`a-${idx}`}>
                                  {hasOverride && <span title="Custom YAML">✎ </span>}
                                  <span className="muted">{ab?.event}</span> → <code>{call?.domain}.{call?.service}</code> ({currentEnt || "—"})
                                  <button type="button" className="secondary" style={{ marginLeft: 6, fontSize: 10 }} onClick={() => setInspectorTab("yaml")} title="Edit event YAML in Widget YAML tab">Edit YAML</button>
                                  <select
                                    value={pending ? pending.newEntityId : currentEnt}
                                    onChange={(e) => {
                                      const newId = e.target.value;
                                      if (newId === currentEnt) return;
                                      if (hasOverride) {
                                        setActionEntityChangePending({ widgetId, event: ev, newEntityId: newId });
                                      } else {
                                        if (!project) return;
                                        const p2 = clone(project);
                                        const abs = (p2 as any).action_bindings || [];
                                        const ab = abs.find((a: any) => actionBindingMatches(a, ev));
                                        if (ab?.call) {
                                          ab.call = { ...ab.call, entity_id: newId, data: { ...(ab.call.data || {}), entity_id: newId } };
                                          setProject(p2, true);
                                          setProjectDirty(true);
                                        }
                                      }
                                    }}
                                    style={{ marginLeft: 6, fontSize: 10, maxWidth: 140 }}
                                  >
                                    <option value={currentEnt}>{currentEnt || "(entity)"}</option>
                                    {entities.filter((e) => e?.entity_id && e.entity_id !== currentEnt).slice(0, 100).map((e) => (
                                      <option key={e.entity_id} value={e.entity_id}>{e.entity_id}</option>
                                    ))}
                                  </select>
                                  <button type="button" className="danger" style={{ marginLeft: 4, fontSize: 10 }} onClick={() => { if (!project) return; const p2 = clone(project); const abs = (p2 as any).action_bindings || []; const aIdx = abs.findIndex((a: any) => actionBindingMatches(a, ev)); if (aIdx >= 0) { abs.splice(aIdx, 1); (p2 as any).action_bindings = abs; setProject(p2, true); setProjectDirty(true); setActionEntityChangePending((p) => p?.widgetId === widgetId && p?.event === ev ? null : p); } }} title="Delete this binding">Delete</button>
                                </li>
                              );
                            })}
                          </ul>
                        ))}
                        {actionEntityChangePending && (() => {
                          const p = actionEntityChangePending;
                          const abs = (project as any)?.action_bindings || [];
                          const pendingMatch = (a: any, evt: string) =>
                            (String(a?.widget_id) === widgetId || (spinboxChildId != null && String(a?.widget_id) === spinboxChildId)) && a?.event === evt;
                          const ab = abs.find((a: any) => pendingMatch(a, p.event));
                          if (!ab) { setActionEntityChangePending(null); return null; }
                          return (
                            <div style={{ marginTop: 8, padding: 10, background: "rgba(255,200,100,0.1)", borderRadius: 6, border: "1px solid rgba(255,180,80,0.4)" }}>
                              <div style={{ fontSize: 12, marginBottom: 6 }}>This binding has custom YAML. After changing entity to <code>{p.newEntityId}</code>:</div>
                              <div style={{ display: "flex", gap: 8 }}>
                                <button type="button" className="primary" style={{ fontSize: 11 }} onClick={() => {
                                  if (!project) return;
                                  const p2 = clone(project);
                                  const abs2 = (p2 as any).action_bindings || [];
                                  const ab2 = abs2.find((a: any) => pendingMatch(a, p.event));
                                  if (ab2?.call) {
                                    ab2.call = { ...ab2.call, entity_id: p.newEntityId, data: { ...(ab2.call.data || {}), entity_id: p.newEntityId } };
                                    setProject(p2, true);
                                    setProjectDirty(true);
                                  }
                                  setActionEntityChangePending(null);
                                }}>Keep current YAML</button>
                                <button type="button" className="secondary" style={{ fontSize: 11 }} onClick={() => {
                                  if (!project) return;
                                  const p2 = clone(project);
                                  const abs2 = (p2 as any).action_bindings || [];
                                  const ab2 = abs2.find((a: any) => pendingMatch(a, p.event));
                                  if (ab2?.call) {
                                    ab2.call = { ...ab2.call, entity_id: p.newEntityId, data: { ...(ab2.call.data || {}), entity_id: p.newEntityId } };
                                    if (ab2.yaml_override !== undefined) delete ab2.yaml_override;
                                    setProject(p2, true);
                                    setProjectDirty(true);
                                  }
                                  setActionEntityChangePending(null);
                                }}>Reset to auto-generated</button>
                                <button type="button" className="ghost" style={{ fontSize: 11 }} onClick={() => setActionEntityChangePending(null)}>Cancel</button>
                              </div>
                            </div>
                          );
                        })()}
                        {editingLinkOverride?.forWidgetId === widgetId && (
                          <div style={{ marginTop: 8, padding: 8, background: "rgba(255,255,255,.04)", borderRadius: 4 }}>
                            <div className="muted" style={{ fontSize: 10, marginBottom: 4 }}>Custom YAML for this display binding (used by compiler instead of generated).</div>
                            <YamlEditor value={editingOverrideYaml} onChange={setEditingOverrideYaml} minHeight={100} maxHeight={200} placeholder="e.g. - lvgl.label.update:&#10;    id: my_id&#10;    text: !lambda return x;" />
                            <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                              <button type="button" onClick={() => {
                                if (!project || !editingLinkOverride) return;
                                const p2 = clone(project);
                                const links = (p2 as any).links || [];
                                const ln = links[editingLinkOverride.linkIndex] as any;
                                if (!ln) {
                                  setEditingLinkOverride(null);
                                  setEditingOverrideYaml("");
                                  return;
                                }
                                const trimmed = editingOverrideYaml.trim() || undefined;
                                const iu = editingLinkOverride.intervalUpdateIndex;
                                if (iu != null && ln?.source?.type === "interval" && Array.isArray(ln.source.updates) && ln.source.updates[iu]) {
                                  ln.source.updates[iu] = { ...ln.source.updates[iu], yaml_override: trimmed };
                                } else if (ln.target && typeof ln.target === "object") {
                                  ln.target = { ...ln.target, yaml_override: trimmed };
                                }
                                setProject(p2, true);
                                setProjectDirty(true);
                                setEditingLinkOverride(null);
                                setEditingOverrideYaml("");
                              }}>Save</button>
                              <button type="button" className="secondary" onClick={() => { setEditingLinkOverride(null); setEditingOverrideYaml(""); }}>Cancel</button>
                            </div>
                          </div>
                        )}
                      </div>
                      {builderMode === "display" && (
                        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
                          <div>
                            <div className="fieldLabel" style={{ fontSize: 11, marginBottom: 2 }}>Entity</div>
                            <div className="muted" style={{ fontSize: 10, marginBottom: 4 }}>Type any word to match entity id or name (e.g. shed). Pick from list.</div>
                            <input
                              placeholder="Search entities..."
                              value={entityQuery}
                              onChange={(e) => { setEntityQuery(e.target.value); setBuilderEntityDropdownOpen(true); }}
                              onFocus={() => setBuilderEntityDropdownOpen(true)}
                              onBlur={() => setTimeout(() => setBuilderEntityDropdownOpen(false), 180)}
                              style={{ width: "100%", boxSizing: "border-box" }}
                            />
                            {builderEntityDropdownOpen && (
                              <div style={{ maxHeight: 180, overflowY: "auto", border: "1px solid var(--divider-color)", borderRadius: 4, marginTop: 2, background: "var(--panel-bg, #1e293b)" }}>
                                {filteredEntities.map((e) => (
                                  <div
                                    key={e.entity_id}
                                    onMouseDown={(ev) => { ev.preventDefault(); setBindEntity(e.entity_id); setEntityQuery(""); setBindAttr(""); setBuilderEntityDropdownOpen(false); }}
                                    style={{ padding: "6px 10px", cursor: "pointer", fontSize: 12, borderBottom: "1px solid rgba(255,255,255,.06)" }}
                                  >
                                    {e.entity_id}{e.friendly_name ? ` — ${e.friendly_name}` : ""}
                                  </div>
                                ))}
                                {filteredEntities.length === 0 && <div className="muted" style={{ padding: 8, fontSize: 12 }}>No matching entities.</div>}
                              </div>
                            )}
                            {bindEntity && <div className="muted" style={{ marginTop: 4, fontSize: 11 }}>Selected: {bindEntity}</div>}
                          </div>
                          <div>
                            <div className="fieldLabel" style={{ fontSize: 11, marginBottom: 2 }}>Attribute</div>
                            <div className="muted" style={{ fontSize: 10, marginBottom: 4 }}>{requiresNumeric ? "Numeric only: pick an attribute, or (state) for number / input_number entities." : "HA state or entity attribute to show."}</div>
                            <select
                              value={
                                bindAttr !== ""
                                  ? bindAttr
                                  : requiresNumeric && !numericEntityAllowsState && selectedEntityAttrs.length > 0
                                    ? selectedEntityAttrs[0]
                                    : ""
                              }
                              onChange={(e) => setBindAttr(e.target.value)}
                              style={{ width: "100%" }}
                            >
                              {(!requiresNumeric || numericEntityAllowsState) && <option value="">(state)</option>}
                              {selectedEntityAttrs.map((k)=> <option key={k} value={k}>{k}</option>)}
                            </select>
                          </div>
                          <div>
                            <div className="fieldLabel" style={{ fontSize: 11, marginBottom: 2 }}>Update widget</div>
                            <div className="muted" style={{ fontSize: 10, marginBottom: 4 }}>Which property of this {widgetType} gets the value.</div>
                            <select value={displayActions.includes(bindAction as any) ? bindAction : (displayActions[0] || "label_text")} onChange={(e)=>setBindAction(e.target.value)} style={{ width: "100%" }}>
                              {displayActions.map((act) => (
                                <option key={act} value={act}>{DISPLAY_ACTION_LABELS[act]}</option>
                              ))}
                            </select>
                          </div>
                          {(bindAction === "label_text" || bindAction === "arc_value" || bindAction === "slider_value" || bindAction === "bar_value" || bindAction === "spinbox2_value") && (
                            <>
                              <div>
                                <div className="fieldLabel" style={{ fontSize: 11, marginBottom: 2 }}>Format</div>
                                <div className="muted" style={{ fontSize: 10, marginBottom: 4 }}>Printf-style for displayed text (e.g. %.1f or %.1f°).</div>
                                <input value={bindFormat} onChange={(e)=>setBindFormat(e.target.value)} placeholder="%.1f" style={{ width: "100%", boxSizing: "border-box" }} />
                              </div>
                              <div>
                                <div className="fieldLabel" style={{ fontSize: 11, marginBottom: 2 }}>Scale</div>
                                <div className="muted" style={{ fontSize: 10, marginBottom: 4 }}>Multiply numeric value (e.g. 100 for 0–1 → 0–100).</div>
                                <input type="number" value={bindScale} onChange={(e)=>setBindScale(Number(e.target.value || 1))} step="0.1" style={{ width: "100%", boxSizing: "border-box" }} />
                              </div>
                            </>
                          )}
                          <button disabled={!project || !selectedWidgetIds.length || !bindEntity || (requiresNumeric && !numericEntityAllowsState && !bindAttr && selectedEntityAttrs.length === 0)} onClick={() => {
                            if (!project) return;
                            const wid = selectedWidgetIds[0];
                            const ent = bindEntity;
                            const attr =
                              bindAttr.trim() !== ""
                                ? bindAttr
                                : requiresNumeric && !numericEntityAllowsState && selectedEntityAttrs.length > 0
                                  ? selectedEntityAttrs[0]
                                  : "";
                            const act = displayActions.includes(bindAction as any) ? bindAction : (displayActions[0] || "label_text");
                            const p2 = clone(project);
                            (p2 as any).bindings = (p2 as any).bindings || [];
                            (p2 as any).links = (p2 as any).links || [];
                            let kind: any = "state";
                            let linkAttr = attr;
                            if (act === "button_bg_color") {
                              kind = "attribute_text";
                              linkAttr = "rgb_color";
                            } else if (act === "button_white_temp") {
                              kind = "attribute_number";
                              linkAttr = "color_temp";
                            } else if (act === "widget_checked") kind = "binary";
                            else if (attr) kind = "attribute_number";
                            const v = entities.find((x)=>x.entity_id===ent)?.attributes?.[linkAttr || attr];
                            if ((linkAttr || attr) && (typeof v === "string" || Array.isArray(v) || (v && typeof v === "object"))) kind = "attribute_text";
                            if (!linkAttr && !attr && (act === "label_text" || act === "spinbox2_value")) kind = "state";
                            (p2 as any).bindings.push({ entity_id: ent, kind, attribute: linkAttr || attr || undefined });
                            (p2 as any).links.push({ source: { entity_id: ent, kind, attribute: linkAttr || attr || "" }, target: { widget_id: wid, action: act, format: (bindFormat != null && String(bindFormat).trim() !== "") ? String(bindFormat).trim() : "%.1f", scale: bindScale } });
                            const pageWidgets = (p2 as any).pages?.[safePageIndex]?.widgets || [];
                            const usedIds = new Set(pageWidgets.map((w: any) => w?.id).filter(Boolean));
                            const friendlyId = friendlyWidgetIdFromBinding(ent, attr || "state", usedIds);
                            const renameResult = renameWidgetInProject(p2, safePageIndex, wid, friendlyId);
                            const finalProject = renameResult.ok && renameResult.newId ? renameResult.project : p2;
                            const finalWid = renameResult.newId ?? wid;
                            if (createMatchingActions) {
                              const actionWidgetId = spinboxChildId ?? finalWid;
                              const effectiveType = spinboxChildId
                                ? "spinbox"
                                : (widgetType === "container" || !INPUT_WIDGET_TYPES.includes(widgetType as any) && !CLICK_TOGGLE_WIDGET_TYPES.includes(widgetType as any))
                                  ? (act === "arc_value" ? "arc" : act === "slider_value" ? "slider" : act === "bar_value" ? "bar" : act === "widget_checked" ? "button" : widgetType)
                                  : widgetType;
                              const actions = getMatchingActionBindings(effectiveType, ent, kind, attr || "");
                              (finalProject as any).action_bindings = (finalProject as any).action_bindings || [];
                              for (const a of actions) {
                                (finalProject as any).action_bindings.push({ widget_id: actionWidgetId, event: a.event, call: a.call });
                              }
                            }
                            if (act === "button_bg_color") {
                              (finalProject as any).action_bindings = (finalProject as any).action_bindings || [];
                              (finalProject as any).action_bindings.push({
                                widget_id: finalWid,
                                event: "on_apply",
                                call: {
                                  domain: "esptoolkit",
                                  service: "set_light_rgb",
                                  entity_id: ent,
                                  data: {},
                                },
                              });
                            }
                            if (act === "button_white_temp") {
                              (finalProject as any).action_bindings = (finalProject as any).action_bindings || [];
                              (finalProject as any).action_bindings.push({
                                widget_id: finalWid,
                                event: "on_apply",
                                call: {
                                  domain: "esptoolkit",
                                  service: "set_light_color_temp",
                                  entity_id: ent,
                                  data: {},
                                },
                              });
                            }
                            if (renameResult.ok && renameResult.newId) {
                              setProject(finalProject, true);
                              setSelectedWidgetIds([renameResult.newId]);
                            } else {
                              setProject(finalProject, true);
                            }
                            setProjectDirty(true);
                          }}>Add display binding</button>
                          {((INPUT_WIDGET_TYPES.includes(widgetType as any) || OPTION_SELECT_WIDGET_TYPES.includes(widgetType as any) || CLICK_TOGGLE_WIDGET_TYPES.includes(widgetType as any)) ||
                            spinboxChildId ||
                            ["arc_value", "slider_value", "bar_value", "spinbox2_value", "widget_checked"].includes(bindAction)) && (
                            <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, cursor: "pointer", fontSize: 12, color: "#b8bfc9" }}>
                              <input type="checkbox" checked={createMatchingActions} onChange={(e)=>setCreateMatchingActions(e.target.checked)} />
                              Also create action bindings to send value to HA
                            </label>
                          )}
                        </div>
                      )}
                      {builderMode === "action" && (
                        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
                          {eventOptions.length === 0 ? (
                            <div className="muted" style={{ fontSize: 12 }}>This widget type ({widgetType}) has no events for action bindings.</div>
                          ) : (
                            <>
                              <div>
                                <div className="fieldLabel" style={{ fontSize: 11, marginBottom: 2 }}>Event</div>
                                <div className="muted" style={{ fontSize: 10, marginBottom: 4 }}>When the user does this on the device.</div>
                                <select value={eventOptions.includes(actionEvent) ? actionEvent : eventOptions[0]} onChange={(e)=>setActionEvent(e.target.value)} style={{ width: "100%" }}>
                                  {eventOptions.map((ev) => (
                                    <option key={ev} value={ev}>{EVENT_LABELS[ev] || ev}</option>
                                  ))}
                                </select>
                              </div>
                              <div style={{ position: "relative" }}>
                                <div className="fieldLabel" style={{ fontSize: 11, marginBottom: 2 }}>Entity</div>
                                <div className="muted" style={{ fontSize: 10, marginBottom: 4 }}>Type to search; pick from list.</div>
                                <input
                                  placeholder="e.g. switch.living_room"
                                  value={actionEntity}
                                  onChange={(e) => { setActionEntity(e.target.value); setActionEntityDropdownOpen(true); }}
                                  onFocus={() => setActionEntityDropdownOpen(true)}
                                  onBlur={() => setTimeout(() => setActionEntityDropdownOpen(false), 180)}
                                  style={{ width: "100%", boxSizing: "border-box" }}
                                />
                                {actionEntityDropdownOpen && (
                                  <div style={{ maxHeight: 180, overflowY: "auto", border: "1px solid var(--divider-color)", borderRadius: 4, marginTop: 2, background: "var(--panel-bg, #1e293b)" }}>
                                    {entities
                                      .filter((e) => e?.entity_id && entityMatchesBindingSearch(e, actionEntity))
                                      .slice(0, 200)
                                      .map((e) => (
                                        <div
                                          key={e.entity_id}
                                          onClick={() => { setActionEntity(e.entity_id); setActionEntityDropdownOpen(false); }}
                                          style={{ padding: "6px 10px", cursor: "pointer", fontSize: 12, borderBottom: "1px solid rgba(255,255,255,.06)" }}
                                        >
                                          {e.entity_id}{e.friendly_name ? ` — ${e.friendly_name}` : ""}
                                        </div>
                                      ))}
                                    {entities.filter((e) => !e?.entity_id ? false : !actionEntity.trim() ? true : (String(e.entity_id).toLowerCase().includes(actionEntity.trim().toLowerCase()) || String(e?.friendly_name || "").toLowerCase().includes(actionEntity.trim().toLowerCase()))).length === 0 && <div className="muted" style={{ padding: 8, fontSize: 12 }}>No matching entities.</div>}
                                  </div>
                                )}
                                {linkRowsForWidget.length > 0 && (
                                  <button
                                    type="button"
                                    className="secondary"
                                    style={{ marginTop: 4, fontSize: 11 }}
                                    onClick={() => {
                                      const firstHa = linkRowsForWidget.map((r) => r.link as any).find((l) => String(l?.source?.entity_id || "").trim());
                                      setActionEntity(String(firstHa?.source?.entity_id || ""));
                                    }}
                                  >
                                    Use same as display binding
                                  </button>
                                )}
                              </div>
                              <div>
                                <div className="fieldLabel" style={{ fontSize: 11, marginBottom: 2 }}>Service</div>
                                <div className="muted" style={{ fontSize: 10, marginBottom: 4 }}>Only services relevant to the entity domain are shown.</div>
                                <select value={actionService} onChange={(e)=>setActionService(e.target.value)} style={{ width: "100%" }}>
                                  <option value="">(select service)</option>
                                  {serviceOptions.map((opt) => (
                                    <option key={opt.service} value={opt.service}>{opt.label} ({opt.service})</option>
                                  ))}
                                </select>
                              </div>
                              <button disabled={!project || !selectedWidgetIds.length || !actionService || !actionEntity} onClick={() => {
                                if (!project) return;
                                const wid = selectedWidgetIds[0];
                                const actionWid = spinboxChildId ?? wid;
                                const [domain, service] = actionService.split(".");
                                if (!domain || !service) return;
                                const p2 = clone(project);
                                (p2 as any).action_bindings = (p2 as any).action_bindings || [];
                                const ent = String(actionEntity || "").trim();
                                (p2 as any).action_bindings.push({
                                  widget_id: actionWid,
                                  event: eventOptions.includes(actionEvent) ? actionEvent : eventOptions[0],
                                  call: {
                                    domain,
                                    service,
                                    entity_id: ent,
                                    data: { entity_id: ent },
                                  },
                                });
                                setProject(p2, true);
                                setProjectDirty(true);
                              }}>Add action binding</button>
                            </>
                          )}
                        </div>
                      )}
                    </>
                  );
                })()}
              </div>
            ); })()}
            {inspectorTab === "yaml" && (
              <div className="section">
                <div className="sectionTitle">Widget YAML</div>
                {selectedWidgetIds.length !== 1 ? (
                  <div className="muted" style={{ marginTop: 10, fontSize: 12 }}>Select a single widget to view and edit its YAML.</div>
                ) : (() => {
                  const widgetId = selectedWidgetIds[0];
                  const selWidget = widgetsFlat.find((w: any) => w?.id === widgetId) ?? widgets.find((w: any) => w?.id === widgetId);
                  if (!selWidget) return <div className="muted">Widget not found.</div>;
                  const widgetType = selWidget?.type || "container";
                  const customEvents = (selWidget as any).custom_events || {};
                  const eventOptions = ["on_click", "on_press", "on_release", "on_value", "on_change", "on_focus", "on_defocus"];
                  return (
                    <>
                      <div style={{ marginTop: 10 }}>
                        <div className="muted" style={{ fontSize: 11, marginBottom: 8 }}><span style={{ color: "rgba(255,255,255,0.6)" }}>Auto</span> = generated at compile; <span style={{ color: "rgba(100,180,255,0.95)" }}>Edited</span> = stored in project. One box per event; edit and Save to store.</div>
                        <div className="fieldLabel" style={{ fontSize: 11, marginBottom: 4 }}>Full widget preview</div>
                        {widgetYamlPreviewLoading && (
                          <div className="muted" style={{ padding: 10, fontSize: 12 }}>Loading…</div>
                        )}
                        {widgetYamlPreviewError && !widgetYamlPreviewLoading && (
                          <div>
                            <div className="error" style={{ padding: 10, fontSize: 12, borderRadius: 6 }}>{widgetYamlPreviewError}</div>
                            <button
                              type="button"
                              className="secondary"
                              style={{ marginTop: 6, fontSize: 11 }}
                              onClick={() => {
                                if (!project || selectedWidgetIds.length !== 1) return;
                                setWidgetYamlPreviewLoading(true);
                                setWidgetYamlPreviewError(null);
                                previewWidgetYaml(project, selectedWidgetIds[0], safePageIndex)
                                  .then(({ yaml, event_snippets }) => {
                                    setWidgetYamlPreview(yaml);
                                    setWidgetYamlEventSnippets(event_snippets ?? {});
                                    setWidgetYamlPreviewError(null);
                                  })
                                  .catch((e: any) => { setWidgetYamlPreviewError(String(e?.message || e)); })
                                  .finally(() => setWidgetYamlPreviewLoading(false));
                              }}
                            >
                              Retry
                            </button>
                          </div>
                        )}
                        {!widgetYamlPreviewLoading && widgetYamlPreview != null && (
                          <>
                            <YamlEditor readOnly value={widgetYamlPreview || "(empty)"} minHeight={120} maxHeight={280} />
                            <button
                              type="button"
                              className="secondary"
                              style={{ marginTop: 6, fontSize: 11 }}
                              onClick={() => {
                                if (!project || selectedWidgetIds.length !== 1) return;
                                setWidgetYamlPreviewLoading(true);
                                setWidgetYamlPreviewError(null);
                                previewWidgetYaml(project, selectedWidgetIds[0], safePageIndex)
                                  .then(({ yaml, event_snippets }) => {
                                    setWidgetYamlPreview(yaml);
                                    setWidgetYamlEventSnippets(event_snippets ?? {});
                                    setWidgetYamlPreviewError(null);
                                  })
                                  .catch((e: any) => { setWidgetYamlPreviewError(String(e?.message || e)); })
                                  .finally(() => setWidgetYamlPreviewLoading(false));
                              }}
                            >
                              Refresh preview
                            </button>
                          </>
                        )}
                      </div>
                      <div style={{ marginTop: 16, padding: 10, borderRadius: 6, background: "rgba(100,160,255,0.06)", border: "1px solid rgba(100,160,255,0.2)" }}>
                        <div className="fieldLabel" style={{ fontSize: 11, marginBottom: 4, display: "flex", alignItems: "center", gap: 8 }}>
                          Action events
                          <span className="muted" style={{ fontSize: 10 }}>Empty / Auto / Edited. One box per event; Reset = back to Auto, Save = store.</span>
                        </div>
                        {widgetEventError && (
                          <div className="error" style={{ padding: 8, fontSize: 11, borderRadius: 6, marginBottom: 8 }}>{widgetEventError}</div>
                        )}
                        {(() => {
                          const actionBindings = (project as any)?.action_bindings || [];
                          return eventOptions.map((ev) => {
                            const snippet = widgetYamlEventSnippets[ev];
                            const effectiveFromApi = (snippet?.yaml ?? "").trim();
                            const source = (snippet?.source ?? "empty") as string;
                            const abForEvent = actionBindings.find((ab: any) => String(ab?.widget_id) === widgetId && ab?.event === ev);
                            const storedOverride = (customEvents[ev] ?? "").trim() || (abForEvent?.yaml_override ?? "").trim();
                            const draftKey = `${widgetId}:${ev}`;
                            const hasStored = !!storedOverride;
                            const displayValue = hasStored ? (storedOverride || effectiveFromApi) : effectiveFromApi;
                            const draftValue = widgetEventDrafts[draftKey] !== undefined ? widgetEventDrafts[draftKey] : displayValue;
                            const badgeLabel = hasStored ? "Edited" : (source === "auto" ? "Auto" : "Empty");
                            const badgeStyle = source === "empty" && !hasStored
                              ? { background: "rgba(255,255,255,0.12)", color: "rgba(255,255,255,0.5)" }
                              : hasStored
                                ? { background: "rgba(100,160,255,0.25)", color: "rgba(200,220,255,0.95)" }
                                : { background: "rgba(255,255,255,0.12)", color: "rgba(255,255,255,0.65)" };
                            const hasValue = !!draftValue.trim() || !!effectiveFromApi || !!storedOverride;
                            const isDirty = hasStored ? (draftValue.trim() !== storedOverride) : (draftValue.trim() !== effectiveFromApi);
                            return (
                              <details key={ev} style={{ marginBottom: 6 }} open={hasValue}>
                                <summary style={{ cursor: "pointer", fontSize: 12, padding: "6px 0", color: hasValue ? "rgba(200,220,255,0.95)" : "#888", display: "flex", alignItems: "center", gap: 8 }}>
                                  {ev}
                                  <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 4, ...badgeStyle }}>{badgeLabel}</span>
                                  {isDirty && <span className="muted" style={{ fontSize: 10 }}>unsaved</span>}
                                  {hasValue && !isDirty && "✓"}
                                </summary>
                                <YamlEditor
                                  value={draftValue}
                                  onChange={(v) => {
                                    setWidgetEventDrafts((prev) => ({ ...prev, [draftKey]: v }));
                                    setWidgetEventError(null);
                                  }}
                                  placeholder={source === "auto" ? "Auto-generated (edit to customize and Save)" : `then:\n  - logger.log: \"${ev} triggered\"\n  - lvgl.page.next:`}
                                  minHeight={80}
                                  maxHeight={180}
                                />
                                <div style={{ marginTop: 6, display: "flex", gap: 8 }}>
                                  <button
                                    type="button"
                                    className="secondary"
                                    style={{ fontSize: 11 }}
                                    onClick={() => {
                                      const p2 = clone(project);
                                      const pg = (p2 as any).pages?.[safePageIndex];
                                      const w = pg?.widgets?.find((x: any) => x?.id === widgetId);
                                      if (w?.custom_events?.[ev] !== undefined) {
                                        delete w.custom_events[ev];
                                        if (Object.keys(w.custom_events).length === 0) delete w.custom_events;
                                      }
                                      const abs = (p2 as any).action_bindings;
                                      if (Array.isArray(abs)) {
                                        const ab = abs.find((x: any) => String(x?.widget_id) === widgetId && x?.event === ev);
                                        if (ab && ab.yaml_override !== undefined) {
                                          delete ab.yaml_override;
                                        }
                                      }
                                      setProject(p2, true);
                                      setProjectDirty(true);
                                      setWidgetEventDrafts((prev) => { const next = { ...prev }; delete next[draftKey]; return next; });
                                      setWidgetEventError(null);
                                      setWidgetYamlPreviewLoading(true);
                                      previewWidgetYaml(p2, widgetId, safePageIndex)
                                        .then(({ yaml: newYaml, event_snippets: newSnippets }) => {
                                          setWidgetYamlPreview(newYaml);
                                          setWidgetYamlEventSnippets(newSnippets ?? {});
                                        })
                                        .catch(() => {})
                                        .finally(() => setWidgetYamlPreviewLoading(false));
                                    }}
                                  >
                                    Reset
                                  </button>
                                  <button
                                    type="button"
                                    className="primary"
                                    style={{ fontSize: 11 }}
                                    onClick={async () => {
                                      const toSave = draftValue.trim();
                                      if (toSave) {
                                        const result = await parseYamlSyntax(toSave);
                                        if (!result.ok) {
                                          setWidgetEventError(`${ev}: ${result.error || "Invalid YAML"}${result.line != null ? ` (line ${result.line})` : ""}`);
                                          return;
                                        }
                                      }
                                      setWidgetEventError(null);
                                      const p2 = clone(project);
                                      const pg = (p2 as any).pages?.[safePageIndex];
                                      const w = pg?.widgets?.find((x: any) => x?.id === widgetId);
                                      if (!Array.isArray((p2 as any).action_bindings)) (p2 as any).action_bindings = [];
                                      const abs = (p2 as any).action_bindings;
                                      const ab = abs.find((x: any) => String(x?.widget_id) === widgetId && x?.event === ev) ?? null;
                                      if (ab) {
                                        if (toSave) ab.yaml_override = toSave;
                                        else if (ab.yaml_override !== undefined) delete ab.yaml_override;
                                      } else if (w) {
                                        if (!toSave) {
                                          if (w.custom_events?.[ev] !== undefined) {
                                            delete w.custom_events[ev];
                                            if (Object.keys(w.custom_events).length === 0) delete w.custom_events;
                                          }
                                        } else {
                                          if (!w.custom_events) w.custom_events = {};
                                          w.custom_events[ev] = toSave;
                                        }
                                      }
                                      setProject(p2, true);
                                      setProjectDirty(true);
                                      setWidgetEventDrafts((prev) => { const next = { ...prev }; delete next[draftKey]; return next; });
                                      // Refetch widget preview with updated project so main YAML and event_snippets (badge) update immediately
                                      setWidgetYamlPreviewLoading(true);
                                      previewWidgetYaml(p2, widgetId, safePageIndex)
                                        .then(({ yaml: newYaml, event_snippets: newSnippets }) => {
                                          setWidgetYamlPreview(newYaml);
                                          setWidgetYamlEventSnippets(newSnippets ?? {});
                                        })
                                        .catch(() => {})
                                        .finally(() => setWidgetYamlPreviewLoading(false));
                                    }}
                                  >
                                    Save
                                  </button>
                                </div>
                              </details>
                            );
                          });
                        })()}
                      </div>
                      <div style={{ marginTop: 16 }}>
                        <button
                          type="button"
                          className="secondary"
                          style={{ fontSize: 12 }}
                          onClick={() => setInspectorTab("builder")}
                        >
                          → Binding Builder (HA actions)
                        </button>
                      </div>
                    </>
                  );
                })()}
              </div>
            )}
            {inspectorTab === "importlog" && (
              <div className="section">
                <div className="sectionTitle">Import log</div>
                <div className="muted" style={{ fontSize: 11, marginBottom: 8 }}>Output from the last YAML import (Import YAML on the welcome screen).</div>
                {importLogLines.length === 0 ? (
                  <div className="muted" style={{ padding: 12, fontSize: 12 }}>No import log yet. Use Import YAML from the welcome screen.</div>
                ) : (
                  <>
                    <pre style={{ margin: 0, padding: 10, fontSize: 11, background: "rgba(0,0,0,0.3)", borderRadius: 6, overflow: "auto", maxHeight: 320, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                      {importLogLines.join("\n")}
                    </pre>
                    <button type="button" className="secondary" style={{ marginTop: 8, fontSize: 11 }} onClick={() => setImportLogLines([])}>Clear log</button>
                  </>
                )}
              </div>
            )}
          </div>
        </aside>
      </main>
    </div>
    )
  );
}

function styleValueToCss(v: any): string {
  if (v == null || v === "") return "";
  if (typeof v === "number" && v >= 0 && v <= 0xffffff) return "#" + v.toString(16).padStart(6, "0");
  return String(v);
}
function cssToStyleValue(css: string): number | string {
  const t = css.trim();
  if (!t) return "";
  const m = /^#?([0-9a-fA-F]{6})$/.exec(t);
  if (m) return parseInt(m[1], 16);
  return t;
}

function intersection<T>(sets: T[][]): T[] {
  if (sets.length === 0) return [];
  let result = sets[0] || [];
  for (let i = 1; i < sets.length; i++) {
    const s = new Set(sets[i] || []);
    result = result.filter((x) => s.has(x));
  }
  return result;
}

function MultiSelectProperties(props: {
  widgetIds: string[];
  widgets: any[];
  project: any;
  setProject: (p: any, fromStorage?: boolean) => void;
  setProjectDirty: (d: boolean) => void;
  safePageIndex: number;
  clone: (x: any) => any;
  assets: {name:string; size:number}[];
}) {
  const { widgetIds, widgets, project, setProject, setProjectDirty, safePageIndex, clone, assets } = props;
  const sel = widgets.filter((w: any) => w && widgetIds.includes(w.id));
  const [schemasByType, setSchemasByType] = useState<Record<string, WidgetSchema>>({});
  const [schemasLoading, setSchemasLoading] = useState(false);

  const selectedTypesKey = useMemo(() => sel.map((w: any) => w.type).filter(Boolean).sort().join(","), [widgetIds.join(","), widgets.length]);
  useEffect(() => {
    if (sel.length === 0) {
      setSchemasByType({});
      return;
    }
    const types = Array.from(new Set(sel.map((w: any) => w.type).filter(Boolean)));
    if (types.length === 0) {
      setSchemasByType({});
      return;
    }
    let cancelled = false;
    setSchemasLoading(true);
    Promise.all(types.map((t) => getWidgetSchema(t).then((r) => (r.ok ? r.schema : null))))
      .then((schemas) => {
        if (cancelled) return;
        const byType: Record<string, WidgetSchema> = {};
        types.forEach((t, i) => {
          if (schemas[i]) byType[t] = schemas[i] as WidgetSchema;
        });
        setSchemasByType(byType);
      })
      .finally(() => {
        if (!cancelled) setSchemasLoading(false);
      });
    return () => { cancelled = true; };
  }, [selectedTypesKey]);

  if (sel.length === 0) return <div className="muted">No widgets found.</div>;
  const first = sel[0];
  const commonX = Number(first.x ?? 0);
  const commonY = Number(first.y ?? 0);
  const commonW = Number(first.w ?? 0);
  const commonH = Number(first.h ?? 0);

  const schemaList = Object.values(schemasByType);
  const commonStyleKeys = schemaList.length > 0
    ? intersection(schemaList.map((s) => Object.keys((s as any).style || {})))
    : [];
  const commonPropsKeys = schemaList.length > 0
    ? intersection(schemaList.map((s) => Object.keys((s as any).props || {})))
    : [];

  const patchAll = (key: string, value: number) => {
    if (!project || Number.isNaN(value)) return;
    const p2 = clone(project);
    const page = (p2 as any).pages?.[safePageIndex];
    if (!page?.widgets) return;
    for (const w of page.widgets) {
      if (w && widgetIds.includes(w.id)) (w as any)[key] = value;
    }
    setProject(p2, true);
    setProjectDirty(true);
  };

  const patchAllStyle = (key: string, value: number | string) => {
    if (!project) return;
    const p2 = clone(project);
    const page = (p2 as any).pages?.[safePageIndex];
    if (!page?.widgets) return;
    for (const w of page.widgets) {
      if (!w || !widgetIds.includes(w.id)) continue;
      if (w.style == null) w.style = {};
      if (value === "" || value == null) {
        delete w.style[key];
      } else {
        (w.style as any)[key] = value;
      }
    }
    setProject(p2, true);
    setProjectDirty(true);
  };

  const patchAllProps = (key: string, value: any) => {
    if (!project) return;
    const p2 = clone(project);
    const page = (p2 as any).pages?.[safePageIndex];
    if (!page?.widgets) return;
    for (const w of page.widgets) {
      if (!w || !widgetIds.includes(w.id)) continue;
      if (w.props == null) w.props = {};
      if (value === "" || value == null || value === undefined) {
        delete w.props[key];
      } else {
        (w.props as any)[key] = value;
      }
    }
    setProject(p2, true);
    setProjectDirty(true);
  };

  const getFirstDef = (section: "style" | "props", key: string): any => {
    for (const s of schemaList) {
      const sec = (s as any)[section];
      if (sec && sec[key]) return sec[key];
    }
    return null;
  };

  const renderCommonStyleField = (key: string) => {
    const def = getFirstDef("style", key);
    const firstStyle = first.style || {};
    const val = firstStyle[key] ?? first.props?.[key];
    const title = def?.title ?? key;
    if (isFontKey(key)) {
      return (
        <div key={key} className="field">
          <div className="fieldLabel">{title}</div>
          {renderFontSelectorControl(String(val ?? ""), (next) => patchAllStyle(key, next), assets)}
        </div>
      );
    }
    if (def?.type === "color" || key === "bg_color" || key === "text_color" || key === "border_color") {
      const css = styleValueToCss(val);
      const hexForPicker = /^#[0-9a-fA-F]{6}$/.test(css) ? css : "#000000";
      return (
        <div key={key} className="field">
          <div className="fieldLabel">{title}</div>
          <div style={{ display: "flex", alignItems: "center" }}>
            <input
              type="color"
              value={hexForPicker}
              onChange={(e) => patchAllStyle(key, cssToStyleValue(e.target.value))}
              style={{ width: 42, height: 28, padding: 0, border: "none", background: "transparent", cursor: "pointer" }}
            />
            <input
              type="text"
              placeholder="#rrggbb"
              value={css}
              onChange={(e) => patchAllStyle(key, cssToStyleValue(e.target.value))}
              style={{ marginLeft: 8 }}
            />
          </div>
        </div>
      );
    }
    if (def?.type === "number") {
      const n = Number(val ?? def?.default ?? 0);
      return (
        <div key={key} className="field">
          <div className="fieldLabel">{title}</div>
          <input type="number" value={n} min={def?.min} max={def?.max} step={def?.step ?? 1} onChange={(e) => patchAllStyle(key, Number(e.target.value))} />
        </div>
      );
    }
    return (
      <div key={key} className="field">
        <div className="fieldLabel">{title}</div>
        <input type="text" value={String(val ?? "")} onChange={(e) => patchAllStyle(key, e.target.value || undefined)} />
      </div>
    );
  };

  const renderCommonPropsField = (key: string) => {
    const def = getFirstDef("props", key);
    const firstProps = first.props || {};
    const val = firstProps[key];
    const title = def?.title ?? key;
    if (isFontKey(key)) {
      return (
        <div key={key} className="field">
          <div className="fieldLabel">{title}</div>
          {renderFontSelectorControl(String(val ?? ""), (next) => patchAllProps(key, next), assets)}
        </div>
      );
    }
    if (def?.type === "number") {
      const n = Number(val ?? def?.default ?? 0);
      return (
        <div key={key} className="field">
          <div className="fieldLabel">{title}</div>
          <input type="number" value={n} min={def?.min} max={def?.max} step={def?.step ?? 1} onChange={(e) => patchAllProps(key, Number(e.target.value))} />
        </div>
      );
    }
    if (def?.type === "boolean") {
      return (
        <div key={key} className="field">
          <div className="fieldLabel">{title}</div>
          <select value={String(!!val)} onChange={(e) => patchAllProps(key, e.target.value === "true")}>
            <option value="true">true</option>
            <option value="false">false</option>
          </select>
        </div>
      );
    }
    return (
      <div key={key} className="field">
        <div className="fieldLabel">{title}</div>
        <input type="text" value={String(val ?? "")} onChange={(e) => patchAllProps(key, e.target.value || undefined)} />
      </div>
    );
  };

  return (
    <div className="section">
      <div className="muted" style={{ marginBottom: 8 }}>{widgetIds.length} widgets selected</div>
      <div className="sectionTitle" style={{ fontSize: 12 }}>Common layout</div>
      <div className="field">
        <div className="fieldLabel">X</div>
        <input type="number" value={commonX} onChange={(e) => patchAll("x", Number(e.target.value))} />
      </div>
      <div className="field">
        <div className="fieldLabel">Y</div>
        <input type="number" value={commonY} onChange={(e) => patchAll("y", Number(e.target.value))} />
      </div>
      <div className="field">
        <div className="fieldLabel">Width</div>
        <input type="number" value={commonW} onChange={(e) => patchAll("w", Number(e.target.value))} />
      </div>
      <div className="field">
        <div className="fieldLabel">Height</div>
        <input type="number" value={commonH} onChange={(e) => patchAll("h", Number(e.target.value))} />
      </div>
      <div className="sectionTitle" style={{ fontSize: 12, marginTop: 12 }}>Common style</div>
      {schemasLoading ? (
        <div className="muted" style={{ fontSize: 12 }}>Loading…</div>
      ) : commonStyleKeys.length === 0 ? (
        <div className="muted" style={{ fontSize: 12 }}>No style properties common to all selected widget types.</div>
      ) : (
        commonStyleKeys.map(renderCommonStyleField)
      )}
      {!schemasLoading && commonPropsKeys.length > 0 && (
        <>
          <div className="sectionTitle" style={{ fontSize: 12, marginTop: 12 }}>Common props</div>
          {commonPropsKeys.map(renderCommonPropsField)}
        </>
      )}
      <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>Other properties vary; select one widget to edit.</div>
    </div>
  );
}

// ESPHome LVGL built-in fonts (Montserrat). User can pick these without uploading assets.
const BUILTIN_LVGL_FONTS = ["montserrat_8","montserrat_10","montserrat_12","montserrat_14","montserrat_16","montserrat_18","montserrat_20","montserrat_22","montserrat_24","montserrat_26","montserrat_28","montserrat_30","montserrat_32","montserrat_34","montserrat_36","montserrat_38","montserrat_40","montserrat_42","montserrat_44","montserrat_46","montserrat_48"];
/** Vendored variable fonts (synced to `/config/esptoolkit_assets` on add-on start). Always listed in the UI; filenames must match those files. */
const APPROVED_ASSET_FONT_FILES_LIST = [
  "Montserrat[wght].ttf",
  "Montserrat-Italic[wght].ttf",
  "Roboto[wdth,wght].ttf",
  "Inter[opsz,wght].ttf",
  "OpenSans[wdth,wght].ttf",
  "NotoSans[wdth,wght].ttf",
] as const;
const APPROVED_ASSET_FONT_SIZES = [10,12,14,16,18,20,24,28,32,36,40];

function isFontKey(key: string): boolean {
  const k = String(key || "").toLowerCase();
  return k === "font" || k.endsWith("_font") || k.includes("text_font");
}

function buildApprovedFontOptions(assets: {name:string; size:number}[]) {
  const onServer = new Set((assets || []).map((a) => a.name));
  const options = [
    ...BUILTIN_LVGL_FONTS.map((f) => ({ value: f, label: f.replace("montserrat_", "Montserrat ") + "px", group: "Built-in (Montserrat)" })),
    ...APPROVED_ASSET_FONT_FILES_LIST.flatMap((fn) =>
      APPROVED_ASSET_FONT_SIZES.map((size) => ({
        value: `asset:${fn}:${size}`,
        label: `${fn} (${size}px)` + (onServer.has(fn) ? "" : " — missing on server"),
        group: "Bundled font files (TTF in esptoolkit_assets)",
      })),
    ),
  ];
  return options;
}

function renderFontSelectorControl(rawValue: string, onChange: (value: string | undefined) => void, assets: {name:string; size:number}[]) {
  const options = buildApprovedFontOptions(assets);
  const optionValues = new Set(options.map((o) => o.value));
  const selected = optionValues.has(rawValue) ? rawValue : "";
  const grouped = options.reduce<Record<string, {value:string; label:string}[]>>((acc, o) => {
    if (!acc[o.group]) acc[o.group] = [];
    acc[o.group].push({ value: o.value, label: o.label });
    return acc;
  }, {});
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <select
        value={selected}
        onChange={(e) => {
          const v = e.target.value;
          onChange(v || undefined);
        }}
        style={{ width: "100%", maxWidth: 260 }}
      >
        <option value="">(default)</option>
        {Object.entries(grouped).map(([group, items]) => (
          <optgroup key={group} label={group}>
            {items.map((it) => (
              <option key={it.value} value={it.value}>{it.label}</option>
            ))}
          </optgroup>
        ))}
      </select>
      {rawValue && !selected && (
        <div className="muted" style={{ fontSize: 11 }}>
          Current value is not in approved fonts. Pick a listed font to replace it.
        </div>
      )}
    </div>
  );
}

function ScreensaverInspector(props: { widget: any; onChange: (section: string, key: string, value: any) => void }) {
  const { widget, onChange } = props;
  const propsObj = widget?.props || {};
  const timeout = Number(propsObj.timeout_seconds ?? 60);
  const backlightId = String(propsObj.backlight_id ?? "display_backlight");
  return (
    <div className="section">
      <div className="sectionTitle" style={{ fontSize: 12 }}>Screen saver</div>
      <div className="field">
        <div className="fieldLabel" title="Idle time before display blanks">Timeout (seconds)</div>
        <input
          type="number"
          min={5}
          max={86400}
          step={1}
          value={timeout}
          onChange={(e) => onChange("props", "timeout_seconds", Math.max(5, Math.min(86400, Number(e.target.value) || 60)))}
        />
      </div>
      <div className="field">
        <div className="fieldLabel" title="ESPHome light id for the display backlight">Backlight id</div>
        <input
          type="text"
          value={backlightId}
          onChange={(e) => onChange("props", "backlight_id", e.target.value?.trim() || "display_backlight")}
          placeholder="display_backlight"
          style={{ fontFamily: "ui-monospace, monospace" }}
        />
      </div>
      <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>Editor-only: not shown on device. Touch wakes display.</div>
    </div>
  );
}

function Inspector(props: { widget: any; schema: WidgetSchema; onChange: (section: any, key: string, value: any) => void; assets: {name:string; size:number}[]; assetError?: string | null }) {
  const { widget, schema, onChange, assets, assetError } = props;

  const [fieldFilter, setFieldFilter] = useState<string>("");
  const [modifiedOnly, setModifiedOnly] = useState<boolean>(false);
  const [recentColors, setRecentColors] = useState<string[]>([]);
  const groups = (schema as any).groups as Record<string, { section: string; keys: string[]; defaultCollapsed?: boolean }> | undefined;
  const groupNames = groups ? Object.keys(groups) : [];
  const [groupExpanded, setGroupExpanded] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    if (groups) {
      for (const name of Object.keys(groups)) {
        const gr = groups[name];
        init[name] = !(gr && (gr as any).defaultCollapsed);
      }
    }
    return init;
  });

  const renderSection = (title: string, section: "props"|"style"|"events", fields?: Record<string, any>) => {
    const entriesAll = Object.entries(fields ?? {});
    const entries = entriesAll.filter(([k, def]: any) => {
      const title = String(def?.title ?? k).toLowerCase();
      const keyLc = String(k).toLowerCase();
      const q = fieldFilter.trim().toLowerCase();
      const matches = !q || title.includes(q) || keyLc.includes(q);
      const hasValue = Object.prototype.hasOwnProperty.call((widget[section] || {}), k);
      const modOk = !modifiedOnly || hasValue;
      return matches && modOk;
    });
    if (!entries.length) return null;
    return (
      <div className="section">
        <div className="sectionTitle" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>{title}<button type="button" className="tiny secondary" title="Clear all modified values in this section" onClick={() => {
  if (!confirm(`Clear all modified values in ${title}?`)) return;
  for (const [k2] of entriesAll) {
    const hasV = Object.prototype.hasOwnProperty.call((widget[section] || {}), k2);
    if (hasV) onChange(section as any, k2, undefined);
  }
}}>clear section</button></div>
        {entries.map(([k, def]) => (
          <div key={k} className="field">
            <div className="fieldLabel" title={def.description || def.desc || ""}>{def.title ?? k}</div>
            {renderField(section, k, def)}
          </div>
        ))}
      </div>
    );
  };

  const renderField = (section: string, key: string, def: any) => {
    const hasValue = Object.prototype.hasOwnProperty.call((widget[section] || {}), key);
    const value = hasValue ? (widget[section] || {})[key] : (def.default ?? "");

    const resetBtn = (def && Object.prototype.hasOwnProperty.call(def, "default")) ? (
      <button
        type="button"
        className="tiny secondary"
        style={{ marginLeft: 8 }}
        title="Reset to default"
        onClick={() => onChange(section, key, def.default)}
      >
        reset
      </button>
    ) : null;

    const clearBtn = hasValue ? (
      <button
        type="button"
        className="tiny secondary"
        style={{ marginLeft: 8 }}
        title="Remove this property so it will not be emitted into YAML"
        onClick={() => onChange(section, key, undefined)}
      >
        clear
      </button>
    ) : null;

    if (def.type === "enum") {
      return (
        <div style={{ display: "flex", alignItems: "center" }}>
          <select value={value} onChange={(e) => onChange(section, key, e.target.value)}>
            {(def.values ?? []).map((v: string) => <option key={v} value={v}>{v}</option>)}
          </select>
          {resetBtn}{clearBtn}
        </div>
      );
    }
    if (def.type === "boolean") {
      return (
        <div style={{ display: "flex", alignItems: "center" }}>
          <select value={String(value)} onChange={(e) => onChange(section, key, e.target.value === "true")}>
            <option value="true">true</option>
            <option value="false">false</option>
          </select>
          {resetBtn}{clearBtn}
        </div>
      );
    }
    if (def.type === "yaml_block") {
      return (
        <div>
          <textarea rows={6} value={String(value ?? "")} onChange={(e) => onChange(section, key, e.target.value)} />
          <div style={{ marginTop: 6 }}>{resetBtn}{clearBtn}</div>
        </div>
      );
    }
    if (def.type === "number") {
      const min = def.min;
      const max = def.max;
      const step = def.step ?? 1;
      const useSlider = typeof min === "number" && typeof max === "number" && max - min <= 255;
      const numDisplay = value !== undefined && value !== null && value !== "" ? Number(value) : (typeof def.default === "number" ? def.default : (typeof min === "number" ? min : ""));
      return (
        <div style={{ display: "flex", alignItems: "center" }}>
          {useSlider ? (
            <input
              type="range"
              value={Number(numDisplay ?? min)}
              min={min}
              max={max}
              step={step}
              onChange={(e) => onChange(section, key, Number(e.target.value))}
              style={{ width: 140, marginRight: 8 }}
            />
          ) : null}
          <input
            type="number"
            value={numDisplay}
            min={min}
            max={max}
            placeholder={def.default != null && numDisplay === "" ? String(def.default) : undefined}
            onChange={(e) => {
              const raw = e.target.value;
              if (raw === "") return onChange(section, key, undefined);
              return onChange(section, key, Number(raw));
            }}
          />
          {resetBtn}{clearBtn}
        </div>
      );
    }
    if (def.type === "color") {
      const asStr = String(value ?? "");
      const hexMatch = /^#([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(asStr);
      return (
        <div style={{ display: "flex", alignItems: "center" }}>
          <input
            type="color"
            value={hexMatch ? asStr.slice(0, 7) : "#000000"}
            onChange={(e) => {
              const newHex = e.target.value;
              const alpha = hexMatch && asStr.length === 9 ? asStr.slice(7) : "";
              const full = newHex + alpha;
              onChange(section, key, full);
              setRecentColors((arr) => {
                const next = [full, ...arr.filter((c) => c !== full)];
                return next.slice(0, 8);
              });
            }}
            style={{ width: 42, height: 28, padding: 0, border: "none", background: "transparent" }}
          />
          <input
            value={asStr}
            placeholder="#RRGGBB or #RRGGBBAA"
            onChange={(e) => onChange(section, key, e.target.value)}
            style={{ marginLeft: 8 }}
          />
          {resetBtn}{clearBtn}
        </div>
      );
    }
    if (isFontKey(key)) {
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {renderFontSelectorControl(String(value ?? "").trim(), (next) => onChange(section, key, next), assets)}
          <div style={{ display: "flex", gap: 8 }}>{resetBtn}{clearBtn}</div>
        </div>
      );
    }

    if (def.type === "string_list") {
      const txt = Array.isArray(value) ? value.join("\n") : String(value);
      return (
        <div>
          <textarea rows={4} value={txt} onChange={(e) => onChange(section, key, e.target.value.split(/\r?\n/).filter(Boolean))} />
          <div style={{ marginTop: 6 }}>{resetBtn}{clearBtn}</div>
        </div>
      );
    }
    // Text prop: use textarea so user can insert line breaks (CRLF); emitted to YAML and shown on device.
    if (section === "props" && key === "text") {
      return (
        <div>
          <textarea rows={3} value={String(value ?? "")} onChange={(e) => onChange(section, key, e.target.value || undefined)} placeholder="Use Enter for new line" style={{ width: "100%", boxSizing: "border-box", resize: "vertical" }} />
          <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>New lines in YAML → multi-line on device.</div>
          <div style={{ marginTop: 6 }}>{resetBtn}{clearBtn}</div>
        </div>
      );
    }
    return (
      <div style={{ display: "flex", alignItems: "center" }}>
        <input value={value} onChange={(e) => onChange(section, key, e.target.value)} />
        {resetBtn}{clearBtn}
      </div>
    );
  };

  return (
    <div>
      {assetError && <div className="error" style={{ marginBottom: 8 }}>{assetError}</div>}
      <div className="muted" style={{ marginBottom: 8 }}><strong>{schema.title}</strong> <span className="muted">({schema.type})</span></div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10, flexWrap: "wrap" }}>
        <input
          value={fieldFilter}
          onChange={(e) => setFieldFilter(e.target.value)}
          placeholder="Search properties…"
          style={{ width: 220 }}
        />
        <label className="muted" style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={modifiedOnly} onChange={(e) => setModifiedOnly(e.target.checked)} />
          modified only
        </label>
        <button type="button" className="tiny secondary" onClick={() => { setFieldFilter(""); setModifiedOnly(false); }}>
          reset filters
        </button>
      </div>
      {groups && groupNames.length > 0
        ? groupNames.map((groupName) => {
            const gr = groups[groupName];
            const section = gr?.section ?? "props";
            const keys = Array.isArray(gr?.keys) ? gr.keys : [];
            const fields = (schema as any)[section] || {};
            const entriesAll = keys.map((k) => [k, fields[k]]).filter(([, def]) => def != null);
            const entries = entriesAll.filter(([k, def]: any) => {
              const title = String(def?.title ?? k).toLowerCase();
              const keyLc = String(k).toLowerCase();
              const q = fieldFilter.trim().toLowerCase();
              const matches = !q || title.includes(q) || keyLc.includes(q);
              const hasValue = Object.prototype.hasOwnProperty.call((widget[section] || {}), k);
              const modOk = !modifiedOnly || hasValue;
              return matches && modOk;
            });
            if (!entries.length) return null;
            const expanded = groupExpanded[groupName] !== false;
            return (
              <div key={groupName} className="section" style={{ marginTop: 6 }}>
                <button
                  type="button"
                  className="sectionTitle"
                  style={{ width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer", background: "rgba(255,255,255,.04)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 12px", marginBottom: expanded ? 8 : 0, fontWeight: 600 }}
                  onClick={() => setGroupExpanded((prev) => ({ ...prev, [groupName]: !expanded }))}
                >
                  <span>{groupName}</span>
                  <span style={{ fontSize: 12, color: "var(--muted)" }}>{expanded ? "▼" : "▶"}</span>
                </button>
                {expanded && (
                  <div style={{ paddingLeft: 4 }}>
                    {entries.map(([k, def]: [string, any]) => (
                      <div key={k} className="field" style={{ marginBottom: 10 }}>
                        <div className="fieldLabel" title={def.description || def.desc || ""}>{def.title ?? k}</div>
                        {renderField(section, k, def)}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        : <>
            {renderSection("Props", "props", schema.props)}
            {renderSection("Style", "style", schema.style)}
            {renderSection("Events", "events", schema.events)}
          </>
      }
    </div>
  );
}
