/**
 * Canvas vs Mac LVGL: designer parity export compared to a PNG from the simulator (same WxH).
 *
 * On mismatch: writes test-results/parity/<fixture>-{diff,designer,sim}.png and <fixture>-result.json
 * so you (or Cursor) can inspect, change Canvas/compiler, rerun npm run parity:mac.
 * Subset: PARITY_FIXTURE_NAMES=comma,separated (must match ESPTOOLKIT_PARITY_FIXTURES for mac prepare).
 */
import { test, expect } from "@playwright/test";
import pixelmatch from "pixelmatch";
import { PNG } from "pngjs";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** Matches public/parity-fixtures/*.json — run npm run generate:parity-fixtures after palette/prebuilt changes */
const DEFAULT_PARITY_FIXTURES = ["min_rect", "standard_widgets", "prebuilt_widgets", "entity_small_climate"] as const;

function parityFixtureNames(): readonly string[] {
  const raw = process.env.PARITY_FIXTURE_NAMES?.trim();
  if (!raw) return DEFAULT_PARITY_FIXTURES;
  const names = raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (names.length === 0) return DEFAULT_PARITY_FIXTURES;
  return names;
}

const PARITY_OUT = path.join(__dirname, "../test-results/parity");

function parseDataUrlPng(dataUrl: string): Buffer {
  const m = /^data:image\/png;base64,(.+)$/.exec(dataUrl);
  if (!m) throw new Error("expected data:image/png;base64,…");
  return Buffer.from(m[1], "base64");
}

function simUrlForFixture(fixture: string): string | null {
  const t = process.env.MACSIM_SNAPSHOT_URL_TEMPLATE?.trim();
  if (t) {
    if (!t.includes("{fixture}")) {
      throw new Error("MACSIM_SNAPSHOT_URL_TEMPLATE must contain {fixture}");
    }
    return t.split("{fixture}").join(fixture);
  }
  const legacy = process.env.MACSIM_SNAPSHOT_URL?.trim();
  if (legacy) return legacy;
  return null;
}

function writeParityResult(
  fixture: string,
  designer: PNG,
  simPng: PNG,
  diff: PNG,
  numDiff: number,
  maxDiff: number,
  tol: number,
  passed: boolean
) {
  fs.mkdirSync(PARITY_OUT, { recursive: true });
  const rel = (name: string) => path.join("test-results", "parity", name);
  const base = path.join(PARITY_OUT, fixture);
  if (!passed) {
    fs.writeFileSync(`${base}-diff.png`, Buffer.from(PNG.sync.write(diff)));
    fs.writeFileSync(`${base}-designer.png`, Buffer.from(PNG.sync.write(designer)));
    fs.writeFileSync(`${base}-sim.png`, Buffer.from(PNG.sync.write(simPng)));
  }
  fs.writeFileSync(
    `${base}-result.json`,
    JSON.stringify(
      {
        fixture,
        passed,
        numDiffPixels: numDiff,
        maxAllowedPixels: maxDiff,
        threshold: tol,
        width: designer.width,
        height: designer.height,
        artifactsOnFailure: passed
          ? []
          : [rel(`${fixture}-diff.png`), rel(`${fixture}-designer.png`), rel(`${fixture}-sim.png`)],
        playwrightJson: rel("playwright-report.json"),
        nextStep:
          "Edit Canvas/compiler (or capture/crop); rerun: cd frontend && npm run parity:mac (or npm run test:parity if snapshots already exist).",
      },
      null,
      2
    )
  );
}

test.beforeAll(() => {
  const hasTemplate = !!process.env.MACSIM_SNAPSHOT_URL_TEMPLATE?.trim();
  const hasLegacy = !!process.env.MACSIM_SNAPSHOT_URL?.trim();
  if (!hasTemplate && !hasLegacy) {
    throw new Error(
      "Mac LVGL parity tests require MACSIM_SNAPSHOT_URL_TEMPLATE, e.g. " +
        "http://127.0.0.1:9777/snapshot/{fixture}.png — see docs/PARITY_PIPELINE.md"
    );
  }
  // eslint-disable-next-line no-console
  console.log(
    "[parity:e2e] env OK — Vite preview is up (cold starts: watch webServer npm/vite lines above before this)"
  );
});

