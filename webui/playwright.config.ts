import { defineConfig, devices } from "@playwright/test";

const PORT = 8791;

// The suite drives a real control panel: Playwright starts `webgrid` itself
// (windowed, temp data dir, fixed port) and talks to the same HTTP API the
// page uses.  Chromium is taken from the installed Edge to avoid downloading
// a browser on lab machines.
export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    video: "off",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "edge",
      use: { ...devices["Desktop Edge"], channel: "msedge" },
    },
  ],
  webServer: {
    command:
      "uv run --frozen webgrid --debug --windowed --no-open-dashboard " +
      `--dashboard-port ${PORT} --output-dir .e2e-data --subject e2e-cli ` +
      "--lsl-state-stream E2EState --lsl-state-rate 25",
    url: `http://127.0.0.1:${PORT}/api/state`,
    cwd: "..",
    reuseExistingServer: true,
    timeout: 60_000,
    stdout: "ignore",
    stderr: "ignore",
  },
});
