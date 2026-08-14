import { expect, test, type Page } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";

test.use({ screenshot: "off", trace: "off" });

async function loginSeededWeb(page: Page): Promise<void> {
  const username = process.env.E2E_WEB_USERNAME;
  const password = process.env.E2E_WEB_PASSWORD;
  if (!username || !password) throw new Error("缺少 E2E_WEB_USERNAME 或 E2E_WEB_PASSWORD");

  await page.goto("/login");
  await page.getByLabel("用户名或邮箱").fill(username);
  await page.getByLabel("账号密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/$/u);
}

async function searchManualFingerprint(page: Page, fingerprint: string): Promise<void> {
  await page.getByRole("tab", { name: "手工指纹查询" }).click();
  await page.getByLabel("MD5 / SHA-1 / SHA-256 / SHA-512").fill(fingerprint);
  await page.getByRole("button", { name: "识别并精确查询" }).click();
}

test("Web 查询已验证候选、揭示密码并从页面清除", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const fingerprint = process.env.E2E_VERIFIED_SHA256;
  const password = process.env.E2E_VERIFIED_PASSWORD;
  if (!fingerprint || !password) throw new Error("缺少已验证候选 E2E 数据");

  await loginSeededWeb(page);
  await searchManualFingerprint(page, fingerprint);
  await expect(page.getByText("发现 1 条可见候选")).toBeVisible();
  await expect(page.getByText("已验证 1")).toBeVisible();
  await expect(page.getByText("••••••••")).toBeVisible();
  await expect(page.getByText(password)).toHaveCount(0);

  await page.getByRole("button", { name: "揭示最高可信候选" }).click();
  await expect(page.getByText("本次揭示结果")).toBeVisible();
  await expect(page.getByText(password, { exact: true })).toBeVisible();
  await expect(page.getByText(/今日剩余 \d+ 次/u)).toBeVisible();

  await page.getByRole("button", { name: "从页面清除" }).click();
  await expect(page.getByText("本次揭示结果")).toHaveCount(0);
  await expect(page.getByText(password, { exact: true })).toHaveCount(0);
  expectNoBrowserErrors(browserErrors);
});

test("Web 对未匹配指纹提交授权贡献并刷新为待验证候选", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const fingerprint = process.env.E2E_UNMATCHED_SHA256;
  const password = "Synthetic-Contribution-Password-2026!";
  if (!fingerprint) throw new Error("缺少未匹配指纹 E2E 数据");

  await loginSeededWeb(page);
  await searchManualFingerprint(page, fingerprint);
  await expect(page.getByText("暂无社区匹配")).toBeVisible();

  await page.getByLabel("解压密码").fill(password);
  await page.getByText("我确认自己拥有该压缩包，或已获明确授权进行恢复和贡献。", { exact: true }).click();
  await page.getByRole("button", { name: "提交网页待验证贡献" }).click();

  await expect(page.getByText("网页贡献已进入待验证池，需至少 4 名不同登录用户确认正确后进入总哈希池。", { exact: true })).toBeVisible();
  await expect(page.getByText("发现 1 条可见候选")).toBeVisible();
  await expect(page.getByText("待验证 1")).toBeVisible();
  await expect(page.locator("body")).not.toContainText(password);
  expectNoBrowserErrors(browserErrors);
});

test("Web 游客可提交授权贡献但只进入待验证池", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const fingerprint = "9".repeat(64);
  const password = "Synthetic-Guest-Contribution-2026!";

  await page.goto("/");
  await searchManualFingerprint(page, fingerprint);
  await expect(page.getByText("暂无社区匹配")).toBeVisible();

  await page.getByLabel("解压密码").fill(password);
  await page.getByText("我确认自己拥有该压缩包，或已获明确授权进行恢复和贡献。", { exact: true }).click();
  await page.getByRole("button", { name: "以游客身份提交待验证贡献" }).click();

  await expect(page.getByText("游客贡献已进入待验证池，需至少 4 名不同登录用户确认正确后进入总哈希池。", { exact: true })).toBeVisible();
  await expect(page.getByText("待验证 1")).toBeVisible();
  await expect(page.locator("body")).not.toContainText(password);
  expectNoBrowserErrors(browserErrors);
});

test("Web 从候选结果进入举报并显示本人案件时间线", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const fingerprint = process.env.E2E_VERIFIED_SHA256;
  if (!fingerprint) throw new Error("缺少已验证候选 E2E 数据");

  await loginSeededWeb(page);
  await searchManualFingerprint(page, fingerprint);
  await expect(page.getByRole("link", { name: "举报候选" })).toBeVisible();
  await page.getByRole("link", { name: "举报候选" }).click();

  await expect(page).toHaveURL(/\/trust-cases\?kind=report&candidate_id=[^&]+/u);
  await expect(page.getByRole("heading", { name: "举报与申诉" })).toBeVisible();
  await expect(page.getByLabel("候选 ID")).not.toHaveValue("");
  await page.getByLabel("说明").fill("合成测试：候选内容与本地验证结果不一致。");
  await page.locator("form button[type=submit]").click();

  await expect(page.getByText("举报已提交，感谢你帮助维护内容质量。", { exact: true })).toBeVisible();
  const submittedCase = page.getByRole("article").filter({ hasText: "候选内容不准确" });
  await expect(submittedCase.getByText("候选内容不准确", { exact: true })).toBeVisible();
  await expect(submittedCase.getByText("待处理", { exact: true })).toBeVisible();
  expectNoBrowserErrors(browserErrors);
});
