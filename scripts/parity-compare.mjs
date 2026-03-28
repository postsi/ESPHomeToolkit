#!/usr/bin/env node
/**
 * Compare two PNG files (e.g. designer export vs Mac LVGL snapshot).
 * Usage: node scripts/parity-compare.mjs <a.png> <b.png>
 * Exit 1 if dimensions differ or pixel diff > PARITY_MAX_DIFF_PIXELS (default 0).
 */
import fs from "fs";
import path from "path";
import pixelmatch from "pixelmatch";
import { PNG } from "pngjs";

const aPath = process.argv[2];
const bPath = process.argv[3];
if (!aPath || !bPath) {
  console.error("Usage: node scripts/parity-compare.mjs <a.png> <b.png>");
  process.exit(2);
}
const maxDiff = Number(process.env.PARITY_MAX_DIFF_PIXELS ?? "0");
const threshold = Number(process.env.PARITY_PIXEL_THRESHOLD ?? "0");

const imgA = PNG.sync.read(fs.readFileSync(path.resolve(aPath)));
const imgB = PNG.sync.read(fs.readFileSync(path.resolve(bPath)));
if (imgA.width !== imgB.width || imgA.height !== imgB.height) {
  console.error(`Size mismatch: ${imgA.width}x${imgA.height} vs ${imgB.width}x${imgB.height}`);
  process.exit(1);
}
const diff = new PNG({ width: imgA.width, height: imgA.height });
const n = pixelmatch(imgA.data, imgB.data, diff.data, imgA.width, imgA.height, { threshold });
console.log(`pixelmatch: ${n} differing pixels (threshold=${threshold}, max allowed=${maxDiff})`);
if (n > maxDiff) process.exit(1);
