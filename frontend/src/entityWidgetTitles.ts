/** Built-in entity-widget templates use this title prefix in CONTROL_TEMPLATES (palette + wizard). */
export const ENTITY_WIDGET_TITLE_PREFIX = "Entity • ";
export const ENTITY_WIDGET_DISABLED_PREFIX = "Entity disabled • ";

export function isEntityWidgetTemplateTitle(title: unknown): boolean {
  const t = String(title ?? "");
  return t.startsWith(ENTITY_WIDGET_TITLE_PREFIX) && !t.startsWith(ENTITY_WIDGET_DISABLED_PREFIX);
}

/** User-saved definitions from the HA API (drag / wizard template id). */
export const SAVED_ENTITY_WIDGET_PREFIX = "entity:";

export function isSavedEntityWidgetTemplateId(templateId: string): boolean {
  return templateId.startsWith(SAVED_ENTITY_WIDGET_PREFIX);
}

export function savedEntityWidgetStorageId(templateId: string): string {
  if (!templateId.startsWith(SAVED_ENTITY_WIDGET_PREFIX)) {
    throw new Error(`Expected template id to start with ${SAVED_ENTITY_WIDGET_PREFIX}`);
  }
  return templateId.slice(SAVED_ENTITY_WIDGET_PREFIX.length);
}
