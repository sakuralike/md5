import { expect, test, type Page } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import { dismissAllWebAnnouncements } from "./support/web_announcements";

test.use({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 1,
  hasTouch: true,
  isMobile: true,
  screenshot: "off",
  trace: "off",
});

async function loginSeededWeb(page: Page): Promise<void> {
  const username = process.env.E2E_WEB_USERNAME;
  const password = process.env.E2E_WEB_PASSWORD;
  if (!username || !password) throw new Error("缺少 E2E_WEB_USERNAME 或 E2E_WEB_PASSWORD");

  await page.goto("/login");
  await dismissAllWebAnnouncements(page);
  await page.getByLabel("用户名或邮箱").fill(username);
  await page.getByLabel("账号密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/$/u);
}

test("Web 移动端完成社区首页、发帖、详情、回复和返回首页主旅程", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const title = "E2E 移动端合成数据主题";
  const content = "这是移动端自动化测试发布的合成讨论内容，仅描述合法授权场景中的验证步骤和结果。";
  const reply = "这是移动端自动化测试发布的合成回复。";

  await loginSeededWeb(page);
  await page.goto("/community");
  await expect(page.getByRole("heading", { name: "社区首页" })).toBeVisible();
  await expect(page.getByRole("link", { name: "发布新主题" })).toBeVisible();

  await page.getByRole("link", { name: "发布新主题" }).click();
  await expect(page).toHaveURL(/\/community\/new$/u);
  await expect(page.getByRole("heading", { name: "发布新主题" })).toBeVisible();
  await page.getByLabel("主题标题").fill(title);
  await page.getByLabel("主题内容").fill(content);
  await page.getByLabel(/我确认内容来自合法授权场景/u).click();
  await page.getByRole("button", { name: "发布主题" }).click();

  await expect(page).toHaveURL(/\/community\/posts\/[^/]+$/u);
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByText("还没有回复。", { exact: true })).toBeVisible();

  await page.getByLabel("写回复").fill(reply);
  await page.getByLabel(/我确认回复不包含真实密码/u).click();
  await page.getByRole("button", { name: "发布回复" }).click();
  await expect(page.getByText(reply, { exact: true })).toBeVisible();
  await expect(page.getByText(/^1 条回复，支持两级定向回复。$/u)).toBeVisible();

  await page.getByRole("link", { name: "← 返回社区首页" }).click();
  await expect(page).toHaveURL(/\/community$/u);
  await expect(page.getByRole("link").filter({ hasText: title })).toBeVisible();
  expectNoBrowserErrors(browserErrors);
});
