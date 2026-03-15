

export async function listRecipes(): Promise<any[]> {
  const r = await fetch("/api/esptoolkit/recipes");
  if (!r.ok) throw new Error(`recipes failed: ${r.status}`);
  const data = await r.json();
  return data.recipes || [];
}

export type CompileWarning = { type: string; section?: string; widget_id?: string };

export type CompileResult = { yaml: string; warnings?: CompileWarning[] };

export async function compileYaml(deviceId: string, project?: any): Promise<CompileResult> {
  const r = await fetch(`/api/esptoolkit/devices/${deviceId}/compile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(project ? { project } : {}),
  });
  if (!r.ok) throw new Error(`compile failed: ${r.status}`);
  const data = await r.json();
  return { yaml: data.yaml ?? "", warnings: data.warnings ?? [] };
}

/** Remove LVGL component blocks that reference deleted widgets. Returns cleaned project and list of removed refs. */
export async function cleanupOrphanedComponents(project: any): Promise<{ ok: boolean; project: any; removed: Array<{ section: string; widget_id: string }> }> {
  const r = await fetch("/api/esptoolkit/project/cleanup_orphans", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data?.ok !== true) throw new Error(data?.error ?? `cleanup failed: ${r.status}`);
  return { ok: true, project: data.project, removed: data.removed ?? [] };
}

/** Per-event snippet from widget YAML preview. source: "empty" | "auto" | "edited" */
export type WidgetYamlEventSnippet = { yaml: string; source: string };

/** Preview the exact YAML the compiler would emit for one widget (props, style, action bindings). Returns yaml and per-event snippets. */
export async function previewWidgetYaml(
  project: any,
  widgetId: string,
  pageIndex: number
): Promise<{ yaml: string; event_snippets: Record<string, WidgetYamlEventSnippet> }> {
  const r = await fetch("/api/esptoolkit/preview-widget-yaml", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project, widget_id: widgetId, page_index: pageIndex }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data?.ok === false) throw new Error(data?.error || `preview failed: ${r.status}`);
  return {
    yaml: data.yaml ?? "",
    event_snippets: data.event_snippets ?? {},
  };
}

/** Lightweight YAML syntax check only (no ESPHome). */
export async function parseYamlSyntax(yamlContent: string): Promise<{ ok: boolean; error?: string; line?: number }> {
  const base = typeof window !== "undefined" && window.location?.origin ? window.location.origin : "";
  const r = await fetch(`${base}/api/esptoolkit/parse_yaml`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ yaml: yamlContent }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return { ok: false, error: data?.error ?? `parse failed: ${r.status}` };
  return { ok: data.ok === true, error: data.error, line: data.line };
}

export type ValidateYamlResult = { ok: boolean; stdout?: string; stderr?: string; error?: string; returncode?: number };

export async function validateYaml(yamlText: string, entryId?: string): Promise<ValidateYamlResult> {
  const url = new URL("/api/esptoolkit/validate_yaml", window.location.origin);
  if (entryId) url.searchParams.set("entry_id", entryId);
  const r = await fetch(url.toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ yaml: yamlText }),
  });
  const data = await r.json().catch(() => ({}));
  return {
    ok: data.ok === true,
    stdout: data.stdout ?? "",
    stderr: data.stderr ?? "",
    error: data.error,
    returncode: data.returncode,
  };
}



export async function listEntities() {
  const r = await fetch('/api/esptoolkit/entities');
  if (!r.ok) throw new Error('Failed to list entities');
  return await r.json();
}

export async function getEntity(entity_id: string) {
  const safe = entity_id.replace('.', ',');
  const r = await fetch(`/api/esptoolkit/entity/${safe}`);
  if (!r.ok) throw new Error('Failed to get entity');
  return await r.json();
}


export async function importRecipe(yamlText: string, label?: string, id?: string): Promise<any> {
  const r = await fetch("/api/esptoolkit/recipes/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ yaml: yamlText, label, id }),
  });
  const data = await r.json().catch(()=>({}));
  if (!r.ok || data?.ok === false) {
    throw new Error(data?.error ? `${data.error}${data.detail ? `: ${data.detail}` : ""}` : `import failed: ${r.status}`);
  }
  return data;
}

export async function updateRecipeLabel(recipe_id: string, label: string): Promise<void> {
  const r = await fetch(`/api/esptoolkit/recipes/user/${encodeURIComponent(recipe_id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  });
  const data = await r.json().catch(()=>({}));
  if (!r.ok || data?.ok === false) {
    throw new Error(data?.error ? `${data.error}${data.detail ? `: ${data.detail}` : ""}` : `update failed: ${r.status}`);
  }
}

export async function deleteRecipe(recipe_id: string): Promise<void> {
  const r = await fetch(`/api/esptoolkit/recipes/user/${encodeURIComponent(recipe_id)}`, {
    method: "DELETE",
  });
  const data = await r.json().catch(()=>({}));
  if (!r.ok || data?.ok === false) {
    throw new Error(data?.error ? `${data.error}${data.detail ? `: ${data.detail}` : ""}` : `delete failed: ${r.status}`);
  }
}

export async function cloneRecipe(source_id: string, label?: string, id?: string): Promise<any> {
  const r = await fetch('/api/esptoolkit/recipes/clone', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_id, label, id }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data?.ok === false) {
    throw new Error(data?.error ? `${data.error}${data.detail ? `: ${data.detail}` : ''}` : `clone failed: ${r.status}`);
  }
  return data;
}

export async function exportRecipe(recipe_id: string): Promise<any> {
  const r = await fetch(`/api/esptoolkit/recipes/${encodeURIComponent(recipe_id)}/export`);
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data?.ok === false) {
    throw new Error(data?.error ? `${data.error}${data.detail ? `: ${data.detail}` : ''}` : `export failed: ${r.status}`);
  }
  return data;
}

// --- Custom cards (v1: card = snapshot of current page) ---

export async function listCards(): Promise<{ id: string; name: string; description: string; device_types: string[] }[]> {
  const r = await fetch("/api/esptoolkit/cards");
  if (!r.ok) throw new Error(`cards list failed: ${r.status}`);
  const data = await r.json();
  return data.cards || [];
}

export async function getCard(cardId: string): Promise<any> {
  const r = await fetch(`/api/esptoolkit/cards/${encodeURIComponent(cardId)}`);
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(d?.error === "not_found" ? "Card not found" : `get card failed: ${r.status}`);
  }
  const data = await r.json();
  return data.card;
}

export async function saveCard(definition: {
  id?: string;
  name: string;
  description?: string;
  device_types: string[];
  widgets: any[];
  links: any[];
  action_bindings?: any[];
  scripts?: any[];
}): Promise<{ ok: boolean; id: string }> {
  const r = await fetch("/api/esptoolkit/cards", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(definition),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data?.ok === false) {
    throw new Error(data?.error ? String(data.error).replace(/_/g, " ") : `save card failed: ${r.status}`);
  }
  return { ok: true, id: data.id };
}

export async function deleteCard(cardId: string): Promise<void> {
  const r = await fetch(`/api/esptoolkit/cards/${encodeURIComponent(cardId)}`, { method: "DELETE" });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data?.ok === false) {
    throw new Error(data?.error ? String(data.error) : `delete card failed: ${r.status}`);
  }
}
