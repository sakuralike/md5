import { expect, test, type APIResponse, type Page } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";

// 身份闭环会处理短期合成邮箱凭证与刷新令牌，不生成截图或网络 Trace。
test.use({ screenshot: "off", trace: "off" });

interface BrowserTokenPayload {
  access_token: string;
  user: Record<string, unknown>;
}

interface ApiErrorPayload {
  code: string;
}

const apiBaseUrl = "http://127.0.0.1:18100/api/v1";
const webOrigin = "http://127.0.0.1:15173";

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`缺少 ${name} 合成配置`);
  return value;
}

async function bootstrapSeededSession(page: Page, rawRefreshToken: string): Promise<BrowserTokenPayload> {
  await page.context().addCookies([
    {
      name: "pd_web_refresh",
      value: rawRefreshToken,
      domain: "127.0.0.1",
      path: "/api/v1/web/auth",
      httpOnly: true,
      secure: false,
      sameSite: "Lax",
    },
  ]);
  const refreshed = await page.request.post(`${apiBaseUrl}/web/auth/refresh`, {
    headers: { Origin: webOrigin },
  });
  expect(refreshed.status()).toBe(200);
  const tokens = (await refreshed.json()) as BrowserTokenPayload;
  await page.goto("/");
  await page.evaluate((session) => {
    sessionStorage.setItem(
      "password_detective_session_v2",
      JSON.stringify({ accessToken: session.access_token, user: session.user }),
    );
  }, tokens);
  await page.reload();
  return tokens;
}

async function expectApiError(response: APIResponse, status: number, code: string): Promise<void> {
  expect(response.status()).toBe(status);
  const body = (await response.json()) as ApiErrorPayload;
  expect(body.code).toBe(code);
}

test("Web 邮箱待验证、一次性验证、重放拒绝与已验证状态形成闭环", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const token = required("E2E_WEB_EMAIL_VERIFY_TOKEN");
  await bootstrapSeededSession(page, required("E2E_WEB_EMAIL_VERIFY_REFRESH_TOKEN"));
  await page.goto("/security");
  await expect(page.getByText("待验证", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "重新发送验证邮件" })).toBeVisible();

  await page.goto(`/verify-email?token=${encodeURIComponent(token)}`);
  await expect(page).toHaveURL(/\/verify-email$/u);
  await expect(page.getByText("验证成功", { exact: true })).toBeVisible();
  await expect(page.getByText("邮箱验证成功", { exact: true })).toBeVisible();
  expect(await page.content()).not.toContain(token);

  await page.goto(`/verify-email?token=${encodeURIComponent(token)}`);
  await expect(page).toHaveURL(/\/verify-email$/u);
  await expect(page.getByText("验证未完成", { exact: true })).toBeVisible();
  await expect(page.getByText("验证链接无效或已过期", { exact: true })).toBeVisible();
  browserErrors.splice(0);

  await page.goto("/security");
  await expect(page.getByText("已验证", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "重新发送验证邮件" })).toHaveCount(0);
  expectNoBrowserErrors(browserErrors);
});

test("Web 刷新令牌轮换后拒绝旧令牌重放并撤销令牌族", async ({ page, request }) => {
  const browserErrors = observeBrowserErrors(page);
  await bootstrapSeededSession(page, required("E2E_WEB_REFRESH_TOKEN"));
  await expect(page.getByRole("link", { name: "账号安全" })).toBeVisible();
  const initialCookie = (await page.context().cookies(`${apiBaseUrl}/web/auth/refresh`)).find(
    (cookie) => cookie.name === "pd_web_refresh",
  );
  if (!initialCookie) throw new Error("登录后未获得 Web HttpOnly 刷新令牌 Cookie");

  const rotated = await page.request.post(`${apiBaseUrl}/web/auth/refresh`, {
    headers: { Origin: webOrigin },
  });
  expect(rotated.status()).toBe(200);
  const rotatedTokens = (await rotated.json()) as BrowserTokenPayload;
  const rotatedCookie = (await page.context().cookies(`${apiBaseUrl}/web/auth/refresh`)).find(
    (cookie) => cookie.name === "pd_web_refresh",
  );
  if (!rotatedCookie) throw new Error("刷新后未获得轮换 Cookie");
  expect(rotatedCookie.value).not.toBe(initialCookie.value);

  const replay = await request.post(`${apiBaseUrl}/web/auth/refresh`, {
    headers: {
      Cookie: `pd_web_refresh=${initialCookie.value}`,
      Origin: webOrigin,
    },
  });
  await expectApiError(replay, 401, "auth.refresh_token_reused");

  const currentTokenRejected = await request.get(`${apiBaseUrl}/me/profile`, {
    headers: { Authorization: `Bearer ${rotatedTokens.access_token}` },
  });
  expect(currentTokenRejected.status()).toBe(401);
  const currentTokenError = (await currentTokenRejected.json()) as ApiErrorPayload;
  expect(currentTokenError.code).toBe("auth.session_revoked");

  const rotatedRefreshRejected = await request.post(`${apiBaseUrl}/web/auth/refresh`, {
    headers: {
      Cookie: `pd_web_refresh=${rotatedCookie.value}`,
      Origin: webOrigin,
    },
  });
  await expectApiError(rotatedRefreshRejected, 401, "auth.refresh_token_reused");
  expectNoBrowserErrors(browserErrors);
});

