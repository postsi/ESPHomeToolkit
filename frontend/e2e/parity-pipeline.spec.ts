/**
 * Canvas vs Mac LVGL: designer parity export compared to a PNG from the simulator (same WxH).
 *
 * Modes (PARITY_MODE):
 * - perceptual (default): box-downsample (~160px wide) then pixelmatch — ignores most font/AA noise;
 *   pass when coarseDiffRatio <= PARITY_COARSE_MAX_RATIO (default 0.12).
 * - strict: identical pixels — threshold 0, max 0 (override with PARITY_PIXEL_THRESHOLD / PARITY_MAX_DIFF_PIXELS).
 *
 * On mismatch: writes test-results/parity/<fixture>-{diff,designer,sim}.png and <fixture>-result.json
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

function parityMode(): "strict" | "perceptual" {
  const m = (process.env.PARITY_MODE ?? "perceptual").trim().toLowerCase();
  if (m === "strict" || m === "pixel" || m === "exact") return "strict";
  return "perceptual";
}

/** Average RGBA into a smaller buffer so full-res font AA / subpixel noise averages out (human-ish “similar”). */
function boxDownsample(src: Buffer, sw: number, sh: number, dst: Buffer, dw: number, dh: number): void {
  const sx = sw / dw;
  const sy = sh / dh;
  for (let dy = 0; dy < dh; dy++) {
    const y0 = Math.floor(dy * sy);
    const y1 = Math.min(sh, Math.floor((dy + 1) * sy));
    if (y1 <= y0) continue;
    for (let dx = 0; dx < dw; dx++) {
      const x0 = Math.floor(dx * sx);
      const x1 = Math.min(sw, Math.floor((dx + 1) * sx));
      if (x1 <= x0) continue;
      let r = 0,
        g = 0,
        b = 0,
        a = 0,
        c = 0;
      for (let y = y0; y < y1; y++) {
        for (let x = x0; x < x1; x++) {
          const i = (y * sw + x) << 2;
          r += src[i];
          g += src[i + 1];
          b += src[i + 2];
          a += src[i + 3];
          c++;
        }
      }
      const oi = (dy * dw + dx) << 2;
      dst[oi] = Math.round(r / c);
      dst[oi + 1] = Math.round(g / c);
      dst[oi + 2] = Math.round(b / c);
      dst[oi + 3] = Math.round(a / c);
    }
  }
}

function coarseParityMetrics(
  designer: PNG,
  simPng: PNG,
  maxWidth: number,
  threshold: number
): {
  coarseW: number;
  coarseH: number;
  coarseDiffPixels: number;
  coarseTotalPixels: number;
  coarseDiffRatio: number;
} {
  const w = designer.width;
  const h = designer.height;
  const coarseW = Math.min(maxWidth, w);
  const coarseH = Math.max(1, Math.round((coarseW * h) / w));
  const bufA = Buffer.alloc(coarseW * coarseH * 4);
  const bufB = Buffer.alloc(coarseW * coarseH * 4);
  boxDownsample(designer.data, w, h, bufA, coarseW, coarseH);
  boxDownsample(simPng.data, w, h, bufB, coarseW, coarseH);
  const diffSmall = Buffer.alloc(coarseW * coarseH * 4);
  const coarseDiffPixels = pixelmatch(bufA, bufB, diffSmall, coarseW, coarseH, { threshold });
  const coarseTotalPixels = coarseW * coarseH;
  return {
    coarseW,
    coarseH,
    coarseDiffPixels,
    coarseTotalPixels,
    coarseDiffRatio: coarseDiffPixels / coarseTotalPixels,
  };
}

