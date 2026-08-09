import { expect, test } from "@playwright/test";
import { loginWorkflowAdmin } from "./support/admin_session";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";

// 管理处置请求包含短期合成凭据和案件数据，关闭截图与网络 Trace。
test.use({ screenshot: "off", trace: "off" });

test("Admin 审核待验证候选并写入状态时间线", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const fingerprint = process.env.E2E_ADMIN_PENDING_SHA256;
  if (!fingerprint) throw new Error("缺少待审核候选 E2E 数据");

  await loginWorkflowAdmin(page);
  await page.goto("/candidates");
  await expect(page.getByRole("heading", { name: "候选审核" })).toBeVisible();
  await page.getByLabel("候选 / 存档 / 指纹").fill(fingerprint);
  await page.getByRole("button", { name: "查询", exact: true }).click();

  await expect(page.getByText(`sha256:${fingerprint}`, { exact: true }).first()).toBeVisible();
  await page
    .getByLabel("审核说明（进入状态时间线，不写入审计详情）")
    .fill("合成测试：独立证据满足人工审核要求。");
  await page.getByRole("button", { name: "审核通过" }).click();

  await expect(page.getByRole("status")).toContainText("已完成“审核通过”");
  await expect(page.getByText("待验证 → 已验证", { exact: true })).toBeVisible();
  await expect(
    page.getByText("manual.verified_by_review · 合成测试：独立证据满足人工审核要求。", {
      exact: true,
    }),
  ).toBeVisible();
  expectNoBrowserErrors(browserErrors);
});

test("Admin 指派、处理并解决候选举报，原子隔离关联候选", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const caseId = process.env.E2E_ADMIN_CASE_ID;
  const candidateFingerprint = process.env.E2E_ADMIN_CASE_SHA256;
  if (!caseId || !candidateFingerprint) throw new Error("缺少举报案件 E2E 数据");

  const admin = await loginWorkflowAdmin(page);
  await page.goto("/trust-cases");
  await expect(page.getByRole("heading", { name: "举报与申诉" })).toBeVisible();
  await page.getByLabel("搜索").fill(caseId);
  const filterButton = page.getByRole("button", { name: "筛选" });
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        new URL(response.url()).pathname.endsWith(`/admin/trust-cases/${caseId}`),
    ),
    filterButton.click(),
  ]);
  await expect(page.getByRole("article")).toContainText("合成测试：候选内容需要管理员复核。");

  const assigneeInput = page.getByLabel("负责人用户 ID");
  await assigneeInput.fill(admin.id);
  await expect(assigneeInput).toHaveValue(admin.id);
  await page
    .getByLabel("处理说明（不要粘贴密码、令牌或个人敏感信息）")
    .fill("合成测试：由当前值班管理员接手。");
  await expect(assigneeInput).toHaveValue(admin.id);
  await page.getByRole("button", { name: "指派负责人" }).click();
  await expect(page.getByRole("status")).toContainText("已更新案件负责人");
  await expect(page.getByRole("article")).toContainText(admin.id);

  await page.getByRole("button", { name: "开始处理" }).click();
  await expect(page.getByRole("status")).toContainText("已完成“开始处理”");
  await expect(page.getByRole("article").getByText("处理中", { exact: true })).toBeVisible();

  const resolutionNote = "合成测试：确认举报成立并隔离关联候选。";
  await page
    .getByLabel("处理说明（不要粘贴密码、令牌或个人敏感信息）")
    .fill(resolutionNote);
  await page.getByRole("button", { name: "确认并已处置" }).click();

  await expect(page.getByRole("status")).toContainText("已完成“确认并已处置”");
  await expect(page.getByRole("article").getByText("已解决", { exact: true })).toBeVisible();
  await expect(page.getByText("admin.action_taken", { exact: true })).toBeVisible();
  await expect(page.getByRole("article").getByText(resolutionNote, { exact: true }).first()).toBeVisible();

  await page.goto("/candidates");
  await page.getByLabel("候选 / 存档 / 指纹").fill(candidateFingerprint);
  await page.getByRole("button", { name: "查询", exact: true }).click();
  await expect(page.getByText(`sha256:${candidateFingerprint}`, { exact: true }).first()).toBeVisible();
  await expect(page.getByText("已验证 → 隔离中", { exact: true })).toBeVisible();
  expectNoBrowserErrors(browserErrors);
});
