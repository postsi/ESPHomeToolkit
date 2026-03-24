import React, { useState } from "react";
import type { DeviceSummary } from "./api";

const MAX_RECENT = 4;

function friendlyToId(s: string): string {
  return (
    s
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "") || "device"
  );
}

export interface WelcomePanelProps {
  /** Full list of devices. */
  devices: DeviceSummary[];
  /** Up to 4 most recently opened device IDs (order = most recent first). */
  recentDeviceIds: string[];
  /** Called when user clicks a device row to load that device. */
  onLoadDevice: (deviceId: string) => void;
  /** Called when user clicks "Open device" (opens picker modal). */
  onOpenDevicePicker: () => void;
  /** Called when user clicks "Add device". */
  onAddDevice: () => void;
  /** Called when user clicks "Manage devices" (opens manage modal). */
  onManageDevices: () => void;
  /** Called when user clicks "Import YAML" (opens import modal). */
  onImportYaml?: () => void;
  /** Optional: recipe labels by id for display. */
  recipeLabels?: Record<string, string>;
  /** Duplicate device + UI (same contract as Manage devices). */
  onCopyDevice: (sourceDeviceId: string, newName: string, newSlug: string) => void | Promise<void>;
  /** Delete device and its UI. */
  onDeleteDevice: (deviceId: string) => void | Promise<void>;
  /** Disable copy/delete actions while a request is in flight. */
  busy?: boolean;
}

