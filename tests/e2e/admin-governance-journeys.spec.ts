import { expect, test, type Page } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import { currentTotp } from "./support/totp";

interface AdminCredentials {
  id: string;
  username: string;
  password: string;
  totpSecret: string;
}

function adminCredentials(kind: "WORKFLOW" | "REVIEWER"): AdminCredentials {
  const id = process.env[`E2E_ADMIN_${kind}_ID`];
  const username = process.env[`E2E_ADMIN_${kind}_USERNAME`];
  const password = process.env[`E2E_ADMIN_${kind}_PASSWORD`];
  const totpSecret = process.env[`E2E_ADMIN_${kind}_TOTP_SECRET`];
  if (!id || !username || !password || !totpSecret) {
    throw new Error(`缺少 ${kind} Admin E2E 合成账号配置`);
  }
  return { id, username, password, totpSecret };
}

async function loginAdmin(page: Page, account: AdminCredentials): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("用户名或邮箱").fill(account.username);
  await page.getByLabel("密码", { exact: true }).fill(account.password);
  await page.getByLabel("动态验证码（仅已启用 TOTP 时填写）").fill(currentTotp(account.totpSecret));
  await page.getByRole("button", { name: "登录管理端" }).click();
  await expect(page).toHaveURL(/\/$/u);
  await expect(page.getByRole("heading", { name: "运营仪表盘" })).toBeVisible();
}

async function chooseGovernanceReason(page: Page, reason: string): Promise<void> {
  const actionPanel = page.getByText(/确认(?:停用|恢复)账号/u).locator("..").locator("..");
  await actionPanel.getByRole("combobox").click();
  await page.getByRole("option", { name: reason }).click();
}

// 管理操作包含短期合成凭据，关闭截图与 Trace，避免认证材料进入失败制品。
test.use({ screenshot: "off", trace: "off" });

test("Admin 停用普通用户、撤销活跃会话并恢复账号", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const admin = adminCredentials("WORKFLOW");
  const username = process.env.E2E_ADMIN_GOVERNANCE_USERNAME;
  if (!username) throw new Error("缺少用户治理 E2E 合成账号");

  await loginAdmin(page, admin);
  await page.goto("/users");
  await expect(page.getByRole("heading", { name: "用户审批工作台" })).toBeVisible();
  await page.getByLabel("搜索用户").fill(username);
  await page.getByRole("button", { name: "查询", exact: true }).click();
  const row = page.getByRole("row").filter({ hasText: username });
  await expect(row).toContainText("1");
  await row.getByRole("button", { name: "详情与治理" }).click();
  await expect(page.getByRole("heading", { name: username })).toBeVisible();

  await page.getByRole("button", { name: "停用账号" }).click();
  await chooseGovernanceReason(page, "安全风险");
  await page.getByLabel("当前密码").fill(admin.password);
  await page.getByLabel("TOTP 验证码").fill(currentTotp(admin.totpSecret));
  await page.getByRole("button", { name: "确认并执行" }).click();
  await expect(page.getByRole("status")).toContainText("账号已停用，并撤销 1 个活跃会话");
  await expect(page.getByRole("button", { name: "恢复账号" })).toBeVisible();

  await page.getByRole("button", { name: "恢复账号" }).click();
  await chooseGovernanceReason(page, "申诉通过");
  await page.getByLabel("当前密码").fill(admin.password);
  await page.getByLabel("TOTP 验证码").fill(currentTotp(admin.totpSecret));
  await page.getByRole("button", { name: "确认并执行" }).click();
  await expect(page.getByRole("status")).toContainText("账号已恢复为正常状态");
  await expect(page.getByRole("button", { name: "停用账号" })).toBeVisible();
  expectNoBrowserErrors(browserErrors);
});

test("Admin 由不同管理员创建并批准普通角色变更，撤销目标会话", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const requester = adminCredentials("WORKFLOW");
  const reviewer = adminCredentials("REVIEWER");
  const targetId = process.env.E2E_ADMIN_ROLE_TARGET_ID;
  const targetUsername = process.env.E2E_ADMIN_ROLE_TARGET_USERNAME;
  if (!targetId || !targetUsername) throw new Error("缺少角色审批 E2E 目标账号");

  await loginAdmin(page, requester);
  await page.goto("/role-changes");
  await expect(page.getByRole("heading", { name: "角色变更审批工作台" })).toBeVisible();
  await page.getByPlaceholder("合成用户 ID").fill(targetId);
  await page.getByLabel("当前密码").fill(requester.password);
  await page.getByLabel("TOTP 动态码").fill(currentTotp(requester.totpSecret));
  await page.getByRole("button", { name: "创建请求" }).click();
  await expect(page.getByText(/已创建，等待另一名管理员复核/u)).toBeVisible();

  await page.getByRole("button", { name: "退出" }).click();
  await expect(page).toHaveURL(/\/login$/u);
  await loginAdmin(page, reviewer);
  await page.goto("/role-changes");
  const pendingRow = page.getByRole("row").filter({ hasText: "普通用户 → 可信贡献者" });
  await pendingRow.getByRole("button", { name: "查看" }).click();
  await expect(page.getByText(targetId, { exact: true })).toBeVisible();
  await page.getByLabel("当前密码").fill(reviewer.password);
  await page.getByLabel("TOTP 动态码").fill(currentTotp(reviewer.totpSecret));
  await page.getByRole("button", { name: "批准选中" }).click();
  await expect(page.getByText("角色变更已批准，已撤销 1 个目标活跃会话。", { exact: true })).toBeVisible();
  await expect(page.getByText("已批准", { exact: true }).last()).toBeVisible();

  await page.goto("/users");
  await page.getByLabel("搜索用户").fill(targetUsername);
  await page.getByRole("button", { name: "查询", exact: true }).click();
  const targetRow = page.getByRole("row").filter({ hasText: targetUsername });
  await expect(targetRow).toContainText("可信贡献者");
  await expect(targetRow).toContainText("0");
  expectNoBrowserErrors(browserErrors);
});
