import React, { useCallback, useMemo, useRef, useState } from "react";
import { Stage, Layer, Rect, Text, Transformer, Line, Group, Circle, Arc, Shape } from "react-konva";
import { computeArcBackground, pointerAngleToValue, valueToAngle } from "./arcGeometry";
import {
  snap,
  toFillColor,
  fontSizeFromFontId,
  textLayoutFromWidget,
  safeWidgets,
  computeLayoutPositions,
  clampResizeBox,
  clampDragPosition,
  clampDragPositionCentered,
  widgetsInSelectionRect,
  parentInfo as parentInfoUtil,
  absPos as absPosUtil,
} from "./canvasUtils";

type Widget = {
  id: string;
  type: string;
  x: number;
  y: number;
  w: number;
  h: number;
  parent_id?: string;
  props?: any;
  style?: any;
  events?: any;
};

type Props = {
  widgets: Widget[];
  selectedIds: string[];
  width: number;
  height: number;
  gridSize: number;
  showGrid: boolean;
  /** LVGL disp_bg_color for preview (hex e.g. #1a1a2e). */
  dispBgColor?: string;
  liveOverrides?: Record<string, { text?: string; value?: number; checked?: boolean; selected_index?: number }>;
  onSelect: (id: string, additive: boolean) => void;
  onSelectNone: () => void;
  onDropCreate?: (type: string, x: number, y: number) => void;
  onChangeMany: (patches: { id: string; patch: Partial<Widget> }[], commit?: boolean) => void;
  /** When true, widgets are interactive for simulation (click/drag update state, actions fire). */
  simulationMode?: boolean;
  /** Simulation state overrides (merged with liveOverrides when simulationMode). */
  simOverrides?: Record<string, { text?: string; value?: number; checked?: boolean; selected_index?: number }>;
  onSimulateUpdate?: (widgetId: string, updates: { value?: number; checked?: boolean; selected_index?: number; text?: string }) => void;
  onSimulateAction?: (widgetId: string, event: string, payload?: { value?: number; checked?: boolean; selected_index?: number; color?: string; text?: string }) => void;
  /** When in simulation mode, opening a colour picker widget opens this callback instead of firing on_click. */
  onOpenColorPicker?: (widgetId: string, currentColorHex: string) => void;
  /** When in simulation mode, opening a white picker widget opens this callback to set color temp (mireds). */
  onOpenWhitePicker?: (widgetId: string, currentMireds: number) => void;
  /** When in simulation mode, opening a textarea widget opens this callback to edit text and fire on_value. */
  onOpenTextarea?: (widgetId: string, currentText: string) => void;
};

