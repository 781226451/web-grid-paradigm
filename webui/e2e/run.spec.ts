import { expect, test } from "@playwright/test";

import { choose, numberInput, toggle } from "./helpers";

test("a short demo run completes and fills the tables", async ({ page }) => {
  await page.goto("/");

  await choose(page, "input", "demo");
  await numberInput(page, "blocks", "1");
  await numberInput(page, "targets", "3");
  await numberInput(page, "countdown_seconds", "0");
  await numberInput(page, "iti", "0.1");
  await toggle(page, "fullscreen", false);
  await toggle(page, "auto_exit", true);
  await choose(page, "reward", "test");

  await page.getByRole("button", { name: "启动实验" }).click();

  // Parameters lock while the session runs.
  await expect(page.getByRole("button", { name: "中止" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "启动实验" })).toBeDisabled();

  // Three demo trials finish by themselves; the KPI card then shows 3 hits.
  await expect(page.locator('[data-kpi="命中"] .value')).toHaveText("3", {
    timeout: 60_000,
  });
  await expect(page.locator("table tbody tr").first()).toBeVisible();

  // The run goes back to idle on its own (auto-exit) and unlocks the form.
  await expect(page.getByRole("button", { name: "启动实验" })).toBeEnabled({ timeout: 60_000 });
  await expect(page.locator(".device[data-device=reward] .status")).toContainText("test 模式");

  // The finished run is listed in the history card.
  const history = page.locator(".n-card", { hasText: "历史运行" });
  await expect(history.locator("table tbody tr")).toHaveCount(1);
  await expect(history.locator("table tbody tr")).toContainText("完成");

  // The panel computes the block BPS itself; it must agree with the server.
  const bpsText = await page.locator('[data-kpi="本 block BPS"] .value').textContent();
  const bps = Number(bpsText);
  const snapshot = await page.evaluate(async () => (await fetch("/api/state")).json());
  expect(bps).toBeGreaterThan(0);
  expect(Math.abs(bps - snapshot.state.block_bps)).toBeLessThan(0.05);
});

test("a rejected start keeps the form usable and shows the error", async ({ page }) => {
  await page.route("**/api/start", (route) =>
    route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ error: "targets must be >= 1" }),
    }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: "启动实验" }).click();

  await expect(page.locator(".n-alert")).toContainText("targets must be >= 1");
  await expect(page.getByRole("button", { name: "启动实验" })).toBeEnabled();
  await expect(page.locator("[data-field=targets] input")).toBeEnabled();
});
