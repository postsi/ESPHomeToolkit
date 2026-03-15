import React from "react";
import type { DeviceSummary } from "./api";

export interface OpenDevicePickerModalProps {
  open: boolean;
  onClose: () => void;
  devices: DeviceSummary[];
  recipeLabels?: Record<string, string>;
  onSelect: (deviceId: string) => void;
}

export default function OpenDevicePickerModal({
  open,
  onClose,
  devices,
  recipeLabels = {},
  onSelect,
}: OpenDevicePickerModalProps) {
  if (!open) return null;

  const sorted = [...devices].sort((a, b) => {
    const na = (a.name || a.device_id).toLowerCase();
    const nb = (b.name || b.device_id).toLowerCase();
    return na.localeCompare(nb);
  });

  return (
    <div className="modalOverlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480, maxHeight: "80vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div className="modalHeader">
          <div className="title">Open device</div>
          <button type="button" className="ghost" onClick={onClose}>✕</button>
        </div>
        <p className="muted" style={{ padding: "0 16px 8px", margin: 0, fontSize: 13 }}>
          Select a device to open its UI. Sorted by name.
        </p>
        <div style={{ flex: 1, overflowY: "auto", padding: "0 16px 16px" }}>
          {sorted.length === 0 ? (
            <p className="muted">No devices. Add a device first.</p>
          ) : (
            <ul className="list compact" style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {sorted.map((d) => (
                <li key={d.device_id} style={{ marginBottom: 8 }}>
                  <button
                    type="button"
                    className="row"
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: "12px 14px",
                      borderRadius: 10,
                      border: "1px solid var(--border, #333)",
                      background: "rgba(255,255,255,0.03)",
                      cursor: "pointer",
                      display: "flex",
                      flexDirection: "column",
                      gap: 2,
                      alignItems: "flex-start",
                    }}
                    onClick={() => { onSelect(d.device_id); onClose(); }}
                  >
                    <span style={{ fontWeight: 600 }}>{d.name || d.device_id}</span>
                    {d.hardware_recipe_id && (
                      <span className="muted" style={{ fontSize: 12 }}>
                        {recipeLabels[d.hardware_recipe_id] || d.hardware_recipe_id}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
