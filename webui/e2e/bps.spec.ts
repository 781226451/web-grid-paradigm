import { expect, test } from "@playwright/test";

// The achieved-bitrate formula clamps the net count at zero, so a block with
// more misclicks than hits reports 0.00 bits/s instead of a negative rate.

const payload = {
  reset: true,
  server_time: Date.now() / 1000,
  status: "running",
  control: true,
  state: {
    phase: "run",
    block: 1,
    trials_done: 1,
    block_elapsed: 4,
    block_bps: 0,
    config: { blocks: 1, targets: 8, rows: 8, cols: 10, max_seconds: 0 },
    grid: { rows: 8, cols: 10, left: 0, top: 0, pitch: 1, line: 1 },
    reward_count: 0,
    reward_total: 0,
  },
  trial_offset: 0,
  trials: [
    {
      block: 1,
      trial: 1,
      cell: "r1c1",
      outcome: "hit",
      rt: 0.5,
      misclicks: 5,
      path_efficiency: null,
    },
  ],
  blocks: [],
  runs: [],
  logs: [],
  lsl: { enabled: false, live: false, stream: "WebGridState", rate: 10, sent: 0, consumers: 0, error: null },
  reward_device: {
    connected: false,
    port: "COM3",
    baud: 9600,
    sent: 0,
    errors: 0,
    error: null,
    ports: [],
  },
};

test("a negative net count clamps the block BPS to zero", async ({ page }) => {
  await page.route("**/events", (route) =>
    route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
      body: `data: ${JSON.stringify(payload)}\n\n`,
    }),
  );

  await page.goto("/");

  const value = page.locator('[data-kpi="本 block BPS"] .value');
  await expect(value).toHaveText("0.00");

  const card = page.locator('[data-kpi="本 block BPS"]');
  await expect(card).toHaveAttribute("title", /max\(命中 − 误点, 0\)/);
  await expect(page.locator(".progress .meta")).toContainText("0.00 BPS");
});
