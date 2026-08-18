import { expect, test } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import { loginWorkflowAdmin } from "./support/admin_session";

// 配置保存和告警处置会使用合成管理员会话，禁止写入截图与 Trace 制品。
test.use({ screenshot: "off", trace: "off" });

test("Admin 直接保存并重置系统配置与 SMTP 设置", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  await loginWorkflowAdmin(page);

  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "系统配置工作台" })).toBeVisible();
  await expect(page.getByText("直接保存设置，当前配置将立即生效；不提供版本历史、差异预览或回滚快照。", { exact: true })).toBeVisible();
  await expect(page.getByLabel("每日明文查看配额")).toBeVisible();
  await expect(page.getByRole("heading", { name: "SMTP 邮件投递" })).toBeVisible();
  await expect(page.locator("#smtp-host")).toBeVisible();
  await expect(page.locator("#smtp-port")).toBeVisible();
  await expect(page.locator("#smtp-password")).toHaveAttribute("type", "password");
  await expect(page.getByRole("button", { name: "保存 SMTP 设置" })).toBeVisible();
  await expect(page.getByRole("button", { name: "重置 SMTP 编辑" })).toBeVisible();

  const dailyQuota = page.getByLabel("每日明文查看配额");
  const initialQuota = await dailyQuota.inputValue();
  const savedQuota = initialQuota === "21" ? "22" : "21";
  await dailyQuota.fill(savedQuota);
  await page.getByRole("button", { name: "保存设置", exact: true }).click();
  await expect(page.getByText("系统设置已直接保存并立即生效。", { exact: true })).toBeVisible();

  await dailyQuota.fill(savedQuota === "21" ? "23" : "22");
  await page.getByRole("button", { name: "重置当前编辑", exact: true }).click();
  await expect(dailyQuota).toHaveValue(savedQuota);
  await expect(page.getByText("已恢复到当前已保存的系统设置。", { exact: true })).toBeVisible();

  const smtpHost = page.locator("#smtp-host");
  const savedSmtpHost = await smtpHost.inputValue();
  await smtpHost.fill("smtp-reset.synthetic.example.com");
  await page.getByRole("button", { name: "重置 SMTP 编辑" }).click();
  await expect(smtpHost).toHaveValue(savedSmtpHost);
  await expect(page.getByText("已恢复到当前已保存的 SMTP 设置。", { exact: true })).toBeVisible();

  await expect(page.getByText("不可变版本历史", { exact: true })).toHaveCount(0);
  await expect(page.getByText("版本差异预览", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /发布|回滚/u })).toHaveCount(0);
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
