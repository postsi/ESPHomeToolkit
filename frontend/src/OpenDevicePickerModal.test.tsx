/**
 * Component tests for OpenDevicePickerModal. Require jsdom (see frontend/package.json and docs/TESTING.md).
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, it, expect, afterEach, vi } from "vitest";
import OpenDevicePickerModal from "./OpenDevicePickerModal";

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

describe("OpenDevicePickerModal", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  const devices = [
    { device_id: "b", name: "Beta", slug: "beta" },
    { device_id: "a", name: "Alpha", slug: "alpha" },
  ];

  it("renders nothing when open is false", () => {
    const { container, unmount } = render(
      <OpenDevicePickerModal open={false} onClose={vi.fn()} devices={[]} onSelect={vi.fn()} />
    );
    expect(container.textContent).not.toContain("Open device");
    unmount();
  });

  it("renders title and devices sorted by name when open", () => {
    const { container, unmount } = render(
      <OpenDevicePickerModal open onClose={vi.fn()} devices={devices} onSelect={vi.fn()} />
    );
    expect(container.textContent).toContain("Open device");
    expect(container.textContent).toContain("Alpha");
    expect(container.textContent).toContain("Beta");
    const order = container.textContent!.indexOf("Alpha") < container.textContent!.indexOf("Beta");
    expect(order).toBe(true);
    unmount();
  });

  it("shows empty state when no devices", () => {
    const { container, unmount } = render(
      <OpenDevicePickerModal open onClose={vi.fn()} devices={[]} onSelect={vi.fn()} />
    );
    expect(container.textContent).toMatch(/No devices/);
    unmount();
  });
});
