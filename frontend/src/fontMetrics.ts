/**
 * Mirror `custom_components/esptoolkit/api/views.py::_font_px_from_id` so
 * spinbox2 row height and similar layout match compiled YAML (not preview-only font sizes).
 */
export function fontPxFromId(fontId: string | number | undefined | null, defaultPx = 14): number {
  const s = String(fontId ?? "").trim();
  if (!s) return defaultPx;
  const assetM = s.match(/:(\d{1,3})$/);
  if (assetM) {
    const n = parseInt(assetM[1]!, 10);
    if (!Number.isNaN(n)) return Math.max(6, Math.min(96, n));
    return defaultPx;
  }
  const suffixM = s.match(/_(\d{1,3})$/);
  if (suffixM) {
    const n = parseInt(suffixM[1]!, 10);
    if (!Number.isNaN(n)) return Math.max(6, Math.min(96, n));
    return defaultPx;
  }
  return defaultPx;
}
