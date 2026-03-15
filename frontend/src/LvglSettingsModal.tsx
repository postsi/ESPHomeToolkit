import React, { useEffect, useState } from "react";

export type LvglConfig = {
  main?: { disp_bg_color?: string; buffer_size?: string; [k: string]: unknown };
  style_definitions?: Array<{ id: string; [k: string]: unknown }>;
  theme?: Record<string, Record<string, unknown>>;
  gradients?: Array<{ id: string; direction?: string; stops?: Array<{ color?: string; position?: number }> }>;
  top_layer?: { widgets?: any[] };
};

type Tab = "main" | "styles" | "theme" | "gradients";

type Props = {
  open: boolean;
  onClose: () => void;
  config: LvglConfig | undefined;
  onSave: (config: LvglConfig) => void;
};

const WIDGET_TYPES = ["button", "label", "arc", "slider", "bar", "checkbox", "dropdown", "roller", "spinbox", "textarea", "switch", "container"];

export default function LvglSettingsModal({ open, onClose, config, onSave }: Props) {
  const [tab, setTab] = useState<Tab>("main");
  const [main, setMain] = useState<{ disp_bg_color: string; buffer_size: string }>({ disp_bg_color: "#0B0F14", buffer_size: "100%" });
  const [styleDefs, setStyleDefs] = useState<Array<{ id: string; [k: string]: unknown }>>([]);
  const [theme, setTheme] = useState<Record<string, Record<string, unknown>>>({});
  const [gradients, setGradients] = useState<Array<{ id: string; direction?: string; stops?: Array<{ color?: string; position?: number }> }>>([]);

  useEffect(() => {
    if (!open || !config) return;
    setMain({
      disp_bg_color: (config.main?.disp_bg_color as string) || "#0B0F14",
      buffer_size: (config.main?.buffer_size as string) || "100%",
    });
    setStyleDefs(Array.isArray(config.style_definitions) ? config.style_definitions.map((s) => ({ ...s, id: s.id || "style" })) : []);
    setTheme(typeof config.theme === "object" && config.theme ? { ...config.theme } : {});
    setGradients(Array.isArray(config.gradients) ? config.gradients.map((g) => ({ ...g, id: g.id || "grad", stops: g.stops || [] })) : []);
  }, [open, config]);

  const handleSave = () => {
    onSave({
      main: { ...main },
      style_definitions: styleDefs.filter((s) => (s.id || "").trim()),
      theme: Object.keys(theme).length ? theme : undefined,
      gradients: gradients.filter((g) => (g.id || "").trim()),
      top_layer: config?.top_layer,
    });
    onClose();
  };

  if (!open) return null;

  return (
    <div className="modalOverlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 560, maxHeight: "85vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div className="modalHeader">
          <div className="title">LVGL settings</div>
          <button className="ghost" onClick={onClose}>✕</button>
        </div>
        <div style={{ display: "flex", gap: 4, padding: "0 16px 8px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
          {(["main", "styles", "theme", "gradients"] as Tab[]).map((t) => (
            <button key={t} type="button" className={tab === t ? "panelTab active" : "panelTab"} onClick={() => setTab(t)} style={{ padding: "6px 12px" }}>
              {t === "main" ? "Main" : t === "styles" ? "Style definitions" : t === "theme" ? "Theme" : "Gradients"}
            </button>
          ))}
        </div>
        <div style={{ flex: 1, overflow: "auto", padding: 16 }}>
          {tab === "main" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <label className="label">Display background color</label>
              <input type="color" value={main.disp_bg_color} onChange={(e) => setMain((m) => ({ ...m, disp_bg_color: e.target.value }))} style={{ width: 60, height: 36, padding: 2, cursor: "pointer" }} />
              <input type="text" value={main.disp_bg_color} onChange={(e) => setMain((m) => ({ ...m, disp_bg_color: e.target.value }))} style={{ fontFamily: "monospace", width: "100%", maxWidth: 120 }} />
              <label className="label">Buffer size</label>
              <input type="text" value={main.buffer_size} onChange={(e) => setMain((m) => ({ ...m, buffer_size: e.target.value }))} placeholder="e.g. 100% or 25%" style={{ width: "100%", maxWidth: 120 }} />
              <div className="muted" style={{ fontSize: 12 }}>Percentage of display size. 100% default; lower saves RAM.</div>
            </div>
          )}

          {tab === "styles" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div className="muted" style={{ fontSize: 12 }}>Named styles applied to widgets via <code>styles: id</code>. Add style props (e.g. text_color, border_width) as key-value.</div>
              {styleDefs.map((sd, i) => (
                <div key={i} style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 10 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
                    <input value={sd.id} onChange={(e) => setStyleDefs((s) => s.map((x, j) => (j === i ? { ...x, id: e.target.value } : x)))} placeholder="Style ID" style={{ flex: 1, fontFamily: "monospace" }} />
                    <button type="button" className="ghost" onClick={() => setStyleDefs((s) => s.filter((_, j) => j !== i))}>Remove</button>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--muted)" }}>Extra props: add in widget inspector or YAML. Here you set the reusable style id.</div>
                </div>
              ))}
              <button type="button" className="secondary" onClick={() => setStyleDefs((s) => [...s, { id: `style_${s.length + 1}` }])}>Add style definition</button>
            </div>
          )}

          {tab === "theme" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div className="muted" style={{ fontSize: 12 }}>Default styles per widget type. All widgets of that type inherit these until overridden.</div>
              {WIDGET_TYPES.map((wtype) => (
                <div key={wtype} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ minWidth: 100 }}>{wtype}</span>
                  <input type="text" value={theme[wtype] ? JSON.stringify(theme[wtype]) : ""} onChange={(e) => { const v = e.target.value.trim(); setTheme((t) => (v ? { ...t, [wtype]: (() => { try { return JSON.parse(v); } catch { return {}; } })() } : { ...t, [wtype]: undefined })); }} placeholder={'{} or {"border_width": 2}'} style={{ flex: 1, fontFamily: "monospace", fontSize: 12 }} />
                </div>
              ))}
            </div>
          )}

          {tab === "gradients" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div className="muted" style={{ fontSize: 12 }}>Gradient definitions referenced by style <code>bg_grad: id</code>. Direction: hor, ver.</div>
              {gradients.map((g, i) => (
                <div key={i} style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 10 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
                    <input value={g.id} onChange={(e) => setGradients((gr) => gr.map((x, j) => (j === i ? { ...x, id: e.target.value } : x)))} placeholder="Gradient ID" style={{ flex: 1, fontFamily: "monospace" }} />
                    <select value={g.direction || "hor"} onChange={(e) => setGradients((gr) => gr.map((x, j) => (j === i ? { ...x, direction: e.target.value } : x)))}>
                      <option value="hor">Horizontal</option>
                      <option value="ver">Vertical</option>
                    </select>
                    <button type="button" className="ghost" onClick={() => setGradients((gr) => gr.filter((_, j) => j !== i))}>Remove</button>
                  </div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>Stops (color + position 0–1):</div>
                  {(g.stops || []).map((stop, si) => {
                    const hexColor = typeof stop.color === "string" && stop.color.startsWith("#") ? stop.color : typeof stop.color === "number" ? "#" + (stop.color & 0xFFFFFF).toString(16).padStart(6, "0") : "#000000";
                    return (
                    <div key={si} style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4 }}>
                      <input type="color" value={hexColor} onChange={(e) => setGradients((gr) => gr.map((x, j) => (j !== i ? x : { ...x, stops: (x.stops || []).map((s, k) => (k === si ? { ...s, color: e.target.value } : s)) })))} style={{ width: 36, height: 28, padding: 0, cursor: "pointer" }} />
                      <input type="number" min={0} max={1} step={0.1} value={stop.position ?? 0} onChange={(e) => setGradients((gr) => gr.map((x, j) => (j !== i ? x : { ...x, stops: (x.stops || []).map((s, k) => (k === si ? { ...s, position: parseFloat(e.target.value) || 0 } : s)) })))} style={{ width: 60 }} />
                      <button type="button" className="ghost" onClick={() => setGradients((gr) => gr.map((x, j) => (j !== i ? x : { ...x, stops: (x.stops || []).filter((_, k) => k !== si) })))}>×</button>
                    </div>
                  ); })}
                  <button type="button" className="ghost" style={{ fontSize: 12 }} onClick={() => setGradients((gr) => gr.map((x, j) => (j !== i ? x : { ...x, stops: [...(x.stops || []), { color: "#808080", position: 0.5 }] })))}>+ Add stop</button>
                </div>
              ))}
              <button type="button" className="secondary" onClick={() => setGradients((g) => [...g, { id: `grad_${g.length + 1}`, direction: "hor", stops: [{ color: "#000000", position: 0 }, { color: "#ffffff", position: 1 }] }])}>Add gradient</button>
            </div>
          )}
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", padding: 16, borderTop: "1px solid var(--border)", flexShrink: 0 }}>
          <button className="ghost" onClick={onClose}>Cancel</button>
          <button onClick={handleSave}>Save</button>
        </div>
      </div>
    </div>
  );
}