export default function Canvas({
  widgets: rawWidgets,
  selectedIds,
  width,
  height,
  gridSize,
  showGrid,
  dispBgColor,
  liveOverrides = {},
  onSelect,
  onSelectNone,
  simulationMode = false,
  simOverrides,
  onSimulateUpdate,
  onSimulateAction,
  onOpenColorPicker,
  onOpenWhitePicker,
  onOpenTextarea,
  onDropCreate,
  onChangeMany,
}: Props) {
  const widgets = useMemo(() => safeWidgets(rawWidgets) as Widget[], [rawWidgets]);
    const layoutPos = useMemo(() => computeLayoutPositions(widgets), [widgets]);
const stageRef = useRef<any>(null);
  const trRef = useRef<any>(null);

  // Remember positions at drag start for multi-drag delta application
  const dragStartRef = useRef<Record<string, { x: number; y: number }>>({});
  // Last value during sim drag (so on_release can send current value without relying on async setState)
  const lastSimValueRef = useRef<Record<string, number>>({});
  // Box selection: drag on empty space to select multiple widgets
  const [selectionBox, setSelectionBox] = useState<{ startX: number; startY: number; endX: number; endY: number } | null>(null);
  const boxSelectStartRef = useRef<{ x: number; y: number } | null>(null);
  const BOX_SELECT_THRESHOLD = 5;

  React.useEffect(() => {
    if (!trRef.current) return;
    const nodes = selectedIds
      .map((id) => stageRef.current?.findOne(`#${id}`))
      .filter(Boolean);
    trRef.current.nodes(nodes);
    trRef.current.getLayer()?.batchDraw();
  }, [selectedIds]);

  // When box-selecting, listen for mouseup globally so we catch release outside the stage
  const finishSelectionBox = useCallback(() => {
    if (!selectionBox) return;
    const { startX, startY, endX, endY } = selectionBox;
    const minX = Math.min(startX, endX);
    const maxX = Math.max(startX, endX);
    const minY = Math.min(startY, endY);
    const maxY = Math.max(startY, endY);
    const topLevel = widgets.filter((w) => !w.parent_id);
    const items = topLevel.map((w) => {
      const { ax, ay } = absPos(w);
      return { id: w.id, ax, ay, w: w.w || 100, h: w.h || 50 };
    });
    const idsInBox = widgetsInSelectionRect(minX, maxX, minY, maxY, items);
    setSelectionBox(null);
    if (idsInBox.length > 0) {
      onSelectNone();
      idsInBox.forEach((id) => onSelect(id, true));
    } else {
      onSelectNone();
    }
  }, [selectionBox, widgets, onSelect, onSelectNone]);

  React.useEffect(() => {
    if (!selectionBox) return;
    const onUp = () => {
      finishSelectionBox();
      boxSelectStartRef.current = null;
    };
    window.addEventListener("mouseup", onUp);
    return () => window.removeEventListener("mouseup", onUp);
  }, [selectionBox, finishSelectionBox]);

  const selectedSet = new Set(selectedIds);
  const [dragAtLimit, setDragAtLimit] = useState(false);
  const [resizeAtLimit, setResizeAtLimit] = useState(false);

  const widgetById = useMemo(() => {
    const m = new Map<string, Widget>();
    for (const w of widgets) m.set(w.id, w);
    return m;
  }, [widgets]);

  const childrenByParent = useMemo(() => {
    const m = new Map<string, Widget[]>();
    for (const w of widgets) {
      if (!w.parent_id) continue;
      let arr = m.get(w.parent_id);
      if (!arr) { arr = []; m.set(w.parent_id, arr); }
      arr.push(w);
    }
    return m;
  }, [widgets]);

  const parentInfo = (w: Widget) => parentInfoUtil(w, widgetById, width, height);
  const absPos = (w: Widget) => absPosUtil(w, widgetById, width, height);

  const renderWidget = (w: Widget, isSel: boolean, opts?: { localPosition?: boolean }) => {
    const { ax, ay } = opts?.localPosition ? { ax: w.x, ay: w.y } : absPos(w);
    const override = simulationMode ? { ...liveOverrides[w.id], ...simOverrides?.[w.id] } : liveOverrides[w.id];
    // Simple, intentionally lightweight previews (not pixel-perfect LVGL).
    // The goal is to make layouts usable while we keep the runtime YAML generator authoritative.
    const p = w.props || {};
    const s = w.style || {};
    const title = (override?.text !== undefined ? override.text : (p.text ?? p.label ?? p.name ?? w.type)) as string;

    // Style helpers (schema-driven properties land in `style`). Support LVGL extras:
    // opacity (opa), shadow_ofs_x/y, shadow_width/color/opa/spread, clip_corner, border_side.
    const bg = toFillColor(s.bg_color ?? s.background_color ?? p.bg_color, "#111827");
    const isColorPicker = w.type && String(w.type).toLowerCase() === "color_picker";
    const isWhitePicker = w.type && String(w.type).toLowerCase() === "white_picker";
    const fillColor = isColorPicker
      ? toFillColor(override?.value !== undefined ? override.value : (p.value ?? s.bg_color), "#4080FF")
      : isWhitePicker
        ? (() => {
            const mireds = override?.value !== undefined ? override.value : Number(p.value ?? 326) || 326;
            const m = Math.max(153, Math.min(500, mireds));
            const t = (m - 153) / (500 - 153);
            const r = 255;
            const g = Math.round(255 - 75 * t);
            const b = Math.round(255 - 135 * t);
            return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${b.toString(16).padStart(2, "0")}`;
          })()
        : bg;
    const border = toFillColor(s.border_color ?? p.border_color, isSel ? "#059669" : "#374151");
    const borderWidth = Number(s.border_width ?? p.border_width ?? 2);
    const opacityRaw = s.opa ?? p.opacity ?? 100;
    const opacity = typeof opacityRaw === "number" ? opacityRaw / 100 : 1;
    const radiusRaw = Math.min(12, Math.max(0, Number(s.radius ?? s.corner_radius ?? p.radius ?? p.corner_radius ?? 8)));
    const radius = Math.min(radiusRaw, Math.floor(w.w / 2), Math.floor(w.h / 2));
    const shadowW = Number(s.shadow_width ?? 0);
    const shadowOfsX = Number(s.shadow_ofs_x ?? 0);
    const shadowOfsY = Number(s.shadow_ofs_y ?? 0);
    const shadowCol = toFillColor(s.shadow_color, "#000000");
    const shadowOpa = Number(s.shadow_opa ?? 100) / 100;
    const textColor = toFillColor(s.text_color ?? p.text_color, "#e5e7eb");
    // Arc children in a group: transparent base so concentric rings don't cover each other.
    const isArcChild = !!(w.type && String(w.type).toLowerCase().includes("arc") && w.parent_id);
    const fontId = s.text_font ?? p.text_font;
    const fontSize = Math.max(8, Math.min(48, fontSizeFromFontId(fontId) ?? 16)); // Canvas preview: mimic font id size

    const hasShadow = shadowW > 0 || shadowOfsX !== 0 || shadowOfsY !== 0;
    const outlineW = Math.max(0, Number(s.outline_width ?? 0));
    const outlinePad = Number(s.outline_pad ?? 0);
    const outlineColor = toFillColor(s.outline_color, "#374151");
    const outlineOpa = Number(s.outline_opa ?? 0) / 100;
    const transformAngle = Number(s.transform_angle ?? 0);
    const transformZoom = Number(s.transform_zoom ?? 100) / 100;
    const isSliderOrArcOrBar = w.type === "slider" || w.type === "arc" || w.type === "arc_labeled" || w.type === "bar";
    const simDraggable = simulationMode && isSliderOrArcOrBar;
    const handleSimClick = () => {
      console.log("[Simulator] Canvas handleSimClick", w.id, w.type, { simulationMode, hasOnSimulateAction: !!onSimulateAction });
      if (!simulationMode) return;
      if (w.type === "color_picker" && onOpenColorPicker) {
        onOpenColorPicker(w.id, fillColor);
        return;
      }
      if (w.type === "white_picker" && onOpenWhitePicker) {
        const mireds = override?.value !== undefined ? override.value : Math.max(153, Math.min(500, Number(p.value ?? 326) || 326));
        onOpenWhitePicker(w.id, mireds);
        return;
      }
      if (w.type === "textarea" && onOpenTextarea) {
        const displayText = override?.text !== undefined ? override.text : String(p.text ?? "Text…");
        onOpenTextarea(w.id, displayText);
        return;
      }
      if (!onSimulateUpdate && !onSimulateAction) return;
      if (w.type === "button" || w.type === "container" || w.type === "obj") {
        onSimulateAction?.(w.id, "on_click");
      } else if (w.type === "switch") {
        const cur = override?.checked ?? (p as any).state ?? false;
        const nextChecked = !cur;
        onSimulateUpdate?.(w.id, { checked: nextChecked });
        onSimulateAction?.(w.id, "on_change", { checked: nextChecked });
      } else if (w.type === "dropdown" || w.type === "roller") {
        const opts = Array.isArray(p.options) ? p.options : [];
        const n = Math.max(1, opts.length);
        const cur = override?.selected_index ?? (p as any).selected_index ?? 0;
        const next = (cur + 1) % n;
        onSimulateUpdate?.(w.id, { selected_index: next });
        onSimulateAction?.(w.id, "on_change", { selected_index: next });
      } else if (w.type === "checkbox") {
        const cur = override?.checked ?? (p as any).checked ?? (p as any).state ?? false;
        const nextChecked = !cur;
        onSimulateUpdate?.(w.id, { checked: nextChecked });
        onSimulateAction?.(w.id, "on_change", { checked: nextChecked });
      }
    };
    const handleSimDragMove = (e: any) => {
      if (!simulationMode || !onSimulateUpdate || !isSliderOrArcOrBar) return;
      const stage = e.target.getStage();
      const pos = stage?.getPointerPosition();
      if (!pos) return;
      const minVal = Number(p.min_value ?? 0);
      const maxVal = Number(p.max_value ?? 100);
      if (w.type === "slider") {
        const pad = 8;
        const trackLen = w.w - pad * 2;
        const frac = Math.max(0, Math.min(1, (pos.x - ax - pad) / trackLen));
        const val = minVal + frac * (maxVal - minVal);
        const rounded = Math.round(val);
        lastSimValueRef.current[w.id] = rounded;
        onSimulateUpdate(w.id, { value: rounded });
      } else if (w.type === "bar") {
        const pad = 8;
        const isVert = w.h > w.w;
        const trackLen = isVert ? w.h - pad * 2 : w.w - pad * 2;
        const frac = isVert
          ? Math.max(0, Math.min(1, (pos.y - ay - pad) / trackLen))
          : Math.max(0, Math.min(1, (pos.x - ax - pad) / trackLen));
        const val = minVal + frac * (maxVal - minVal);
        const rounded = Math.round(val);
        lastSimValueRef.current[w.id] = rounded;
        onSimulateUpdate(w.id, { value: rounded });
      } else if (w.type === "arc" || w.type === "arc_labeled") {
        const cx = ax + w.w / 2;
        const cy = ay + w.h / 2;
        const angle = Math.atan2(pos.y - cy, pos.x - cx) * (180 / Math.PI);
        const pointerDeg = angle < 0 ? angle + 360 : angle;
        const rot = Number(p.rotation ?? 0);
        const startAngle = Number(p.start_angle ?? 135);
        const endAngle = Number(p.end_angle ?? 45);
        const mode = String(p.mode ?? "NORMAL").toUpperCase() as "NORMAL" | "REVERSE" | "SYMMETRICAL";
        const val = pointerAngleToValue(rot, startAngle, endAngle, mode, minVal, maxVal, pointerDeg);
        const rounded = Math.round(val);
        lastSimValueRef.current[w.id] = rounded;
        onSimulateUpdate(w.id, { value: rounded });
      }
    };
    const handleSimClickSetValue = (e: any) => {
      if (!simulationMode || !isSliderOrArcOrBar) return;
      e.cancelBubble = true;
      handleSimDragMove(e);
      if (onSimulateAction) {
        const value = lastSimValueRef.current[w.id];
        onSimulateAction(w.id, "on_release", value != null ? { value } : undefined);
      }
    };
    // Base background (optional outline behind, then main rect); selection outline when selected
    const base = (
      <>
        {isSel && (
          <Rect x={ax - 3} y={ay - 3} width={w.w + 6} height={w.h + 6} stroke="#06b6d4" strokeWidth={2} dash={[8, 4]} cornerRadius={radius + 3} fillEnabled={false} listening={false} />
        )}
        {outlineW > 0 && (
          <Rect x={ax - outlinePad - outlineW} y={ay - outlinePad - outlineW} width={w.w + 2 * (outlinePad + outlineW)} height={w.h + 2 * (outlinePad + outlineW)} stroke={outlineColor} strokeWidth={outlineW} cornerRadius={radius + outlinePad + outlineW} fillEnabled={false} opacity={outlineOpa} listening={false} />
        )}
        <Rect
          id={w.id}
          x={transformAngle !== 0 || transformZoom !== 1 ? ax + w.w / 2 : ax}
          y={transformAngle !== 0 || transformZoom !== 1 ? ay + w.h / 2 : ay}
          width={w.w}
          height={w.h}
          offsetX={transformAngle !== 0 || transformZoom !== 1 ? w.w / 2 : 0}
          offsetY={transformAngle !== 0 || transformZoom !== 1 ? w.h / 2 : 0}
          rotation={transformAngle}
          scaleX={transformZoom}
          scaleY={transformZoom}
          fill={isArcChild ? "transparent" : fillColor}
          stroke={isArcChild ? "transparent" : border}
          strokeWidth={isArcChild ? 0 : borderWidth}
          cornerRadius={radius}
          opacity={opacity}
          {...(hasShadow && {
          shadowColor: shadowCol,
          shadowBlur: shadowW || 4,
          shadowOffset: { x: shadowOfsX, y: shadowOfsY },
          shadowOpacity: shadowOpa,
        })}
        draggable={!w.parent_id && (!simulationMode || !simDraggable)}
        dragBoundFunc={simulationMode
          ? (simDraggable ? (pos) => ({ x: (transformAngle !== 0 || transformZoom !== 1 ? ax + w.w / 2 : ax), y: (transformAngle !== 0 || transformZoom !== 1 ? ay + w.h / 2 : ay) }) : undefined)
          : (pos) => {
              const isCentered = transformAngle !== 0 || transformZoom !== 1;
              const r = isCentered
                ? clampDragPositionCentered(pos.x, pos.y, w.w, w.h, width, height)
                : clampDragPosition(pos.x, pos.y, w.w, w.h, width, height);
              setDragAtLimit(r.atLimit);
              return { x: r.x, y: r.y };
            }}
        onClick={simulationMode ? (e) => { e.cancelBubble = true; handleSimClick(); } : (e) => onSelect(w.parent_id || w.id, !!e.evt.shiftKey)}
        onTap={simulationMode ? (e) => { e.cancelBubble = true; handleSimClick(); } : (e) => onSelect(w.parent_id || w.id, !!(e.evt as any).shiftKey)}
        onDragMove={simDraggable ? handleSimDragMove : undefined}
        onDragStart={!simulationMode ? () => {
          // snapshot selected positions
          const snap0: Record<string, { x: number; y: number }> = {};
          for (const id of selectedIds.length ? selectedIds : [w.id]) {
            const ww = widgetById.get(id);
            if (ww) snap0[id] = { x: ww.x, y: ww.y };
          }
          dragStartRef.current = snap0;
        } : undefined}
        onDragEnd={(e) => {
          if (simulationMode) {
            if (onSimulateAction && (w.type === "slider" || w.type === "arc" || w.type === "arc_labeled" || w.type === "bar")) {
              const value = lastSimValueRef.current[w.id];
              onSimulateAction(w.id, "on_release", value != null ? { value } : undefined);
            }
            return;
          }
          const node = e.target;
          const alt = !!e.evt.altKey; // hold ALT to disable snapping
          const nx = alt ? node.x() : snap(node.x(), gridSize);
          const ny = alt ? node.y() : snap(node.y(), gridSize);

          // For parented widgets, node.x/node.y are absolute; store relative in model.
          const parent = w.parent_id ? widgetById.get(w.parent_id) : undefined;
          const parentAbs = parent ? absPos(parent) : { ax: 0, ay: 0 };
          const modelX = nx - parentAbs.ax;
          const modelY = ny - parentAbs.ay;

          const start = dragStartRef.current[w.id] || { x: w.x, y: w.y };
          const dx = modelX - start.x;
          const dy = modelY - start.y;

          const ids = selectedIds.length ? selectedIds : [w.id];
          const patches = ids
            .map((id) => {
              const s = dragStartRef.current[id] || widgetById.get(id);
              if (!s) return null;
              return { id, patch: { x: (s as any).x + dx, y: (s as any).y + dy } };
            })
            .filter(Boolean) as { id: string; patch: Partial<Widget> }[];

          onChangeMany(patches, true);
          setDragAtLimit(false);
        }}
        onTransformEnd={(e) => {
          const node = e.target;
          const alt = !!(e.evt as { altKey?: boolean }).altKey; // hold ALT to disable snapping
          const scaleX = node.scaleX();
          const scaleY = node.scaleY();
          node.scaleX(1);
          node.scaleY(1);

          const oldW = node.width();
          const oldH = node.height();
          let ww = Math.max(20, oldW * scaleX);
          let hh = Math.max(20, oldH * scaleY);
          let xx = node.x();
          let yy = node.y();

          if (!alt) {
            ww = snap(ww, gridSize);
            hh = snap(hh, gridSize);
            xx = snap(xx, gridSize);
            yy = snap(yy, gridSize);
          }

          const children = childrenByParent.get(w.id);
          if (children && children.length > 0) {
            const sx = oldW > 0 ? ww / oldW : 1;
            const sy = oldH > 0 ? hh / oldH : 1;
            const patches: { id: string; patch: Partial<Widget> }[] = [
              { id: w.id, patch: { w: ww, h: hh } },
              ...children.map((c) => ({
                id: c.id,
                patch: {
                  x: c.x * sx,
                  y: c.y * sy,
                  w: Math.max(4, c.w * sx),
                  h: Math.max(4, c.h * sy),
                },
              })),
            ];
            onChangeMany(patches, true);
          } else {
            const parent = w.parent_id ? widgetById.get(w.parent_id) : undefined;
            const parentAbs = parent ? absPos(parent) : { ax: 0, ay: 0 };
            const modelX = xx - parentAbs.ax;
            const modelY = yy - parentAbs.ay;
            onChangeMany([{ id: w.id, patch: { x: modelX, y: modelY, w: ww, h: hh } }], true);
          }
          setResizeAtLimit(false);
        }}
      />
      </>
    );

    // Type-specific adornments
    const type = w.type.toLowerCase();
    // Colour picker / white picker: show only the swatch (no label/text)
    if (type === "color_picker" || type === "white_picker") {
      return <Group key={w.id}>{base}</Group>;
    }
    if (type.includes("label") && type !== "arc_labeled") {
      const layout = textLayoutFromWidget(ax, ay, w.w, w.h, p, s);
      const longMode = String(p.long_mode ?? s.long_mode ?? "CLIP").toUpperCase();
      const wrap = longMode === "WRAP";
      const ellipsisLabel = longMode !== "WRAP" && longMode !== "CLIP";
      let labelText = String(title);
      if (p.recolor || s.recolor) {
        labelText = labelText.replace(/#[\dA-Fa-f]{6}\s*/g, "").trim() || labelText;
      }
      return (
        <Group key={w.id}>
          {base}
          <Text
            text={labelText}
            x={layout.x}
            y={layout.y}
            width={layout.width}
            height={layout.height}
            align={layout.align}
            verticalAlign={layout.verticalAlign}
            fontSize={fontSize}
            fill={textColor}
            wrap={wrap ? "word" : undefined}
            ellipsis={ellipsisLabel}
            listening={false}
          />
        </Group>
      );
    }

    if (type.includes("button")) {
      const checked = override?.checked ?? (p as any).checked ?? false;
      const layout = textLayoutFromWidget(ax, ay, w.w, w.h, p, s);
      return (
        <Group key={w.id}>
          {base}
          <Rect
            x={ax + 6}
            y={ay + 6}
            width={w.w - 12}
            height={w.h - 12}
            fill={String(checked ? (s.inner_bg_color ?? "#065f46") : (s.inner_bg_color ?? "#0b1220"))}
            stroke={String(s.inner_border_color ?? (isSel ? "#34d399" : "#1f2937"))}
            strokeWidth={Number(s.inner_border_width ?? 2)}
            cornerRadius={Math.min(10, Math.max(0, Number(s.radius ?? s.corner_radius ?? p.radius ?? p.corner_radius ?? 10)), Math.floor((w.w - 12) / 2), Math.floor((w.h - 12) / 2))}
            listening={false}
          />
          <Text
            text={String(title || "Button")}
            x={layout.x}
            y={layout.y}
            width={layout.width}
            height={layout.height}
            align={layout.align}
            verticalAlign={layout.verticalAlign}
            fontSize={fontSize}
            fill={textColor}
            listening={false}
          />
        </Group>
      );
    }

    // Container: render children inside a group. With children, use a positioned Group so arcs/widgets render in local coords and the whole group is the drag target.
    if (type === "container" || type.includes("container")) {
      const kids = childrenByParent.get(w.id) || [];
      const clip = !!(p.clip_children ?? p.clipChildren);
      if (kids.length > 0) {
        const baseLocal = (
          <>
            {isSel && (
              <Rect x={-3} y={-3} width={w.w + 6} height={w.h + 6} stroke="#06b6d4" strokeWidth={2} dash={[8, 4]} cornerRadius={radius + 3} fillEnabled={false} listening={false} />
            )}
            {outlineW > 0 && (
              <Rect x={-outlinePad - outlineW} y={-outlinePad - outlineW} width={w.w + 2 * (outlinePad + outlineW)} height={w.h + 2 * (outlinePad + outlineW)} stroke={outlineColor} strokeWidth={outlineW} cornerRadius={radius + outlinePad + outlineW} fillEnabled={false} opacity={outlineOpa} listening={false} />
            )}
            <Rect
              x={0}
              y={0}
              width={w.w}
              height={w.h}
              fill={bg}
              stroke={border}
              strokeWidth={borderWidth}
              cornerRadius={radius}
              opacity={opacity}
              listening={false}
            />
          </>
        );
        return (
          <Group
            key={w.id}
            id={w.id}
            x={ax}
            y={ay}
            width={w.w}
            height={w.h}
            clipFunc={clip ? (ctx) => { ctx.rect(0, 0, w.w, w.h); } : undefined}
            draggable={!w.parent_id && (!simulationMode || !simDraggable)}
            dragBoundFunc={!simulationMode && !w.parent_id ? (pos) => {
              const r = clampDragPosition(pos.x, pos.y, w.w, w.h, width, height);
              setDragAtLimit(r.atLimit);
              return { x: r.x, y: r.y };
            } : undefined}
            onClick={simulationMode ? (e) => { e.cancelBubble = true; handleSimClick(); } : (e) => onSelect(w.parent_id || w.id, !!e.evt.shiftKey)}
            onTap={simulationMode ? (e) => { e.cancelBubble = true; handleSimClick(); } : (e) => onSelect(w.parent_id || w.id, !!(e.evt as any).shiftKey)}
            onDragStart={!simulationMode ? () => {
              const snap0: Record<string, { x: number; y: number }> = {};
              for (const id of selectedIds.length ? selectedIds : [w.id]) {
                const ww = widgetById.get(id);
                if (ww) snap0[id] = { x: ww.x, y: ww.y };
              }
              dragStartRef.current = snap0;
            } : undefined}
            onDragEnd={(e) => {
              if (simulationMode) return;
              const node = e.target;
              const alt = !!e.evt.altKey;
              const nx = alt ? node.x() : snap(node.x(), gridSize);
              const ny = alt ? node.y() : snap(node.y(), gridSize);
              const parent = w.parent_id ? widgetById.get(w.parent_id) : undefined;
              const parentAbs = parent ? absPos(parent) : { ax: 0, ay: 0 };
              const modelX = nx - parentAbs.ax;
              const modelY = ny - parentAbs.ay;
              const start = dragStartRef.current[w.id] || { x: w.x, y: w.y };
              const dx = modelX - start.x;
              const dy = modelY - start.y;
              const ids = selectedIds.length ? selectedIds : [w.id];
              const patches = ids
                .map((id) => {
                  const s = dragStartRef.current[id] || widgetById.get(id);
                  if (!s) return null;
                  return { id, patch: { x: (s as any).x + dx, y: (s as any).y + dy } };
                })
                .filter(Boolean) as { id: string; patch: Partial<Widget> }[];
              onChangeMany(patches, true);
              setDragAtLimit(false);
            }}
            onTransformEnd={(e) => {
              const node = e.target;
              const alt = !!(e.evt as { altKey?: boolean }).altKey;
              const scaleX = node.scaleX();
              const scaleY = node.scaleY();
              node.scaleX(1);
              node.scaleY(1);
              const oldW = node.width();
              const oldH = node.height();
              let ww = Math.max(20, oldW * scaleX);
              let hh = Math.max(20, oldH * scaleY);
              let xx = node.x();
              let yy = node.y();
              if (!alt) {
                ww = snap(ww, gridSize);
                hh = snap(hh, gridSize);
                xx = snap(xx, gridSize);
                yy = snap(yy, gridSize);
              }
              const children = childrenByParent.get(w.id);
              if (children && children.length > 0) {
                const sx = oldW > 0 ? ww / oldW : 1;
                const sy = oldH > 0 ? hh / oldH : 1;
                const patches: { id: string; patch: Partial<Widget> }[] = [
                  { id: w.id, patch: { w: ww, h: hh } },
                  ...children.map((c) => ({
                    id: c.id,
                    patch: {
                      x: c.x * sx,
                      y: c.y * sy,
                      w: Math.max(4, c.w * sx),
                      h: Math.max(4, c.h * sy),
                    },
                  })),
                ];
                onChangeMany(patches, true);
              } else {
                const parent = w.parent_id ? widgetById.get(w.parent_id) : undefined;
                const parentAbs = parent ? absPos(parent) : { ax: 0, ay: 0 };
                const modelX = xx - parentAbs.ax;
                const modelY = yy - parentAbs.ay;
                onChangeMany([{ id: w.id, patch: { x: modelX, y: modelY, w: ww, h: hh } }], true);
              }
              setResizeAtLimit(false);
            }}
          >
            {baseLocal}
            {kids.map((k) => renderWidget(k, selectedSet.has(k.id), { localPosition: true }))}
          </Group>
        );
      }
      return (
        <Group
          key={w.id}
          clipFunc={
            clip
              ? (ctx) => {
                  ctx.rect(ax, ay, w.w, w.h);
                }
              : undefined
          }
        >
          {base}
          {kids.map((k) => renderWidget(k, selectedSet.has(k.id)))}
        </Group>
      );
    }

    if (type === "bar") {
      const barMin = Number(p.min_value ?? 0);
      const barMax = Number(p.max_value ?? 100);
      const val = override?.value !== undefined ? override.value : Number(p.value ?? (barMin + barMax) / 2);
      const startVal = Number(p.start_value ?? barMin);
      const mode = String(p.mode ?? "NORMAL").toUpperCase();
      const isVert = w.h > w.w;
      const pad = Math.min(4, Math.floor(Math.min(w.w, w.h) / 4));
      const trackLen = Math.max(1, isVert ? w.h - pad * 2 : w.w - pad * 2);
      const thick = Math.max(1, Math.min(isVert ? w.w - pad * 2 : w.h - pad * 2, 20));
      let normStart = barMax > barMin ? (startVal - barMin) / (barMax - barMin) : 0;
      let normEnd = barMax > barMin ? (val - barMin) / (barMax - barMin) : 0.5;
      if (mode === "RANGE" && normStart > normEnd) [normStart, normEnd] = [normEnd, normStart];
      if (mode === "SYMMETRICAL") normStart = 0.5;
      const trackFill = String(s.bg_color ?? "#1f2937");
      const indFill = String((w.indicator || {}).bg_color ?? "#10b981");
      const barCornerR = Math.min(thick / 2, trackLen / 2);
      if (isVert) {
        const tx = ax + (w.w - thick) / 2;
        const ty = ay + pad;
        const indH = Math.max(0, trackLen * (normEnd - normStart));
        const indCornerR = Math.min(barCornerR, indH / 2);
        const simHandleBarV = simulationMode && simDraggable ? (
          <Rect x={ax} y={ay + pad} width={w.w} height={trackLen} fill="transparent" listening={true} draggable={true}
            dragBoundFunc={(pos) => ({ x: ax, y: ay + pad })}
            onClick={handleSimClickSetValue}
            onTap={handleSimClickSetValue}
            onDragMove={handleSimDragMove}
            onDragStart={() => {}}
            onDragEnd={() => {
              if (onSimulateAction) {
                const value = lastSimValueRef.current[w.id];
                onSimulateAction(w.id, "on_release", value != null ? { value } : undefined);
              }
            }}
          />
        ) : null;
        return (
          <Group key={w.id}>
            {base}
            <Rect x={tx} y={ty} width={thick} height={trackLen} fill={trackFill} cornerRadius={barCornerR} listening={false} />
            {indH > 0 && <Rect x={tx} y={ty + trackLen * (1 - normEnd)} width={thick} height={indH} fill={indFill} cornerRadius={indCornerR} listening={false} />}
            {simHandleBarV}
          </Group>
        );
      }
      const indW = Math.max(0, trackLen * (normEnd - normStart));
      const indCornerRH = Math.min(barCornerR, indW / 2);
      const simHandleBarH = simulationMode && simDraggable ? (
        <Rect x={ax + pad} y={ay} width={trackLen} height={w.h} fill="transparent" listening={true} draggable={true}
          dragBoundFunc={(pos) => ({ x: ax + pad, y: ay })}
          onClick={handleSimClickSetValue}
          onTap={handleSimClickSetValue}
          onDragMove={handleSimDragMove}
          onDragStart={() => {}}
          onDragEnd={() => {
            if (onSimulateAction) {
              const value = lastSimValueRef.current[w.id];
              onSimulateAction(w.id, "on_release", value != null ? { value } : undefined);
            }
          }}
        />
      ) : null;
      return (
        <Group key={w.id}>
          {base}
          <Rect x={ax + pad} y={ay + (w.h - thick) / 2} width={trackLen} height={thick} fill={trackFill} cornerRadius={barCornerR} listening={false} />
          {indW > 0 && <Rect x={ax + pad + trackLen * normStart} y={ay + (w.h - thick) / 2} width={indW} height={thick} fill={indFill} cornerRadius={indCornerRH} listening={false} />}
          {simHandleBarH}
        </Group>
      );
    }

    if (type === "slider") {
      const barMin = Number(p.min_value ?? 0);
      const barMax = Number(p.max_value ?? 100);
      const val = override?.value !== undefined ? override.value : Number(p.value ?? (barMin + barMax) / 2);
      const mode = String(p.mode ?? "NORMAL").toUpperCase();
      const isVert = w.h > w.w;
      const pad = 10;
      const trackLen = isVert ? w.h - pad * 2 : w.w - pad * 2;
      const thick = Math.min(isVert ? w.w - pad * 2 : w.h - pad * 2, 12);
      let norm = barMax > barMin ? (val - barMin) / (barMax - barMin) : 0.5;
      const normStart = 0;
      const trackFill = String(s.bg_color ?? "#1f2937");
      const indFill = String((w.indicator || {}).bg_color ?? "#10b981");
      const sliderKnob = w.knob || {};
      const sliderKnobR = Number(sliderKnob.radius ?? 0) > 0 ? Number(sliderKnob.radius) : (Number(sliderKnob.width ?? 0) > 0 || Number(sliderKnob.height ?? 0) > 0 ? Math.max(Number(sliderKnob.width ?? 0), Number(sliderKnob.height ?? 0)) / 2 : 0);
      const knobR = Math.max(6, sliderKnobR > 0 ? Math.min(sliderKnobR, (isVert ? w.w : w.h) / 2 - 4) : Math.min(thick * 1.2, (isVert ? w.w : w.h) / 4));
      const knobFill = String(sliderKnob.bg_color ?? s.bg_color ?? "#e5e7eb");
      if (isVert) {
        const tx = ax + w.w / 2;
        const ty = ay + pad;
        const knobY = ty + trackLen * (1 - norm);
        const simHandle = simulationMode && simDraggable ? (
          <Rect x={ax} y={ay + pad} width={w.w} height={trackLen} fill="transparent" listening={true} draggable={true}
            dragBoundFunc={(pos) => ({ x: ax, y: ay + pad })}
            onClick={handleSimClickSetValue}
            onTap={handleSimClickSetValue}
            onDragMove={handleSimDragMove}
            onDragStart={() => {}}
            onDragEnd={() => {
              if (onSimulateAction) {
                const value = lastSimValueRef.current[w.id];
                onSimulateAction(w.id, "on_release", value != null ? { value } : undefined);
              }
            }}
          />
        ) : null;
        return (
          <Group key={w.id}>
            {base}
            <Rect x={tx - thick / 2} y={ty} width={thick} height={trackLen} fill={trackFill} cornerRadius={thick / 2} listening={false} />
            <Rect x={tx - thick / 2} y={knobY} width={thick} height={trackLen * norm} fill={indFill} cornerRadius={thick / 2} listening={false} />
            <Circle x={tx} y={knobY} radius={knobR} fill={knobFill} stroke={border} strokeWidth={1} listening={false} />
            {simHandle}
          </Group>
        );
      }
      const knobX = ax + pad + trackLen * norm;
      const simHandleH = simulationMode && simDraggable ? (
        <Rect x={ax + pad} y={ay} width={trackLen} height={w.h} fill="transparent" listening={true} draggable={true}
          dragBoundFunc={(pos) => ({ x: ax + pad, y: ay })}
          onClick={handleSimClickSetValue}
          onTap={handleSimClickSetValue}
          onDragMove={handleSimDragMove}
          onDragStart={() => {}}
          onDragEnd={() => {
            if (onSimulateAction) {
              const value = lastSimValueRef.current[w.id];
              onSimulateAction(w.id, "on_release", value != null ? { value } : undefined);
            }
          }}
        />
      ) : null;
      return (
        <Group key={w.id}>
          {base}
          <Rect x={ax + pad} y={ay + (w.h - thick) / 2} width={trackLen} height={thick} fill={trackFill} cornerRadius={thick / 2} listening={false} />
          <Rect x={ax + pad} y={ay + (w.h - thick) / 2} width={trackLen * norm} height={thick} fill={indFill} cornerRadius={thick / 2} listening={false} />
          <Circle x={knobX} y={ay + w.h / 2} radius={knobR} fill={knobFill} stroke={border} strokeWidth={1} listening={false} />
          {simHandleH}
        </Group>
      );
    }

    if (type.includes("arc") || type.includes("gauge") || type === "meter") {
      // LVGL/Canvas convention: 0°=right, 90°=bottom, 180°=left, 270°=top; angles increase clockwise.
      const cx = ax + w.w / 2;
      const cy = ay + w.h / 2;
      // Use arc_width from props when set (e.g. WiFi fan rings); else default track thickness.
      const arcWidthProp = Number(p.arc_width ?? 0);
      const trackW = arcWidthProp > 0
        ? Math.max(1, Math.min(16, arcWidthProp))
        : Math.max(4, Math.min(16, Math.min(w.w, w.h) / 8));
      // Radius to center of track: scale with widget size so concentric arcs (e.g. 16–48px) each get distinct r.
      const half = Math.min(w.w, w.h) / 2;
      const r = Math.max(trackW / 2 + 1, half - trackW / 2 - 2);
      const rot = Number(p.rotation ?? 0);
      const bgStart = Number(p.start_angle ?? 135);
      const bgEnd = Number(p.end_angle ?? 45);
      // Background: draw from start to end clockwise (LVGL convention). See arcGeometry.test.ts.
      const bg = computeArcBackground(rot, bgStart, bgEnd);
      const { sweepCw } = bg;
      const min = Number(p.min_value ?? 0);
      const max = Number(p.max_value ?? 100);
      const val = override?.value !== undefined ? override.value : Number(p.value ?? (min + max) / 2);
      const mode = String(p.mode ?? "NORMAL").toUpperCase();
      let indStart = bgStart;
      let indSweep = 0;
      if (max > min) {
        const t = (val - min) / (max - min);
        if (mode === "SYMMETRICAL") {
          const mid = bgStart + sweepCw / 2;
          indStart = mid;
          indSweep = t * (sweepCw / 2);
        } else if (mode === "REVERSE") {
          indStart = bgEnd;
          indSweep = -t * sweepCw;
        } else {
          indSweep = t * sweepCw;
        }
      }
      const endDeg = indStart + indSweep;
      const knobAngleDeg = (rot + endDeg + 720) % 360;
      const knobDef = w.knob || {};
      let knobRadiusFromProp = Number(knobDef.radius ?? 0);
      // LVGL uses 0x7FFF as "default" knob size; treat any very large value as default for a visible knob
      if (knobRadiusFromProp > 24 || knobRadiusFromProp === 0x7FFF) knobRadiusFromProp = 0;
      const knobW = Number(knobDef.width ?? 0);
      const knobH = Number(knobDef.height ?? 0);
      const knobR = knobRadiusFromProp > 0
        ? Math.min(r - 2, knobRadiusFromProp)
        : (knobW > 0 || knobH > 0 ? Math.min(r - 2, Math.max(knobW, knobH) / 2) : Math.min(r - 2, 12));
      // Cap knob so small concentric arcs (e.g. WiFi fan) aren't covered by a huge knob
      const knobSize = Math.max(2, Math.min(6, knobR > 0 ? knobR : r - 1));
      const knobX = cx + r * Math.cos((knobAngleDeg * Math.PI) / 180);
      const knobY = cy + r * Math.sin((knobAngleDeg * Math.PI) / 180);
      const bgStroke = toFillColor(s.bg_color ?? p.bg_color, "#1f2937");
      // Indicator (filled part) must use a visible color; never fall back to bg_color or track matches fill (invisible).
      const indStroke = toFillColor((w.indicator || {}).bg_color, "#10b981");
      const knobFill = toFillColor(knobDef.bg_color ?? s.bg_color, "#e5e7eb");
      const innerR = r - trackW / 2;
      const outerR = r + trackW / 2;
      const toRad = (deg: number) => ((deg % 360 + 360) % 360) * (Math.PI / 180);
      const simHandleArc = simulationMode && simDraggable ? (
        <Circle x={cx} y={cy} radius={outerR + knobSize} fill="transparent" listening={true} draggable={true}
          dragBoundFunc={(pos) => ({ x: cx, y: cy })}
          onClick={handleSimClickSetValue}
          onTap={handleSimClickSetValue}
          onDragMove={handleSimDragMove}
          onDragStart={() => {}}
          onDragEnd={() => {
            if (onSimulateAction) {
              const value = lastSimValueRef.current[w.id];
              onSimulateAction(w.id, "on_release", value != null ? { value } : undefined);
            }
          }}
        />
      ) : null;
      // Indicator arc: from start to end of the filled segment (direction matches sweep sign)
      const indFromDeg = (rot + (indSweep >= 0 ? indStart : endDeg) + 720) % 360;
      const indToDeg = (rot + (indSweep >= 0 ? endDeg : indStart) + 720) % 360;
      const indStartRad = toRad(indFromDeg);
      const indEndRad = indToDeg === 0 ? 2 * Math.PI : toRad(indToDeg);
      const indClockwise = indSweep >= 0;
      return (
        <Group key={w.id}>
          {base}
          <Shape
            x={cx}
            y={cy}
            sceneFunc={(ctx, shape) => {
              ctx.beginPath();
              ctx.arc(0, 0, outerR, bg.bgStartRad, bg.bgEndRad, bg.anticlockwise);
              ctx.arc(0, 0, innerR, bg.bgEndRad, bg.bgStartRad, !bg.anticlockwise);
              ctx.closePath();
              ctx.fillStrokeShape(shape);
            }}
            fill={bgStroke}
            listening={false}
          />
          {indSweep !== 0 && (
            <Shape
              x={cx}
              y={cy}
              sceneFunc={(ctx, shape) => {
                ctx.beginPath();
                ctx.arc(0, 0, outerR, indStartRad, indEndRad, !indClockwise);
                ctx.arc(0, 0, innerR, indEndRad, indStartRad, indClockwise);
                ctx.closePath();
                ctx.fillStrokeShape(shape);
              }}
              fill={indStroke}
              listening={false}
            />
          )}
          {p.adjustable !== false && (
            <Circle x={knobX} y={knobY} radius={knobSize} fill={knobFill} stroke={border} strokeWidth={1} listening={false} />
          )}
          {simHandleArc}
          {w.type === "arc_labeled" && (() => {
            const labelOffset = Math.max(4, Math.min(20, Math.min(w.w, w.h) / 10));
            const labelR = outerR + labelOffset;
            const tickLen = Math.max(2, Math.min(6, Math.min(w.w, w.h) / 40));
            const labelFontSizeProp = Number(s.label_font_size ?? 0);
            const labelFontId = s.label_text_font ?? p.label_text_font ?? s.text_font ?? p.text_font;
            const baseFontSize = labelFontSizeProp > 0 ? labelFontSizeProp : (fontSizeFromFontId(labelFontId) ?? 12);
            const scaleRef = 100;
            const scaleFactor = Math.min(w.w, w.h) / scaleRef;
            const labelFontSize = Math.max(8, Math.min(24, Math.round(baseFontSize * scaleFactor)));
            const labelColor = toFillColor(s.label_text_color ?? p.label_text_color ?? s.text_color, "#e5e7eb");
            const minInt = Math.ceil(min);
            const maxInt = Math.floor(max);
            const tickInterval = Math.max(1, Number(s.tick_interval ?? p.tick_interval ?? 1));
            const labelInterval = Math.max(1, Number(s.label_interval ?? p.label_interval ?? 2));
            const ticks: number[] = [];
            for (let v = minInt; v <= maxInt; v++) {
              if ((v - minInt) % tickInterval === 0) ticks.push(v);
            }
            const labelValues: number[] = [];
            for (let v = minInt; v <= maxInt; v++) {
              if ((v - minInt) % labelInterval === 0) labelValues.push(v);
            }
            return (
              <>
                {ticks.map((value) => {
                  const angleDeg = valueToAngle(rot, bgStart, bgEnd, mode as "NORMAL" | "REVERSE" | "SYMMETRICAL", min, max, value);
                  const angleRad = (angleDeg * Math.PI) / 180;
                  const c = Math.cos(angleRad);
                  const s_ = Math.sin(angleRad);
                  return (
                    <Line
                      key={`tick-${value}`}
                      x={cx}
                      y={cy}
                      points={[(outerR - tickLen) * c, (outerR - tickLen) * s_, (outerR + tickLen) * c, (outerR + tickLen) * s_]}
                      stroke={labelColor}
                      strokeWidth={1}
                      listening={false}
                    />
                  );
                })}
                {labelValues.map((value) => {
                  const angleDeg = valueToAngle(rot, bgStart, bgEnd, mode as "NORMAL" | "REVERSE" | "SYMMETRICAL", min, max, value);
                  const angleRad = (angleDeg * Math.PI) / 180;
                  const lx = cx + labelR * Math.cos(angleRad);
                  const ly = cy + labelR * Math.sin(angleRad);
                  const text = String(value);
                  const pad = 6;
                  const box = Math.max(20, text.length * labelFontSize * 0.6 + pad);
                  const half = box / 2;
                  return (
                    <Text
                      key={`label-${value}`}
                      x={lx - half}
                      y={ly - labelFontSize / 2}
                      width={box}
                      height={labelFontSize + 2}
                      text={text}
                      fontSize={labelFontSize}
                      fill={labelColor}
                      align="center"
                      verticalAlign="middle"
                      listening={false}
                    />
                  );
                })}
              </>
            );
          })()}
          {/* ESPHome/LVGL arc has no built-in value label; device shows only arc + knob. A separate label widget is used if value text is needed. */}
        </Group>
      );
    }

    if (type === "switch") {
      const checked = !!(override?.checked ?? p.checked ?? p.state);
      const trackH = Math.max(14, w.h - 8);
      const switchKnob = w.knob || {};
      const thumbR = Math.max(4, Number(switchKnob.radius ?? 0) > 0 ? Number(switchKnob.radius) : (Number(switchKnob.width ?? 0) > 0 || Number(switchKnob.height ?? 0) > 0 ? Math.max(Number(switchKnob.width ?? 0), Number(switchKnob.height ?? 0)) / 2 : 8));
      const trackW = Math.max(40, w.w - 8);
      const knobX = checked ? ax + 4 + trackW - thumbR - 4 : ax + 4 + thumbR + 4;
      const trackFill = checked ? String((w.indicator || {}).bg_color ?? s.bg_color ?? "#10b981") : String(s.bg_color ?? "#1f2937");
      const knobFill = String(switchKnob.bg_color ?? s.text_color ?? "#e5e7eb");
      return (
        <Group key={w.id}>
          {base}
          <Rect x={ax + 4} y={ay + (w.h - trackH) / 2} width={trackW} height={trackH} fill={trackFill} cornerRadius={trackH / 2} listening={false} />
          <Circle x={knobX} y={ay + w.h / 2} radius={thumbR} fill={knobFill} stroke={border} strokeWidth={1} listening={false} />
        </Group>
      );
    }

    if (type === "checkbox") {
      const checked = !!(override?.checked ?? (w.state || {}).checked ?? p.checked ?? p.state);
      const size = Math.min(24, w.h - 8);
      const labelLeft = ax + 6 + size + 8;
      const labelW = w.w - 6 - size - 8;
      const layout = textLayoutFromWidget(labelLeft, ay, labelW, w.h, p, s);
      const labelText = String(p.text ?? (title || "Checkbox"));
      return (
        <Group key={w.id}>
          {base}
          <Rect x={ax + 6} y={ay + (w.h - size) / 2} width={size} height={size} stroke="#6b7280" strokeWidth={2} cornerRadius={4} fill="transparent" listening={false} />
          {checked && (
            <Text text="✓" x={ax + 6} y={ay + (w.h - size) / 2 - 2} width={size} height={size} align="center" fontSize={size - 4} fill="#10b981" listening={false} />
          )}
          <Text text={labelText} x={layout.x} y={layout.y} width={layout.width} height={layout.height} align={layout.align} verticalAlign={layout.verticalAlign} fontSize={fontSize} fill={textColor} listening={false} />
        </Group>
      );
    }

    if (type === "dropdown") {
      let opts: string[];
      if (Array.isArray(p.options)) {
        opts = p.options.map((o: any) => String(o ?? ""));
      } else if (typeof p.options === "string") {
        const s = p.options.trim();
        opts = s.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
        if (opts.length <= 1 && s.includes("\\n")) opts = s.split("\\n").map((x) => x.trim()).filter(Boolean);
      } else {
        opts = ["Option 1", "Option 2"];
      }
      if (opts.length === 0) opts = ["Select…"];
      const selIdx = Math.min(Math.max(0, Number(override?.selected_index ?? p.selected_index ?? 0)), opts.length - 1);
      const displayText = override?.text !== undefined ? String(override.text) : (p.selected_text && String(p.selected_text).trim() ? String(p.selected_text) : String(opts[selIdx] ?? opts[0] ?? "Select…"));
      const ddBg = toFillColor(s.bg_color ?? p.bg_color, "#1e293b");
      const selectedPart = (w as any).dropdown_list?.selected || (w as any).selected || {};
      const selText = toFillColor(selectedPart.text_color, textColor);
      const layout = textLayoutFromWidget(ax, ay, w.w, w.h, p, s);
      const textW = Math.max(20, layout.width - 24);
      return (
        <Group key={w.id}>
          {base}
          <Rect x={ax + 6} y={ay + 6} width={w.w - 12} height={w.h - 12} fill={ddBg} stroke="#334155" strokeWidth={1} cornerRadius={6} listening={false} />
          <Text text={displayText} x={layout.x} y={layout.y} width={textW} height={layout.height} align={layout.align} verticalAlign={layout.verticalAlign} fontSize={fontSize} fill={selText} ellipsis listening={false} />
          <Text text="▼" x={ax + w.w - 24} y={ay + (w.h - 12) / 2} width={16} align="center" fontSize={10} fill={selText} listening={false} />
        </Group>
      );
    }

    if (type === "image" || type === "animimg") {
      const clipCorner = !!(p.clip_corner ?? s.clip_corner);
      const innerRadius = clipCorner ? Math.min(8, (Math.min(w.w, w.h) - 12) / 4) : 0;
      return (
        <Group key={w.id}>
          {base}
          <Rect x={ax + 6} y={ay + 6} width={w.w - 12} height={w.h - 12} fill="#1f2937" stroke="#4b5563" strokeWidth={1} cornerRadius={innerRadius} listening={false} />
          <Text text="🖼" x={ax} y={ay + (w.h - 20) / 2} width={w.w} align="center" fontSize={14} fill="#9ca3af" listening={false} />
        </Group>
      );
    }

    if (type === "obj") {
      return (
        <Group key={w.id}>
          {base}
          <Text text="obj" x={ax + 8} y={ay + (w.h - 14) / 2} fontSize={12} fill="#9ca3af" fontStyle="italic" listening={false} />
        </Group>
      );
    }

    if (type === "textarea") {
      const taBg = toFillColor(s.bg_color ?? p.bg_color, "#1e293b");
      const layout = textLayoutFromWidget(ax + 6, ay + 6, w.w - 12, w.h - 12, p, s);
      const cursorPart = w.cursor || {};
      const cursorColor = toFillColor(cursorPart.color, textColor);
      const cursorW = Math.max(1, Math.min(8, Number(cursorPart.width ?? 2)));
      const cx = layout.x + 2;
      const displayText = override?.text !== undefined ? String(override.text) : String(p.text ?? "Text…");
      return (
        <Group key={w.id}>
          {base}
          <Rect x={ax + 6} y={ay + 6} width={w.w - 12} height={w.h - 12} fill={taBg} stroke="#334155" strokeWidth={1} cornerRadius={4} listening={false} />
          <Text text={displayText} x={layout.x} y={layout.y} width={layout.width} height={layout.height} align={layout.align} verticalAlign={layout.verticalAlign} fontSize={fontSize} fill={textColor} ellipsis listening={false} />
          <Rect x={cx} y={ay + 8} width={cursorW} height={w.h - 16} fill={cursorColor} listening={false} />
        </Group>
      );
    }

    if (type === "roller") {
      const opts = Array.isArray(p.options) ? p.options : ["Option 1", "Option 2", "Option 3"];
      const selected = Math.min(Math.max(0, Number(override?.selected_index ?? (p as any).selected_index ?? (p as any).selected ?? 0)), opts.length - 1);
      const visibleRows = Math.max(1, Math.min(20, Number((p as any).visible_row_count ?? 3)));
      const rowH = (w.h - 16) / visibleRows;
      const visible = Math.max(1, Math.floor((w.h - 16) / rowH));
      const start = Math.max(0, selected - Math.floor(visible / 2));
      const rollBg = toFillColor(s.bg_color ?? p.bg_color, "#1e293b");
      const itemsPart = (w as any).main || (w as any).items || {};
      const selectedPart = w.selected || {};
      const itemBg = toFillColor(itemsPart.bg_color, rollBg);
      const itemText = toFillColor(itemsPart.text_color, "#94a3b8");
      const selBg = toFillColor(selectedPart.bg_color, rollBg);
      const selText = toFillColor(selectedPart.text_color, textColor);
      return (
        <Group key={w.id}>
          {base}
          <Rect x={ax + 6} y={ay + 6} width={w.w - 12} height={w.h - 12} fill={rollBg} stroke="#334155" strokeWidth={1} cornerRadius={4} listening={false} />
          {opts.slice(start, start + visible).map((opt: string, i: number) => {
            const isSel = i + start === selected;
            return (
              <Group key={i} listening={false}>
                {isSel && selBg !== rollBg && <Rect x={ax + 8} y={ay + 8 + i * rowH} width={w.w - 16} height={rowH - 2} fill={selBg} cornerRadius={2} listening={false} />}
                <Text text={String(opt).slice(0, 20)} x={ax + 12} y={ay + 8 + i * rowH} width={w.w - 24} fontSize={Math.min(12, rowH - 4)} fill={isSel ? selText : itemText} ellipsis listening={false} />
              </Group>
            );
          })}
        </Group>
      );
    }

    if (type === "spinner") {
      const cx = ax + w.w / 2;
      const cy = ay + w.h / 2;
      const r = Math.min(w.w, w.h) / 4 - 4;
      const arcW = Math.max(3, r / 4);
      const indColor = String((w.indicator || {}).bg_color ?? "#10b981");
      return (
        <Group key={w.id}>
          {base}
          <Arc x={cx} y={cy} innerRadius={r - arcW / 2} outerRadius={r + arcW / 2} angle={90} rotation={0} stroke={indColor} strokeWidth={arcW} fillEnabled={false} clockwise listening={false} />
        </Group>
      );
    }

    if (type === "spinbox") {
      // Native spinbox: value box only (no +/-). Prebuilt "Spinbox with +/-" adds real - and + buttons as siblings.
      const rangeFrom = Number(p.range_from ?? 0);
      const rangeTo = Number(p.range_to ?? 100);
      const decimalPlaces = Math.max(0, Math.min(6, Number(p.decimal_places ?? 0)));
      const step = decimalPlaces >= 1 ? 10 ** -decimalPlaces : 1;
      const rawVal = override?.value !== undefined ? Number(override.value) : Number(p.value ?? 0);
      const displayVal = decimalPlaces >= 1 ? rawVal.toFixed(decimalPlaces) : String(Math.round(rawVal));
      const valueLayout = { x: ax, y: ay, width: w.w, height: w.h, align: "center" as const, verticalAlign: "middle" as const };
      const cursorPart = w.cursor || {};
      const cursorColor = toFillColor(cursorPart.color, textColor);
      const cursorW = Math.max(1, Math.min(8, Number(cursorPart.width ?? 2)));
      const cx = ax + 8;
      const handleSpinboxStep = (delta: number) => {
        if (!simulationMode || !onSimulateUpdate || !onSimulateAction) return;
        const next = Math.max(rangeFrom, Math.min(rangeTo, rawVal + delta * step));
        const rounded = decimalPlaces >= 1 ? Math.round(next * 10 ** decimalPlaces) / 10 ** decimalPlaces : Math.round(next);
        onSimulateUpdate(w.id, { value: rounded });
        onSimulateAction(w.id, "on_change", { value: rounded });
      };
      const zoneW = Math.min(36, Math.floor(w.w / 3));
      return (
        <Group key={w.id}>
          {base}
          <Rect x={ax + 6} y={ay + 6} width={w.w - 12} height={w.h - 12} fill="#0b1220" stroke="#374151" strokeWidth={1} cornerRadius={6} listening={false} />
          <Text text={displayVal} x={valueLayout.x} y={valueLayout.y} width={valueLayout.width} height={valueLayout.height} align={valueLayout.align} verticalAlign={valueLayout.verticalAlign} fontSize={fontSize} fill={textColor} listening={false} />
          <Rect x={cx} y={ay + 8} width={cursorW} height={w.h - 16} fill={cursorColor} listening={false} />
          {simulationMode && onSimulateUpdate && onSimulateAction && (
            <>
              <Rect x={ax} y={ay} width={zoneW} height={w.h} fill="transparent" listening onClick={(e) => { e.cancelBubble = true; handleSpinboxStep(-1); }} onTap={(e) => { e.cancelBubble = true; handleSpinboxStep(-1); }} />
              <Rect x={ax + w.w - zoneW} y={ay} width={zoneW} height={w.h} fill="transparent" listening onClick={(e) => { e.cancelBubble = true; handleSpinboxStep(1); }} onTap={(e) => { e.cancelBubble = true; handleSpinboxStep(1); }} />
            </>
          )}
        </Group>
      );
    }

    if (type === "qrcode") {
      const light = String(p.light_color ?? "#ffffff");
      const dark = String(p.dark_color ?? "#000000");
      const sz = Math.min(w.w, w.h) * 0.6;
      const tx = ax + (w.w - sz) / 2;
      const ty = ay + (w.h - sz) / 2;
      const cell = Math.max(3, sz / 12);
      const cols = Math.floor(sz / cell);
      return (
        <Group key={w.id}>
          {base}
          <Rect x={tx} y={ty} width={sz} height={sz} fill={light} stroke="#374151" listening={false} />
          {Array.from({ length: cols * cols }, (_, i) => {
            const c = i % cols;
            const r = Math.floor(i / cols);
            if ((c + r) % 3 === 0 || (c % 2 === 0 && r % 2 === 0)) return null;
            return <Rect key={i} x={tx + c * cell + 1} y={ty + r * cell + 1} width={cell - 1} height={cell - 1} fill={dark} listening={false} />;
          })}
        </Group>
      );
    }

    if (type === "led") {
      const brightness = override?.value !== undefined ? Math.min(100, Math.max(0, override.value)) : Math.min(100, Math.max(0, Number(p.brightness ?? 100)));
      const ledColor = String(p.color ?? s.bg_color ?? "#00ff00");
      const dim = brightness / 100;
      const r = Math.min(w.w, w.h) / 4 - 2;
      const fill = dim >= 0.01 ? ledColor : "#1f2937";
      const opacity = dim >= 0.01 ? 0.3 + 0.7 * dim : 0.4;
      return (
        <Group key={w.id}>
          {base}
          <Circle x={ax + w.w / 2} y={ay + w.h / 2} radius={r} fill={fill} opacity={opacity} stroke={dim >= 0.01 ? "#34d399" : "#374151"} strokeWidth={2} listening={false} />
        </Group>
      );
    }

    if (type === "line") {
      const pts = Array.isArray(p.points) && p.points.length >= 2
        ? p.points.flatMap((pt: string) => {
            const [a, b] = String(pt).split(",").map(Number);
            return [ax + (Number.isFinite(a) ? a : 0), ay + (Number.isFinite(b) ? b : 0)];
          })
        : [ax, ay, ax + w.w, ay + w.h];
      const lineColor = String(p.line_color ?? s.border_color ?? "#10b981");
      const lineW = Math.max(1, Number(p.line_width ?? 2));
      const rounded = !!p.line_rounded;
      return (
        <Group key={w.id}>
          {base}
          <Line points={pts} stroke={lineColor} strokeWidth={lineW} lineCap={rounded ? "round" : "butt"} lineJoin={rounded ? "round" : "miter"} listening={false} />
        </Group>
      );
    }

    if (type === "tabview") {
      const tabH = 24;
      const tabs = Array.isArray(p.tabs) ? p.tabs : ["Tab 1", "Tab 2"];
      const position = String((p as any).position ?? "TOP").toUpperCase();
      const atTop = position !== "BOTTOM";
      const tabW = Math.max(40, (w.w - 12 - (tabs.length - 1) * 4) / tabs.length);
      const tabBarY = atTop ? ay + 6 : ay + w.h - 6 - tabH;
      const contentY = atTop ? ay + 6 + tabH : ay + 6;
      const contentH = w.h - 12 - tabH;
      return (
        <Group key={w.id}>
          {base}
          {tabs.slice(0, 6).map((t: string, i: number) => (
            <Rect key={i} x={ax + 6 + i * (tabW + 4)} y={tabBarY} width={tabW} height={tabH} fill={String((w as any).tab_style?.bg_color ?? "#374151")} cornerRadius={4} listening={false} />
          ))}
          <Rect x={ax + 6} y={contentY} width={w.w - 12} height={contentH} fill={String(s.bg_color ?? "#0b1220")} cornerRadius={0} listening={false} />
          {tabs[0] && <Text text={String(tabs[0]).slice(0, 12)} x={ax + 12} y={tabBarY + 4} width={tabW - 8} fontSize={11} fill={textColor} ellipsis listening={false} />}
        </Group>
      );
    }
    if (type === "tileview") {
      const tiles = Array.isArray((p as any).tiles) ? (p as any).tiles : ["0,0", "1,0"];
      const n = Math.min(Math.max(1, tiles.length), 6);
      const cols = n <= 2 ? 2 : Math.ceil(Math.sqrt(n));
      const rows = Math.ceil(n / cols);
      const tw = (w.w - 8 * (cols + 1)) / cols;
      const th = (w.h - 8 * (rows + 1)) / rows;
      return (
        <Group key={w.id}>
          {base}
          {Array.from({ length: n }, (_, i) => (
            <Rect key={i} x={ax + 8 + (i % cols) * (tw + 8)} y={ay + 8 + Math.floor(i / cols) * (th + 8)} width={tw} height={th} fill="#374151" cornerRadius={4} listening={false} />
          ))}
          <Text text="Tile" x={ax} y={ay + (w.h - 12) / 2} width={w.w} align="center" fontSize={11} fill="#9ca3af" listening={false} />
        </Group>
      );
    }

    if (type === "buttonmatrix") {
      const pad = 6;
      const mapRows = Array.isArray(p.map) ? p.map : ["1", "2", "3", "4"];
      const rows = mapRows.length;
      const cols = Math.max(1, mapRows.reduce((m: number, row: string) => {
        const n = typeof row === "string" ? row.split(/[\s,]+/).filter(Boolean).length : 0;
        return Math.max(m, n);
      }, 1));
      const widthWeights = typeof p.width === "string" && p.width.trim()
        ? p.width.trim().split(/\s+/).map((x: string) => Math.max(0.1, Number(x) || 1)).slice(0, cols)
        : null;
      const totalWeight = widthWeights ? widthWeights.reduce((a: number, b: number) => a + b, 0) : cols;
      const bwPerCol = widthWeights
        ? (w.w - pad * (cols + 1)) / totalWeight
        : (w.w - pad * (cols + 1)) / cols;
      const bh = Math.min(28, (w.h - pad * (rows + 1)) / rows);
      const labels = mapRows.flatMap((row: string) => (typeof row === "string" ? row.split(/[\s,]+/).filter(Boolean) : []));
      const colX = (c: number) => widthWeights
        ? ax + pad + widthWeights.slice(0, c).reduce((a: number, b: number) => a + bwPerCol * b, 0) + c * pad
        : ax + pad + c * (bwPerCol + pad);
      const cellW = (c: number) => (widthWeights && widthWeights[c] != null ? widthWeights[c] * bwPerCol : bwPerCol);
      const numCells = Math.min(rows * cols, 24);
      const simClick = simulationMode && onSimulateAction
        ? (i: number) => (e: any) => {
            e.cancelBubble = true;
            onSimulateAction(w.id, "on_value", { selected_index: i });
          }
        : undefined;
      return (
        <Group key={w.id}>
          {base}
          {Array.from({ length: numCells }, (_, i) => {
            const c = i % cols;
            const r = Math.floor(i / cols);
            const bx = colX(c);
            const by = ay + pad + r * (bh + pad);
            const bw = cellW(c);
            return (
              <Group key={i}>
                <Rect
                  x={bx}
                  y={by}
                  width={bw}
                  height={bh}
                  fill="#374151"
                  cornerRadius={4}
                  listening={!!simClick}
                  onClick={simClick ? (e) => simClick(i)(e) : undefined}
                  onTap={simClick ? (e) => simClick(i)(e) : undefined}
                />
                <Text text={String(labels[i] ?? "").slice(0, 4)} x={bx} y={by + (bh - 10) / 2} width={bw} align="center" fontSize={Math.min(10, bh - 4)} fill={textColor} listening={false} />
              </Group>
            );
          })}
        </Group>
      );
    }

    if (type === "keyboard") {
      const pad = 4;
      const keyW = (w.w - pad * 11) / 10;
      const keyH = Math.min(24, (w.h - pad * 5) / 4);
      const simKeyClick = simulationMode && onSimulateAction
        ? (i: number) => (e: any) => {
            e.cancelBubble = true;
            onSimulateAction(w.id, "on_value", { selected_index: i });
          }
        : undefined;
      return (
        <Group key={w.id}>
          {base}
          {Array.from({ length: 4 * 10 }, (_, i) => (
            <Rect
              key={i}
              x={ax + pad + (i % 10) * (keyW + pad)}
              y={ay + pad + Math.floor(i / 10) * (keyH + pad)}
              width={keyW}
              height={keyH}
              fill="#374151"
              cornerRadius={2}
              listening={!!simKeyClick}
              onClick={simKeyClick ? (e) => simKeyClick(i)(e) : undefined}
              onTap={simKeyClick ? (e) => simKeyClick(i)(e) : undefined}
            />
          ))}
          <Text text="⌨" x={ax} y={ay + w.h - 20} width={w.w} align="center" fontSize={12} fill="#9ca3af" listening={false} />
        </Group>
      );
    }

    if (type === "canvas") {
      const transparent = !!p.transparent;
      return (
        <Group key={w.id}>
          {base}
          <Rect x={ax + 8} y={ay + 8} width={w.w - 16} height={w.h - 16} fill={transparent ? "rgba(15,23,42,0.5)" : "#0b1220"} stroke="#374151" strokeWidth={1} listening={false} />
          <Text text="canvas" x={ax} y={ay + (w.h - 12) / 2} width={w.w} align="center" fontSize={11} fill="#6b7280" fontStyle="italic" listening={false} />
        </Group>
      );
    }

    if (type === "msgboxes") {
      return (
        <Group key={w.id}>
          {base}
          <Rect x={ax + 6} y={ay + 6} width={w.w - 12} height={28} fill="#374151" cornerRadius={4} listening={false} />
          <Rect x={ax + 6} y={ay + 34} width={w.w - 12} height={w.h - 40} fill={String(s.bg_color ?? "#0b1220")} cornerRadius={4} listening={false} />
          <Text text="Title" x={ax + 12} y={ay + 10} fontSize={12} fill={textColor} listening={false} />
          <Text text="Message…" x={ax + 12} y={ay + 42} width={w.w - 24} fontSize={11} fill="#9ca3af" listening={false} />
        </Group>
      );
    }

    // Default: label in top-left
    return (
      <Group key={w.id}>
        {base}
        <Text text={w.type} x={ax + 6} y={ay + 6} fontSize={14} fill="#e5e7eb" listening={false} />
      </Group>
    );
  };

  const gridLines = () => {
    if (!showGrid || gridSize <= 1) return null;
    const lines: any[] = [];
    for (let x = gridSize; x < width; x += gridSize) {
      lines.push(
        <Line
          key={`vx_${x}`}
          points={[x, 0, x, height]}
          stroke="#111827"
          strokeWidth={1}
          listening={false}
        />
      );
    }
    for (let y = gridSize; y < height; y += gridSize) {
      lines.push(
        <Line
          key={`hy_${y}`}
          points={[0, y, width, y]}
          stroke="#111827"
          strokeWidth={1}
          listening={false}
        />
      );
    }
    return lines;
  };

  const containerRef = useRef<HTMLDivElement>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const prebuilt = e.dataTransfer.getData('application/x-esphome-prebuilt-widget');
    const tmpl = e.dataTransfer.getData('application/x-esphome-control-template');
    const type = e.dataTransfer.getData('application/x-esphome-widget-type');
    console.log('[ETD Drop] prebuilt:', JSON.stringify(prebuilt), 'tmpl:', JSON.stringify(tmpl), 'type:', JSON.stringify(type), 'target:', (e.target as HTMLElement)?.tagName);
    const payload = prebuilt ? `prebuilt:${prebuilt}` : tmpl ? `tmpl:${tmpl}` : type;
    if (!payload || !onDropCreate) {
      console.log('[ETD Drop] No payload or no onDropCreate, aborting');
      return;
    }
    const el = containerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    let x = e.clientX - rect.left;
    let y = e.clientY - rect.top;
    if (rect.width > 0 && rect.height > 0 && (rect.width !== width || rect.height !== height)) {
      x = (x / rect.width) * width;
      y = (y / rect.height) * height;
    }
    x = Math.max(0, Math.min(width, x));
    y = Math.max(0, Math.min(height, y));
    console.log('[ETD Drop] Calling onDropCreate with payload:', payload, 'at', x, y);
    onDropCreate(payload, snap(x, gridSize), snap(y, gridSize));
  };

  return (
    <div
      ref={containerRef}
      onDragOver={(e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
      }}
      onDrop={handleDrop}
      style={{ width, height, minWidth: width, minHeight: height, position: "relative" }}
    >
    <Stage
      width={width}
      height={height}
      ref={stageRef}
      style={{ background: /^#[0-9a-fA-F]{6}$/.test(dispBgColor || "") ? dispBgColor : "#0b0f14", borderRadius: 12, overflow: "hidden" }}
      onMouseDown={(e) => {
        if (simulationMode) return;
        const clickedOnEmpty = e.target === e.target.getStage();
        if (clickedOnEmpty) {
          const pos = e.target.getStage()?.getPointerPosition();
          if (pos) {
            boxSelectStartRef.current = { x: pos.x, y: pos.y };
          } else {
            onSelectNone();
          }
        }
      }}
      onMouseMove={(e) => {
        if (simulationMode) return;
        const pos = e.target.getStage()?.getPointerPosition();
        if (selectionBox && pos) {
          setSelectionBox((prev) => prev ? { ...prev, endX: pos.x, endY: pos.y } : null);
        } else if (boxSelectStartRef.current && pos) {
          const dx = pos.x - boxSelectStartRef.current.x;
          const dy = pos.y - boxSelectStartRef.current.y;
          if (Math.sqrt(dx * dx + dy * dy) >= BOX_SELECT_THRESHOLD) {
            setSelectionBox({
              startX: boxSelectStartRef.current.x,
              startY: boxSelectStartRef.current.y,
              endX: pos.x,
              endY: pos.y,
            });
            boxSelectStartRef.current = null;
          }
        }
      }}
      onMouseUp={(e) => {
        if (simulationMode) return;
        if (e.target !== e.target.getStage()) return;
        if (selectionBox) {
          finishSelectionBox();
        } else if (boxSelectStartRef.current) {
          boxSelectStartRef.current = null;
          onSelectNone();
        }
      }}
    >
      <Layer>
        {gridLines()}
        {(() => {
          const topLevel = widgets.filter((w) => !w.parent_id);
          return topLevel.map((w) => renderWidget(w, selectedSet.has(w.id)));
        })()}
        <Transformer
          ref={trRef}
          rotateEnabled={false}
          anchorSize={10}
          anchorFill="#06b6d4"
          anchorStroke="#fff"
          borderStroke="#06b6d4"
          boundBoxFunc={(oldBox, newBox) => {
            const { box, clamped } = clampResizeBox(newBox, width, height, 20);
            if (clamped) setResizeAtLimit(true);
            return { ...box, rotation: newBox.rotation ?? oldBox.rotation ?? 0 };
          }}
        />
        {selectionBox && (
          <Rect
            x={Math.min(selectionBox.startX, selectionBox.endX)}
            y={Math.min(selectionBox.startY, selectionBox.endY)}
            width={Math.abs(selectionBox.endX - selectionBox.startX)}
            height={Math.abs(selectionBox.endY - selectionBox.startY)}
            stroke="#10b981"
            strokeWidth={2}
            dash={[6, 4]}
            fill="rgba(16, 185, 129, 0.08)"
            listening={false}
          />
        )}
      </Layer>
    </Stage>
    {(dragAtLimit || resizeAtLimit) && (
      <div
        style={{
          position: "absolute",
          bottom: 12,
          left: "50%",
          transform: "translateX(-50%)",
          padding: "6px 12px",
          borderRadius: 8,
          background: "rgba(6, 182, 212, 0.95)",
          color: "#0b0f14",
          fontSize: 12,
          fontWeight: 600,
          pointerEvents: "none",
          boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
        }}
      >
        {dragAtLimit ? "At screen edge" : "At max size"}
      </div>
    )}
    </div>
  );
}
