import { useCallback, useEffect, useMemo, useRef } from "react";
import { assetFileUrl } from "./api";
import { fontSizeFromFontId } from "./canvasUtils";

/** Stable CSS font-family name for an uploaded asset filename (TTF/OTF). */
export function cssFontFamilyForAssetFile(filename: string): string {
  return `EtdAsset_${filename.replace(/[^a-zA-Z0-9._-]/g, "_")}`;
}

type WidgetFontNode = {
  props?: Record<string, unknown>;
  style?: Record<string, unknown>;
  widgets?: unknown;
};

function collectAssetFontFiles(
  widgets: Array<WidgetFontNode> | undefined,
  assetSet: Set<string>
): string[] {
  const out = new Set<string>();
  const consider = (fid: unknown) => {
    if (typeof fid !== "string" || !fid.startsWith("asset:")) return;
    const last = fid.lastIndexOf(":");
    if (last <= "asset:".length) return;
    const file = fid.slice("asset:".length, last);
    if (!file || /[\\/]/.test(file) || file.startsWith(".")) return;
    if (!assetSet.has(file)) return;
    if (!/\.(ttf|otf)$/i.test(file)) return;
    out.add(file);
  };
  const walk = (list: Array<WidgetFontNode> | undefined) => {
    for (const w of list || []) {
      if (!w || typeof w !== "object") continue;
      consider(w.style?.text_font);
      consider(w.props?.text_font);
      consider(w.style?.label_text_font);
      consider(w.props?.label_text_font);
      const kids = w.widgets;
      if (Array.isArray(kids)) walk(kids as WidgetFontNode[]);
    }
  };
  walk(widgets);
  return [...out];
}

/**
 * Resolves widget font ids to browser font-family + size; injects @font-face for asset:* TTF/OTF.
 */
export function usePreviewFontResolver(
  widgets: Array<{ props?: Record<string, unknown>; style?: Record<string, unknown> }> | undefined,
  assets: { name: string }[] | undefined
) {
  const assetSet = useMemo(() => new Set((assets ?? []).map((a) => a.name)), [assets]);
  const injectedTags = useRef(new Set<string>());

  useEffect(() => {
    const files = collectAssetFontFiles(widgets, assetSet);
    for (const file of files) {
      const tagId = `etd-ff-${file.replace(/[^a-zA-Z0-9_-]/g, "_")}`;
      if (injectedTags.current.has(tagId)) continue;
      const fam = cssFontFamilyForAssetFile(file);
      const el = document.createElement("style");
      el.setAttribute("data-etd-font", tagId);
      const src = assetFileUrl(file);
      el.textContent = `@font-face{font-family:'${fam}';src:url("${src}") format("opentype");font-display:swap;}`;
      document.head.appendChild(el);
      injectedTags.current.add(tagId);
    }
  }, [widgets, assetSet]);

  const resolvePreviewFont = useCallback(
    (fontId: unknown): { fontFamily: string; fontSize: number; approximate: boolean } => {
      const fallbackStack = "Montserrat, system-ui, sans-serif";
      if (fontId == null || (typeof fontId === "string" && !fontId.trim())) {
        return { fontFamily: fallbackStack, fontSize: 16, approximate: false };
      }
      const id = String(fontId).trim();
      const parsedSize = fontSizeFromFontId(id);
      const size = Math.max(8, Math.min(48, parsedSize ?? 16));

      if (id.startsWith("asset:")) {
        const last = id.lastIndexOf(":");
        const file = last > "asset:".length ? id.slice("asset:".length, last) : "";
        const px = last > "asset:".length ? parseInt(id.slice(last + 1), 10) : NaN;
        const sz = Number.isFinite(px) ? Math.max(8, Math.min(48, px)) : size;
        if (!file || !assetSet.has(file) || !/\.(ttf|otf)$/i.test(file)) {
          return { fontFamily: fallbackStack, fontSize: sz, approximate: true };
        }
        const fam = cssFontFamilyForAssetFile(file);
        return { fontFamily: `${fam}, ${fallbackStack}`, fontSize: sz, approximate: false };
      }

      if (/^montserrat_\d+$/i.test(id)) {
        return { fontFamily: fallbackStack, fontSize: size, approximate: false };
      }

      return { fontFamily: fallbackStack, fontSize: size, approximate: true };
    },
    [assetSet]
  );

  const fontPreviewBanner = useMemo(() => {
    if (!widgets?.length) return null;
    const visit = (list: Array<WidgetFontNode> | undefined): boolean => {
      for (const w of list || []) {
        if (!w || typeof w !== "object") continue;
        const ids = [w.style?.text_font, w.props?.text_font, w.style?.label_text_font, w.props?.label_text_font];
        for (const fid of ids) {
          if (resolvePreviewFont(fid).approximate) return true;
        }
        const kids = w.widgets;
        if (Array.isArray(kids) && visit(kids as WidgetFontNode[])) return true;
      }
      return false;
    };
    if (visit(widgets)) {
      return "Preview uses fallback fonts for some widgets (missing TTF/OTF asset or unknown font id). The device uses fonts from your YAML.";
    }
    return null;
  }, [widgets, resolvePreviewFont]);

  return { resolvePreviewFont, fontPreviewBanner };
}
