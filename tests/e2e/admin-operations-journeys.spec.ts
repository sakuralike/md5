import { expect, test } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import { loginWorkflowAdmin } from "./support/admin_session";
import { currentTotp } from "./support/totp";

// 配置发布和告警处置会短暂输入合成管理员凭据，禁止写入截图与 Trace 制品。
test.use({ screenshot: "off", trace: "off" });

async function fillSettingsReauthentication(
  page: import("@playwright/test").Page,
  password: string,
  totpSecret: string,
): Promise<void> {
  await page.getByLabel("当前密码").fill(password);
  await page.getByLabel("TOTP 动态码").fill(currentTotp(totpSecret));
}

test("Admin 创建并发布配置版本，再从历史版本生成不可变回滚版本", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const admin = await loginWorkflowAdmin(page);

  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "系统配置治理工作台" })).toBeVisible();
  await expect(page.getByText("尚无配置版本，请创建首个草稿。")).toBeVisible();

  await page.getByLabel("每日明文查看配额").fill("21");
  await page.getByRole("button", { name: "创建不可变草稿" }).click();
  await expect(page.getByText(/不可变草稿 .* 已创建，可在差异确认后发布/u)).toBeVisible();
  await expect(page.getByRole("table").getByText("草稿", { exact: true })).toBeVisible();

  await fillSettingsReauthentication(page, admin.password, admin.totpSecret);
  await page.getByRole("button", { name: "发布选中草稿" }).click();
  await expect(page.getByText(/版本 .* 已发布并写入运行时配置投影/u)).toBeVisible();
  await expect(page.getByRole("table").getByText("当前生效", { exact: true })).toBeVisible();

  await page.getByLabel("每日明文查看配额").fill("22");
  await page.getByRole("button", { name: "创建不可变草稿" }).click();
  await expect(page.getByText(/不可变草稿 .* 已创建，可在差异确认后发布/u)).toBeVisible();
  await fillSettingsReauthentication(page, admin.password, admin.totpSecret);
  await page.getByRole("button", { name: "发布选中草稿" }).click();
  await expect(page.getByText(/版本 .* 已发布并写入运行时配置投影/u)).toBeVisible();

  const historicalRow = page.getByRole("row").filter({ hasText: "历史版本" });
  await expect(historicalRow).toHaveCount(1);
  await historicalRow.click();
  await expect(page.getByRole("button", { name: "回滚到选中历史版本" })).toBeEnabled();
  await expect(page.getByLabel("每日明文查看配额")).toHaveValue("21");

  await fillSettingsReauthentication(page, admin.password, admin.totpSecret);
  await page.getByRole("button", { name: "回滚到选中历史版本" }).click();
  await expect(page.getByText(/已从历史版本 .* 创建新的不可变回滚版本/u)).toBeVisible();
  await expect(page.getByLabel("每日明文查看配额")).toHaveValue("21");
  await expect(page.getByRole("row").filter({ hasText: "版本回滚" })).toContainText("当前生效");
  expectNoBrowserErrors(browserErrors);
});

test("Admin 指派风险告警、开始核查并确认处置", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  await loginWorkflowAdmin(page);
  const candidateId = process.env.E2E_ADMIN_RISK_CANDIDATE_ID;
  const reviewerUsername = process.env.E2E_ADMIN_REVIEWER_USERNAME;
  if (!candidateId || !reviewerUsername) throw new Error("缺少风险告警 E2E 合成数据配置");

  await page.goto("/risk-alerts");
  await expect(page.getByRole("heading", { name: "风险告警" })).toBeVisible();
  const detail = page.locator("article").filter({ hasText: candidateId });
  await expect(detail).toBeVisible();
  await expect(detail).toContainText("待响应");
  await expect(detail).toContainText("3");

  const assignmentPanel = detail.getByRole("heading", { name: "负责人指派" }).locator("..");
  await assignmentPanel.getByRole("combobox").click();
  await page.getByRole("option", { name: new RegExp(reviewerUsername, "u") }).click();
  await assignmentPanel.getByRole("textbox").fill("合成值班指派，不包含敏感标识");
  await assignmentPanel.getByRole("button", { name: "更新负责人" }).click();
  await expect(page.getByRole("status")).toContainText("告警负责人已更新");
  await expect(detail).toContainText(reviewerUsername);

  const actionPanel = detail.getByRole("heading", { name: "告警处置" }).locator("..");
  await actionPanel.getByRole("textbox").fill("已开始核查合成失败聚合事件");
  await actionPanel.getByRole("button", { name: "开始核查" }).click();
  await expect(page.getByRole("status")).toContainText("已完成“开始核查”");
  await expect(detail).toContainText("核查中");

  await actionPanel.getByRole("textbox").fill("合成告警已完成处置并确认恢复");
  await actionPanel.getByRole("button", { name: "确认已处置" }).click();
  await expect(page.getByRole("status")).toContainText("已完成“确认已处置”");
  await expect(detail).toContainText("已解决");
  await expect(detail).toContainText("合成告警已完成处置并确认恢复");
  await expect(detail.getByRole("heading", { name: "不可变告警时间线" }).locator("..")).toContainText(
    "risk_alert.transitioned",
  );
  expectNoBrowserErrors(browserErrors);
});
