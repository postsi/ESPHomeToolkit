/**
 * Entity search for Binding Builder: word-based matching so "shed" matches light.shed, sensor.shed_temperature, etc.
 */

/** Match entity against binding search: query is split into words; entity matches if entity_id or friendly_name contains every word (case-insensitive). E.g. "shed" matches light.shed, sensor.shed_temperature; "shed light" matches entities containing both. */
export function entityMatchesBindingSearch(
  entity: { entity_id?: string; friendly_name?: string },
  query: string
): boolean {
  const q = String(query || "").trim();
  if (!q) return true;
  const words = q.toLowerCase().split(/\s+/).filter((w) => w.length > 0);
  const eid = String(entity?.entity_id ?? "").toLowerCase();
  const name = String(entity?.friendly_name ?? "").toLowerCase();
  const searchText = eid + " " + name;
  return words.every((w) => searchText.includes(w));
}
