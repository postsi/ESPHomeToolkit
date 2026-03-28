/**
 * Writes static parity JSON under public/parity-fixtures/ for designer vs Mac LVGL snapshot tests.
 * Run: npx tsx scripts/generate-parity-fixtures.ts
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { PREBUILT_WIDGETS } from "../src/prebuiltWidgets/index.ts";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const outDir = path.join(root, "public", "parity-fixtures");

/** Real builtin on HA; mac_sim compile must not use fake `parity_*` recipe ids. */
const PARITY_RECIPE_ID = "jc1060p470_esp32p4_1024x600";
const PARITY_SCREEN_W = 1024;
const PARITY_SCREEN_H = 600;
/** Page + preview background for parity (compiler page bg; must match App parity Canvas dispBgColor). */
const PARITY_DISP_BG = "#000000";

/** Matches custom_components/esptoolkit/api/views.py PALETTE_WIDGET_TYPES ∪ EXTRA_WIDGET_TYPES (incl. spinbox2). */
const STANDARD_TYPES = [
  "animimg",
  "arc",
  "arc_labeled",
  "bar",
  "button",
  "buttonmatrix",
  "canvas",
  "checkbox",
  "color_picker",
  "container",
  "dropdown",
  "image",
  "keyboard",
  "label",
  "led",
  "line",
  "meter",
  "msgboxes",
  "obj",
  "qrcode",
  "roller",
  "slider",
  "spinbox",
  "spinbox2",
  "spinner",
  "switch",
  "tabview",
  "textarea",
  "tileview",
  "white_picker",
].sort();

const styleBox = { bg_color: 0x1e293b, border_width: 1, border_color: 0x475569, radius: 6 };

function minimalStandard(type: string, id: string, x: number, y: number, w: number, h: number): Record<string, unknown> {
  const base: Record<string, unknown> = { id, type, x, y, w, h, props: {}, style: { ...styleBox } };
  const p = base.props as Record<string, unknown>;
  switch (type) {
    case "label":
      p.text = "Lbl";
      break;
    case "button":
      p.text = "Btn";
      break;
    case "switch":
      p.checked = true;
      break;
    case "checkbox":
      p.state = true;
      break;
    case "slider":
      Object.assign(p, { min_value: 0, max_value: 100, value: 35, mode: "NORMAL" });
      break;
    case "bar":
      Object.assign(p, { min_value: 0, max_value: 100, value: 55, mode: "NORMAL" });
      break;
    case "arc":
    case "meter":
      Object.assign(p, {
        min_value: 0,
        max_value: 100,
        value: 40,
        start_angle: 135,
        end_angle: 45,
        mode: "NORMAL",
        rotation: 0,
      });
      break;
    case "arc_labeled":
      Object.assign(p, {
        min_value: 0,
        max_value: 100,
        value: 25,
        start_angle: 135,
        end_angle: 45,
        rotation: 0,
        mode: "NORMAL",
        adjustable: false,
      });
      (base.style as Record<string, unknown>)["tick_color"] = "#e2e8f0";
      (base.style as Record<string, unknown>)["tick_width"] = 2;
      (base.style as Record<string, unknown>)["label_text_color"] = "#e2e8f0";
      break;
    case "dropdown":
      p.options = "A\nB\nC";
      break;
    case "roller":
      Object.assign(p, { options: ["One", "Two", "Three"], visible_row_count: 3 });
      break;
    case "textarea":
      p.text = "Hi";
      break;
    case "spinbox":
      Object.assign(p, { value: 42, range_from: 0, range_to: 99, decimal_places: 0 });
      break;
    case "spinbox2":
      Object.assign(p, {
        value: 12,
        min_value: 0,
        max_value: 99,
        step: 1,
        decimal_places: 0,
        minus_text: "-",
        plus_text: "+",
      });
      base.events = {};
      break;
    case "color_picker":
      p.value = 0xff8040;
      base.style = { bg_color: 0xff8040, radius: 6 };
      break;
    case "white_picker":
      p.value = 300;
      base.style = { bg_color: 0xe8dcc8, radius: 6 };
      break;
    case "led":
      p.color = 0x22c55e;
      p.brightness = 100;
      break;
    case "line":
      p.line_width = 2;
      p.line_rounded = true;
      break;
    case "tabview":
      p.tabs = ["A", "B"];
      break;
    case "tileview":
      p.tiles = ["0,0", "1,0"];
      break;
    case "buttonmatrix":
      p.map = ["1 2", "3 4"];
      break;
    case "keyboard":
      break;
    case "msgboxes":
      break;
    case "canvas":
      p.transparent = false;
      break;
    case "qrcode":
      p.text = "ETD";
      break;
    case "spinner":
      break;
    case "container":
    case "obj":
    case "image":
    case "animimg":
    default:
      break;
  }
  return base;
}