export default function WelcomePanel({
  devices,
  recentDeviceIds,
  onLoadDevice,
  onOpenDevicePicker,
  onAddDevice,
  onManageDevices,
  onImportYaml,
  recipeLabels = {},
  onCopyDevice,
  onDeleteDevice,
  busy = false,
}: WelcomePanelProps) {
  const [recentContextMenu, setRecentContextMenu] = useState<{
    x: number;
    y: number;
    device: DeviceSummary;
  } | null>(null);
  const [copySource, setCopySource] = useState<DeviceSummary | null>(null);
  const [copyName, setCopyName] = useState("");
  const [copySlug, setCopySlug] = useState("");

  const recentDevices = recentDeviceIds
    .slice(0, MAX_RECENT)
    .map((id) => devices.find((d) => d.device_id === id))
    .filter((d): d is DeviceSummary => d != null);

  // When we have no recent history but we do have devices, show devices (up to MAX_RECENT, by name) so the list is useful
  const displayDevices =
    recentDevices.length > 0
      ? recentDevices
      : devices.length > 0
        ? devices
            .slice()
            .sort((a, b) => (a.name || a.device_id).localeCompare(b.name || b.device_id))
            .slice(0, MAX_RECENT)
        : [];
  const isFallbackList = recentDevices.length === 0 && devices.length > 0;

  const openCopyDialog = (d: DeviceSummary) => {
    setRecentContextMenu(null);
    setCopySource(d);
    setCopyName((d.name || d.device_id) + " (copy)");
    setCopySlug(friendlyToId((d.name || d.device_id) + "_copy"));
  };

  const saveCopy = () => {
    if (!copySource || !copyName.trim() || !copySlug.trim()) return;
    void onCopyDevice(copySource.device_id, copyName.trim(), copySlug.trim());
    setCopySource(null);
  };

  const handleDeleteFromMenu = (d: DeviceSummary) => {
    setRecentContextMenu(null);
    const label = d.name || d.device_id;
    if (window.confirm(`Delete device "${label}" and its UI? This cannot be undone.`)) {
      void onDeleteDevice(d.device_id);
    }
  };

  return (
    <div
      className="welcomePanel"
      style={{
        padding: 32,
        maxWidth: 600,
        margin: "0 auto",
        display: "flex",
        flexDirection: "column",
        gap: 24,
      }}
    >
      <p className="muted" style={{ fontSize: 15, margin: 0, lineHeight: 1.5 }}>
        Design LVGL touch screen UIs for your ESPHome devices. Select or add a device, then design its screen and bind it to Home Assistant.
      </p>
      <p className="muted" style={{ fontSize: 12, margin: 0, lineHeight: 1.45 }}>
        <strong>Simulate</strong> and <strong>Mac sim</strong> appear above the canvas after you open a device. For Mac sim, set the token under{" "}
        <strong>Settings → Devices &amp; services → EspToolkit → Configure</strong> (integration, not the add-on).
      </p>

      <div className="section" style={{ marginTop: 0 }}>
        <div className="sectionTitle">Recent devices</div>
        {displayDevices.length > 0 ? (
          <>
            <p className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
              {isFallbackList
                ? "Click a device to open its UI; right-click to copy or delete. This list will show your most recently opened devices once you've opened some."
                : "Click a device to open its UI. Right-click for copy or delete."}
            </p>
            <ul className="list compact" style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {displayDevices.map((d) => (
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
                    onClick={() => onLoadDevice(d.device_id)}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setRecentContextMenu({ x: e.clientX, y: e.clientY, device: d });
                    }}
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
          </>
        ) : (
          <p className="muted" style={{ fontSize: 13, margin: 0 }}>
            No recent devices. Open or add a device to see them here.
          </p>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <button type="button" className="primary" onClick={onOpenDevicePicker} style={{ padding: "12px 16px", fontSize: 15 }}>
            Open device
          </button>
          <span className="muted" style={{ fontSize: 12 }}>
            Choose from all devices (sorted by name).
          </span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <button type="button" className="secondary" onClick={onAddDevice} style={{ padding: "12px 16px", fontSize: 15 }}>
            Add device
          </button>
          <span className="muted" style={{ fontSize: 12 }}>
            Add a device by choosing a hardware recipe (built-in or imported). You then design its screen and deploy. Creating new hardware recipes is done elsewhere.
          </span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <button type="button" className="secondary" onClick={onManageDevices} style={{ padding: "12px 16px", fontSize: 15 }}>
            Manage devices
          </button>
          <span className="muted" style={{ fontSize: 12 }}>
            Copy, rename, or delete devices and their UIs.
          </span>
        </div>
        {onImportYaml && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <button type="button" className="secondary" onClick={onImportYaml} style={{ padding: "12px 16px", fontSize: 15 }}>
              Import YAML
            </button>
            <span className="muted" style={{ fontSize: 12 }}>
              Import a device from full ESPHome YAML. Recipe is matched or created; LVGL UI is reverse-engineered into the Designer.
            </span>
          </div>
        )}
      </div>

      {devices.length === 0 && (
        <p className="muted" style={{ fontSize: 14 }}>
          No devices yet. Add a device to get started.
        </p>
      )}

      {recentContextMenu && (
        <div
          style={{ position: "fixed", inset: 0, zIndex: 9999 }}
          onClick={() => setRecentContextMenu(null)}
          onContextMenu={(e) => {
            e.preventDefault();
            setRecentContextMenu(null);
          }}
        >
          <div
            style={{
              position: "absolute",
              left: recentContextMenu.x,
              top: recentContextMenu.y,
              background: "#2a2a2a",
              border: "1px solid #444",
              borderRadius: 6,
              boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
              minWidth: 160,
              overflow: "hidden",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ padding: "8px 12px", fontSize: 11, color: "#888", borderBottom: "1px solid #444" }}>
              {recentContextMenu.device.name || recentContextMenu.device.device_id}
            </div>
            <button
              type="button"
              disabled={busy}
              style={{
                display: "block",
                width: "100%",
                padding: "10px 12px",
                textAlign: "left",
                background: "transparent",
                border: "none",
                color: "#e5e5e5",
                cursor: busy ? "not-allowed" : "pointer",
                fontSize: 13,
              }}
              onMouseOver={(e) => {
                if (!busy) e.currentTarget.style.background = "#3a3a3a";
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.background = "transparent";
              }}
              onClick={() => openCopyDialog(recentContextMenu.device)}
            >
              Copy device…
            </button>
            <button
              type="button"
              disabled={busy}
              style={{
                display: "block",
                width: "100%",
                padding: "10px 12px",
                textAlign: "left",
                background: "transparent",
                border: "none",
                borderTop: "1px solid #444",
                color: "#ef4444",
                cursor: busy ? "not-allowed" : "pointer",
                fontSize: 13,
              }}
              onMouseOver={(e) => {
                if (!busy) e.currentTarget.style.background = "#3a3a3a";
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.background = "transparent";
              }}
              onClick={() => handleDeleteFromMenu(recentContextMenu.device)}
            >
              Delete device…
            </button>
          </div>
        </div>
      )}

      {copySource && (
        <div className="modalOverlay" onClick={() => !busy && setCopySource(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <div className="modalHeader">
              <div className="title">Copy device</div>
              <button type="button" className="ghost" disabled={busy} onClick={() => setCopySource(null)}>
                ✕
              </button>
            </div>
            <div style={{ padding: "0 16px 16px" }}>
              <div className="muted" style={{ marginBottom: 12, fontSize: 12 }}>
                Copy &quot;{copySource.name || copySource.device_id}&quot; and its UI to a new device.
              </div>
              <label className="fieldLabel" style={{ display: "block", marginBottom: 4 }}>
                New device name
              </label>
              <input
                value={copyName}
                onChange={(e) => setCopyName(e.target.value)}
                placeholder="Device name"
                style={{ width: "100%", marginBottom: 10 }}
                disabled={busy}
              />
              <label className="fieldLabel" style={{ display: "block", marginBottom: 4 }}>
                Slug (for export)
              </label>
              <input
                value={copySlug}
                onChange={(e) => setCopySlug(e.target.value)}
                placeholder="slug"
                style={{ width: "100%", marginBottom: 12 }}
                disabled={busy}
              />
              <div style={{ display: "flex", gap: 8 }}>
                <button type="button" className="primary" disabled={busy || !copyName.trim() || !copySlug.trim()} onClick={saveCopy}>
                  {busy ? "Working…" : "Create copy"}
                </button>
                <button type="button" className="secondary" disabled={busy} onClick={() => setCopySource(null)}>
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
