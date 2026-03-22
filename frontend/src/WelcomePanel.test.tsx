/**
 * Component tests for WelcomePanel. Require jsdom (see frontend/package.json and docs/TESTING.md).
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, it, expect, afterEach, vi } from "vitest";
import type { DeviceSummary } from "./api";
import WelcomePanel from "./WelcomePanel";

function render(ui: React.ReactElement): { container: HTMLElement; unmount: () => void } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(ui);
  });
  return {
    container,
    unmount: () => {
      act(() => {
        root.unmount();
      });
      document.body.removeChild(container);
    },
  };
}

describe("WelcomePanel", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  const defaultProps = {
    devices: [] as DeviceSummary[],
    recentDeviceIds: [] as string[],
    onLoadDevice: vi.fn(),
    onOpenDevicePicker: vi.fn(),
    onAddDevice: vi.fn(),
    onManageDevices: vi.fn(),
    onCopyDevice: vi.fn(),
    onDeleteDevice: vi.fn(),
  };

  it("renders intro, Open device, Add device and Manage devices", () => {
    const { container, unmount } = render(<WelcomePanel {...defaultProps} />);
    expect(container.textContent).toMatch(/Design LVGL touch screen UIs/);
    expect(container.textContent).toContain("Open device");
    expect(container.textContent).toContain("Add device");
    expect(container.textContent).toContain("Manage devices");
    unmount();
  });

  it("shows No devices yet when devices list is empty", () => {
    const { container, unmount } = render(<WelcomePanel {...defaultProps} />);
    expect(container.textContent).toContain("No devices yet");
    unmount();
  });

  it("shows Recent devices when recentDeviceIds and devices match", () => {
    const devices = [
      { device_id: "d1", name: "Living Room Panel", slug: "living_room" },
    ];
    const { container, unmount } = render(
      <WelcomePanel
        {...defaultProps}
        devices={devices}
        recentDeviceIds={["d1"]}
      />
    );
    expect(container.textContent).toContain("Recent devices");
    expect(container.textContent).toContain("Living Room Panel");
    expect(container.textContent).toContain("Right-click for copy or delete");
    unmount();
  });

  it("shows Recent devices section with device list when recentDeviceIds empty but devices exist (fallback)", () => {
    const devices: DeviceSummary[] = [{ device_id: "d1", name: "Test Device", slug: "test_device" }];
    const { container, unmount } = render(
      <WelcomePanel
        {...defaultProps}
        devices={devices}
        recentDeviceIds={[]}
      />
    );
    expect(container.textContent).toContain("Recent devices");
    expect(container.textContent).toContain("Test Device");
    expect(container.textContent).toContain("most recently opened devices once you've opened some");
    expect(container.textContent).toContain("Open device");
    unmount();
  });

  it("shows Recent devices section with empty state when no devices at all", () => {
    const { container, unmount } = render(
      <WelcomePanel {...defaultProps} devices={[]} recentDeviceIds={[]} />
    );
    expect(container.textContent).toContain("Recent devices");
    expect(container.textContent).toContain("No recent devices");
    expect(container.textContent).toContain("Open or add a device to see them here");
    unmount();
  });

  it("does not throw when recipeLabels is undefined", () => {
    expect(() => {
      const { unmount } = render(
        <WelcomePanel {...defaultProps} devices={[{ device_id: "d1", name: "Test", slug: "test" }]} recipeLabels={undefined} />
      );
      unmount();
    }).not.toThrow();
  });

  it("opens context menu on right-click and calls onDeleteDevice when delete is confirmed", () => {
    const onDeleteDevice = vi.fn();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const devices = [{ device_id: "d1", name: "Panel One", slug: "panel_one" }];
    const { container, unmount } = render(
      <WelcomePanel {...defaultProps} devices={devices} recentDeviceIds={["d1"]} onDeleteDevice={onDeleteDevice} />
    );
    const rowBtn = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes("Panel One"));
    expect(rowBtn).toBeTruthy();
    act(() => {
      rowBtn!.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: 100, clientY: 100 }));
    });
    const deleteBtn = [...container.querySelectorAll("button")].find((b) => b.textContent === "Delete device…");
    expect(deleteBtn).toBeTruthy();
    act(() => {
      deleteBtn!.click();
    });
    expect(confirmSpy).toHaveBeenCalled();
    expect(onDeleteDevice).toHaveBeenCalledWith("d1");
    confirmSpy.mockRestore();
    unmount();
  });
});
