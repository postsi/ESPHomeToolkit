/**
 * Loads SectionBasedComponentsPanel via import() only when mounted.
 * Keeps panel and apiSections out of the main bundle to avoid TDZ in Safari.
 */
import React, { useEffect, useState } from "react";

type Props = {
  project: any;
  setProject: (p: any, commit?: boolean) => void;
  setProjectDirty: (dirty: boolean) => void;
  onClose: () => void;
  onSaveAndPersist?: (updatedProject: any) => void | Promise<void>;
  deviceId?: string | null;
  entryId?: string | null;
};

export default function ComponentsPanelLoader(props: Props) {
  const [Panel, setPanel] = useState<React.ComponentType<Props> | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    import("./SectionBasedComponentsPanel")
      .then((m) => {
        if (!cancelled) setPanel(() => m.default);
      })
      .catch((e) => {
        if (!cancelled) setErr(e?.message ?? "Failed to load");
      });
    return () => { cancelled = true; };
  }, []);

  if (err) {
    return (
      <div className="modalOverlay" onClick={props.onClose}>
        <div className="modal" style={{ padding: 24 }} onClick={(e) => e.stopPropagation()}>
          <div style={{ color: "#e88" }}>{err}</div>
          <button type="button" onClick={props.onClose}>Close</button>
        </div>
      </div>
    );
  }
  if (!Panel) {
    return (
      <div className="modalOverlay" onClick={props.onClose}>
        <div className="modal" style={{ padding: 24 }} onClick={(e) => e.stopPropagation()}>
          Loading Components…
        </div>
      </div>
    );
  }
  return <Panel {...props} />;
}
