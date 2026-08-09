import { expect, type Page } from "@playwright/test";

export async function exerciseSkipLink(page: Page): Promise<void> {
  const skipLink = page.getByRole("link", { name: "跳到主要内容" });
  await page.keyboard.press("Tab");
  await expect(skipLink).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
}
