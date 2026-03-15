import React, { useState } from "react";
import type { DeviceSummary } from "./api";

export interface ManageDevicesModalProps {
  open: boolean;
  onClose: () => void;
  devices: DeviceSummary[];
  recipeLabels?: Record<string, string>;
  busy?: boolean;
  onOpen: (deviceId: string) => void;
  onRename: (deviceId: string, payload: { name: string; slug: string; hardware_recipe_id?: string | null }) => void;
  onCopy: (sourceDeviceId: string, newName: string, newSlug: string) => void;
  onDelete: (deviceId: string) => void;
}

function friendlyToId(s: string): string {
  return s
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    || "device";
}

export default function ManageDevicesModal({
  open,
  onClose,
  devices,
  recipeLabels = {},
  busy = false,
  onOpen,
  onRename,
  onCopy,
  onDelete,
}: ManageDevicesModalProps) {
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameName, setRenameName] = useState("");
  const [renameSlug, setRenameSlug] = useState("");
  const [copyId, setCopyId] = useState<string | null>(null);
  const [copyName, setCopyName] = useState("");
  const [copySlug, setCopySlug] = useState("");

  if (!open) return null;

  const startRename = (d: DeviceSummary) => {
    setRenameId(d.device_id);
    setRenameName(d.name || "");
    setRenameSlug(d.slug || d.device_id || "");
    setCopyId(null);
  };

  const saveRename = () => {
    if (renameId) {
      onRename(renameId, { name: renameName.trim(), slug: renameSlug.trim() });
      setRenameId(null);
    }
  };

  const startCopy = (d: DeviceSummary) => {
    setCopyId(d.device_id);
    setCopyName((d.name || d.device_id) + " (copy)");
    setCopySlug(friendlyToId((d.name || d.device_id) + "_copy"));
    setRenameId(null);
  };

  const saveCopy = () => {
    if (copyId && copyName.trim() && copySlug.trim()) {
      onCopy(copyId, copyName.trim(), copySlug.trim());
      setCopyId(null);
    }
  };

  const handleDelete = (deviceId: string, name: string) => {
    if (window.confirm(`Delete device "${name}" and its UI? This cannot be undone.`)) {
      onDelete(deviceId);
    }
  };

  return (
    <div className="modalOverlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 520, maxHeight: "90vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div className="modalHeader">
          <div className="title">Manage devices</div>
          <button type="button" className="ghost" onClick={onClose}>✕</button>
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: "0 16px 16px" }}>
          {devices.length === 0 ? (
            <p className="muted">No devices. Add a device from the welcome screen.</p>
          ) : (
            <ul className="list" style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {devices.map((d) => (
                <li key={d.device_id} style={{ marginBottom: 12 }}>
                  {renameId === d.device_id ? (
                    <div style={{ padding: 12, border: "1px solid var(--border)", borderRadius: 10, background: "rgba(0,0,0,0.2)" }}>
                      <label className="fieldLabel" style={{ display: "block", marginBottom: 4 }}>Name</label>
                      <input
                        value={renameName}
                        onChange={(e) => setRenameName(e.target.value)}
                        placeholder="Device name"
                        style={{ width: "100%", marginBottom: 8 }}
                      />
                      <label className="fieldLabel" style={{ display: "block", marginBottom: 4 }}>Slug (for export)</label>
                      <input
                        value={renameSlug}
                        onChange={(e) => setRenameSlug(e.target.value)}
                        placeholder="slug"
                        style={{ width: "100%", marginBottom: 8 }}
                      />
                      <div style={{ display: "flex", gap: 8 }}>
                        <button type="button" className="primary" disabled={busy} onClick={saveRename}>Save</button>
                        <button type="button" className="secondary" onClick={() => setRenameId(null)}>Cancel</button>
                      </div>
                    </div>
                  ) : copyId === d.device_id ? (
                    <div style={{ padding: 12, border: "1px solid var(--border)", borderRadius: 10, background: "rgba(0,0,0,0.2)" }}>
                      <div className="muted" style={{ marginBottom: 8, fontSize: 12 }}>Copy device and its UI to a new device.</div>
                      <label className="fieldLabel" style={{ display: "block", marginBottom: 4 }}>New device name</label>
                      <input
                        value={copyName}
                        onChange={(e) => setCopyName(e.target.value)}
                        placeholder="Name"
                        style={{ width: "100%", marginBottom: 8 }}
                      />
                      <label className="fieldLabel" style={{ display: "block", marginBottom: 4 }}>Slug (used for device id)</label>
                      <input
                        value={copySlug}
                        onChange={(e) => setCopySlug(e.target.value)}
                        placeholder="slug"
                        style={{ width: "100%", marginBottom: 8 }}
                      />
                      <div style={{ display: "flex", gap: 8 }}>
                        <button type="button" className="primary" disabled={busy || !copyName.trim() || !copySlug.trim()} onClick={saveCopy}>Create copy</button>
                        <button type="button" className="secondary" onClick={() => setCopyId(null)}>Cancel</button>
                      </div>
                    </div>
                  ) : (
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 12,
                        flexWrap: "wrap",
                        padding: "10px 12px",
                        border: "1px solid var(--border)",
                        borderRadius: 10,
                        background: "rgba(255,255,255,0.02)",
                      }}
                    >
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 600 }}>{d.name || d.device_id}</div>
                        {d.hardware_recipe_id && (
                          <div className="muted" style={{ fontSize: 12 }}>{recipeLabels[d.hardware_recipe_id] || d.hardware_recipe_id}</div>
                        )}
                      </div>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        <button type="button" className="secondary" disabled={busy} onClick={() => onOpen(d.device_id)} title="Open this device">Open</button>
                        <button type="button" className="ghost" disabled={busy} onClick={() => startRename(d)} title="Rename">Rename</button>
                        <button type="button" className="ghost" disabled={busy} onClick={() => startCopy(d)} title="Copy device and UI">Copy</button>
                        <button type="button" className="danger" disabled={busy} onClick={() => handleDelete(d.device_id, d.name || d.device_id)} title="Delete device and its UI">Delete</button>
                      </div>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
