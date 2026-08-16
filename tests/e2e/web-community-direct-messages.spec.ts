import { expect, test, type Page } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import { dismissAllWebAnnouncements } from "./support/web_announcements";

test.use({ screenshot: "off", trace: "off" });

interface DirectMessageIdentity {
  username: string;
  password: string;
}

function requiredIdentity(prefix: string): DirectMessageIdentity {
  const username = process.env[`${prefix}_USERNAME`];
  const password = process.env[`${prefix}_PASSWORD`];
  if (!username || !password) throw new Error(`缺少 ${prefix}_USERNAME 或 ${prefix}_PASSWORD`);
  return { username, password };
}

async function login(page: Page, identity: DirectMessageIdentity): Promise<void> {
  await page.goto("/login");
  await dismissAllWebAnnouncements(page);
  await page.getByLabel("用户名或邮箱").fill(identity.username);
  await page.getByLabel("账号密码").fill(identity.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/$/u);
}

async function logout(page: Page): Promise<void> {
  await page.getByRole("button", { name: /打开 .* 的账户菜单/u }).click();
  await page.getByRole("menuitem", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/\/login$/u);
}

test("Web 私信完成发起、双向收发、已读、归档、静音和非成员隔离旅程", async ({ page }, testInfo) => {
  const sender = requiredIdentity("E2E_WEB_DM_SENDER");
  const recipient = requiredIdentity("E2E_WEB_DM_RECIPIENT");
  const outsider = requiredIdentity("E2E_WEB_DM_OUTSIDER");
  const browserErrors = observeBrowserErrors(page);
  const outbound = `E2E ${testInfo.project.name} 私信合成消息`;
  const reply = `E2E ${testInfo.project.name} 私信合成回复`;

  await login(page, sender);
  await page.goto(`/community/users/${recipient.username}`);
  await expect(page.getByText(`@${recipient.username}`, { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "发送私信" }).click();
  await expect(page).toHaveURL(/\/community\/messages\/[^/]+$/u);
  const conversationUrl = page.url();

  await expect(page.getByRole("heading", { name: "私信会话" })).toBeVisible();
  await expect(page.getByText(/当前不是端到端加密/u)).toBeVisible();
  await expect(page.getByText(/仅会话成员可读取/u)).toBeVisible();
  await page.getByLabel("消息内容").fill(outbound);
  await page.getByRole("button", { name: "发送消息" }).click();
  await expect(page.getByText(outbound, { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "返回私信收件箱" }).click();
  const senderRow = page.locator("article").filter({ hasText: `@${recipient.username}` });
  await expect(senderRow).toBeVisible();
  await senderRow.getByRole("button", { name: "归档" }).click();
  await expect(senderRow.getByText("已归档", { exact: true })).toBeVisible();
  await senderRow.getByRole("button", { name: "恢复" }).click();
  await expect(senderRow.getByText("已归档", { exact: true })).toHaveCount(0);
  await senderRow.getByRole("button", { name: "静音 7 天" }).click();
  await expect(senderRow.getByText("静音中", { exact: true })).toBeVisible();
  await senderRow.getByRole("button", { name: "取消静音" }).click();
  await expect(senderRow.getByText("静音中", { exact: true })).toHaveCount(0);

  await logout(page);
  await login(page, recipient);
  await page.goto("/community/messages");
  const recipientRow = page.locator("article").filter({ hasText: `@${sender.username}` });
  await expect(recipientRow).toBeVisible();
  await expect(recipientRow.getByText(/未读 \d+/u)).toBeVisible();
  await recipientRow.getByRole("link", { name: "打开会话" }).click();
  await expect(page.getByText(outbound, { exact: true })).toBeVisible();
  await page.getByLabel("消息内容").fill(reply);
  await page.getByRole("button", { name: "发送消息" }).click();
  await expect(page.getByText(reply, { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "返回私信收件箱" }).click();
  const readRow = page.locator("article").filter({ hasText: `@${sender.username}` });
  await expect(readRow.getByText(/未读 \d+/u)).toHaveCount(0);

  await logout(page);
  await login(page, sender);
  await page.goto(conversationUrl);
  await expect(page.getByText(reply, { exact: true })).toBeVisible();
  expectNoBrowserErrors(browserErrors);

  await logout(page);
  await login(page, outsider);
  const deniedResponse = page.waitForResponse(
    (response) => response.url().includes("/direct-conversations/") && response.status() === 404,
  );
  await page.goto(conversationUrl);
  await deniedResponse;
  await expect(page.getByRole("alert")).toContainText("无权访问该私信会话");
  await expect(page.getByText(outbound, { exact: true })).toHaveCount(0);
});
