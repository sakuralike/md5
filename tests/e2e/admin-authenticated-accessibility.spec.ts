import { expect, test } from "@playwright/test";
import { exerciseSkipLink } from "./support/accessibility";
import { bootstrapSeededAdminSession, requiredAdminFixture } from "./support/admin_session";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import {
  expectNoSeriousAccessibilityViolations,
  expectPageVisualBaseline,
} from "./support/visual_assertions";

test("Admin 用户治理与角色审批覆盖桌面、移动、跳转主内容及 WCAG 基线", async ({ page }, testInfo) => {
  const browserErrors = observeBrowserErrors(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await bootstrapSeededAdminSession(
    page,
    requiredAdminFixture("E2E_ADMIN_ACCESSIBILITY_REFRESH_TOKEN"),
  );
  await page.goto("/users");
  await expect(page.getByRole("heading", { name: "用户治理工作台" })).toBeVisible();

  await exerciseSkipLink(page);
  await expectPageVisualBaseline(page, testInfo, {
    name: "admin-user-governance-desktop",
    criticalRegions: [
      page.getByRole("heading", { name: "用户治理工作台" }),
      page.getByRole("navigation", { name: "管理导航" }),
      page.getByRole("table"),
    ],
  });
  await expectNoSeriousAccessibilityViolations(page);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/role-changes");
  await expect(page.getByRole("heading", { name: "角色变更审批工作台" })).toBeVisible();
  await expectPageVisualBaseline(page, testInfo, {
    name: "admin-role-changes-mobile",
    criticalRegions: [
      page.getByRole("heading", { name: "角色变更审批工作台" }),
      page.getByRole("heading", { name: "角色变更请求", exact: true }),
    ],
  });
  await expectNoSeriousAccessibilityViolations(page);
  expectNoBrowserErrors(browserErrors);
});
