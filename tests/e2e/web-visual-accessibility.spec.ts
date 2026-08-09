import { expect, test } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import { expectNoSeriousAccessibilityViolations, expectPageVisualBaseline } from "./support/visual_assertions";

test("Web 登录页形成桌面视觉、键盘顺序与错误提示门禁", async ({ page }, testInfo) => {
  const browserErrors = observeBrowserErrors(page);
  await page.goto("/login");

  const loginInput = page.getByLabel("用户名或邮箱");
  const passwordInput = page.getByLabel("账号密码");
  const totpInput = page.getByLabel("TOTP 验证码（已启用时填写）");
  const submitButton = page.getByRole("button", { name: "登录", exact: true });
  await expectPageVisualBaseline(page, testInfo, {
    name: "web-login-desktop",
    criticalRegions: [page.getByRole("banner"), page.getByRole("heading", { name: "登录密码侦探社" }), submitButton],
  });

  await loginInput.focus();
  await expect(loginInput).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(passwordInput).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(totpInput).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(submitButton).toBeFocused();

  await loginInput.fill("synthetic_visual_invalid");
  await passwordInput.fill("Synthetic-Visual-Invalid-2026");
  await submitButton.click();
  const alert = page.getByRole("alert");
  await expect(alert).toBeVisible();
  await expect(alert).not.toBeEmpty();
  await expect(alert).toHaveAttribute("aria-live", "assertive");
  browserErrors.length = 0;
  await expectNoSeriousAccessibilityViolations(page);
  expectNoBrowserErrors(browserErrors);
});

test.describe("Web 移动端视觉门禁", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("Web 首页移动视口保持关键内容可见且无页面级溢出", async ({ page }, testInfo) => {
    const browserErrors = observeBrowserErrors(page);
    await page.goto("/");
    await expectPageVisualBaseline(page, testInfo, {
      name: "web-home-mobile",
      criticalRegions: [
        page.getByRole("banner"),
        page.getByRole("heading", { name: "计算压缩包指纹，精确寻找可信候选。" }),
        page.getByRole("contentinfo"),
      ],
      minimumScreenshotBytes: 8_000,
    });
    await expectNoSeriousAccessibilityViolations(page);
    expectNoBrowserErrors(browserErrors);
  });
});
