/**
 * Compiler parity: _layout_audit_for_project using the same walk as canvasUtils.yamlRectPageForChild.
 */
import {
  modelInt,
  projectDisplayDimensions,
  yamlRectPageForChild,
  type WidgetLike,
} from "./canvasUtils";

export type LayoutAuditRect = { x: number; y: number; w: number; h: number };

export type LayoutAuditEntry = {
  id: string;
  type: string;
  parent_id: string | null;
  model_rect: LayoutAuditRect;
  yaml_rect_page: LayoutAuditRect;
  note: string | null;
};

export type LayoutAuditResult = {
  page_index: number;
  display: { w: number; h: number };
  widgets: LayoutAuditEntry[];
  overlaps: { a: string; b: string; intersection_px: number }[];
  notes: string[];
};

function widgetLikeFromRaw(w: Record<string, unknown>): WidgetLike {
  return {
    id: String(w.id || ""),
    x: Number(w.x ?? 0),
    y: Number(w.y ?? 0),
    w: Number(w.w ?? 100),
    h: Number(w.h ?? 50),
    parent_id: w.parent_id ? String(w.parent_id) : undefined,
    type: String(w.type || ""),
    props: (w.props as Record<string, unknown>) || {},
    style: (w.style as Record<string, unknown>) || {},
  };
}

function computeOverlaps(entries: LayoutAuditEntry[]): LayoutAuditResult["overlaps"] {
  const overlaps: LayoutAuditResult["overlaps"] = [];
  for (let i = 0; i < entries.length; i++) {
    const a = entries[i];
    const ra = a.yaml_rect_page;
    for (let j = i + 1; j < entries.length; j++) {
      const b = entries[j];
      const rb = b.yaml_rect_page;
      if (ra.x < rb.x + rb.w && ra.x + ra.w > rb.x && ra.y < rb.y + rb.h && ra.y + ra.h > rb.y) {
        const ix0 = Math.max(ra.x, rb.x);
        const iy0 = Math.max(ra.y, rb.y);
        const ix1 = Math.min(ra.x + ra.w, rb.x + rb.w);
        const iy1 = Math.min(ra.y + ra.h, rb.y + rb.h);
        const area = Math.max(0, ix1 - ix0) * Math.max(0, iy1 - iy0);
        overlaps.push({ a: a.id, b: b.id, intersection_px: area });
      }
    }
  }
  return overlaps;
}

export { projectDisplayDimensions } from "./canvasUtils";

export function layoutAuditForProject(project: Record<string, unknown>, pageIndex = 0): LayoutAuditResult {
  const pages = (project.pages as unknown[]) || [];
  if (!Array.isArray(pages) || pageIndex < 0 || pageIndex >= pages.length) {
    return { page_index: pageIndex, display: { w: 0, h: 0 }, widgets: [], overlaps: [], notes: [] };
  }
  const page = pages[pageIndex] as Record<string, unknown>;
  const raw = (page.widgets as unknown[]) || [];
  const allWidgets: Record<string, unknown>[] = [];
  for (const w of raw) {
    if (!w || typeof w !== "object") continue;
    const o = w as Record<string, unknown>;
    const id = String(o.id || "").trim();
    if (!id || id.startsWith("screensaver_")) continue;
    allWidgets.push(o);
  }

  const disp = projectDisplayDimensions(project);
  const kids = new Map<string, Record<string, unknown>[]>();
  for (const w of allWidgets) {
    const pid = String(w.parent_id || "");
    if (pid) {
      let arr = kids.get(pid);
      if (!arr) {
        arr = [];
        kids.set(pid, arr);
      }
      arr.push(w);
    }
  }

  const entries: LayoutAuditEntry[] = [];

  const walk = (
    w: Record<string, unknown>,
    parentOuterX: number,
    parentOuterY: number,
    parent: Record<string, unknown> | null,
    pfullW: number,
    pfullH: number
  ) => {
    const wl = widgetLikeFromRaw(w);
    const parentWl = parent ? widgetLikeFromRaw(parent) : null;
    const r = yamlRectPageForChild(wl, parentOuterX, parentOuterY, parentWl, pfullW, pfullH);
    entries.push({
      id: wl.id,
      type: wl.type || "",
      parent_id: wl.parent_id ?? null,
      model_rect: r.model_rect,
      yaml_rect_page: r.yaml_rect_page,
      note: r.note,
    });
    const pwI = modelInt(wl.w ?? 100);
    const phI = modelInt(wl.h ?? 50);
    for (const c of kids.get(wl.id) || []) {
      walk(c, r.outer_x, r.outer_y, w, pwI, phI);
    }
  };

  const roots = allWidgets.filter((x) => !x.parent_id);
  for (const root of roots) {
    walk(root, 0, 0, null, disp.w, disp.h);
  }

  return {
    page_index: pageIndex,
    display: disp,
    widgets: entries,
    overlaps: computeOverlaps(entries),
    notes: [
      "yaml_rect_page: page-absolute box as emitted (padding + align + composite widgets).",
      "arc_labeled and spinbox2 often differ from model w×h; overlaps here usually match on-device overlap.",
    ],
  };
}
