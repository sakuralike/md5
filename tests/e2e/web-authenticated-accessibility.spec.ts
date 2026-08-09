import { expect, test } from "@playwright/test";
import { exerciseSkipLink } from "./support/accessibility";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import {
  expectNoSeriousAccessibilityViolations,
  expectPageVisualBaseline,
} from "./support/visual_assertions";
import { bootstrapSeededWebSession, requiredWebFixture } from "./support/web_session";

async function expectPageBaseline(
  page: Parameters<typeof expectPageVisualBaseline>[0],
  testInfo: Parameters<typeof expectPageVisualBaseline>[1],
  options: Parameters<typeof expectPageVisualBaseline>[2],
): Promise<void> {
  await expectPageVisualBaseline(page, testInfo, options);
  await expectNoSeriousAccessibilityViolations(page);
}

test("Web 账号安全桌面端具备跳转主内容、视觉与 WCAG 基线", async ({ page }, testInfo) => {
  const browserErrors = observeBrowserErrors(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await bootstrapSeededWebSession(
    page,
    requiredWebFixture("E2E_WEB_ACCESSIBILITY_SECURITY_REFRESH_TOKEN"),
  );
  await page.goto("/security");
  await expect(page.getByRole("heading", { name: "账号与隐私中心" })).toBeVisible();

  await exerciseSkipLink(page);
  await expectPageBaseline(page, testInfo, {
    name: "web-security-desktop",
    criticalRegions: [
      page.getByRole("heading", { name: "账号与隐私中心" }),
      page.getByRole("tablist"),
      page.getByText("基础资料", { exact: true }),
    ],
  });
  expectNoBrowserErrors(browserErrors);
});

test("Web 隐私中心移动端保持响应式与 WCAG 基线", async ({ page }, testInfo) => {
  const browserErrors = observeBrowserErrors(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await bootstrapSeededWebSession(
    page,
    requiredWebFixture("E2E_WEB_ACCESSIBILITY_PRIVACY_REFRESH_TOKEN"),
  );
  await page.goto("/account/privacy");
  await expect(page.getByRole("heading", { name: "隐私与授权中心" })).toBeVisible();

  await exerciseSkipLink(page);
  await expectPageBaseline(page, testInfo, {
    name: "web-privacy-mobile",
    criticalRegions: [
      page.getByRole("heading", { name: "隐私与授权中心" }),
      page.getByText("授权声明", { exact: true }),
      page.getByRole("heading", { name: "个人数据导出" }),
    ],
  });
  expectNoBrowserErrors(browserErrors);
});

test("Web 贡献、信誉、案件与活动页面覆盖桌面和移动端无障碍门禁", async ({ page }, testInfo) => {
  const browserErrors = observeBrowserErrors(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await bootstrapSeededWebSession(
    page,
    requiredWebFixture("E2E_WEB_ACCESSIBILITY_WORKFLOW_REFRESH_TOKEN"),
  );

  await page.goto("/submissions");
  await expect(page.getByRole("heading", { name: "我的贡献" })).toBeVisible();
  await exerciseSkipLink(page);
  await expectPageBaseline(page, testInfo, {
    name: "web-submissions-desktop",
    criticalRegions: [
      page.getByRole("heading", { name: "我的贡献" }),
      page.getByText("查看授权贡献证据及当前候选状态。此页面不会返回或缓存候选密码。"),
    ],
  });

  await page.goto("/reputation");
  await expect(page.getByRole("heading", { name: "积分与信誉" })).toBeVisible();
  await expectPageBaseline(page, testInfo, {
    name: "web-reputation-desktop",
    criticalRegions: [
      page.getByRole("heading", { name: "积分与信誉" }),
      page.getByRole("button", { name: "刷新" }),
      page.getByRole("heading", { name: "积分流水" }),
    ],
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/trust-cases");
  await expect(page.getByRole("heading", { name: "举报与申诉" })).toBeVisible();
  await expectPageBaseline(page, testInfo, {
    name: "web-trust-cases-mobile",
    criticalRegions: [
      page.getByRole("heading", { name: "举报与申诉" }),
      page.getByRole("button", { name: "提交举报", exact: true }).first(),
      page.getByRole("heading", { name: "我的案件" }),
    ],
  });

  await page.goto("/account/activity");
  await expect(page.getByRole("heading", { name: "账号活动记录" })).toBeVisible();
  await expectPageBaseline(page, testInfo, {
    name: "web-account-activity-mobile",
    criticalRegions: [
      page.getByRole("heading", { name: "账号活动记录" }),
      page.getByRole("heading", { name: "密码揭示历史" }),
      page.getByRole("button", { name: "刷新" }),
    ],
  });
  expectNoBrowserErrors(browserErrors);
});
