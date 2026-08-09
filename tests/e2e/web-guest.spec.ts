import { expect, test } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";

test("Web 公开首页可访问且受保护页面将游客送往登录页", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "计算压缩包指纹，精确寻找可信候选。" })).toBeVisible();
  await page.goto("/trust-cases");
  await expect(page).toHaveURL(/\/login$/u);
  expectNoBrowserErrors(browserErrors);
});