test.describe("Designer canvas vs Mac LVGL snapshot", () => {
  for (const fixture of parityFixtureNames()) {
    test(`fixture ${fixture}`, async ({ page, request }) => {
      test.setTimeout(120_000);
      const templateSet = !!process.env.MACSIM_SNAPSHOT_URL_TEMPLATE?.trim();
      const legacyOnly = !!process.env.MACSIM_SNAPSHOT_URL?.trim() && !templateSet;
      if (legacyOnly && fixture !== "min_rect") {
        test.skip(true, "Set MACSIM_SNAPSHOT_URL_TEMPLATE to compare every fixture (legacy URL is single-image)");
        return;
      }

      const simUrl = simUrlForFixture(fixture);
      expect(simUrl, "sim URL").toBeTruthy();

      // list reporter prints nothing during long waits — log milestones for humans / agents.
      // eslint-disable-next-line no-console
      console.log(`[parity:e2e] ${fixture}: loading designer (?etd_parity=1&etd_fixture=…)`);
      await page.goto(`?etd_parity=1&etd_fixture=${fixture}`, { waitUntil: "load" });
      // eslint-disable-next-line no-console
      console.log(`[parity:e2e] ${fixture}: waiting for html[data-etd-parity-ready] (up to 90s)…`);
      await page.waitForSelector("html[data-etd-parity-ready='1']", { state: "attached", timeout: 90_000 });
      // eslint-disable-next-line no-console
      console.log(`[parity:e2e] ${fixture}: exporting Konva PNG`);
      const dataUrl = await page.evaluate(
        () => (window as unknown as { __ETD_EXPORT_CANVAS_PNG__?: () => string }).__ETD_EXPORT_CANVAS_PNG__?.()
      );
      expect(dataUrl).toMatch(/^data:image\/png/);
      const designer = PNG.sync.read(parseDataUrlPng(dataUrl!));

      // eslint-disable-next-line no-console
      console.log(`[parity:e2e] ${fixture}: GET sim ${simUrl}`);
      const res = await request.get(simUrl!);
      expect(res.ok(), `sim GET ${simUrl} → HTTP ${res.status()}`).toBeTruthy();
      const ct = res.headers()["content-type"] || "";
      expect(ct.includes("png"), `expected image/png, got ${ct}`).toBe(true);
      const simPng = PNG.sync.read(Buffer.from(await res.body()));

      expect(simPng.width, `${fixture}: width`).toBe(designer.width);
      expect(simPng.height, `${fixture}: height`).toBe(designer.height);
      const diff = new PNG({ width: designer.width, height: designer.height });
      const tol = Number(process.env.PARITY_PIXEL_THRESHOLD ?? "0");
      const numDiff = pixelmatch(designer.data, simPng.data, diff.data, designer.width, designer.height, { threshold: tol });
      const maxDiff = Number(process.env.PARITY_MAX_DIFF_PIXELS ?? "0");
      const passed = numDiff <= maxDiff;
      writeParityResult(fixture, designer, simPng, diff, numDiff, maxDiff, tol, passed);
      // eslint-disable-next-line no-console
      console.log(
        `[parity:e2e] ${fixture}: pixelmatch ${numDiff} diff px (max ${maxDiff}) → ${passed ? "PASS" : "FAIL"}`
      );
      expect(
        numDiff,
        `${fixture}: ${numDiff} pixels differ (max allowed ${maxDiff}, threshold ${tol}) — see ${path.join(PARITY_OUT, fixture)}-result.json and *-diff.png`
      ).toBeLessThanOrEqual(maxDiff);
    });
  }
});
