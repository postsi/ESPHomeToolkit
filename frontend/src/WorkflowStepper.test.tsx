/**
 * Component tests for WorkflowStepper. Require jsdom (see frontend/package.json and docs/TESTING.md).
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, it, expect, afterEach } from "vitest";
import WorkflowStepper, { type WorkflowStep } from "./WorkflowStepper";

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

describe("WorkflowStepper", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("renders all six steps", () => {
    const { container, unmount } = render(
      <WorkflowStepper currentStep={1} completedSteps={new Set()} />
    );
    expect(container.textContent).toMatch(/1\. Choose device/);
    expect(container.textContent).toMatch(/2\. Load or add device/);
    expect(container.textContent).toMatch(/6\. Deploy/);
    unmount();
  });

  it("does not throw when completedSteps is undefined", () => {
    expect(() => {
      const { unmount } = render(
        <WorkflowStepper
          currentStep={2}
          completedSteps={undefined as unknown as Set<WorkflowStep>}
        />
      );
      unmount();
    }).not.toThrow();
  });

  it("renders with undefined completedSteps and shows step labels", () => {
    const { container, unmount } = render(
      <WorkflowStepper
        currentStep={2}
        completedSteps={undefined as unknown as Set<WorkflowStep>}
      />
    );
    expect(container.textContent).toMatch(/2\. Load or add device/);
    unmount();
  });

  it("shows completed steps with checkmark when Set has steps", () => {
    const { container, unmount } = render(
      <WorkflowStepper
        currentStep={3}
        completedSteps={new Set([1, 2] as WorkflowStep[])}
      />
    );
    const buttons = container.querySelectorAll("button");
    expect(buttons.length).toBe(6);
    const text = Array.from(buttons).map((b) => b.textContent).join(" ");
    expect(text).toMatch(/✓/);
    unmount();
  });

  it("shows step guidance and next label when provided", () => {
    const { container, unmount } = render(
      <WorkflowStepper
        currentStep={1}
        completedSteps={new Set()}
        stepGuidance="Select the ESPHome device."
        nextStepLabel="Select device"
      />
    );
    expect(container.textContent).toContain("Select the ESPHome device.");
    expect(container.textContent).toMatch(/Next:.*Select device/);
    unmount();
  });
});
