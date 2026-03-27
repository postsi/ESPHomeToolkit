import { arcLabeledVisualOverflowPad } from "./arcLabeledBounds";

/**
 * Resize a container to the axis-aligned bounding box of its direct children,
 * and shift those children so the tight box starts at (0,0). Mutates `widgets`.
 * arc_labeled widgets use extra margin so scale labels/ticks outside w×h are not clipped by the card.
 */
export function fitContainerToDirectChildrenBounds(widgets: any[], rootId: string): void {
  const root = widgets.find((w) => w && w.id === rootId && (w.type === "container" || w.type === "obj"));
  if (!root) return;
  const children = widgets.filter((w) => w && w.parent_id === rootId);
  if (!children.length) return;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const c of children) {
    const x = Number(c.x ?? 0);
    const y = Number(c.y ?? 0);
    const rw = Number(c.w ?? 0);
    const rh = Number(c.h ?? 0);
    let left = x;
    let top = y;
    let right = x + rw;
    let bottom = y + rh;
    if (c.type === "arc_labeled") {
      const pad = arcLabeledVisualOverflowPad(c);
      left -= pad.left;
      top -= pad.top;
      right += pad.right;
      bottom += pad.bottom;
    }
    minX = Math.min(minX, left);
    minY = Math.min(minY, top);
    maxX = Math.max(maxX, right);
    maxY = Math.max(maxY, bottom);
  }
  if (!Number.isFinite(minX) || !Number.isFinite(maxX)) return;
  const bw = Math.max(1, maxX - minX);
  const bh = Math.max(1, maxY - minY);
  for (const c of children) {
    c.x = Number(c.x ?? 0) - minX;
    c.y = Number(c.y ?? 0) - minY;
  }
  root.w = bw;
  root.h = bh;
}

function _isContainerLike(t: unknown): boolean {
  const s = String(t || "").toLowerCase();
  return s === "container" || s === "obj";
}

/**
 * Bottom-up fit for nested entity widgets: resize every container/obj in a tree
 * to direct-children bounds, starting from deepest descendants.
 */
export function fitContainerTreeToDescendantBounds(widgets: any[], rootId: string): void {
  const byParent = new Map<string, any[]>();
  for (const w of widgets || []) {
    const pid = String(w?.parent_id || "");
    if (!pid) continue;
    const arr = byParent.get(pid) || [];
    arr.push(w);
    byParent.set(pid, arr);
  }
  const visit = (id: string) => {
    const kids = byParent.get(id) || [];
    for (const k of kids) {
      if (_isContainerLike(k?.type) && k?.id) visit(String(k.id));
    }
    fitContainerToDirectChildrenBounds(widgets, id);
  };
  visit(String(rootId || ""));
}

/**
 * Re-fit only descendant container/obj nodes under a root (leave root size unchanged).
 * Useful for "frame-only resize": user changes outer card shell, while stale inner clipping
 * containers are normalized to their own children so labels are not cut off.
 */
export function fitDescendantContainerTrees(widgets: any[], rootId: string): void {
  const byParent = new Map<string, any[]>();
  for (const w of widgets || []) {
    const pid = String(w?.parent_id || "");
    if (!pid) continue;
    const arr = byParent.get(pid) || [];
    arr.push(w);
    byParent.set(pid, arr);
  }
  const topKids = byParent.get(String(rootId || "")) || [];
  for (const k of topKids) {
    if (_isContainerLike(k?.type) && k?.id) {
      fitContainerTreeToDescendantBounds(widgets, String(k.id));
    }
  }
}

/**
 * Normalize widgets when saving a page as a user-defined entity widget:
 * multiple top-level roots are wrapped in one container with relative child coords.
 * A single existing tree (one root container) gets its root sized to child bounds.
 */
export function normalizeWidgetsForEntityWidgetExport(widgets: any[]): any[] {
  const clone = JSON.parse(JSON.stringify(widgets ?? [])) as any[];
  if (clone.length === 0) return clone;

  const ids = new Set(clone.map((w) => w?.id).filter(Boolean));
  const roots = clone.filter((w) => w && (!w.parent_id || !ids.has(w.parent_id)));
  if (roots.length === 1) {
    const r = roots[0];
    if (_isContainerLike(r.type)) {
      fitContainerTreeToDescendantBounds(clone, r.id);
    }
    return clone;
  }
  if (roots.length < 1) {
    return clone;
  }

  const topIds = new Set(roots.map((w) => w.id));
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const w of roots) {
    const wx = Number(w.x ?? 0);
    const wy = Number(w.y ?? 0);
    const ww = Number(w.w ?? 0);
    const hh = Number(w.h ?? 0);
    minX = Math.min(minX, wx);
    minY = Math.min(minY, wy);
    maxX = Math.max(maxX, wx + ww);
    maxY = Math.max(maxY, wy + hh);
  }
  const gw = Math.max(1, maxX - minX);
  const gh = Math.max(1, maxY - minY);
  const rootId = `entity_saved_${Math.random().toString(16).slice(2, 10)}`;
  const root: any = {
    id: rootId,
    type: "container",
    x: minX,
    y: minY,
    w: gw,
    h: gh,
    props: {},
    style: { bg_color: 0x1e1e1e, radius: 8 },
  };
  const reparented = roots.map((w) => ({
    ...w,
    parent_id: rootId,
    x: Number(w.x ?? 0) - minX,
    y: Number(w.y ?? 0) - minY,
  }));
  const rest = clone.filter((w) => !topIds.has(w.id));
  const merged = [root, ...reparented, ...rest];
  fitContainerTreeToDescendantBounds(merged, rootId);
  return merged;
}
