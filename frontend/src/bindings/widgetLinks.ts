/**
 * Resolve which project.links[] rows apply to a widget for Binding Builder / UI.
 * YAML import can produce interval links with empty target and widget ids under source.updates[].
 */

export type DisplayLinkRow = {
  /** Index in project.links */
  globalIndex: number;
  link: Record<string, unknown>;
  /** When set, this row is one slice of an interval link (source.updates[i]). */
  intervalUpdateIndex?: number;
};

export function displayLinkRowsForWidget(links: unknown[] | undefined, widgetId: string): DisplayLinkRow[] {
  const wid = String(widgetId || "").trim();
  const rows: DisplayLinkRow[] = [];
  if (!wid || !Array.isArray(links)) return rows;

  links.forEach((ln, globalIndex) => {
    if (!ln || typeof ln !== "object") return;
    const link = ln as Record<string, unknown>;
    const tgt = link.target as Record<string, unknown> | undefined;
    const tw = String(tgt?.widget_id || "").trim();
    if (tw === wid) {
      rows.push({ globalIndex, link });
      return;
    }
    const src = link.source as Record<string, unknown> | undefined;
    if (String(src?.type || "").trim() === "interval" && Array.isArray(src?.updates)) {
      (src.updates as unknown[]).forEach((u, intervalUpdateIndex) => {
        if (!u || typeof u !== "object") return;
        const uw = String((u as Record<string, unknown>).widget_id || "").trim();
        if (uw === wid) rows.push({ globalIndex, link, intervalUpdateIndex });
      });
    }
  });
  return rows;
}
