import { expect, test } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import { loginWorkflowAdmin } from "./support/admin_session";

test.use({ screenshot: "off", trace: "off" });

test("Admin Web 公告后台完成新建、自动关闭秒数设置和发布", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const title = `浏览器验收公告-${Date.now()}`;
  await loginWorkflowAdmin(page);
  await page.goto("/web-announcements");

  await expect(page.getByRole("heading", { name: "Web 端公告管理" })).toBeVisible();
  await page.getByLabel("标题").fill(title);
  await page.getByLabel("正文").fill("这是浏览器验收使用的 Web 公告正文。");
  await page.getByLabel("自动关闭秒数").fill("2");
  await page.getByRole("button", { name: "保存草稿" }).click();

  await expect(page.getByText("公告草稿已创建。", { exact: true })).toBeVisible();
  const record = page.getByRole("button", { name: new RegExp(title, "u") });
  await expect(record).toContainText("2 秒自动关闭");
  await expect(record).toContainText("草稿");

  await page.getByRole("button", { name: "发布公告" }).click();
  await expect(page.getByText("公告已发布，Web 端将在下次请求时看到。", { exact: true })).toBeVisible();
  await expect(record).toContainText("已发布");
  expectNoBrowserErrors(browserErrors);
});