/** One standard widget on the parity screen (for isolate-and-fix compile/compare loops). */
function buildSingleWidgetProject(type: string): Record<string, unknown> {
  const w = 280;
  const h = 160;
  const x = Math.floor((PARITY_SCREEN_W - w) / 2);
  const y = Math.floor((PARITY_SCREEN_H - h) / 2);
  return {
    model_version: 1,
    disp_bg_color: PARITY_DISP_BG,
    device: {
      screen: { width: PARITY_SCREEN_W, height: PARITY_SCREEN_H },
      hardware_recipe_id: PARITY_RECIPE_ID,
    },
    pages: [{ page_id: "main", name: "Main", widgets: [minimalStandard(type, `std_${type}`, x, y, w, h)] }],
  };
}

function buildStandardProject(): Record<string, unknown> {
  const pad = 12;
  const cols = 6;
  const colW = Math.floor((PARITY_SCREEN_W - 2 * pad) / cols);
  const rows = Math.ceil(STANDARD_TYPES.length / cols);
  const rowH = Math.floor((PARITY_SCREEN_H - 2 * pad - 24) / rows);
  const widgetW = Math.max(72, colW - 20);
  const widgetH = Math.max(56, rowH - 14);
  const widgets: Record<string, unknown>[] = [];
  STANDARD_TYPES.forEach((t, i) => {
    const c = i % cols;
    const r = Math.floor(i / cols);
    const x = pad + c * colW;
    const y = pad + r * rowH;
    widgets.push(minimalStandard(t, `std_${t}`, x, y, widgetW, widgetH));
  });
  return {
    model_version: 1,
    disp_bg_color: PARITY_DISP_BG,
    device: {
      screen: { width: PARITY_SCREEN_W, height: PARITY_SCREEN_H },
      hardware_recipe_id: PARITY_RECIPE_ID,
    },
    pages: [{ page_id: "main", name: "Main", widgets }],
  };
}

function widgetListBBox(widgets: any[]): { minX: number; minY: number; maxX: number; maxY: number; height: number } {
  const byId = new Map<string, any>(widgets.map((w) => [w.id, w]));
  function absTL(w: any): { x: number; y: number } {
    if (!w.parent_id) return { x: Number(w.x ?? 0), y: Number(w.y ?? 0) };
    const p = byId.get(w.parent_id);
    if (!p) return { x: Number(w.x ?? 0), y: Number(w.y ?? 0) };
    const t = absTL(p);
    return { x: t.x + Number(w.x ?? 0), y: t.y + Number(w.y ?? 0) };
  }
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;
  for (const w of widgets) {
    const { x, y } = absTL(w);
    const ww = Number(w.w ?? 0),
      hh = Number(w.h ?? 0);
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x + ww);
    maxY = Math.max(maxY, y + hh);
  }
  if (!Number.isFinite(minX)) return { minX: 0, minY: 0, maxX: 100, maxY: 100, height: 100 };
  return { minX, minY, maxX, maxY, height: maxY - minY };
}

/** Normalize glyphs that vary across platforms/fonts in headless Chrome. */
function scrubGlyphs(widgets: any[]) {
  for (const w of widgets) {
    if (w.type === "label" && w.props?.text === "\u2600") w.props.text = "Sun";
    if (w.type === "button" && typeof w.props?.text === "string" && w.props.text.includes("\u232b"))
      w.props.text = w.props.text.replace(/\u232b/g, "Del");
  }
}

