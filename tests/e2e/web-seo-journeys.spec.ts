import { expect, test } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";

test.use({ screenshot: "off", trace: "off" });

async function expectSafeNoIndex(page: Parameters<typeof observeBrowserErrors>[0]): Promise<void> {
  await expect(page.locator('meta[name="robots"]')).toHaveCount(1);
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "noindex, nofollow");
  await expect(page.locator('meta[name="description"]')).toHaveCount(0);
  await expect(page.locator('meta[name="keywords"]')).toHaveCount(0);
  await expect(page.locator('link[rel="canonical"]')).toHaveCount(0);
  await expect(page.locator('meta[property^="og:"]')).toHaveCount(0);
}

test("Web SEO 运行时在默认关闭索引时保持安全元标签", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);

  await page.goto("/");
  await expect(page).toHaveTitle("密码侦探社");
  await expectSafeNoIndex(page);

  await page.goto("/community?query=synthetic-secret#private-fragment");
  await expect(page).toHaveURL(/\/community\?query=synthetic-secret#private-fragment$/u);
  await expectSafeNoIndex(page);

  await page.goto("/login");
  await expectSafeNoIndex(page);

  expectNoBrowserErrors(browserErrors);
});

test("Web SEO 元标签不会复制会话查询参数或哈希片段", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  await page.goto("/community?token=synthetic-token#synthetic-fragment");

  const canonical = page.locator('link[rel="canonical"]');
  if ((await canonical.count()) > 0) {
    const href = await canonical.getAttribute("href");
    expect(href).not.toContain("?");
    expect(href).not.toContain("#");
  }
  const metadataContents = await page.locator("head").evaluate((head) =>
    Array.from(head.querySelectorAll("meta, link"), (element) =>
      element.getAttribute("content") ?? element.getAttribute("href") ?? "",
    ),
  );
  expect(metadataContents.join("\n")).not.toContain("synthetic-token");
  expect(metadataContents.join("\n")).not.toContain("synthetic-fragment");
  expectNoBrowserErrors(browserErrors);
});