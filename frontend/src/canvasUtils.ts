/**
 * Pure helpers for Canvas: resize/drag clamping, snap, colors, layout, selection.
 * Kept in one module so we can unit-test all canvas behavior (e.g. resize handle bug).
 */

export type WidgetLike = {
  id: string;
  x: number;
  y: number;
  w?: number;
  h?: number;
  parent_id?: string;
  props?: Record<string, unknown>;
  style?: Record<string, unknown>;
};

export function snap(n: number, grid: number): number {
  if (!grid || grid <= 1) return n;
  return Math.round(n / grid) * grid;
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
      pos.set(k.id, { x: cx, y: cy });
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
  const px = p.x;
  const py = p.y;
  const pw = p.w || 100;
  const ph = p.h || 50;
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

/** Widget top-left in canvas coords (for rendering and hit-test). */
export function absPos(
  w: WidgetLike,
  widgetById: Map<string, WidgetLike>,
  width: number,
  height: number
): { ax: number; ay: number } {
  const { ax: pax, ay: pay, pw, ph } = parentInfo(w, widgetById, width, height);
  const align = String((w.props || {}).align ?? "TOP_LEFT").toUpperCase();
  const x = w.x;
  const y = w.y;
  const ww = w.w || 100;
  const hh = w.h || 50;
  if (align === "TOP_LEFT" || !align) return { ax: pax + x, ay: pay + y };
  const pw2 = pw / 2;
  const ph2 = ph / 2;
  let ox = 0;
  let oy = 0;
  if (align === "CENTER") {
    ox = x + ww / 2 - pw2;
    oy = y + hh / 2 - ph2;
  } else if (align === "TOP_MID") ox = x + ww / 2 - pw2;
  else if (align === "TOP_RIGHT") ox = x + ww - pw;
  else if (align === "LEFT_MID") oy = y + hh / 2 - ph2;
  else if (align === "RIGHT_MID") {
    ox = x + ww - pw;
    oy = y + hh / 2 - ph2;
  } else if (align === "BOTTOM_LEFT") oy = y + hh - ph;
  else if (align === "BOTTOM_MID") {
    ox = x + ww / 2 - pw2;
    oy = y + hh - ph;
  } else if (align === "BOTTOM_RIGHT") {
    ox = x + ww - pw;
    oy = y + hh - ph;
  }
  const centerX = pax + pw2 + ox;
  const centerY = pay + ph2 + oy;
  return { ax: centerX - ww / 2, ay: centerY - hh / 2 };
}