function buildPrebuiltProject(): Record<string, unknown> {
  const gap = 8;
  const colXs = [10, 344, 678];
  const yCur = [12, 12, 12];
  const all: any[] = [];
  for (const pw of PREBUILT_WIDGETS) {
    const built = pw.build({ x: 0, y: 0 });
    const list = built.widgets ?? [];
    if (list.length === 0) continue;
    scrubGlyphs(list);
    const bb = widgetListBBox(list);
    let ci = 0;
    let bestY = yCur[0];
    for (let k = 1; k < colXs.length; k++) {
      if (yCur[k] < bestY) {
        bestY = yCur[k];
        ci = k;
      }
    }
    const colX = colXs[ci];
    const yCursor = yCur[ci];
    const dx = colX - bb.minX;
    const dy = yCursor - bb.minY;
    for (const w of list) {
      const w2 = { ...w };
      if (!w2.parent_id) {
        w2.x = Number(w2.x ?? 0) + dx;
        w2.y = Number(w2.y ?? 0) + dy;
      }
      all.push(w2);
    }
    yCur[ci] = yCursor + bb.height + gap;
  }
  return {
    model_version: 1,
    disp_bg_color: PARITY_DISP_BG,
    device: {
      screen: { width: PARITY_SCREEN_W, height: PARITY_SCREEN_H },
      hardware_recipe_id: PARITY_RECIPE_ID,
    },
    pages: [{ page_id: "main", name: "Main", widgets: all }],
  };
}

function buildEntitySmallClimateProject(): Record<string, unknown> {
  const src = path.join(root, "src", "fixtures", "entitybuilder-project-min.json");
  const raw = JSON.parse(fs.readFileSync(src, "utf8")) as {
    device?: { screen?: { width?: number; height?: number }; hardware_recipe_id?: string };
    pages?: { page_id?: string; name?: string; widgets?: any[] }[];
  };
  const sw = Number(raw.device?.screen?.width) || 480;
  const sh = Number(raw.device?.screen?.height) || 480;
  const sx = PARITY_SCREEN_W / sw;
  const sy = PARITY_SCREEN_H / sh;
  const pages = (raw.pages ?? []).map((p) => ({
    ...p,
    widgets: (p.widgets ?? []).map((w: any) => ({
      ...w,
      x: Number(w.x ?? 0) * sx,
      y: Number(w.y ?? 0) * sy,
      w: Number(w.w ?? 0) * sx,
      h: Number(w.h ?? 0) * sy,
    })),
  }));
  return {
    ...raw,
    model_version: 1,
    disp_bg_color: PARITY_DISP_BG,
    device: {
      screen: { width: PARITY_SCREEN_W, height: PARITY_SCREEN_H },
      hardware_recipe_id: PARITY_RECIPE_ID,
    },
    pages,
  };
}

function main() {
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, "standard_widgets.json"), JSON.stringify(buildStandardProject(), null, 2));
  fs.writeFileSync(path.join(outDir, "prebuilt_widgets.json"), JSON.stringify(buildPrebuiltProject(), null, 2));
  fs.writeFileSync(path.join(outDir, "entity_small_climate.json"), JSON.stringify(buildEntitySmallClimateProject(), null, 2));
  console.log(
    `Wrote standard_widgets, prebuilt_widgets, entity_small_climate (${PARITY_RECIPE_ID} ${PARITY_SCREEN_W}x${PARITY_SCREEN_H}) →`,
    outDir
  );
  if (process.argv.includes("--per-widget")) {
    for (const t of STANDARD_TYPES) {
      const name = `widget_${t}`;
      fs.writeFileSync(path.join(outDir, `${name}.json`), JSON.stringify(buildSingleWidgetProject(t), null, 2));
    }
    console.log(`Wrote widget_<type>.json (${STANDARD_TYPES.length} files, ${PARITY_RECIPE_ID}) →`, outDir);
  }
}

main();
