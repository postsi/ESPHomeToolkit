/**
 * Simulate UI actions (drop widget, drop prebuilt, change many) without rendering Canvas.
 * Used by tests to assert that "placing canvas items" produces the expected project state.
 * Mirrors the logic in App.tsx onDropCreate and onChangeMany.
 */

import { PREBUILT_WIDGETS } from "./prebuiltWidgets";

export type Project = {
  pages: Array<{ page_id: string; name: string; widgets: any[] }>;
  [k: string]: any;
};

/** Minimal project with one page and no widgets (same shape the UI starts from). */
export function defaultProject(): Project {
  return {
    pages: [{ page_id: "main", name: "Main", widgets: [] }],
  };
}

let _testIdCounter = 0;

/** Reset counter for deterministic ids in tests (call at start of each test if needed). */
export function resetSimulationIdCounter() {
  _testIdCounter = 0;
}

function nextId(type: string): string {
  _testIdCounter += 1;
  return `${type}_${_testIdCounter}`;
}

/**
 * Simulate dropping a simple widget (label, button, switch, etc.) onto the canvas at (x, y).
 * Returns a new project; does not mutate.
 */
export function simulateDropWidget(
  project: Project,
  type: string,
  x: number,
  y: number
): Project {
  const p2 = JSON.parse(JSON.stringify(project)) as Project;
  const page = p2.pages?.[0];
  if (!page || !Array.isArray(page.widgets)) return project;

  const id = nextId(type);
  const isColorPicker = type.toLowerCase() === "color_picker";
  const isWhitePicker = type.toLowerCase() === "white_picker";
  const w = {
    id,
    type,
    x,
    y,
    w: isColorPicker || isWhitePicker ? 80 : 120,
    h: isColorPicker || isWhitePicker ? 36 : 48,
    props: isColorPicker ? { value: 0x4080ff } : isWhitePicker ? { value: 326 } : {},
    style: isColorPicker ? { bg_color: 0x4080ff, radius: 8 } : isWhitePicker ? { bg_color: 0xffd9bc, radius: 8 } : {},
    events: {},
  };
  page.widgets.push(w);
  return p2;
}

/**
 * Simulate dropping a prebuilt (e.g. prebuilt_battery, prebuilt_spinbox_buttons) at (x, y).
 * Merges widgets and optional action_bindings / scripts into the project.
 */
export function simulateDropPrebuilt(
  project: Project,
  prebuiltId: string,
  x: number,
  y: number
): Project {
  const pw = PREBUILT_WIDGETS.find((p) => p.id === prebuiltId);
  if (!pw) return project;

  const p2 = JSON.parse(JSON.stringify(project)) as Project;
  const page = p2.pages?.[0];
  if (!page) return project;
  if (!Array.isArray(page.widgets)) page.widgets = [];

  const built = pw.build({ x, y });
  const widgets = built.widgets ?? [];
  for (const w of widgets) page.widgets.push(w);

  if (Array.isArray(built.action_bindings) && built.action_bindings.length > 0) {
    p2.action_bindings = Array.isArray(p2.action_bindings) ? p2.action_bindings : [];
    for (const ab of built.action_bindings) p2.action_bindings.push(ab);
  }
  if (Array.isArray(built.scripts) && built.scripts.length > 0) {
    const rootId = widgets[0]?.id ?? null;
    p2.scripts = Array.isArray(p2.scripts) ? p2.scripts : [];
    for (const s of built.scripts) p2.scripts.push({ ...s, _source_root_id: rootId });
  }
  return p2;
}

/**
 * Simulate applying position/size patches (e.g. after drag or resize on canvas).
 * patches: [{ id: widgetId, patch: { x?, y?, w?, h?, ... } }, ...]
 */
export function simulateChangeMany(
  project: Project,
  patches: Array<{ id: string; patch: Record<string, any> }>,
  pageIndex = 0
): Project {
  const p2 = JSON.parse(JSON.stringify(project)) as Project;
  const page = p2.pages?.[pageIndex];
  if (!page?.widgets) return project;

  for (const { id, patch } of patches) {
    const w = page.widgets.find((x: any) => x && x.id === id);
    if (w) Object.assign(w, patch);
  }
  return p2;
}

/** Return widget count on the first page. */
export function widgetCount(project: Project, pageIndex = 0): number {
  return project.pages?.[pageIndex]?.widgets?.length ?? 0;
}

/** Return the first widget with the given type, or undefined. */
export function findWidgetByType(project: Project, type: string, pageIndex = 0): any {
  return project.pages?.[pageIndex]?.widgets?.find((w: any) => w?.type === type);
}
