import { expect, test } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";

// 认证请求含短期合成凭据，不生成可能记录请求体或令牌的 Trace。
test.use({ screenshot: "off", trace: "off" });

test("Web 游客门禁、注册、退出和重新登录形成真实 API 闭环", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const password = process.env.E2E_WEB_PASSWORD;
  if (!password) throw new Error("缺少 E2E_WEB_PASSWORD");

  await page.goto("/trust-cases");
  await expect(page).toHaveURL(/\/login$/u);
  await expect(page.getByRole("heading", { name: "登录密码侦探社" })).toBeVisible();

  await page.getByRole("link", { name: "立即注册" }).click();
  await page.getByLabel("用户名").fill("synthetic_e2e_web");
  await page.getByLabel("邮箱").fill("synthetic-e2e-web@example.com");
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "注册并登录" }).click();

  await expect(page).toHaveURL(/\/$/u);
  await expect(page.getByRole("heading", { name: "计算压缩包指纹，精确寻找可信候选。" })).toBeVisible();
  await expect(page.getByRole("link", { name: "举报申诉" })).toBeVisible();

  await page.getByRole("button", { name: "退出" }).click();
  await expect(page).toHaveURL(/\/login$/u);

  await page.getByLabel("用户名或邮箱").fill("synthetic_e2e_web");
  await page.getByLabel("账号密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/$/u);
  await expect(page.getByRole("link", { name: "账号安全" })).toBeVisible();
  expectNoBrowserErrors(browserErrors);
});
