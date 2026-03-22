import { describe, it, expect } from "vitest";
import { displayLinkRowsForWidget } from "./widgetLinks";

describe("displayLinkRowsForWidget", () => {
  it("includes links with target.widget_id match", () => {
    const links = [
      { source: { entity_id: "sensor.a" }, target: { widget_id: "lbl1", action: "label_text" } },
      { source: { entity_id: "sensor.b" }, target: { widget_id: "lbl2", action: "label_text" } },
    ];
    const rows = displayLinkRowsForWidget(links, "lbl1");
    expect(rows).toHaveLength(1);
    expect(rows[0].globalIndex).toBe(0);
    expect(rows[0].intervalUpdateIndex).toBeUndefined();
  });

  it("includes interval link rows when widget appears in source.updates (import shape)", () => {
    const links = [
      {
        source: {
          type: "interval",
          interval_seconds: 30,
          updates: [
            { widget_id: "clock_lbl", action: "label_text", yaml_override: "x" },
            { widget_id: "other", action: "label_text" },
          ],
        },
        target: {},
      },
    ];
    const rows = displayLinkRowsForWidget(links, "clock_lbl");
    expect(rows).toHaveLength(1);
    expect(rows[0].globalIndex).toBe(0);
    expect(rows[0].intervalUpdateIndex).toBe(0);
  });

  it("does not duplicate HA link that also has empty target and no interval match", () => {
    const links = [{ source: { entity_id: "sensor.x" }, target: { widget_id: "w" } }];
    expect(displayLinkRowsForWidget(links, "w")).toHaveLength(1);
  });

  it("returns empty for unknown widget", () => {
    expect(displayLinkRowsForWidget([], "a")).toEqual([]);
    expect(displayLinkRowsForWidget([{ target: { widget_id: "x" } }], "")).toEqual([]);
  });
});
