/**
 * Normalize widgets when saving a page as a user-defined entity widget:
 * multiple top-level roots are wrapped in one container with relative child coords.
 * A single existing tree (one root container + descendants) is left as-is.
 */
export function normalizeWidgetsForEntityWidgetExport(widgets: any[]): any[] {
  const clone = JSON.parse(JSON.stringify(widgets ?? [])) as any[];
  if (clone.length === 0) return clone;

  const ids = new Set(clone.map((w) => w?.id).filter(Boolean));
  const roots = clone.filter((w) => w && (!w.parent_id || !ids.has(w.parent_id)));
  if (roots.length <= 1) {
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
  return [root, ...reparented, ...rest];
}