test("Web 刷新在缺少 Cookie 与自然过期时返回明确拒绝", async ({ request }) => {
  const missing = await request.post(`${apiBaseUrl}/web/auth/refresh`, {
    headers: { Cookie: "", Origin: webOrigin },
  });
  await expectApiError(missing, 401, "auth.authentication_required");

  const expired = await request.post(`${apiBaseUrl}/web/auth/refresh`, {
    headers: {
      Cookie: `pd_web_refresh=${required("E2E_WEB_EXPIRED_REFRESH_TOKEN")}`,
      Origin: webOrigin,
    },
  });
  await expectApiError(expired, 401, "auth.refresh_token_expired");
});

test("Web 多标签并发刷新只允许一次轮换并撤销竞争令牌族", async ({ request }) => {
  const refreshUrl = `${apiBaseUrl}/web/auth/refresh`;
  const headers = {
    Cookie: `pd_web_refresh=${required("E2E_WEB_CONCURRENT_REFRESH_TOKEN")}`,
    Origin: webOrigin,
  };
  const responses = await Promise.all([
    request.post(refreshUrl, { headers }),
    request.post(refreshUrl, { headers }),
  ]);
  const successful = responses.find((response) => response.status() === 200);
  const rejected = responses.find((response) => response.status() === 401);
  expect(successful, "并发刷新应有且仅有一个请求成功").toBeDefined();
  expect(rejected, "竞争刷新应触发旧令牌重放拒绝").toBeDefined();
  expect(responses.filter((response) => response.status() === 200)).toHaveLength(1);
  expect(responses.filter((response) => response.status() === 401)).toHaveLength(1);
  if (!successful || !rejected) return;
  await expectApiError(rejected, 401, "auth.refresh_token_reused");

  const tokens = (await successful.json()) as BrowserTokenPayload;
  const currentTokenRejected = await request.get(`${apiBaseUrl}/me/profile`, {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
  });
  await expectApiError(currentTokenRejected, 401, "auth.session_revoked");

  const setCookie = successful.headers()["set-cookie"] ?? "";
  const rotatedCookie = /pd_web_refresh=([^;]+)/u.exec(setCookie)?.[1];
  expect(rotatedCookie, "成功响应应下发轮换后的刷新 Cookie").toBeTruthy();
  if (!rotatedCookie) return;
  const rotatedRefreshRejected = await request.post(refreshUrl, {
    headers: { Cookie: `pd_web_refresh=${rotatedCookie}`, Origin: webOrigin },
  });
  await expectApiError(rotatedRefreshRejected, 401, "auth.refresh_token_reused");
});
test.describe("Web 移动端与键盘门禁", () => {
  test.use({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });

  test("邮箱验证页在移动视口无横向溢出且可由键盘返回登录", async ({ page }) => {
    const browserErrors = observeBrowserErrors(page);
    await page.goto("/verify-email");
    await expect(page.getByRole("heading", { name: "邮箱验证" })).toBeVisible();
    await expect(page.getByText("验证链接缺少有效凭证，请从邮件中的完整链接重新打开。", { exact: true })).toBeVisible();

    const dimensions = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);

    const returnLink = page.getByRole("link", { name: "返回登录" });
    await returnLink.focus();
    await expect(returnLink).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/login$/u);
    await expect(page.getByRole("heading", { name: "登录密码侦探社" })).toBeVisible();
    expectNoBrowserErrors(browserErrors);
  });
});
