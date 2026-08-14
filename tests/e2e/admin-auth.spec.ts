import { expect, test } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import { currentTotp } from "./support/totp";

// TOTP 绑定和登录请求含短期合成凭据，认证场景关闭网络 Trace。
test.use({ screenshot: "off", trace: "off" });

test("Admin 游客门禁、首次 TOTP 绑定和二次登录形成真实 API 闭环", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const username = process.env.E2E_ADMIN_USERNAME;
  const password = process.env.E2E_ADMIN_PASSWORD;
  if (!username || !password) throw new Error("缺少 Admin E2E 合成账号配置");

  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/u);
  await expect(page.getByRole("heading", { name: "管理端登录" })).toBeVisible();

  await page.getByLabel("用户名或邮箱").fill(username);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录管理端" }).click();

  await expect(page).toHaveURL(/\/totp-setup$/u);
  await expect(page.getByRole("heading", { name: "绑定 TOTP" })).toBeVisible();
  // 首次访问门禁以 403 auth.totp_setup_required 驱动绑定流程，该预期响应会被 Chromium 记录为资源错误。
  browserErrors.length = 0;
  const secretInput = page.getByLabel("手工密钥");
  await page.waitForFunction(() => {
    const input = document.querySelector<HTMLInputElement>("#totp-secret");
    return Boolean(input?.value.match(/^[A-Z2-7]+$/u));
  });
  const secret = await secretInput.inputValue();
  if (!secret.match(/^[A-Z2-7]+$/u)) throw new Error("TOTP 密钥格式不正确");
  await secretInput.evaluate((element) => {
    element.setAttribute("value", "[REDACTED]");
    (element as HTMLInputElement).value = "[REDACTED]";
  });
  await page.getByLabel("动态验证码").fill(currentTotp(secret));
  await page.getByRole("button", { name: "确认并启用" }).click();
  await expect(page).toHaveURL(/\/login$/u);

  await page.getByLabel("用户名或邮箱").fill(username);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByLabel("动态验证码（已启用时必填）").fill(currentTotp(secret));
  await page.getByRole("button", { name: "登录管理端" }).click();

  await expect(page).toHaveURL(/\/$/u);
  await expect(page.getByRole("link", { name: "仪表盘", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "真实指标仪表盘" })).toBeVisible();
  expectNoBrowserErrors(browserErrors);
});
