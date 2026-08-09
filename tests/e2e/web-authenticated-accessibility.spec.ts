import { expect, test } from "@playwright/test";
import { exerciseSkipLink } from "./support/accessibility";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import {
  expectNoSeriousAccessibilityViolations,
  expectPageVisualBaseline,
} from "./support/visual_assertions";
import { bootstrapSeededWebSession, requiredWebFixture } from "./support/web_session";

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
  await expectPageVisualBaseline(page, testInfo, {
    name: "web-security-desktop",
    criticalRegions: [
      page.getByRole("heading", { name: "账号与隐私中心" }),
      page.getByRole("tablist"),
      page.getByText("基础资料", { exact: true }),
    ],
  });
  await expectNoSeriousAccessibilityViolations(page);
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
  await expectPageVisualBaseline(page, testInfo, {
    name: "web-privacy-mobile",
    criticalRegions: [
      page.getByRole("heading", { name: "隐私与授权中心" }),
      page.getByText("授权声明", { exact: true }),
      page.getByRole("heading", { name: "个人数据导出" }),
    ],
  });
  await expectNoSeriousAccessibilityViolations(page);
  expectNoBrowserErrors(browserErrors);
});
