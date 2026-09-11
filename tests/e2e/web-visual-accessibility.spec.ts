import { expect, test } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import {
  expectGradientControlContrast,
  expectNoSeriousAccessibilityViolations,
  expectPageVisualBaseline,
} from "./support/visual_assertions";
import { dismissAllWebAnnouncements } from "./support/web_announcements";

test("Web 主题开关保留主题、ARIA 状态与原生键盘操作", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  await page.goto("/");
  await page.evaluate(() => {
    window.localStorage.setItem("pd-theme", "light");
  });
  await page.reload();
  await dismissAllWebAnnouncements(page);

  const themeToggle = page.getByRole("switch", { name: "切换主题" });
  await expect(themeToggle).toHaveAttribute("aria-checked", "false");
  await themeToggle.focus();
  await page.keyboard.press("Enter");
  await expect(themeToggle).toHaveAttribute("aria-checked", "true");
  await expect.poll(() => page.evaluate(() => window.localStorage.getItem("pd-theme"))).toBe("dark");
  await expect.poll(() => page.evaluate(() => document.documentElement.style.colorScheme)).toBe("dark");

  await page.reload();
  await expect(themeToggle).toHaveAttribute("aria-checked", "true");
  await themeToggle.focus();
  await page.keyboard.press("Space");
  await expect(themeToggle).toHaveAttribute("aria-checked", "false");
  await expect.poll(() => page.evaluate(() => window.localStorage.getItem("pd-theme"))).toBe("light");
  expectNoBrowserErrors(browserErrors);
});

test("Web 登录页形成桌面视觉、键盘顺序与错误提示门禁", async ({ page }, testInfo) => {
  const browserErrors = observeBrowserErrors(page);
  await page.goto("/login");
  await dismissAllWebAnnouncements(page);

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
  await expect(page.getByRole("checkbox", { name: "记住登录账号" })).toBeFocused();
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

test("Web 深色渐变按钮在交互状态保持白色文字对比度", async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem("pd-theme", "dark"));
  await page.goto("/login");
  await dismissAllWebAnnouncements(page);
  const button = page.getByRole("button", { name: "登录", exact: true });
  await expect(button).toBeVisible();
  await expect(page.locator("html")).toHaveClass(/dark/u);
  await expectGradientControlContrast(button, "Web dark default");
  await button.hover();
  await expect.poll(async () => {
    const filter = await button.evaluate((element) => getComputedStyle(element).filter);
    return Number(/brightness\(([\d.]+)\)/u.exec(filter)?.[1] ?? 0);
  }).toBeGreaterThanOrEqual(1.08);
  await expectGradientControlContrast(button, "Web dark hover");
  await page.mouse.move(0, 0);
  await page.getByRole("checkbox", { name: "记住登录账号" }).focus();
  await page.keyboard.press("Tab");
  await expect(button).toBeFocused();
  await expect.poll(() => button.evaluate((element) => element.matches(":focus-visible"))).toBe(true);
  await expectGradientControlContrast(button, "Web dark focus-visible");
  await button.evaluate((element) => {
    (element as HTMLButtonElement).disabled = true;
  });
  await expect.poll(() => button.evaluate((element) => getComputedStyle(element).filter)).toMatch(/^none$/u);
  await expectGradientControlContrast(button, "Web dark disabled");
});

test.describe("Web 移动端视觉门禁", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("Web 首页移动视口保持关键内容可见且无页面级溢出", async ({ page }, testInfo) => {
    const browserErrors = observeBrowserErrors(page);
    await page.goto("/");
    await dismissAllWebAnnouncements(page);
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