/** 2×2 grid: TL designer, TR sim, BL per-channel sum (clamped), BR abs RGB diff ×6 (grayscale) — makes bg tint drift obvious. */
function buildParityCompositePng(designer: PNG, sim: PNG): PNG {
  const W = designer.width;
  const H = designer.height;
  const out = new PNG({ width: W * 2, height: H * 2 });
  const stride = W * 2;

  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const si = (W * y + x) << 2;
      const dr = designer.data[si];
      const dg = designer.data[si + 1];
      const db = designer.data[si + 2];
      const da = designer.data[si + 3];
      const sr = sim.data[si];
      const sg = sim.data[si + 1];
      const sb = sim.data[si + 2];
      const sa = sim.data[si + 3];

      const write = (ox: number, oy: number, r: number, g: number, b: number, a: number) => {
        const oi = (stride * oy + ox) << 2;
        out.data[oi] = r;
        out.data[oi + 1] = g;
        out.data[oi + 2] = b;
        out.data[oi + 3] = a;
      };

      write(x, y, dr, dg, db, da);
      write(W + x, y, sr, sg, sb, sa);

      const sumR = Math.min(255, dr + sr);
      const sumG = Math.min(255, dg + sg);
      const sumB = Math.min(255, db + sb);
      write(x, H + y, sumR, sumG, sumB, 255);

      const er = Math.abs(dr - sr);
      const eg = Math.abs(dg - sg);
      const eb = Math.abs(db - sb);
      const m = Math.max(er, eg, eb);
      const amp = Math.min(255, m * 6);
      write(W + x, H + y, amp, amp, amp, 255);
    }
  }
  return out;
}

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
  passed: boolean,
  extra: Record<string, unknown> = {}
) {
  fs.mkdirSync(PARITY_OUT, { recursive: true });
  const rel = (name: string) => path.join("test-results", "parity", name);
  const base = path.join(PARITY_OUT, fixture);
  if (!passed) {
    fs.writeFileSync(`${base}-diff.png`, Buffer.from(PNG.sync.write(diff)));
    fs.writeFileSync(`${base}-designer.png`, Buffer.from(PNG.sync.write(designer)));
    fs.writeFileSync(`${base}-sim.png`, Buffer.from(PNG.sync.write(simPng)));
    const composite = buildParityCompositePng(designer, simPng);
    fs.writeFileSync(`${base}-composite.png`, Buffer.from(PNG.sync.write(composite)));
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
        compositeLayout: `${designer.width * 2}×${designer.height * 2}: TL designer, TR sim, BL per-channel sum (clamped), BR max(|ΔR|,|ΔG|,|ΔB|)×6 grayscale`,
        artifactsOnFailure: passed
          ? []
          : [
              rel(`${fixture}-diff.png`),
              rel(`${fixture}-designer.png`),
              rel(`${fixture}-sim.png`),
              rel(`${fixture}-composite.png`),
            ],
        playwrightJson: rel("playwright-report.json"),
        nextStep:
          "Edit Canvas/compiler (or capture/crop); rerun: cd frontend && npm run parity:mac (or npm run test:parity if snapshots already exist).",
        ...extra,
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
    `[parity:e2e] env OK — mode=${parityMode()} — Vite preview is up (cold starts: watch webServer npm/vite lines above before this)`
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
      const mode = parityMode();

      if (mode === "strict") {
        const tol = Number(process.env.PARITY_PIXEL_THRESHOLD ?? "0");
        const numDiff = pixelmatch(designer.data, simPng.data, diff.data, designer.width, designer.height, { threshold: tol });
        const maxDiff = Number(process.env.PARITY_MAX_DIFF_PIXELS ?? "0");
        const passed = numDiff <= maxDiff;
        writeParityResult(fixture, designer, simPng, diff, numDiff, maxDiff, tol, passed, {
          parityMode: "strict",
        });
        // eslint-disable-next-line no-console
        console.log(
          `[parity:e2e] ${fixture}: strict pixelmatch ${numDiff} diff px (max ${maxDiff}, thr ${tol}) → ${passed ? "PASS" : "FAIL"}`
        );
        expect(
          numDiff,
          `${fixture}: ${numDiff} pixels differ (max allowed ${maxDiff}, threshold ${tol}) — see ${path.join(PARITY_OUT, fixture)}-result.json and *-diff.png`
        ).toBeLessThanOrEqual(maxDiff);
        return;
      }

      // Perceptual: coarse downsample ratio (font/AA averaged away).
      const coarseW = Number(process.env.PARITY_COARSE_WIDTH ?? "160");
      const coarseThr = Number(process.env.PARITY_COARSE_THRESHOLD ?? "0.12");
      const maxRatio = Number(process.env.PARITY_COARSE_MAX_RATIO ?? "0.12");
      const coarse = coarseParityMetrics(designer, simPng, coarseW, coarseThr);
      const fullTol = Number(process.env.PARITY_PIXEL_FULL_THRESHOLD ?? "0.12");
      const fullResDiffRelaxed = pixelmatch(designer.data, simPng.data, diff.data, designer.width, designer.height, {
        threshold: fullTol,
      });
      const maxCoarsePixels = Math.ceil(coarse.coarseTotalPixels * maxRatio);
      const passed = coarse.coarseDiffRatio <= maxRatio;
      writeParityResult(
        fixture,
        designer,
        simPng,
        diff,
        coarse.coarseDiffPixels,
        maxCoarsePixels,
        coarseThr,
        passed,
        {
          parityMode: "perceptual",
          coarseWidth: coarse.coarseW,
          coarseHeight: coarse.coarseH,
          coarseThreshold: coarseThr,
          coarseTotalPixels: coarse.coarseTotalPixels,
          coarseDiffRatio: Number(coarse.coarseDiffRatio.toFixed(5)),
          coarseMaxRatio: maxRatio,
          fullResDiffPixelsRelaxed: fullResDiffRelaxed,
          fullResThreshold: fullTol,
        }
      );
      // eslint-disable-next-line no-console
      console.log(
        `[parity:e2e] ${fixture}: perceptual coarse ${(coarse.coarseDiffRatio * 100).toFixed(2)}% diff (${coarse.coarseDiffPixels}/${coarse.coarseTotalPixels}, max ${(maxRatio * 100).toFixed(0)}%) → ${passed ? "PASS" : "FAIL"}; full@${fullTol} ${fullResDiffRelaxed} px (informational)`
      );
      expect(
        coarse.coarseDiffRatio,
        `${fixture}: coarse diff ratio ${coarse.coarseDiffRatio.toFixed(4)} > max ${maxRatio} (${coarse.coarseW}×${coarse.coarseH} @ threshold ${coarseThr}) — see ${path.join(PARITY_OUT, fixture)}-result.json`
      ).toBeLessThanOrEqual(maxRatio);
    });
  }
});
