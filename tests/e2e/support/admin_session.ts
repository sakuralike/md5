import { expect, type Page } from "@playwright/test";
import { currentTotp } from "./totp";

export interface WorkflowAdminCredentials {
  id: string;
  username: string;
  password: string;
  totpSecret: string;
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
  await page.getByLabel("动态验证码（已启用时必填）").fill(currentTotp(credentials.totpSecret));
  await page.getByRole("button", { name: "登录管理端" }).click();
  await expect(page).toHaveURL(/\/$/u);
  await expect(page.getByRole("heading", { name: "真实指标仪表盘" })).toBeVisible();
  return credentials;
}
