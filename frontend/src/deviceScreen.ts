/**
 * Physical display size for the designer canvas and Mac SDL sim.
 * No arbitrary fallbacks: size comes from the project (device.screen, filled by the API from the
 * hardware recipe metadata when possible) or from WxH embedded in the hardware_recipe_id string.
 */

export type ResolvedDeviceScreen = {
  width: number;
  height: number;
  /** Where width/height came from (for UI labeling only) */
  source: "device.screen" | "recipe_id";
};

export function resolveDeviceScreen(
  project: unknown,
  hardwareRecipeId: string | undefined | null,
): ResolvedDeviceScreen | null {
  const p = project as {
    device?: { screen?: { width?: unknown; height?: unknown }; hardware_recipe_id?: string };
  } | null;
  const dev = p?.device;
  const sw = dev?.screen?.width;
  const sh = dev?.screen?.height;
  if (sw != null && sh != null) {
    const wi = Number(sw);
    const hi = Number(sh);
    if (Number.isFinite(wi) && Number.isFinite(hi) && wi > 0 && hi > 0) {
      return { width: Math.round(wi), height: Math.round(hi), source: "device.screen" };
    }
  }
  const rid = String(hardwareRecipeId ?? dev?.hardware_recipe_id ?? "").trim();
  const m = /(\d{3,4})x(\d{3,4})/i.exec(rid);
  if (m) {
    const wi = parseInt(m[1], 10);
    const hi = parseInt(m[2], 10);
    if (wi > 0 && hi > 0) {
      return { width: wi, height: hi, source: "recipe_id" };
    }
  }
  return null;
}
