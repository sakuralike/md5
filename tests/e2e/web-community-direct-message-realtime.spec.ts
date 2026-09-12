import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import { dismissAllWebAnnouncements } from "./support/web_announcements";

test.use({ screenshot: "off", trace: "off" });
test.setTimeout(90_000);

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
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await dismissAllWebAnnouncements(page);
  await page.getByLabel("用户名或邮箱").fill(identity.username);
  await page.getByLabel("账号密码").fill(identity.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/$/u);
}

async function currentDirectCursor(page: Page): Promise<number> {
  return page.evaluate(() => {
    const key = Object.keys(sessionStorage).find((candidate) =>
      candidate.startsWith("community-direct-message-last-event:"),
    );
    if (!key) return -1;
    const value = Number(sessionStorage.getItem(key));
    return Number.isSafeInteger(value) ? value : -1;
  });
}

async function expectCursorAfter(page: Page, previous: number): Promise<void> {
  await expect.poll(() => currentDirectCursor(page), { timeout: 15_000 }).toBeGreaterThan(previous);
}

async function closeContexts(...contexts: BrowserContext[]): Promise<void> {
  await Promise.allSettled(contexts.map((context) => context.close()));
}

test("双用户私信实时同步未读、已读回执并通过游标恢复断线消息", async ({ browser }, testInfo) => {
  const senderIdentity = requiredIdentity("E2E_WEB_DM_SENDER");
  const recipientIdentity = requiredIdentity("E2E_WEB_DM_RECIPIENT");
  const senderContext = await browser.newContext();
  const recipientContext = await browser.newContext();
  const senderPage = await senderContext.newPage();
  const recipientPage = await recipientContext.newPage();
  const senderErrors = observeBrowserErrors(senderPage);
  const recipientErrors = observeBrowserErrors(recipientPage);
  const senderRequestFailures: string[] = [];
  const recipientRequestFailures: string[] = [];
  let recipientNetworkTransition = false;
  senderPage.on("requestfailed", (request) => senderRequestFailures.push(request.url()));
  recipientPage.on("requestfailed", (request) => {
    if (!recipientNetworkTransition) recipientRequestFailures.push(request.url());
  });

  const firstMessage = `E2E ${testInfo.project.name} 实时私信一`;
  const recoveredMessageOne = `E2E ${testInfo.project.name} 断线补偿二`;
  const recoveredMessageTwo = `E2E ${testInfo.project.name} 断线补偿三`;

  try {
    await Promise.all([
      login(senderPage, senderIdentity),
      login(recipientPage, recipientIdentity),
    ]);
    await recipientPage.goto("/community/messages");

    await senderPage.goto(`/community/users/${recipientIdentity.username}`);
    await senderPage.getByRole("button", { name: "发送私信" }).click();
    await expect(senderPage).toHaveURL(/\/community\/messages\/[^/]+$/u);
    const conversationUrl = senderPage.url();
    senderRequestFailures.length = 0;
    recipientRequestFailures.length = 0;

    await senderPage.getByLabel("消息内容").fill(firstMessage);
    await senderPage.getByRole("button", { name: "发送消息" }).click();
    await expect(senderPage.getByText(firstMessage, { exact: true })).toBeVisible();

    const recipientRow = recipientPage.locator("article").filter({
      hasText: `@${senderIdentity.username}`,
    });
    await expect(recipientRow).toBeVisible({ timeout: 15_000 });
    await expect(recipientRow.getByText("未读 1", { exact: true })).toBeVisible();
    await recipientPage.getByRole("button", { name: /打开 .* 的账户菜单/u }).click();
    await expect(recipientPage.getByLabel("未读私信数量")).toHaveText("1");
    await recipientPage.keyboard.press("Escape");

    await recipientRow.getByRole("link", { name: "打开会话" }).click();
    await expect(recipientPage.getByText(firstMessage, { exact: true })).toBeVisible();
    await expect(
      senderPage
        .locator("article")
        .filter({ has: senderPage.getByText(firstMessage, { exact: true }) })
        .getByText("对方已读", { exact: true }),
    ).toBeVisible({ timeout: 15_000 });
    const cursorBeforeOffline = await currentDirectCursor(recipientPage);
    expect(cursorBeforeOffline).toBeGreaterThanOrEqual(0);

    expectNoBrowserErrors(recipientErrors);
    expect(senderRequestFailures).toEqual([]);
    expect(recipientRequestFailures).toEqual([]);
    recipientErrors.length = 0;
    recipientNetworkTransition = true;
    await recipientContext.setOffline(true);
    await senderPage.getByLabel("消息内容").fill(recoveredMessageOne);
    await senderPage.getByRole("button", { name: "发送消息" }).click();
    await expect(senderPage.getByText(recoveredMessageOne, { exact: true })).toBeVisible();
    const sendButton = senderPage.getByRole("button", { name: "发送消息", exact: true });
    await expect(sendButton).toBeVisible();
    await senderPage.getByLabel("消息内容").fill(recoveredMessageTwo);
    await expect(sendButton).toBeEnabled();
    await sendButton.click();
    await expect(senderPage.getByText(recoveredMessageTwo, { exact: true })).toBeVisible();

    await recipientContext.setOffline(false);
    await expectCursorAfter(recipientPage, cursorBeforeOffline);
    expect(
      recipientErrors.filter(
        (error) =>
          !error.includes("ERR_INTERNET_DISCONNECTED") &&
          !error.includes("WebKit encountered an internal error"),
      ),
    ).toEqual([]);
    recipientErrors.length = 0;
    await expect(recipientPage.getByText(recoveredMessageOne, { exact: true })).toBeVisible({
      timeout: 15_000,
    });
    await expect(recipientPage.getByText(recoveredMessageTwo, { exact: true })).toBeVisible();
    for (const messageBody of [firstMessage, recoveredMessageOne, recoveredMessageTwo]) {
      await expect(
        senderPage
          .locator("article")
          .filter({ has: senderPage.getByText(messageBody, { exact: true }) })
          .getByText("对方已读", { exact: true }),
      ).toBeVisible({ timeout: 15_000 });
    }

    await recipientPage.reload();
    await expect(recipientPage).toHaveURL(conversationUrl);
    await expect(recipientPage.getByText(recoveredMessageOne, { exact: true })).toBeVisible();
    await expect(recipientPage.getByText(recoveredMessageTwo, { exact: true })).toBeVisible();
    recipientNetworkTransition = false;
    await recipientPage.waitForTimeout(500);
    expectNoBrowserErrors(senderErrors);
    expectNoBrowserErrors(recipientErrors);
    expect(senderRequestFailures).toEqual([]);
    expect(recipientRequestFailures).toEqual([]);
  } finally {
    await closeContexts(senderContext, recipientContext);
  }
});
