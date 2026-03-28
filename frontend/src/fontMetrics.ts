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

/** Match views.py::_spinbox2_emitted_height (row container height in YAML). */
export function spinbox2EmittedRowHeight(w: {
  h?: number;
  props?: Record<string, unknown>;
  style?: Record<string, unknown>;
}): number {
  const hVal = Math.floor(Number(w.h ?? 48));
  const props = w.props || {};
  const style = w.style || {};
  const raw = String(style.text_font ?? props.font ?? "").trim();
  const fontPx = fontPxFromId(raw || undefined, 14);
  const borderW = Math.floor(Number(style.border_width ?? 1) || 0);
  const outlineW = Math.floor(Number(style.outline_width ?? 0) || 0);
  const edge = Math.max(0, borderW, outlineW);
  return Math.max(hVal, fontPx + 22 + 2 * edge);
}
