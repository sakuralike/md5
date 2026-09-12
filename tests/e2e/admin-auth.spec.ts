import { expect, test } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";

// 登录请求含短期合成凭据，认证场景关闭网络 Trace。
test.use({ screenshot: "off", trace: "off" });

test("Admin 游客门禁、默认关闭 TOTP 的密码登录和可选设置入口形成真实 API 闭环", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const username = process.env.E2E_ADMIN_USERNAME;
  const password = process.env.E2E_ADMIN_PASSWORD;
  if (!username || !password) throw new Error("缺少 Admin E2E 合成账号配置");

  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/u);
  await expect(page.getByRole("heading", { name: "管理端登录" })).toBeVisible();
  await expect(page.getByText("TOTP 默认关闭", { exact: true })).toBeVisible();

  await page.getByLabel("用户名或邮箱").fill(username);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录管理端" }).click();

  await expect(page).toHaveURL(/\/$/u);
  await expect(page.getByRole("link", { name: "仪表盘", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "运营仪表盘" })).toBeVisible();

  await page.goto("/totp-setup");
  await expect(page).toHaveURL(/\/totp-setup$/u);
  await expect(page.getByRole("heading", { name: "绑定 TOTP" })).toBeVisible();
  await expect(page.getByText("可选安全增强", { exact: true })).toBeVisible();
  await expect(page.getByText(/TOTP 默认关闭/u)).toBeVisible();
  expectNoBrowserErrors(browserErrors);
});
