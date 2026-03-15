import React from "react";
import type { DeviceSummary } from "./api";

const MAX_RECENT = 4;

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
  /** Optional: recipe labels by id for display. */
  recipeLabels?: Record<string, string>;
}

export default function WelcomePanel({
  devices,
  recentDeviceIds,
  onLoadDevice,
  onOpenDevicePicker,
  onAddDevice,
  onManageDevices,
  recipeLabels = {},
}: WelcomePanelProps) {
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

      <div className="section" style={{ marginTop: 0 }}>
        <div className="sectionTitle">Recent devices</div>
        {displayDevices.length > 0 ? (
          <>
            <p className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
              {isFallbackList
                ? "Click a device to open its UI. This list will show your most recently opened devices once you've opened some."
                : "Click a device to open its UI."}
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
      </div>

      {devices.length === 0 && (
        <p className="muted" style={{ fontSize: 14 }}>
          No devices yet. Add a device to get started.
        </p>
      )}
    </div>
  );
}
