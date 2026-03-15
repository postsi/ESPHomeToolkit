/** Sections defaults for Components panel (Design v2). When deviceId and entryId are provided, backend substitutes __ETD_DEVICE_NAME__. */
export async function getSectionsDefaults(
  project: any,
  recipeId?: string,
  deviceId?: string | null,
  entryId?: string | null
): Promise<{
  sections: Record<string, string>;
  default_sections: Record<string, string>;
  section_states: Record<string, string>;
  compiler_owned: string[];
  categories: Record<string, string[]>;
  keys_with_additions: string[];
}> {
  const body: Record<string, unknown> = {
    project,
    recipe_id: recipeId ?? (project?.device?.hardware_recipe_id ?? project?.hardware?.recipe_id ?? "") ?? "",
  };
  if (deviceId) body.device_id = deviceId;
  if (entryId) body.entry_id = entryId;
  const r = await fetch("/api/esptoolkit/sections/defaults", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data?.ok === false) throw new Error(data?.error ?? `sections/defaults failed: ${r.status}`);
  const cat = data.categories ?? {};
  const categories: Record<string, string[]> = {};
  for (const [k, v] of Object.entries(cat)) {
    categories[k] = Array.isArray(v) ? v : [];
  }
  const keys_with_additions = Array.isArray(data.keys_with_additions) ? data.keys_with_additions : [];
  const default_sections = (data.default_sections && typeof data.default_sections === "object") ? data.default_sections : {};
  const section_states = (data.section_states && typeof data.section_states === "object") ? data.section_states : {};
  const compiler_owned = Array.isArray(data.compiler_owned) ? data.compiler_owned : [];
  return { sections: data.sections ?? {}, default_sections, section_states, compiler_owned, categories, keys_with_additions };
}

/** Design v2: save section contents to project.esphome_yaml. Returns updated project. */
export async function saveSections(project: any, sections: Record<string, string>): Promise<{ project: any }> {
  const r = await fetch("/api/esptoolkit/sections/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project, sections }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data?.ok === false) throw new Error(data?.error ?? `sections/save failed: ${r.status}`);
  return { project: data.project ?? project };
}
