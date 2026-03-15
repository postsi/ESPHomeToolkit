/**
 * Component tests for WelcomePanel. Require jsdom (see frontend/package.json and docs/TESTING.md).
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, it, expect, afterEach, vi } from "vitest";
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
    devices: [] as { device_id: string; name?: string; slug?: string; hardware_recipe_id?: string | null }[],
    recentDeviceIds: [] as string[],
    onLoadDevice: vi.fn(),
    onOpenDevicePicker: vi.fn(),
    onAddDevice: vi.fn(),
    onManageDevices: vi.fn(),
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
    expect(container.textContent).toContain("Click a device to open its UI");
    unmount();
  });

  it("shows Recent devices section with device list when recentDeviceIds empty but devices exist (fallback)", () => {
    const devices = [{ device_id: "d1", name: "Test Device" }];
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
        <WelcomePanel {...defaultProps} devices={[{ device_id: "d1", name: "Test" }]} recipeLabels={undefined} />
      );
      unmount();
    }).not.toThrow();
  });
});
