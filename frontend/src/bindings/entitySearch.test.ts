/**
 * Entity search for Binding Builder: word-based matching (§4.2 UX).
 */
import { describe, it, expect } from "vitest";
import { entityMatchesBindingSearch } from "./entitySearch";

describe("entityMatchesBindingSearch", () => {
  it("matches when query is empty (show all)", () => {
    expect(entityMatchesBindingSearch({ entity_id: "light.shed", friendly_name: "Shed" }, "")).toBe(true);
    expect(entityMatchesBindingSearch({ entity_id: "sensor.any" }, "   ")).toBe(true);
  });

  it("matches single word in entity_id", () => {
    expect(entityMatchesBindingSearch({ entity_id: "light.shed" }, "shed")).toBe(true);
    expect(entityMatchesBindingSearch({ entity_id: "light.shed_ceiling" }, "shed")).toBe(true);
    expect(entityMatchesBindingSearch({ entity_id: "sensor.shed_temperature" }, "shed")).toBe(true);
    expect(entityMatchesBindingSearch({ entity_id: "switch.myshed" }, "shed")).toBe(true);
  });

  it("matches single word in friendly_name", () => {
    expect(entityMatchesBindingSearch({ entity_id: "light.kitchen", friendly_name: "Shed light" }, "shed")).toBe(true);
    expect(entityMatchesBindingSearch({ entity_id: "sensor.xyz", friendly_name: "Living room temp" }, "living")).toBe(true);
  });

  it("requires all words for multi-word query", () => {
    expect(entityMatchesBindingSearch({ entity_id: "light.shed", friendly_name: "Shed" }, "shed light")).toBe(true);
    expect(entityMatchesBindingSearch({ entity_id: "light.living_room", friendly_name: "Living room" }, "living room")).toBe(true);
    expect(entityMatchesBindingSearch({ entity_id: "sensor.shed", friendly_name: "Shed only" }, "shed light")).toBe(false);
  });

  it("is case-insensitive", () => {
    expect(entityMatchesBindingSearch({ entity_id: "light.Shed" }, "shed")).toBe(true);
    expect(entityMatchesBindingSearch({ entity_id: "light.shed", friendly_name: "SHED" }, "Shed")).toBe(true);
  });

  it("rejects when word not present", () => {
    expect(entityMatchesBindingSearch({ entity_id: "light.kitchen" }, "shed")).toBe(false);
    expect(entityMatchesBindingSearch({ entity_id: "light.shed" }, "garage")).toBe(false);
  });

  it("handles missing entity_id or friendly_name", () => {
    expect(entityMatchesBindingSearch({ entity_id: "", friendly_name: "Shed" }, "shed")).toBe(true);
    expect(entityMatchesBindingSearch({ entity_id: "light.shed" }, "shed")).toBe(true);
    expect(entityMatchesBindingSearch({} as any, "shed")).toBe(false);
  });
});
