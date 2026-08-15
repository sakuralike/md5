import { expect, test, type Page } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import { dismissAllWebAnnouncements } from "./support/web_announcements";

// 认证请求含短期合成凭据，不生成可能记录请求体或令牌的 Trace。
test.use({ screenshot: "off", trace: "off" });

async function logout(page: Page): Promise<void> {
  await page.getByRole("button", { name: /打开 .* 的账户菜单/u }).click();
  await page.getByRole("menuitem", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/\/login$/u);
}

test("Web 游客门禁、注册、退出和重新登录形成真实 API 闭环", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const password = process.env.E2E_WEB_PASSWORD;
  if (!password) throw new Error("缺少 E2E_WEB_PASSWORD");

  // 每次运行使用独立的合成账号，避免复用残留数据导致注册 409。
  const username = `synthetic_web_${Date.now().toString(36)}`.slice(0, 32);
  const email = `${username}@example.com`;

  await page.goto("/trust-cases");
  await dismissAllWebAnnouncements(page);
  await expect(page).toHaveURL(/\/login$/u);
  await expect(page.getByRole("heading", { name: "登录密码侦探社" })).toBeVisible();

  await page.getByRole("link", { name: "立即注册" }).click();
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "注册并登录" }).click();

  await expect(page).toHaveURL(/\/$/u);
  await expect(page.getByRole("heading", { name: "计算压缩包指纹，精确寻找可信候选。" })).toBeVisible();
  const accountMenu = page.getByRole("button", { name: `打开 ${username} 的账户菜单` });
  await expect(accountMenu).toBeVisible();
  await accountMenu.click();
  await page.getByRole("menuitem", { name: "用户中心" }).click();
  await expect(page).toHaveURL(/\/user-center$/u);
  await expect(page.getByRole("heading", { name: "用户中心" })).toBeVisible();
  await expect(page.getByRole("link", { name: "账号安全" })).toBeVisible();

  await logout(page);

  await page.getByLabel("用户名或邮箱").fill(username);
  await page.getByLabel("账号密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/$/u);
  await expect(page.getByRole("button", { name: `打开 ${username} 的账户菜单` })).toBeVisible();
  expectNoBrowserErrors(browserErrors);
});
