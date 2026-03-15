import React from "react";

type Props = { children: React.ReactNode };
type State = { hasError: boolean; error?: any };

/**
 * Bullet-proof UI: prevents a white-screen-of-death if a render path throws.
 * Shows a copy/paste diagnostics block to help troubleshooting.
 */
export default class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: any): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: any, info: any) {
    // eslint-disable-next-line no-console
    console.error("UI crashed", error, info);
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    const diag = {
      error: String(this.state.error?.message || this.state.error || "unknown"),
      stack: String(this.state.error?.stack || ""),
      userAgent: navigator.userAgent,
      time: new Date().toISOString(),
    };

    return (
      <div style={{ fontFamily: "system-ui", padding: 16 }}>
        <h2 style={{ marginTop: 0 }}>ESPHome Touch Designer crashed</h2>
        <p>The UI hit an unexpected error. You can usually reload the page to continue.</p>
        <button
          onClick={() => window.location.reload()}
          style={{ padding: "8px 12px", cursor: "pointer" }}
        >
          Reload
        </button>
        <h3>Diagnostics</h3>
        <p>Copy/paste this into an issue report:</p>
        <pre style={{ background: "#111", color: "#eee", padding: 12, overflow: "auto" }}>
          {JSON.stringify(diag, null, 2)}
        </pre>
      </div>
    );
  }
}
