import type { Page } from "@playwright/test";

/** Fill a Naive UI number input and commit it (blur). */
export async function numberInput(page: Page, name: string, value: string): Promise<void> {
  const input = page.locator(`[data-field=${name}] input`);
  await input.fill(value);
  await input.press("Tab");
}

/** Pick an option from a Naive UI select rendered for a schema field. */
export async function choose(page: Page, name: string, option: string): Promise<void> {
  await page.locator(`[data-field=${name}] .n-base-selection`).click();
  await page.locator(".n-base-select-option", { hasText: new RegExp(`^${option}$`) }).click();
}

/** Toggle a Naive UI switch rendered for a boolean field. */
export async function toggle(page: Page, name: string, on: boolean): Promise<void> {
  const control = page.locator(`[data-field=${name}] .n-switch`);
  const checked = await control.getAttribute("aria-checked");
  if ((checked === "true") !== on) {
    await control.click();
  }
}
