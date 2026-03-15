/**
 * Helpers for project.sections: widget ref sync and widget id collection.
 * Used by Binding Builder (rename widget → update sections) and Create component.
 */

export const SECTION_KEYS_WITH_WIDGET_REF = [
  "switch",
  "light",
  "sensor",
  "number",
  "select",
  "text_sensor",
  "binary_sensor",
] as const;

/** Update project.sections to replace widget: oldId with widget: newId (and id: oldId with id: newId in same block when present). */
export function updateSectionsWidgetRef(
  sections: Record<string, string>,
  oldId: string,
  newId: string
): void {
  if (!sections || !oldId || !newId || oldId === newId) return;
  for (const key of SECTION_KEYS_WITH_WIDGET_REF) {
    const content = sections[key];
    if (!content || typeof content !== "string") continue;
    const widgetRe = new RegExp(
      `(widget:\\s*)(["']?)${oldId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\2`,
      "g"
    );
    let updated = content.replace(widgetRe, `$1$2${newId}$2`);
    const idRe = new RegExp(
      `^(\\s*id:\\s*)(["']?)${oldId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\2\\s*$`,
      "gm"
    );
    updated = updated.replace(idRe, `$1$2${newId}$2`);
    if (updated !== content) sections[key] = updated;
  }
}

/** Recursively collect all widget ids from a list of widgets (including nested widgets). */
export function collectWidgetIds(list: any[]): Set<string> {
  const out = new Set<string>();
  for (const w of list || []) {
    if (w == null || typeof w !== "object") continue;
    if ((w as any).id) out.add((w as any).id);
    if (Array.isArray((w as any).widgets)) {
      for (const id of collectWidgetIds((w as any).widgets)) out.add(id);
    }
  }
  return out;
}
