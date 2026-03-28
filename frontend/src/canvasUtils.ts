/**
 * Pure helpers for Canvas: resize/drag clamping, snap, colors, layout, selection.
 * Kept in one module so we can unit-test all canvas behavior (e.g. resize handle bug).
 */

import { arcLabeledYamlMetrics } from "./arcLabeledYamlMetrics";
import { spinbox2EmittedRowHeight } from "./fontMetrics";

export type WidgetLike = {
  id: string;
  x: number;
  y: number;
  w?: number;
  h?: number;
  parent_id?: string;
  type?: string;
  props?: Record<string, unknown>;
  style?: Record<string, unknown>;
};

export function snap(n: number, grid: number): number {
  if (!grid || grid <= 1) return n;
  return Math.round(n / grid) * grid;
}

/**
 * Integer geometry for preview/layout parity with ESPHome (compiler emits int x/y/w/h).
 * Use for flex-derived positions and anywhere fractional math could drift from the device.
 */
export function layoutInt(n: number): number {
  return Math.round(n);
}

/** Match Python int() on model geometry (truncates toward zero; compiler uses int(w.get('x'), etc.). */
export function modelInt(n: number): number {
  const v = Number(n);
  return Number.isFinite(v) ? Math.trunc(v) : 0;
}

/** views.py::_project_display_dimensions — logical canvas = device.screen. */
export function projectDisplayDimensions(project: Record<string, unknown>): { w: number; h: number } {
  const dev = (project.device as Record<string, unknown> | undefined) || {};
  const scr = (dev.screen as Record<string, unknown> | undefined) || {};
  const sw = modelInt(Number(scr.width ?? 0));
  const sh = modelInt(Number(scr.height ?? 0));
  if (sw > 0 && sh > 0) return { w: sw, h: sh };
  const recipeId = String(
    ((project.hardware as Record<string, unknown> | undefined)?.recipe_id as string) ||
      (dev.hardware_recipe_id as string) ||
      ""
  );
  const m = /(\d{3,4})x(\d{3,4})/i.exec(recipeId);
  if (m) return { w: parseInt(m[1], 10), h: parseInt(m[2], 10) };
  return { w: 480, h: 320 };
}

/** views.py::_style_pad_lvgl — use for emit parity (not only padFromStyle Number paths). */
export function stylePadLvgl(style: Record<string, unknown> | null | undefined): { pl: number; pr: number; pt: number; pb: number } {
  const s = style || {};
  const pa = modelInt(Number(s.pad_all ?? 0));
  const one = (key: string): number => {
    const v = s[key];
    if (v === undefined || v === null) return pa;
    return modelInt(Number(v));
  };
  return { pl: one("pad_left"), pr: one("pad_right"), pt: one("pad_top"), pb: one("pad_bottom") };
}

/** views.py::_apply_align_lvgl — emitted origin in parent content space (integer //). */
export function applyAlignLvglEmit(
  xVal: number,
  yVal: number,
  wVal: number,
  hVal: number,
  align: string,
  parentW: number | null,
  parentH: number | null
): { x: number; y: number } {
  const a = String(align || "TOP_LEFT").trim().toUpperCase();
  if (!a || a === "TOP_LEFT" || parentW == null || parentH == null) return { x: xVal, y: yVal };
  const pw = Math.floor(parentW);
  const ph = Math.floor(parentH);
  const pw2 = Math.floor(pw / 2);
  const ph2 = Math.floor(ph / 2);
  const wv = Math.floor(wVal);
  const hv = Math.floor(hVal);
  const w2 = Math.floor(wVal / 2);
  const h2 = Math.floor(hVal / 2);
  if (a === "CENTER") return { x: xVal + w2 - pw2, y: yVal + h2 - ph2 };
  if (a === "TOP_MID") return { x: xVal + w2 - pw2, y: yVal };
  if (a === "TOP_RIGHT") return { x: xVal + wv - pw, y: yVal };
  if (a === "LEFT_MID") return { x: xVal, y: yVal + h2 - ph2 };
  if (a === "RIGHT_MID") return { x: xVal + wv - pw, y: yVal + h2 - ph2 };
  if (a === "BOTTOM_LEFT") return { x: xVal, y: yVal + hv - ph };
  if (a === "BOTTOM_MID") return { x: xVal + w2 - pw2, y: yVal + hv - ph };
  if (a === "BOTTOM_RIGHT") return { x: xVal + wv - pw, y: yVal + hv - ph };
  return { x: xVal, y: yVal };
}

