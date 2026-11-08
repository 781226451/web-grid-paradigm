import { expect, test } from "@playwright/test";

import { choose } from "./helpers";

test.describe("control panel shell", () => {
  test("renders the parameter form from the server schema", async ({ page }) => {
    await page.goto("/");

    await expect(page).toHaveTitle(/BCI Web-Grid/);
    await expect(page.getByRole("heading", { name: "BCI Web-Grid 控制台" })).toBeVisible();
    await expect(page.locator(".bar .n-tag", { hasText: "已连接" })).toBeVisible();

    // 30 inline fields; device-specific fields live in the "输入设备" dialog.
    await expect(page.locator("form [data-field]")).toHaveCount(30);
    for (const group of ["会话", "实验设计", "任务", "奖励设备", "奖励策略", "输入", "显示", "标记"]) {
      await expect(page.locator(".group-title", { hasText: group })).toBeVisible();
    }

    await expect(page.locator("[data-field=subject] input")).toHaveValue(/sub-/);
    await expect(page.locator("[data-field=blocks] input")).toHaveValue(/\d+/);
  });

  test("input device dialog only shows the selected mode's fields", async ({ page }) => {
    await page.goto("/");

    await choose(page, "input", "joystick");
    await page.getByRole("button", { name: "配置…" }).click();
    await expect(page.getByText("配置串口摇杆")).toBeVisible();
    await expect(page.getByText("波特率", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "取消" }).click();

    await choose(page, "input", "lsl");
    await page.getByRole("button", { name: "配置…" }).click();
    await expect(page.getByText("配置LSL 速度流")).toBeVisible();
    await expect(page.getByText("速度流名称", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "取消" }).click();
  });

  test("editing the joystick dialog updates the device summary", async ({ page }) => {
    await page.goto("/");

    await choose(page, "input", "joystick");
    await page.getByRole("button", { name: "配置…" }).click();
    const dialog = page.locator(".n-modal");
    await dialog.locator("input").first().fill("COM9");
    await page.getByRole("button", { name: "确定" }).click();
    await expect(page.locator(".device[data-device=input] .status")).toContainText(
      "COM9",
    );
  });

  test("dialog values are sent with the start request", async ({ page }) => {
    let payload: Record<string, unknown> = {};
    await page.route("**/api/start", async (route) => {
      payload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({ error: "intentional stop" }),
      });
    });

    await page.goto("/");
    await choose(page, "input", "joystick");
    await page.getByRole("button", { name: "配置…" }).click();
    await page.locator(".n-modal input").first().fill("COM9");
    await page.getByRole("button", { name: "确定" }).click();
    await page.getByRole("button", { name: "启动实验" }).click();

    await expect(page.locator(".n-alert")).toContainText("intentional stop");
    expect(payload.input).toBe("joystick");
    expect(payload.joystick_port).toBe("COM9");
  });

  test("the LSL dialog requires both stream name and type", async ({ page }) => {
    await page.goto("/");

    await choose(page, "input", "lsl");
    await page.getByRole("button", { name: "配置…" }).click();
    const inputs = page.locator(".n-modal input");
    await inputs.nth(0).fill("");
    await page.getByRole("button", { name: "确定" }).click();
    await expect(page.locator(".n-modal")).toContainText(
      "速度流名称和类型都必须填写",
    );

    await inputs.nth(0).fill("WebGridVelocity");
    await page.getByRole("button", { name: "确定" }).click();
    await expect(page.locator(".device[data-device=input] .status")).toContainText(
      "WebGridVelocity",
    );
  });

  test("LSL state card starts from the configured stream and rate", async ({ page }) => {
    await page.goto("/");

    await expect(page.locator('[data-lsl="stream"] input')).toHaveValue("E2EState");
    await expect(page.locator('[data-lsl="rate"] input')).toHaveValue("25");
  });

  test("shows the monitoring and hardware cards", async ({ page }) => {
    await page.goto("/");

    for (const title of [
      "实验参数",
      "实时网格",
      "会话信息",
      "LSL 状态流（供其他 LSL 客户端读取）",
      "进度",
      "本次运行表现",
      "Block 结果",
      "最近 trial",
      "历史运行",
      "日志",
    ]) {
      await expect(page.getByText(title, { exact: true }).first()).toBeVisible();
    }

    // The device line follows the delivery mode; switch back to serial so the
    // assertion does not depend on the previous test.
    await choose(page, "reward", "serial");
    await expect(page.locator(".device[data-device=reward] .status")).toHaveText("未连接");
    await expect(page.getByRole("button", { name: "启动实验" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "中止" })).toBeDisabled();
  });

});
