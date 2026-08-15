import { expect, test, type Page } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";

test.use({ screenshot: "off", trace: "off" });

async function loginSyntheticAdmin(page: Page): Promise<void> {
  const username = process.env.E2E_ADMIN_USERNAME;
  const password = process.env.E2E_ADMIN_PASSWORD;
  if (!username || !password) {
    throw new Error("缺少 E2E_ADMIN_USERNAME 或 E2E_ADMIN_PASSWORD");
  }

  await page.goto("/login");
  await page.getByLabel("用户名或邮箱").fill(username);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录管理端" }).click();
  await expect(page).toHaveURL(/\/$/u);
}

test("Admin 第三方 API 管理页面真实渲染并出现在导航", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  await loginSyntheticAdmin(page);

  await expect(page.getByRole("link", { name: "第三方 API", exact: true })).toBeVisible();
  await page.goto("/third-party-apps");
  await expect(page.getByRole("heading", { name: "第三方应用治理" })).toBeVisible();
  expectNoBrowserErrors(browserErrors);
});
