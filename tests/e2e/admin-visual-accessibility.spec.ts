import { expect, test } from "@playwright/test";
import { loginWorkflowAdmin } from "./support/admin_session";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import { expectNoSeriousAccessibilityViolations, expectPageVisualBaseline } from "./support/visual_assertions";

test("Admin 仪表盘形成桌面视觉与严重 WCAG 门禁", async ({ page }, testInfo) => {
  const browserErrors = observeBrowserErrors(page);
  await loginWorkflowAdmin(page);
  await expectPageVisualBaseline(page, testInfo, {
    name: "admin-dashboard-desktop",
    criticalRegions: [
      page.getByRole("banner"),
      page.getByRole("navigation", { name: "管理导航" }),
      page.getByRole("heading", { name: "真实指标仪表盘" }),
    ],
    minimumScreenshotBytes: 8_000,
  });
  await expectNoSeriousAccessibilityViolations(page);
  expectNoBrowserErrors(browserErrors);
});

test.describe("Admin 移动端视觉与键盘门禁", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("Admin 登录页移动视口无溢出且表单焦点顺序稳定", async ({ page }, testInfo) => {
    const browserErrors = observeBrowserErrors(page);
    await page.goto("/login");
    const loginInput = page.getByLabel("用户名或邮箱");
    const passwordInput = page.getByLabel("密码", { exact: true });
    const totpInput = page.getByLabel("动态验证码（已启用时必填）");
    const submitButton = page.getByRole("button", { name: "登录管理端" });

    await expectPageVisualBaseline(page, testInfo, {
      name: "admin-login-mobile",
      criticalRegions: [page.getByRole("banner"), page.getByRole("heading", { name: "管理端登录" }), submitButton],
    });
    await loginInput.focus();
    await page.keyboard.press("Tab");
    await expect(passwordInput).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(totpInput).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(submitButton).toBeFocused();
    await expectNoSeriousAccessibilityViolations(page);
    expectNoBrowserErrors(browserErrors);
  });
});
