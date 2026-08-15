import { expect, test, type Page } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import { dismissAllWebAnnouncements } from "./support/web_announcements";

test.use({ screenshot: "off", trace: "off" });

async function loginSyntheticWebUser(page: Page): Promise<void> {
  const username = process.env.E2E_WEB_USERNAME;
  const password = process.env.E2E_WEB_PASSWORD;
  if (!username || !password) {
    throw new Error("缺少 E2E_WEB_USERNAME 或 E2E_WEB_PASSWORD");
  }

  await page.goto("/login");
  await dismissAllWebAnnouncements(page);
  await page.getByLabel("用户名或邮箱").fill(username);
  await page.getByLabel("账号密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/$/u);
}

test("Web 第三方授权与已授权应用路由真实渲染", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  await page.route("**/api/v1/third-party/oauth/consent**", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        client_id: "pdc_synthetic-client",
        app_name: "合成桌面工具",
        developer_name: "合成开发者",
        description: "用于真实路由渲染的合成应用",
        redirect_uri: "https://client.example/callback",
        requested_scopes: ["profile:read"],
        approved_scopes: ["profile:read"],
        previously_authorized: false,
      }),
    });
  });
  await loginSyntheticWebUser(page);

  await page.goto(
    "/oauth/authorize?response_type=code&client_id=pdc_synthetic-client&redirect_uri=https%3A%2F%2Fclient.example%2Fcallback&scope=profile%3Aread&state=synthetic-state-0123456789&code_challenge=synthetic-challenge-abcdefghijklmnopqrstuvwxyz0123456789&code_challenge_method=S256",
  );
  await expect(page.getByRole("heading", { name: "合成桌面工具请求访问" })).toBeVisible();

  await page.goto("/account/authorized-applications");
  await expect(page.getByRole("heading", { name: "已授权应用" })).toBeVisible();
  expectNoBrowserErrors(browserErrors);
});
