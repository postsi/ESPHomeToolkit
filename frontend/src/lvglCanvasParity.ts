/**
 * Canvas preview ↔ ESPHome/LVGL parity helpers.
 *
 * ## Alignment / text defaults (single spec — match widget JSON schema + common_extras.json)
 *
 * - **Widget position (`align` prop):** TOP_LEFT default. Canvas `absPos` / `parentInfo` mirror LVGL
 *   alignment offsets relative to the parent content area.
 * - **Text in box (`textLayoutFromWidget` in canvasUtils):** Uses `style.text_align` default LEFT
 *   (common_extras), `props.align` / `style.align` default TOP_LEFT for vertical placement,
 *   and `pad_*` / `pad_all` like LVGL style padding.
 * - **Label `long_mode`:** Schema default CLIP (`schemas/widgets/label.json`). Canvas maps:
 *   WRAP → Konva word wrap; DOT / SCROLL / SCROLL_CIRCULAR → ellipsis (scroll not animated in preview);
 *   CLIP → clip in box (no ellipsis).
 * - **Button:** No `long_mode` in schema; preview uses CLIP (LVGL button label typically clips).
 * - **Textarea:** Multi-line on device; preview defaults to WRAP when `long_mode` omitted.
 * - **Letter spacing:** `style.text_letter_space` (default 0) applied to Konva `letterSpacing` where supported.
 *
 * Gaps: `text_line_space`, scroll animation, exact bitmap font metrics vs browser.
 */

export type LvglLongMode = "WRAP" | "DOT" | "SCROLL" | "SCROLL_CIRCULAR" | "CLIP";

/** Effective LVGL long_mode for canvas drawing (uppercase). */
export function effectiveLongMode(
  widgetType: string,
  props: Record<string, unknown> = {},
  style: Record<string, unknown> = {}
): LvglLongMode {
  const raw = props.long_mode ?? style.long_mode;
  if (typeof raw === "string" && raw.trim()) {
    const u = raw.trim().toUpperCase();
    if (
      u === "WRAP" ||
      u === "DOT" ||
      u === "SCROLL" ||
      u === "SCROLL_CIRCULAR" ||
      u === "CLIP"
    ) {
      return u as LvglLongMode;
    }
  }
  const t = String(widgetType || "").toLowerCase();
  if (t === "textarea") return "WRAP";
  return "CLIP";
}

/** Konva Text props approximating LVGL long_mode (scroll modes are static ellipsis in preview). */
export function konvaLongModeTextProps(mode: LvglLongMode): { wrap?: "word"; ellipsis: boolean } {
  switch (mode) {
    case "WRAP":
      return { wrap: "word", ellipsis: false };
    case "DOT":
    case "SCROLL":
    case "SCROLL_CIRCULAR":
      return { ellipsis: true };
    case "CLIP":
    default:
      return { ellipsis: false };
  }
}
