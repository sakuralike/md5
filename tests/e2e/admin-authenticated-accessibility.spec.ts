import { expect, test } from "@playwright/test";
import { exerciseSkipLink } from "./support/accessibility";
import { bootstrapSeededAdminSession, requiredAdminFixture } from "./support/admin_session";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import {
  expectNoSeriousAccessibilityViolations,
  expectPageVisualBaseline,
} from "./support/visual_assertions";

async function expectPageBaseline(
  page: Parameters<typeof expectPageVisualBaseline>[0],
  testInfo: Parameters<typeof expectPageVisualBaseline>[1],
  options: Parameters<typeof expectPageVisualBaseline>[2],
): Promise<void> {
  await expectPageVisualBaseline(page, testInfo, options);
  await expectNoSeriousAccessibilityViolations(page);
}

test("Admin 用户治理与角色审批覆盖桌面、移动、跳转主内容及 WCAG 基线", async ({ page }, testInfo) => {
  const browserErrors = observeBrowserErrors(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await bootstrapSeededAdminSession(
    page,
    requiredAdminFixture("E2E_ADMIN_ACCESSIBILITY_REFRESH_TOKEN"),
  );
  await page.goto("/users");
  await expect(page.getByRole("heading", { name: "用户审批工作台" })).toBeVisible();

  await exerciseSkipLink(page);
  await expectPageBaseline(page, testInfo, {
    name: "admin-user-governance-desktop",
    criticalRegions: [
      page.getByRole("heading", { name: "用户审批工作台" }),
      page.getByRole("navigation", { name: "管理导航" }),
      page.getByRole("table"),
    ],
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/role-changes");
  await expect(page.getByRole("heading", { name: "角色变更审批工作台" })).toBeVisible();
  await expectPageBaseline(page, testInfo, {
    name: "admin-role-changes-mobile",
    criticalRegions: [
      page.getByRole("heading", { name: "角色变更审批工作台" }),
      page.getByRole("heading", { name: "角色变更请求", exact: true }),
    ],
  });
  expectNoBrowserErrors(browserErrors);
});

test("Admin 候选、案件、配置与风险页面覆盖桌面和移动端无障碍门禁", async ({ page }, testInfo) => {
  const browserErrors = observeBrowserErrors(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await bootstrapSeededAdminSession(
    page,
    requiredAdminFixture("E2E_ADMIN_ACCESSIBILITY_OPERATIONS_REFRESH_TOKEN"),
  );

  await page.goto("/candidates");
  await expect(page.getByRole("heading", { name: "候选审核" })).toBeVisible();
  await exerciseSkipLink(page);
  await expectPageBaseline(page, testInfo, {
    name: "admin-candidates-desktop",
    criticalRegions: [
      page.getByRole("heading", { name: "候选审核" }),
      page.getByRole("form", { name: "候选筛选" }),
      page.getByRole("heading", { name: "审核队列" }),
    ],
  });

  await page.goto("/trust-cases");
  await expect(page.getByRole("heading", { name: "举报与申诉" })).toBeVisible();
  await expectPageBaseline(page, testInfo, {
    name: "admin-trust-cases-desktop",
    criticalRegions: [
      page.getByRole("heading", { name: "举报与申诉" }),
      page.getByLabel("案件类型筛选"),
      page.getByLabel("案件状态筛选"),
    ],
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "系统配置治理工作台" })).toBeVisible();
  await expectPageBaseline(page, testInfo, {
    name: "admin-settings-mobile",
    criticalRegions: [
      page.getByRole("heading", { name: "系统配置治理工作台" }),
      page.getByRole("heading", { name: "配置草稿编辑器" }),
      page.getByLabel("配置变更原因码"),
    ],
  });

  await page.goto("/risk-alerts");
  await expect(page.getByRole("heading", { name: "风险告警" })).toBeVisible();
  await expectPageBaseline(page, testInfo, {
    name: "admin-risk-alerts-mobile",
    criticalRegions: [
      page.getByRole("heading", { name: "风险告警" }),
      page.getByLabel("风险告警状态筛选"),
      page.getByLabel("风险告警负责人筛选"),
    ],
  });
  expectNoBrowserErrors(browserErrors);
});
