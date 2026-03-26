import { describe, expect, it } from "vitest";
import { resolveDeviceScreen } from "./deviceScreen";

describe("resolveDeviceScreen", () => {
  it("uses project.device.screen when set", () => {
    expect(
      resolveDeviceScreen({ device: { screen: { width: 1024, height: 600 } } }, null),
    ).toEqual({ width: 1024, height: 600, source: "device.screen" });
  });

  it("parses WxH from hardware_recipe_id argument", () => {
    expect(resolveDeviceScreen({}, "jc1060p470_esp32p4_1024x600")).toEqual({
      width: 1024,
      height: 600,
      source: "recipe_id",
    });
  });

  it("parses from project.device.hardware_recipe_id when screen missing", () => {
    expect(
      resolveDeviceScreen(
        { device: { hardware_recipe_id: "guition_s3_4848s040_480x480" } },
        null,
      ),
    ).toEqual({ width: 480, height: 480, source: "recipe_id" });
  });

  it("prefers device.screen over recipe id pattern", () => {
    expect(
      resolveDeviceScreen(
        {
          device: {
            screen: { width: 800, height: 480 },
            hardware_recipe_id: "guition_s3_4848s040_480x480",
          },
        },
        "guition_s3_4848s040_480x480",
      ),
    ).toEqual({ width: 800, height: 480, source: "device.screen" });
  });

  it("returns null when size cannot be determined", () => {
    expect(resolveDeviceScreen({}, "")).toBe(null);
    expect(resolveDeviceScreen({ device: {} }, undefined)).toBe(null);
    expect(resolveDeviceScreen({ device: { screen: { width: 0, height: 480 } } }, null)).toBe(null);
  });
});
