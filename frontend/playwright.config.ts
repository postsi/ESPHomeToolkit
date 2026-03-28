import { defineConfig, devices } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  /** list for humans; JSON under test-results/parity for tools / agent loops */
  reporter: [
    ["list"],
    ["json", { outputFile: path.join(__dirname, "test-results", "parity", "playwright-report.json") }],
  ],
  use: {
    baseURL: "http://127.0.0.1:4173/api/esptoolkit/static/",
    trace: "on-first-retry",
    ...devices["Desktop Chrome"],
  },
  webServer: {
    command: "npm run generate:parity-fixtures && npm run build:vite && vite preview --host 127.0.0.1 --port 4173 --strictPort",
    cwd: __dirname,
    url: "http://127.0.0.1:4173/api/esptoolkit/static/",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
