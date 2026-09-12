import { expect, type Page } from "@playwright/test";
import { currentTotp } from "./totp";

export interface WorkflowAdminCredentials {
  id: string;
  username: string;
  password: string;
  totpSecret: string;
}

interface BrowserTokenPayload {
  access_token: string;
  user: Record<string, unknown>;
}

const apiBaseUrl = "http://127.0.0.1:18100/api/v1";
const adminOrigin = "http://127.0.0.1:15174";

export function requiredAdminFixture(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`缺少 ${name} 合成配置`);
  return value;
}

export function workflowAdminCredentials(): WorkflowAdminCredentials {
  const id = process.env.E2E_ADMIN_WORKFLOW_ID;
  const username = process.env.E2E_ADMIN_WORKFLOW_USERNAME;
  const password = process.env.E2E_ADMIN_WORKFLOW_PASSWORD;
  const totpSecret = process.env.E2E_ADMIN_WORKFLOW_TOTP_SECRET;
  if (!id || !username || !password || !totpSecret) {
    throw new Error("缺少 Admin 工作流 E2E 合成账号配置");
  }
  return { id, username, password, totpSecret };
}

export async function loginWorkflowAdmin(page: Page): Promise<WorkflowAdminCredentials> {
  const credentials = workflowAdminCredentials();
  await page.goto("/login");
  await page.getByLabel("用户名或邮箱").fill(credentials.username);
  await page.getByLabel("密码", { exact: true }).fill(credentials.password);
  await page.getByLabel("动态验证码（仅已启用 TOTP 时填写）").fill(currentTotp(credentials.totpSecret));
  await page.getByRole("button", { name: "登录管理端" }).click();
  await expect(page).toHaveURL(/\/$/u);
  await expect(page.getByRole("heading", { name: "运营仪表盘" })).toBeVisible();
  return credentials;
}

export async function bootstrapSeededAdminSession(page: Page, rawRefreshToken: string): Promise<void> {
  await page.context().addCookies([
    {
      name: "pd_admin_refresh",
      value: rawRefreshToken,
      domain: "127.0.0.1",
      path: "/api/v1/admin/auth",
      httpOnly: true,
      secure: false,
      sameSite: "Lax",
    },
  ]);
  const refreshed = await page.request.post(`${apiBaseUrl}/admin/auth/refresh`, {
    headers: { Origin: adminOrigin },
  });
  expect(refreshed.status()).toBe(200);
  const tokens = (await refreshed.json()) as BrowserTokenPayload;
  await page.goto("/");
  await page.evaluate((session) => {
    sessionStorage.setItem(
      "password_detective_admin_session_v2",
      JSON.stringify({ accessToken: session.access_token, user: session.user }),
    );
  }, tokens);
  await page.reload();
}
