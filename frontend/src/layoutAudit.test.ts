import { describe, expect, it } from "vitest";
import golden from "./fixtures/entitybuilder-layout-golden.json";
import projectMin from "./fixtures/entitybuilder-project-min.json";
import { layoutAuditForProject } from "./layoutAudit";
import { widgetFootprintForSelection, type WidgetLike } from "./canvasUtils";

/**
 * Compiler truth: POST .../compile with include_layout_audit (same as device LVGL layout).
 * Golden snapshot from HA EntityBuilder device — refresh fixtures if compiler audit changes intentionally.
 */
describe("layoutAuditForProject vs compiler (EntityBuilder)", () => {
  it("matches golden yaml_rect_page / overlaps for SmallClimate-style card", () => {
    const got = layoutAuditForProject(projectMin as Record<string, unknown>, 0);
    expect(got.page_index).toBe(golden.page_index);
    expect(got.display).toEqual(golden.display);
    expect(got.widgets).toEqual(golden.widgets);
    expect(got.overlaps).toEqual(golden.overlaps);
  });

  it("widgetFootprintForSelection matches yaml_rect_page for each widget (canvas vs device)", () => {
    const page = (projectMin.pages as { widgets: Record<string, unknown>[] }[])[0];
    const raw = page.widgets;
    const list: WidgetLike[] = raw.map((w) => ({
      id: String(w.id),
      x: Number(w.x),
      y: Number(w.y),
      w: Number(w.w),
      h: Number(w.h),
      parent_id: w.parent_id ? String(w.parent_id) : undefined,
      props: (w.props as Record<string, unknown>) || {},
      style: (w.style as Record<string, unknown>) || {},
      type: String(w.type),
    }));
    const byId = new Map(list.map((w) => [w.id, w]));
    const { w: dw, h: dh } = golden.display;
    const audit = layoutAuditForProject(projectMin as Record<string, unknown>, 0);
    const byAuditId = new Map(audit.widgets.map((e) => [e.id, e]));
    for (const w of list) {
      const fp = widgetFootprintForSelection(w, byId, dw, dh);
      const exp = byAuditId.get(w.id)?.yaml_rect_page;
      expect(exp, `missing audit for ${w.id}`).toBeDefined();
      expect(
        { x: fp.ax, y: fp.ay, w: fp.w, h: fp.h },
        `footprint ${w.id} must match compiler yaml_rect_page`
      ).toEqual(exp);
    }
  });
});
