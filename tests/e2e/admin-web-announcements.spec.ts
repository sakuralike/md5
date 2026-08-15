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



test("Admin Web 公告后台真实上传图片并保存图片点击链接", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const title = `Web 图片外链验收-${Date.now()}`;
  const actionUrl = "http://127.0.0.1:15173/announcement-target";
  const imageBuffer = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
    "base64",
  );

  await loginWorkflowAdmin(page);
  await page.goto("/web-announcements");
  await page.getByLabel("标题").fill(title);
  await page.getByLabel("正文").fill("这是带图片和图片外链的 Web 公告验收正文。");
  await page.locator("#announcement-images").setInputFiles({
    name: "synthetic-announcement.png",
    mimeType: "image/png",
    buffer: imageBuffer,
  });

  await expect(page.getByText("已上传 1 张公告图片，请保存草稿。", { exact: true })).toBeVisible();
  await expect(page.getByPlaceholder("也可以手动填写 HTTP(S) 或已上传图片地址；每行一条")).toHaveValue(/web\/announcements\/assets\//u);
  await expect(page.locator('img[alt="公告图片预览"]')).toHaveCount(1);
  await page.getByLabel("图片点击链接（可选）").fill(actionUrl);
  await page.getByRole("button", { name: "保存草稿" }).click();

  await expect(page.getByText("公告草稿已创建。", { exact: true })).toBeVisible();
  const record = page.getByRole("button", { name: new RegExp(title, "u") });
  await expect(record).toContainText("图片 1 张");
  await page.getByRole("button", { name: "发布公告" }).click();
  await expect(page.getByText("公告已发布，Web 端将在下次请求时看到。", { exact: true })).toBeVisible();
  await expect(record).toContainText("已发布");
  expectNoBrowserErrors(browserErrors);
});
