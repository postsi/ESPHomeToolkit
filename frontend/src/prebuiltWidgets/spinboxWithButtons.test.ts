/**
 * Test harness for Spinbox with +/- prebuilt widget.
 * Ensures build() returns a container with one spinbox and two buttons,
 * and that the buttons have custom_events.on_click with lvgl.spinbox.decrement/increment.
 */
import { describe, it, expect } from "vitest";
import { PREBUILT_WIDGETS } from "./index";

describe("Spinbox with +/- prebuilt", () => {
  const prebuilt = PREBUILT_WIDGETS.find((p) => p.id === "prebuilt_spinbox_buttons");
  if (!prebuilt) {
    it("prebuilt_spinbox_buttons exists in PREBUILT_WIDGETS", () => {
      expect(prebuilt).toBeDefined();
    });
    return;
  }

  it("has correct title and description", () => {
    expect(prebuilt.title).toBe("Spinbox with +/-");
    expect(prebuilt.description).toMatch(/spinbox|increment|decrement/i);
  });

  it("build() returns widgets with one container, one spinbox, and two buttons", () => {
    const { widgets } = prebuilt.build({ x: 10, y: 20 });
    expect(widgets.length).toBe(4); // root container + spinbox + minus btn + plus btn

    const root = widgets.find((w) => w.type === "container");
    const spinbox = widgets.find((w) => w.type === "spinbox");
    const buttons = widgets.filter((w) => w.type === "button");
    expect(root).toBeDefined();
    expect(spinbox).toBeDefined();
    expect(buttons.length).toBe(2);

    const minusBtn = buttons.find((b) => (b.props as { text?: string })?.text === "-");
    const plusBtn = buttons.find((b) => (b.props as { text?: string })?.text === "+");
    expect(minusBtn).toBeDefined();
    expect(plusBtn).toBeDefined();
  });

  it("minus button has custom_events.on_click with lvgl.spinbox.decrement", () => {
    const { widgets } = prebuilt.build({ x: 0, y: 0 });
    const buttons = widgets.filter((w) => w.type === "button");
    const minusBtn = buttons.find((b) => (b.props as { text?: string })?.text === "-");
    expect(minusBtn).toBeDefined();
    const customEvents = (minusBtn as { custom_events?: Record<string, string> }).custom_events;
    expect(customEvents?.on_click).toBeDefined();
    expect(customEvents!.on_click).toContain("lvgl.spinbox.decrement");
  });

  it("plus button has custom_events.on_click with lvgl.spinbox.increment", () => {
    const { widgets } = prebuilt.build({ x: 0, y: 0 });
    const buttons = widgets.filter((w) => w.type === "button");
    const plusBtn = buttons.find((b) => (b.props as { text?: string })?.text === "+");
    expect(plusBtn).toBeDefined();
    const customEvents = (plusBtn as { custom_events?: Record<string, string> }).custom_events;
    expect(customEvents?.on_click).toBeDefined();
    expect(customEvents!.on_click).toContain("lvgl.spinbox.increment");
  });

  it("spinbox and buttons share same parent_id (group)", () => {
    const { widgets } = prebuilt.build({ x: 0, y: 0 });
    const root = widgets.find((w) => w.type === "container");
    const spinbox = widgets.find((w) => w.type === "spinbox");
    const buttons = widgets.filter((w) => w.type === "button");
    expect(root?.id).toBeDefined();
    const parentId = (spinbox as { parent_id?: string }).parent_id;
    expect(parentId).toBe(root?.id);
    buttons.forEach((b) => {
      expect((b as { parent_id?: string }).parent_id).toBe(parentId);
    });
  });
});
