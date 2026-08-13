import { expect, test, type Page } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import { currentTotp } from "./support/totp";

// 账号安全旅程会处理短期合成凭据和 TOTP 密钥，不生成截图或网络 Trace。
test.use({ screenshot: "off", trace: "off" });

interface AccountCredentials {
  username: string;
  password: string;
}

function credentials(prefix: "SECURITY" | "TOTP" | "PRIVACY"): AccountCredentials {
  const username = process.env[`E2E_WEB_${prefix}_USERNAME`];
  const password = process.env[`E2E_WEB_${prefix}_PASSWORD`];
  if (!username || !password) throw new Error(`缺少 E2E_WEB_${prefix} 合成账号配置`);
  return { username, password };
}

async function login(page: Page, account: AccountCredentials, totpCode?: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("用户名或邮箱").fill(account.username);
  await page.getByLabel("账号密码").fill(account.password);
  if (totpCode) await page.getByLabel("TOTP 验证码（已启用时填写）").fill(totpCode);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/$/u);
}

async function logout(page: Page): Promise<void> {
  await page.getByRole("button", { name: /打开 .* 的账户菜单/u }).click();
  await page.getByRole("menuitem", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/\/login$/u);
}


test("Web 撤销其他登录会话并在修改密码后收口剩余会话", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const account = credentials("SECURITY");
  const newPassword = process.env.E2E_WEB_SECURITY_NEW_PASSWORD;
  if (!newPassword) throw new Error("缺少 E2E_WEB_SECURITY_NEW_PASSWORD");

  await login(page, account);
  await page.goto("/security");
  await expect(page.getByRole("heading", { name: "账号与隐私中心" })).toBeVisible();

  await page.getByRole("tab", { name: "登录会话" }).click();
  await expect(page.getByRole("button", { name: "撤销会话" })).toHaveCount(2);
  await page.getByRole("button", { name: "撤销会话" }).first().click();
  await expect(page.getByText("会话已撤销", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "撤销会话" })).toHaveCount(1);
  await page.getByRole("tab", { name: "密码与 TOTP" }).click();
  await page.getByLabel("当前密码", { exact: true }).fill(account.password);
  await page.getByLabel("新密码", { exact: true }).fill(newPassword);
  await page.getByLabel("确认新密码").fill(newPassword);
  await page.getByRole("button", { name: "修改密码" }).click();
  await expect(page.getByText("密码已修改，其他登录会话已撤销", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: "登录会话" }).click();
  await expect(page.getByRole("button", { name: "撤销会话" })).toHaveCount(0);
  expectNoBrowserErrors(browserErrors);
});

test("Web 完成 TOTP 绑定、登录门禁、验证登录与停用闭环", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const account = credentials("TOTP");

  await login(page, account);
  await page.goto("/security");
  await page.getByRole("tab", { name: "密码与 TOTP" }).click();
  await expect(page.getByText("未启用", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "生成 TOTP 配置" }).click();
  await expect(page.getByText("TOTP 配置已生成，请在认证器中完成绑定", { exact: true })).toBeVisible();

  const setupPanel = page.getByText("在认证器中添加此账号", { exact: true }).locator("..");
  const secret = (await setupPanel.locator("p.font-mono").textContent())?.trim();
  if (!secret) throw new Error("页面未显示合成 TOTP 密钥");
  await page.getByLabel("认证器验证码").fill(currentTotp(secret));
  await page.getByRole("button", { name: "确认启用" }).click();
  await expect(page.getByText("TOTP 已启用", { exact: true })).toBeVisible();
  await expect(page.getByText("已启用", { exact: true })).toBeVisible();

  await logout(page);
  await page.getByLabel("用户名或邮箱").fill(account.username);
  await page.getByLabel("账号密码").fill(account.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("请输入动态验证码");
  // 这次 401 是验证 TOTP 门禁的预期响应，不应被误判为未处理浏览器错误。
  browserErrors.splice(0);
  await expect(page).toHaveURL(/\/login$/u);

  await page.getByLabel("TOTP 验证码（已启用时填写）").fill(currentTotp(secret));
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/$/u);
  await page.goto("/security");
  await page.getByRole("tab", { name: "密码与 TOTP" }).click();
  await page.locator("#totp-current-password").fill(account.password);
  await page.getByLabel("认证器验证码").fill(currentTotp(secret));
  await page.getByRole("button", { name: "停用 TOTP" }).click();
  await expect(page.getByText("TOTP 已停用", { exact: true })).toBeVisible();
  await expect(page.getByText("未启用", { exact: true })).toBeVisible();
  expectNoBrowserErrors(browserErrors);
});

test("Web 确认隐私用途、一次性下载导出并创建后撤销账号删除请求", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const account = credentials("PRIVACY");

  await login(page, account);
  await page.goto("/account/privacy");
  await expect(page.getByRole("heading", { name: "隐私与授权中心" })).toBeVisible();

  const authorizationCard = page.locator("div.grid.gap-6").first().locator(":scope > div").first();
  const exportPurpose = authorizationCard.locator("div.rounded-xl").filter({ hasText: "个人数据导出" }).last();
  await exportPurpose.getByRole("button", { name: "确认声明" }).click();
  await expect(page.getByText("授权声明已确认", { exact: true })).toBeVisible();
  await expect(exportPurpose.getByText("已确认", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "申请导出" }).click();
  await expect(page.getByText("个人数据导出已生成，请在过期前完成一次性下载", { exact: true })).toBeVisible();
  await expect(page.getByText("ready", { exact: true })).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "一次性下载" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^privacy-export-.+\.json$/u);
  await expect(page.getByText("导出文件已下载，本次下载凭证已销毁", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "一次性下载" })).toBeDisabled();

  await page.getByLabel("当前密码", { exact: true }).fill(account.password);
  await page.getByRole("button", { name: "创建删除请求" }).click();
  await expect(page.getByText("账号删除请求已创建，可在撤销期限前取消", { exact: true })).toBeVisible();
  await expect(page.getByText("pending", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "取消删除请求" }).click();
  await expect(page.getByText("账号删除请求已取消", { exact: true })).toBeVisible();
  await expect(page.getByText("cancelled", { exact: true })).toBeVisible();
  expectNoBrowserErrors(browserErrors);
});