/**
 * Konva id for the Transformer proxy on container/obj widgets that have children.
 * The real node's client rect includes visual overflow (e.g. arc_labeled labels), so the
 * Transformer would use the wrong box and resize/drag math overshoots; a w×h Rect with
 * this id is the transform target instead.
 */
export function containerTransformKonvaId(widgetId: string): string {
  const safe = String(widgetId || "w").replace(/[^a-zA-Z0-9_-]/g, "_");
  return `etd_tr_${safe}`;
}

/** Normalize color to CSS fill (templates use numeric 0xrrggbb). */
export function toFillColor(val: unknown, fallback: string): string {
  if (typeof val === "number" && val >= 0 && val <= 0xffffff) {
    return "#" + val.toString(16).padStart(6, "0");
  }
  if (typeof val === "string" && /^#?[0-9a-fA-F]{6}$/.test(val)) return val.startsWith("#") ? val : "#" + val;
  return fallback;
}

/** Parse pixel size from font id (e.g. montserrat_14 → 14, asset:file.ttf:16 → 16). */
export function fontSizeFromFontId(fontId: unknown): number | null {
  if (fontId == null || typeof fontId !== "string") return null;
  const s = String(fontId).trim();
  if (!s) return null;
  const assetMatch = /:(\d+)$/.exec(s);
  if (assetMatch) return parseInt(assetMatch[1], 10) || null;
  const underscoreMatch = /_(\d+)$/.exec(s);
  if (underscoreMatch) return parseInt(underscoreMatch[1], 10) || null;
  return null;
}

/** LVGL text_align + padding → layout for Konva Text. */
export function textLayoutFromWidget(
  ax: number,
  ay: number,
  width: number,
  height: number,
  props: Record<string, unknown> = {},
  style: Record<string, unknown> = {}
): { x: number; y: number; width: number; height: number; align: "left" | "center" | "right"; verticalAlign: "top" | "middle" | "bottom" } {
  const padLeft = Number(style.pad_all ?? style.pad_left ?? 0);
  const padRight = Number(style.pad_all ?? style.pad_right ?? 0);
  const padTop = Number(style.pad_all ?? style.pad_top ?? 0);
  const padBottom = Number(style.pad_all ?? style.pad_bottom ?? 0);
  const contentW = Math.max(0, width - padLeft - padRight);
  const contentH = Math.max(0, height - padTop - padBottom);
  const left = ax + padLeft;
  const top = ay + padTop;

  const textAlign = String(style.text_align ?? "LEFT").toUpperCase();
  let horizontal: "left" | "center" | "right";
  if (textAlign === "LEFT" || textAlign === "AUTO") horizontal = "left";
  else if (textAlign === "RIGHT") horizontal = "right";
  else horizontal = "center";

  const align = String(props.align ?? style.align ?? "TOP_LEFT").toUpperCase();
  const vertical: "top" | "middle" | "bottom" =
    align === "TOP_LEFT" || align === "TOP_MID" || align === "TOP_RIGHT"
      ? "top"
      : align === "BOTTOM_LEFT" || align === "BOTTOM_MID" || align === "BOTTOM_RIGHT"
        ? "bottom"
        : "middle";

  return { x: left, y: top, width: contentW, height: contentH, align: horizontal, verticalAlign: vertical };
}

export function safeWidgets(list: WidgetLike[] | null | undefined): WidgetLike[] {
  return (list || []).filter((w): w is WidgetLike => !!w && typeof w === "object" && w.id != null);
}

/** Flex layout positions for container.flex_* (read-only preview). */
export function computeLayoutPositions(widgets: WidgetLike[]): Map<string, { x: number; y: number }> {
  const list = safeWidgets(widgets);
  const byId = new Map<string, WidgetLike>();
  list.forEach((w) => byId.set(w.id, w));
  const children = new Map<string, WidgetLike[]>();
  list.forEach((w) => {
    if (w.parent_id) {
      let arr = children.get(w.parent_id);
      if (!arr) {
        arr = [];
        children.set(w.parent_id, arr);
      }
      arr.push(w);
    }
  });

  const pos = new Map<string, { x: number; y: number }>();
  function walk(parentId: string) {
    const parent = byId.get(parentId);
    if (!parent) return;
    const kids = children.get(parentId) || [];
    const layout = String((parent.props || {}).layout || "");
    if (!layout.startsWith("flex_")) return;
    const gap = Number((parent.props || {}).gap || 6);
    const pad = Number((parent.style || {}).pad_left || 0);
    let cx = parent.x + pad;
    let cy = parent.y + Number((parent.style || {}).pad_top || 0);
    const isRow = layout === "flex_row";
    kids.sort((a, b) => a.y - b.y || a.x - b.x || a.id.localeCompare(b.id));
    kids.forEach((k) => {
      pos.set(k.id, { x: layoutInt(cx), y: layoutInt(cy) });
      if (isRow) cx += (k.w || 0) + gap;
      else cy += (k.h || 0) + gap;
    });
    kids.forEach((k) => walk(k.id));
  }
  list.filter((w) => !w.parent_id).forEach((w) => walk(w.id));
  return pos;
}

/** Resize box: normalize negative width/height (Konva can pass when handle dragged past edge), then clamp to canvas. */
export function clampResizeBox(
  newBox: { x: number; y: number; width: number; height: number },
  canvasWidth: number,
  canvasHeight: number,
  minSize: number = 20
): { box: { x: number; y: number; width: number; height: number }; clamped: boolean } {
  let x = newBox.x;
  let y = newBox.y;
  let w = newBox.width;
  let h = newBox.height;
  if (w < 0) {
    x = x + w;
    w = -w;
  }
  if (h < 0) {
    y = y + h;
    h = -h;
  }
  const nx = Math.max(0, Math.min(canvasWidth - minSize, x));
  const ny = Math.max(0, Math.min(canvasHeight - minSize, y));
  const nw = Math.max(minSize, Math.min(w, canvasWidth - nx));
  const nh = Math.max(minSize, Math.min(h, canvasHeight - ny));
  const clamped = nx !== x || ny !== y || nw !== w || nh !== h;
  return { box: { x: nx, y: ny, width: nw, height: nh }, clamped };
}

/** Drag position: clamp so widget stays fully on canvas. */
export function clampDragPosition(
  posX: number,
  posY: number,
  widgetW: number,
  widgetH: number,
  canvasWidth: number,
  canvasHeight: number
): { x: number; y: number; atLimit: boolean } {
  const x = Math.max(0, Math.min(canvasWidth - widgetW, posX));
  const y = Math.max(0, Math.min(canvasHeight - widgetH, posY));
  return { x, y, atLimit: x !== posX || y !== posY };
}

/** Centered drag (when widget has transform origin center). */
export function clampDragPositionCentered(
  posX: number,
  posY: number,
  widgetW: number,
  widgetH: number,
  canvasWidth: number,
  canvasHeight: number
): { x: number; y: number; atLimit: boolean } {
  const halfW = widgetW / 2;
  const halfH = widgetH / 2;
  const x = Math.max(halfW, Math.min(canvasWidth - halfW, posX));
  const y = Math.max(halfH, Math.min(canvasHeight - halfH, posY));
  return { x, y, atLimit: x !== posX || y !== posY };
}

/** Which widget ids overlap the selection rectangle (box select). */
export function widgetsInSelectionRect(
  minX: number,
  maxX: number,
  minY: number,
  maxY: number,
  items: { id: string; ax: number; ay: number; w: number; h: number }[]
): string[] {
  const ids: string[] = [];
  for (const it of items) {
    const ww = it.w;
    const hh = it.h;
    if (!(it.ax + ww < minX || it.ax > maxX || it.ay + hh < minY || it.ay > maxY)) {
      ids.push(it.id);
    }
  }
  return ids;
}

/** LVGL-style padding from widget style (pad_all applies when side-specific missing). */
export function padFromStyle(style: Record<string, unknown> | undefined): {
  pl: number;
  pr: number;
  pt: number;
  pb: number;
} {
  const s = style || {};
  const pa = Number(s.pad_all ?? 0);
  return {
    pl: Number(s.pad_left ?? pa) || 0,
    pr: Number(s.pad_right ?? pa) || 0,
    pt: Number(s.pad_top ?? pa) || 0,
    pb: Number(s.pad_bottom ?? pa) || 0,
  };
}

/**
 * Screen-space top-left of the direct parent's content area (inside padding).
 * Model x/y for children are relative to this origin on device (LVGL).
 */
export function parentContentOriginScreen(
  w: WidgetLike,
  widgetById: Map<string, WidgetLike>,
  width: number,
  height: number
): { ax: number; ay: number } {
  if (!w.parent_id) return { ax: 0, ay: 0 };
  const p = widgetById.get(w.parent_id);
  if (!p) return { ax: 0, ay: 0 };
  const outer = absPos(p, widgetById, width, height);
  const { pl, pt } = stylePadLvgl(p.style as Record<string, unknown> | undefined);
  return { ax: outer.ax + pl, ay: outer.ay + pt };
}

/** Parent absolute position and size (for alignment). */
export function parentInfo(
  w: WidgetLike,
  widgetById: Map<string, WidgetLike>,
  width: number,
  height: number
): { ax: number; ay: number; pw: number; ph: number } {
  if (!w.parent_id) return { ax: 0, ay: 0, pw: width, ph: height };
  const p = widgetById.get(w.parent_id);
  if (!p) return { ax: 0, ay: 0, pw: width, ph: height };
  const grand = parentInfo(p, widgetById, width, height);
  const align = String((p.props || {}).align ?? "TOP_LEFT").toUpperCase();
  const px = modelInt(p.x ?? 0);
  const py = modelInt(p.y ?? 0);
  const pw = modelInt(p.w ?? 100);
  const ph = modelInt(p.h ?? 50);
  if (align === "TOP_LEFT" || !align) return { ax: grand.ax + px, ay: grand.ay + py, pw, ph };
  let pax = grand.ax;
  let pay = grand.ay;
  if (align === "CENTER") {
    pax = grand.ax + grand.pw / 2 - pw / 2;
    pay = grand.ay + grand.ph / 2 - ph / 2;
  } else if (align === "TOP_MID") pax = grand.ax + grand.pw / 2 - pw / 2;
  else if (align === "TOP_RIGHT") pax = grand.ax + grand.pw - pw;
  else if (align === "LEFT_MID") pay = grand.ay + grand.ph / 2 - ph / 2;
  else if (align === "RIGHT_MID") {
    pax = grand.ax + grand.pw - pw;
    pay = grand.ay + grand.ph / 2 - ph / 2;
  } else if (align === "BOTTOM_LEFT") pay = grand.ay + grand.ph - ph;
  else if (align === "BOTTOM_MID") {
    pax = grand.ax + grand.pw / 2 - pw / 2;
    pay = grand.ay + grand.ph - ph;
  } else if (align === "BOTTOM_RIGHT") {
    pax = grand.ax + grand.pw - pw;
    pay = grand.ay + grand.ph - ph;
  }
  return { ax: pax, ay: pay, pw, ph };
}

/**
 * Match views.py::_apply_align_lvgl / schema geometry: non-TOP_LEFT uses parent OUTER w×h.
 * Coordinates are in parent content space (caller adds parent content origin on screen).
 */
export function lvglEmittedOriginInParent(
  x: number,
  y: number,
  wVal: number,
  hVal: number,
  align: string,
  parentOw: number | null,
  parentOh: number | null
): { x: number; y: number } {
  return applyAlignLvglEmit(
    modelInt(x ?? 0),
    modelInt(y ?? 0),
    modelInt(wVal ?? 100),
    modelInt(hVal ?? 50),
    align,
    parentOw,
    parentOh
  );
}

/** Inverse of lvglEmittedOriginInParent: screen-emitted TL in parent content → model top-left x,y. */
export function modelTopLeftFromEmittedOrigin(
  lvx: number,
  lvy: number,
  wVal: number,
  hVal: number,
  align: string,
  parentOw: number | null,
  parentOh: number | null
): { x: number; y: number } {
  const a = String(align || "TOP_LEFT").trim().toUpperCase();
  if (!a || a === "TOP_LEFT" || parentOw == null || parentOh == null) return { x: lvx, y: lvy };
  const pw = Math.floor(parentOw);
  const ph = Math.floor(parentOh);
  const pw2 = Math.floor(pw / 2);
  const ph2 = Math.floor(ph / 2);
  const wv = Math.floor(wVal);
  const hv = Math.floor(hVal);
  const w2 = Math.floor(wVal / 2);
  const h2 = Math.floor(hVal / 2);
  if (a === "CENTER") return { x: lvx - w2 + pw2, y: lvy - h2 + ph2 };
  if (a === "TOP_MID") return { x: lvx - w2 + pw2, y: lvy };
  if (a === "TOP_RIGHT") return { x: lvx - wv + pw, y: lvy };
  if (a === "LEFT_MID") return { x: lvx, y: lvy - h2 + ph2 };
  if (a === "RIGHT_MID") return { x: lvx - wv + pw, y: lvy - h2 + ph2 };
  if (a === "BOTTOM_LEFT") return { x: lvx, y: lvy - hv + ph };
  if (a === "BOTTOM_MID") return { x: lvx - w2 + pw2, y: lvy - hv + ph };
  if (a === "BOTTOM_RIGHT") return { x: lvx - wv + pw, y: lvy - hv + ph };
  return { x: lvx, y: lvy };
}

/** Single widget: page-absolute YAML rect + walk state (views.py layout_audit walk step). */
export type YamlPageEmit = {
  yaml_rect_page: { x: number; y: number; w: number; h: number };
  outer_x: number;
  outer_y: number;
  model_rect: { x: number; y: number; w: number; h: number };
  note: string | null;
};

/**
 * One compiler layout-audit step: child `w` inside parent whose YAML outer top-left is (parentOuterPageX,Y).
 * `pfullW/H` = parent model outer size (int). Canvas, box-select, and layout_audit must use this only.
 */
export function yamlRectPageForChild(
  w: WidgetLike,
  parentOuterPageX: number,
  parentOuterPageY: number,
  parent: WidgetLike | null,
  pfullW: number,
  pfullH: number
): YamlPageEmit {
  const pad = parent ? stylePadLvgl(parent.style as Record<string, unknown> | undefined) : { pl: 0, pr: 0, pt: 0, pb: 0 };
  const contentOx = parentOuterPageX + pad.pl;
  const contentOy = parentOuterPageY + pad.pt;
  const x0 = modelInt(w.x ?? 0);
  const y0 = modelInt(w.y ?? 0);
  const ww = modelInt(w.w ?? 100);
  const hh = modelInt(w.h ?? 50);
  const props = w.props || {};
  const align = String(props.align ?? "TOP_LEFT").trim().toUpperCase();
  const { x: xa, y: ya } = applyAlignLvglEmit(x0, y0, ww, hh, align, pfullW, pfullH);
  const t = String(w.type || "");

  if (t === "arc_labeled") {
    const met = arcLabeledYamlMetrics(w, pfullW, pfullH);
    const ox = contentOx + met.x_val - met.arc_off_x;
    const oy = contentOy + met.y_val - met.arc_off_y;
    const yaml = { x: ox, y: oy, w: met.container_w, h: met.container_h };
    const note = `YAML wrapper ${met.container_w}×${met.container_h} vs model ${ww}×${hh}; place siblings using expanded footprint or extra gap`;
    return {
      yaml_rect_page: yaml,
      outer_x: ox,
      outer_y: oy,
      model_rect: { x: x0, y: y0, w: ww, h: hh },
      note,
    };
  }
  if (t.toLowerCase() === "spinbox2") {
    const rowH = spinbox2EmittedRowHeight(w);
    const ox = contentOx + xa;
    const oy = contentOy + ya;
    const note = rowH !== hh ? `YAML height ${rowH}px (model h ${hh}px)` : null;
    return {
      yaml_rect_page: { x: ox, y: oy, w: ww, h: rowH },
      outer_x: ox,
      outer_y: oy,
      model_rect: { x: x0, y: y0, w: ww, h: hh },
      note,
    };
  }
  const ox = contentOx + xa;
  const oy = contentOy + ya;
  return {
    yaml_rect_page: { x: ox, y: oy, w: ww, h: hh },
    outer_x: ox,
    outer_y: oy,
    model_rect: { x: x0, y: y0, w: ww, h: hh },
    note: null,
  };
}

/** Full page coordinates for `w` (recursive parent chain). Same as walking layout_audit from root. */
export function yamlRectPageForWidget(w: WidgetLike, widgetById: Map<string, WidgetLike>, dispW: number, dispH: number): YamlPageEmit {
  if (!w.parent_id) {
    return yamlRectPageForChild(w, 0, 0, null, dispW, dispH);
  }
  const p = widgetById.get(w.parent_id);
  if (!p) {
    return yamlRectPageForChild(w, 0, 0, null, dispW, dispH);
  }
  const parentEmit = yamlRectPageForWidget(p, widgetById, dispW, dispH);
  const pfullW = modelInt(p.w ?? 100);
  const pfullH = modelInt(p.h ?? 50);
  return yamlRectPageForChild(w, parentEmit.outer_x, parentEmit.outer_y, p, pfullW, pfullH);
}

/** Box select / Canvas page placement: alias for yaml_rect_page (device = compiler). */
export function widgetFootprintForSelection(
  w: WidgetLike,
  widgetById: Map<string, WidgetLike>,
  width: number,
  height: number
): { ax: number; ay: number; w: number; h: number } {
  const e = yamlRectPageForWidget(w, widgetById, width, height);
  const r = e.yaml_rect_page;
  return { ax: r.x, ay: r.y, w: r.w, h: r.h };
}

/** Widget top-left in canvas coords (for rendering and hit-test). */
export function absPos(
  w: WidgetLike,
  widgetById: Map<string, WidgetLike>,
  width: number,
  height: number
): { ax: number; ay: number } {
  const { ax: pax, ay: pay, pw, ph } = parentInfo(w, widgetById, width, height);
  let baseAx = pax;
  let baseAy = pay;
  if (w.parent_id) {
    const par = widgetById.get(w.parent_id);
    if (par) {
      const { pl, pt } = stylePadLvgl(par.style as Record<string, unknown> | undefined);
      baseAx = pax + pl;
      baseAy = pay + pt;
    }
  }
  const align = String((w.props || {}).align ?? "TOP_LEFT").toUpperCase();
  const ww = modelInt(w.w ?? 100);
  const hh = modelInt(w.h ?? 50);
  const em = applyAlignLvglEmit(modelInt(w.x ?? 0), modelInt(w.y ?? 0), ww, hh, align, pw, ph);
  return { ax: baseAx + em.x, ay: baseAy + em.y };
}
