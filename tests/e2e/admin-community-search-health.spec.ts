import { expect, test } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import { loginWorkflowAdmin } from "./support/admin_session";

test.use({ screenshot: "off", trace: "off" });

test("Admin 搜索健康页只展示聚合状态而不展示搜索内容", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);

  await loginWorkflowAdmin(page);
  await page.goto("/community/search-health");

  await expect(page.getByRole("heading", { name: "社区搜索健康" })).toBeVisible();
  await expect(page.getByText("test", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("已完成", { exact: true })).toBeVisible();
  await expect(page.getByText("搜索结果", { exact: true })).toHaveCount(0);
  await expect(page.getByText("查询历史", { exact: true })).toHaveCount(0);
  expectNoBrowserErrors(browserErrors);
});
