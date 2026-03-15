import React from "react";

export const WORKFLOW_STEPS = [
  { step: 1, label: "Choose device" },
  { step: 2, label: "Load or add device" },
  { step: 3, label: "Design screens" },
  { step: 4, label: "Bind entities" },
  { step: 5, label: "Test" },
  { step: 6, label: "Deploy" },
] as const;

export type WorkflowStep = 1 | 2 | 3 | 4 | 5 | 6;

export interface WorkflowStepperProps {
  currentStep: WorkflowStep;
  completedSteps: Set<WorkflowStep>;
  deviceName?: string | null;
  /** Short guidance for the current step (1–2 sentences). */
  stepGuidance?: string;
  /** Label for the suggested next action, e.g. "Set up bindings". */
  nextStepLabel?: string | null;
  /** Called when user clicks a step (optional). */
  onStepClick?: (step: WorkflowStep) => void;
}

export default function WorkflowStepper({
  currentStep,
  completedSteps,
  deviceName,
  stepGuidance,
  nextStepLabel,
  onStepClick,
}: WorkflowStepperProps) {
  const safeCompleted = completedSteps ?? new Set<WorkflowStep>();
  return (
    <div
      className="workflowStepper"
      style={{
        padding: "10px 16px 8px",
        borderBottom: "1px solid var(--border, #333)",
        background: "rgba(0,0,0,0.2)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 4,
          flexWrap: "wrap",
          marginBottom: 8,
        }}
      >
        {WORKFLOW_STEPS.map(({ step, label }, idx) => {
          const done = safeCompleted.has(step as WorkflowStep);
          const current = currentStep === step;
          const clickable = !!onStepClick;
          return (
            <React.Fragment key={step}>
              {idx > 0 && (
                <span
                  className="muted"
                  style={{
                    width: 16,
                    textAlign: "center",
                    fontSize: 12,
                  }}
                >
                  →
                </span>
              )}
              <button
                type="button"
                className="ghost"
                onClick={() => clickable && onStepClick(step as WorkflowStep)}
                disabled={!clickable}
                title={done ? `Done: ${label}` : current ? `Current: ${label}` : label}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "6px 10px",
                  borderRadius: 8,
                  fontSize: 13,
                  fontWeight: current ? 600 : 400,
                  background: current ? "rgba(16, 185, 129, 0.2)" : done ? "rgba(16, 185, 129, 0.08)" : "transparent",
                  border: current ? "1px solid rgba(16, 185, 129, 0.5)" : "1px solid transparent",
                  color: current ? "var(--ha-text-primary, #e5e7eb)" : done ? "var(--muted, #9ca3af)" : "var(--muted, #9ca3af)",
                  cursor: clickable ? "pointer" : "default",
                }}
              >
                {done && <span aria-hidden style={{ fontSize: 14 }}>✓</span>}
                <span>{step}. {label}</span>
              </button>
            </React.Fragment>
          );
        })}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, fontSize: 13 }}>
        {deviceName && (
          <span className="muted" style={{ marginRight: 8 }}>
            Device: <strong style={{ color: "var(--text, #e5e7eb)" }}>{deviceName}</strong>
          </span>
        )}
        {stepGuidance && (
          <span className="muted" style={{ flex: 1, minWidth: 200 }}>
            {stepGuidance}
          </span>
        )}
        {nextStepLabel && currentStep < 6 && (
          <span className="muted">
            Next: <strong style={{ color: "var(--ok, #10b981)" }}>{nextStepLabel}</strong>
          </span>
        )}
      </div>
    </div>
  );
}
