/**
 * Component tests for ManageDevicesModal. Require jsdom (see frontend/package.json and docs/TESTING.md).
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, it, expect, afterEach, vi } from "vitest";
import ManageDevicesModal from "./ManageDevicesModal";

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

describe("ManageDevicesModal", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  const defaultProps = {
    open: true,
    onClose: vi.fn(),
    devices: [
      { device_id: "d1", name: "Device One", slug: "device_one", hardware_recipe_id: "jc1060" },
    ],
    recipeLabels: { jc1060: "JC1060 4.7\" 1024×600" },
    busy: false,
    onOpen: vi.fn(),
    onRename: vi.fn(),
    onCopy: vi.fn(),
    onDelete: vi.fn(),
  };

  it("renders nothing when open is false", () => {
    const { container, unmount } = render(<ManageDevicesModal {...defaultProps} open={false} />);
    expect(container.textContent).not.toContain("Manage devices");
    unmount();
  });

  it("renders title and device list when open", () => {
    const { container, unmount } = render(<ManageDevicesModal {...defaultProps} />);
    expect(container.textContent).toContain("Manage devices");
    expect(container.textContent).toContain("Device One");
    expect(container.textContent).toContain("JC1060 4.7\" 1024×600");
    unmount();
  });

  it("shows Open, Rename, Copy, Delete for each device", () => {
    const { container, unmount } = render(<ManageDevicesModal {...defaultProps} />);
    expect(container.textContent).toContain("Open");
    expect(container.textContent).toContain("Rename");
    expect(container.textContent).toContain("Copy");
    expect(container.textContent).toContain("Delete");
    unmount();
  });

  it("shows empty state when no devices", () => {
    const { container, unmount } = render(<ManageDevicesModal {...defaultProps} devices={[]} />);
    expect(container.textContent).toMatch(/No devices/);
    unmount();
  });
});
