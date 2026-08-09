import { expect, test } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";

test("Admin 受保护入口拒绝未认证访问且不产生浏览器错误", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  await page.goto("/trust-cases");
  await expect(page).toHaveURL(/\/login$/u);
  await expect(page.getByRole("heading", { name: "管理端登录" })).toBeVisible();
  expectNoBrowserErrors(browserErrors);
});
