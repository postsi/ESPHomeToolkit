/**
 * Section-based ESPHome Components panel (Design v2).
 * Single stored YAML per device; sections from recipe. States: Empty, Auto, Edited.
 * Reset = restore to current recipe; Save = write to project.esphome_yaml.
 */
import React, { useCallback, useEffect, useState } from "react";
import { getSectionsDefaults, saveSections } from "./lib/apiSections";
import { parseYamlSyntax, cleanupOrphanedComponents } from "./lib/api";
import YamlEditor from "./YamlEditor";

function clone<T>(x: T): T {
  return JSON.parse(JSON.stringify(x));
}

function sectionState(sectionContent: string, defaultContent: string): "empty" | "auto" | "edited" {
  const s = (sectionContent ?? "").trim();
  const d = (defaultContent ?? "").trim();
  if (!s) return "empty";
  return s === d ? "auto" : "edited";
}

export type SectionBasedComponentsPanelProps = {
  project: any;
  setProject: (p: any, commit?: boolean) => void;
  setProjectDirty: (dirty: boolean) => void;
  onClose: () => void;
  onSaveAndPersist?: (updatedProject: any) => void | Promise<void>;
  deviceId?: string | null;
  entryId?: string | null;
};

export default function SectionBasedComponentsPanel({
  project,
  setProject,
  setProjectDirty,
  onClose,
  onSaveAndPersist,
  deviceId,
  entryId,
}: SectionBasedComponentsPanelProps) {
  const [defaults, setDefaults] = useState<Record<string, string>>({});
  const [sections, setSections] = useState<Record<string, string>>({});
  const [categories, setCategories] = useState<Record<string, string[]>>({});
  const [compilerOwned, setCompilerOwned] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasLocalEdits, setHasLocalEdits] = useState(false);
  const [saving, setSaving] = useState(false);
  const [syntaxError, setSyntaxError] = useState<string | null>(null);
  const [cleanupBusy, setCleanupBusy] = useState(false);
  const [cleanupMessage, setCleanupMessage] = useState<string | null>(null);

  const recipeId = (project?.device?.hardware_recipe_id ?? project?.hardware?.recipe_id ?? "").trim() || "sunton_2432s028r_320x240";

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getSectionsDefaults(project, recipeId, deviceId ?? undefined, entryId ?? undefined)
      .then(({ sections: effective, categories: cat, default_sections: defSections, compiler_owned: co }) => {
        if (cancelled) return;
        setDefaults(defSections && typeof defSections === "object" ? defSections : {});
        setCategories(cat);
        setCompilerOwned(new Set(Array.isArray(co) ? co : []));
        setSections(effective);
        setHasLocalEdits(false);
      })
      .catch((e) => {
        if (!cancelled) setError(e?.message ?? "Failed to load section defaults");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [project, recipeId, deviceId, entryId]);

  const setSectionContent = useCallback((key: string, value: string) => {
    setSections((prev) => ({ ...prev, [key]: value }));
    setHasLocalEdits(true);
    setSyntaxError(null);
  }, []);

  const saveAll = useCallback(async () => {
    setSyntaxError(null);
    for (const k of Object.keys(sections)) {
      const content = (sections[k] ?? "").trim();
      if (!content) continue;
      const result = await parseYamlSyntax(content);
      if (!result.ok) {
        setSyntaxError(`${k}: ${result.error || "Invalid YAML"}${result.line != null ? ` (line ${result.line})` : ""}`);
        return;
      }
    }
    setSaving(true);
    try {
      const { project: updatedProject } = await saveSections(project, sections);
      setProject(updatedProject, true);
      setProjectDirty(true);
      setHasLocalEdits(false);
      if (onSaveAndPersist) await onSaveAndPersist(updatedProject);
    } catch (e: any) {
      setSyntaxError(e?.message ?? "Save failed");
    } finally {
      setSaving(false);
    }
  }, [project, sections, setProject, setProjectDirty, onSaveAndPersist]);

  const resetSection = useCallback((key: string) => {
    setSections((prev) => ({ ...prev, [key]: (defaults[key] ?? "").trim() }));
    setHasLocalEdits(true);
    setSyntaxError(null);
  }, [defaults]);

  const resetAll = useCallback(() => {
    setSections({ ...defaults });
    setHasLocalEdits(true);
    setSyntaxError(null);
  }, [defaults]);

  const requestClose = useCallback(() => {
    if (hasLocalEdits && !window.confirm("You have unsaved changes. Close anyway?")) return;
    onClose();
  }, [hasLocalEdits, onClose]);

  const categoryOrder = [
    "Device & platform",
    "Configuration",
    "Network",
    "Bluetooth",
    "Busses & interfaces",
    "Display & touch",
    "Automation & logic",
    "Sensors & entities",
    "Audio",
    "Debug & monitoring",
    "I/O expanders",
    "Other",
  ];

  return (
    <div className="modalOverlay" onClick={requestClose}>
      <div
        className="modal"
        style={{
          maxWidth: 700,
          maxHeight: "85vh",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modalHeader">
          <div className="title">ESPHome Components</div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button
              type="button"
              className="secondary"
              style={{ fontSize: 12 }}
              onClick={resetAll}
              disabled={loading}
            >
              Reset All
            </button>
            <button
              type="button"
              className="primary"
              style={{ fontSize: 12 }}
              onClick={() => saveAll()}
              disabled={loading || saving}
            >
              {saving ? "Saving…" : "Save All"}
            </button>
            <button className="ghost" onClick={requestClose} type="button">
              ✕
            </button>
          </div>
        </div>
        <div className="muted" style={{ padding: "0 16px 12px", fontSize: 12 }}>
          <strong>Sections</strong> — One stored YAML per device. Empty / Auto (from recipe) / Edited. Reset = restore to current recipe; Save = store. <strong>Full YAML</strong> shows the compiled result.
        </div>
        <div style={{ padding: "0 16px 8px", fontSize: 11, background: "rgba(200,160,80,0.08)", borderBottom: "1px solid rgba(200,160,80,0.2)", color: "rgba(220,200,140,0.95)" }}>
          Advanced: editing raw YAML here can break the device if invalid. Validate with Deploy or Full YAML before flashing.
        </div>
        <div style={{ flex: 1, overflow: "auto", padding: "0 16px 16px" }}>
          {loading && (
            <div className="muted" style={{ padding: 24, textAlign: "center" }}>
              Loading sections…
            </div>
          )}
          {error && (
            <div style={{ padding: 12, background: "rgba(200,80,80,0.2)", borderRadius: 6, marginBottom: 12 }}>
              {error}
            </div>
          )}
          {syntaxError && (
            <div style={{ padding: 12, background: "rgba(200,80,80,0.2)", borderRadius: 6, marginBottom: 12 }}>
              YAML syntax: {syntaxError}
            </div>
          )}
          {!loading && !error && (
            <>
              {categoryOrder.map((catLabel) => {
                const keys = categories[catLabel] || [];
                const withContent = keys.filter((k) => (sections[k] ?? "").trim().length > 0);
                return (
                  <details key={catLabel} style={{ marginBottom: 12 }}>
                    <summary
                      style={{
                        cursor: "pointer",
                        fontSize: 13,
                        fontWeight: 500,
                        padding: "8px 0",
                        borderBottom: "1px solid rgba(255,255,255,0.1)",
                      }}
                    >
                      {catLabel} ({withContent.length})
                    </summary>
                    <div style={{ padding: "8px 0" }}>
                      {keys.map((sectionKey) => {
                        const effective = (sections[sectionKey] ?? "").trim();
                        const defaultContent = (defaults[sectionKey] ?? "").trim();
                        const state = sectionState(sections[sectionKey] ?? "", defaults[sectionKey] ?? "");
                        const stateLabel = state === "empty" ? "Empty" : state === "auto" ? "Auto" : "Edited";
                        const isCompilerOwned = compilerOwned.has(sectionKey);
                        const bgSection = state === "edited" ? "rgba(100,160,255,0.06)" : "rgba(255,255,255,0.03)";
                        const borderSection = state === "edited" ? "1px solid rgba(100,160,255,0.2)" : "1px solid rgba(255,255,255,0.08)";
                        return (
                          <details
                            key={sectionKey}
                            style={{
                              marginBottom: 8,
                              background: bgSection,
                              borderRadius: 6,
                              border: borderSection,
                            }}
                          >
                            <summary
                              style={{
                                cursor: "pointer",
                                fontSize: 12,
                                padding: "8px 10px",
                                display: "flex",
                                alignItems: "center",
                                gap: 8,
                                flexWrap: "wrap",
                              }}
                            >
                              <code style={{ fontWeight: 600 }}>{sectionKey}</code>
                              <span
                                className={state === "empty" ? "muted" : undefined}
                                style={{ fontSize: 10 }}
                                title={state === "empty" ? "No content" : state === "auto" ? "From recipe (unchanged)" : "You have edited this section"}
                              >
                                {stateLabel}
                              </span>
                              {isCompilerOwned && (
                                <span
                                  style={{
                                    fontSize: 10,
                                    padding: "1px 6px",
                                    borderRadius: 4,
                                    background: "rgba(180,120,80,0.25)",
                                    color: "rgba(255,220,180,0.95)",
                                  }}
                                  title="Generated by app; replaced at compile"
                                >
                                  Generated
                                </span>
                              )}
                            </summary>
                            <div style={{ padding: "0 10px 10px" }}>
                              {state === "empty" && !isCompilerOwned && (
                                <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>No content. Add YAML below or use Reset to restore from recipe.</div>
                              )}
                              <YamlEditor
                                value={sections[sectionKey] ?? ""}
                                onChange={(v) => !isCompilerOwned && setSectionContent(sectionKey, v)}
                                placeholder={`# ${sectionKey}\n  ...`}
                                minHeight={100}
                                maxHeight="35vh"
                                variant={state === "edited" ? "manual" : "default"}
                                readOnly={isCompilerOwned}
                              />
                              {!isCompilerOwned && (
                                <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                                  <button
                                    type="button"
                                    className="secondary"
                                    style={{ fontSize: 11 }}
                                    onClick={() => resetSection(sectionKey)}
                                  >
                                    Reset
                                  </button>
                                  <button
                                    type="button"
                                    className="primary"
                                    style={{ fontSize: 11 }}
                                    onClick={() => saveAll()}
                                    disabled={saving}
                                  >
                                    Save
                                  </button>
                                </div>
                              )}
                            </div>
                          </details>
                        );
                      })}
                    </div>
                  </details>
                );
              })}
            </>
          )}
        </div>
        {cleanupMessage && (
          <div className="muted" style={{ padding: "8px 16px", fontSize: 12, borderTop: "1px solid rgba(255,255,255,0.08)" }}>
            {cleanupMessage}
          </div>
        )}
        <div style={{ padding: "12px 16px", borderTop: "1px solid rgba(255,255,255,0.1)", display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" className="secondary" onClick={requestClose}>
            Close
          </button>
          <button
            type="button"
            className="secondary"
            title="Remove Components blocks that reference deleted widgets"
            onClick={async () => {
              setCleanupMessage(null);
              setCleanupBusy(true);
              try {
                // Pass project with panel's current sections so backend has full content to clean
                const projectWithSections = { ...project, sections: { ...(project.sections || {}), ...sections } };
                const res = await cleanupOrphanedComponents(projectWithSections);
                if (res.removed.length > 0) {
                  const cleanedSections = res.project.sections || {};
                  setSections(cleanedSections);
                  if (onSaveAndPersist) {
                    setSaving(true);
                    try {
                      const { project: updated } = await saveSections(res.project, cleanedSections);
                      setProject(updated, true);
                      setProjectDirty(true);
                      await onSaveAndPersist(updated);
                      setCleanupMessage(`Removed ${res.removed.length} orphaned reference(s) and saved.`);
                    } finally {
                      setSaving(false);
                    }
                  } else {
                    setProject(res.project, true);
                    setProjectDirty(true);
                    setCleanupMessage(`Removed ${res.removed.length} orphaned reference(s). Save All to persist.`);
                  }
                } else {
                  setCleanupMessage("No orphaned component references found.");
                }
              } catch (e: any) {
                setCleanupMessage(e?.message ?? "Cleanup failed");
              } finally {
                setCleanupBusy(false);
              }
            }}
            disabled={loading || cleanupBusy}
          >
            {cleanupBusy ? "Cleanup…" : "Cleanup orphaned"}
          </button>
        </div>
      </div>
    </div>
  );
}
