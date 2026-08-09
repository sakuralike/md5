import { expect, type Page } from "@playwright/test";

export async function exerciseSkipLink(page: Page): Promise<void> {
  const skipLink = page.getByRole("link", { name: "跳到主要内容" });
  const browserName = page.context().browser()?.browserType().name();
  if (browserName === "webkit") {
    // Headless WebKit does not expose Safari's system full-keyboard-access preference.
    // Keep real Tab traversal in Chromium/Firefox and verify WebKit focus/activation directly.
    await skipLink.focus();
  } else {
    await page.keyboard.press("Tab");
  }
  await expect(skipLink).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
}
