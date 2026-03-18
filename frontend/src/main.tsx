import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import ErrorBoundary from "./ErrorBoundary";
import "./styles.css";

// When the Designer is opened as the top-level window (e.g. direct /esptoolkit/designer),
// redirect to the tabbed panel so the HA sidebar stays visible on the left.
let shouldRedirect = false;
if (typeof window !== "undefined" && window.self === window.top) {
  const path = window.location.pathname || "";
  if (path.includes("/designer")) {
    const base = path.replace(/\/designer.*$/, "").replace(/\/$/, "") || "/esptoolkit";
    window.location.replace(base || "/esptoolkit");
    shouldRedirect = true;
  }
}

if (!shouldRedirect) {
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </React.StrictMode>
  );
}
