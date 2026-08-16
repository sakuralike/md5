import { expect, test } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import { dismissAllWebAnnouncements } from "./support/web_announcements";

test.use({ screenshot: "off", trace: "off" });

const publicTitle = "E2E 公开社区搜索恢复指南";
const privateTitle = "E2E 私密社区搜索恢复指南";

test("Web 匿名访客只能检索到公开社区内容", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);

  await page.goto("/community/search");
  await dismissAllWebAnnouncements(page);
  await expect(page.getByRole("heading", { name: "搜索社区" })).toBeVisible();

  await page.getByLabel("搜索社区").fill("公开社区搜索恢复");
  await page.getByRole("button", { name: "搜索", exact: true }).click();

  await expect(page.getByText(publicTitle, { exact: true })).toBeVisible();
  await expect(page.getByText(privateTitle, { exact: true })).toHaveCount(0);
  await expect(page.getByText("共找到 1 条公开结果", { exact: true })).toBeVisible();
  expectNoBrowserErrors(browserErrors);
});
