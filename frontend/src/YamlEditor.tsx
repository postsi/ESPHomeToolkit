/**
 * Reusable YAML editor using CodeMirror 6. Use for all YAML display/edit surfaces.
 * Supports editable and read-only modes; dark theme to match the app.
 */
import React, { useMemo } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { yaml } from "@codemirror/lang-yaml";
import { EditorView } from "@codemirror/view";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags } from "@lezer/highlight";

export type YamlEditorProps = {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  placeholder?: string;
  minHeight?: string | number;
  maxHeight?: string | number;
  /** Optional container class or inline style for the wrapper */
  className?: string;
  style?: React.CSSProperties;
  /** Border/style when "manual" or highlighted (e.g. Components panel) */
  variant?: "default" | "manual";
};

/** Brighter syntax colours for YAML on dark background (keys, strings, etc. easy to read). */
const brightYamlHighlight = HighlightStyle.define([
  { tag: tags.keyword, color: "#c084fc" },
  { tag: [tags.propertyName, tags.name], color: "#7dd3fc" },
  { tag: tags.labelName, color: "#93c5fd" },
  { tag: [tags.string, tags.inserted], color: "#86efac" },
  { tag: [tags.number, tags.integer], color: "#fde047" },
  { tag: [tags.bool, tags.atom], color: "#fdba74" },
  { tag: [tags.comment, tags.meta], color: "#94a3b8" },
  { tag: [tags.definition(tags.name), tags.separator], color: "#e2e8f0" },
]);

const darkTheme = EditorView.theme({
  "&": { fontSize: "11px" },
  "&.cm-editor": {
    borderRadius: 4,
    border: "1px solid rgba(255,255,255,0.15)",
    background: "rgba(0,0,0,0.2)",
  },
  "&.cm-editor.cm-focused": { outline: "none" },
  ".cm-scroller": { fontFamily: "ui-monospace, monospace" },
  ".cm-content": { color: "#e2e8f0", caretColor: "#e2e8f0" },
  ".cm-gutters": {
    background: "rgba(0,0,0,0.25)",
    borderRight: "1px solid rgba(255,255,255,0.08)",
    color: "rgba(255,255,255,0.4)",
  },
});

const manualTheme = EditorView.theme({
  "&.cm-editor": {
    border: "1px solid rgba(100,160,255,0.2)",
    background: "rgba(100,160,255,0.05)",
  },
});

export default function YamlEditor({
  value,
  onChange,
  readOnly = false,
  placeholder,
  minHeight = 100,
  maxHeight = "40vh",
  className,
  style,
  variant = "default",
}: YamlEditorProps) {
  const extensions = useMemo(() => {
    const exts = [
      yaml(),
      darkTheme,
      syntaxHighlighting(brightYamlHighlight),
      EditorView.lineWrapping,
    ];
    if (variant === "manual") exts.push(manualTheme);
    if (readOnly) exts.push(EditorView.editable.of(false));
    return exts;
  }, [readOnly, variant]);

  const height =
    typeof minHeight === "number" ? `${minHeight}px` : String(minHeight);
  const maxH = typeof maxHeight === "number" ? `${maxHeight}px` : String(maxHeight);

  return (
    <div className={className} style={{ minHeight: height, maxHeight: maxH, ...style }}>
      <CodeMirror
        value={value}
        onChange={onChange}
        readOnly={readOnly}
        placeholder={placeholder}
        extensions={extensions}
        height={height}
        basicSetup={{
          lineNumbers: true,
          foldGutter: false,
          indentOnInput: true,
          bracketMatching: true,
          highlightActiveLine: !readOnly,
          highlightActiveLineGutter: !readOnly,
        }}
      />
    </div>
  );
}
