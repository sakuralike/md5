import { expect, type Page } from "@playwright/test";

interface BrowserTokenPayload {
  access_token: string;
  user: Record<string, unknown>;
}

const apiBaseUrl = "http://127.0.0.1:18100/api/v1";
const webOrigin = "http://127.0.0.1:15173";

export function requiredWebFixture(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`缺少 ${name} 合成配置`);
  return value;
}

export async function bootstrapSeededWebSession(page: Page, rawRefreshToken: string): Promise<void> {
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
}
