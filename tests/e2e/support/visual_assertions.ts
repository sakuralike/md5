import AxeBuilder from "@axe-core/playwright";
import { expect, type Locator, type Page, type TestInfo } from "@playwright/test";

interface VisualBaselineOptions {
  name: string;
  criticalRegions: Locator[];
  minimumScreenshotBytes?: number;
}

interface AccessibilityViolationSummary {
  id: string;
  impact: string | null | undefined;
  help: string;
  nodes: Array<{
    target: unknown;
    html: string;
    failureSummary: string | undefined;
  }>;
}

export async function expectPageVisualBaseline(
  page: Page,
  testInfo: TestInfo,
  options: VisualBaselineOptions,
): Promise<void> {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.evaluate(async () => document.fonts.ready);

  const metrics = await page.evaluate(() => {
    const clientWidth = document.documentElement.clientWidth;
    const overflowingElements = Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .map((element) => {
        const box = element.getBoundingClientRect();
        return {
          tag: element.tagName.toLowerCase(),
          className: element.className,
          text: (element.textContent ?? "").trim().replace(/\s+/gu, " ").slice(0, 120),
          left: Math.round(box.left),
          right: Math.round(box.right),
          width: Math.round(box.width),
        };
      })
      .filter((element) => element.left < -1 || element.right > clientWidth + 1)
      .sort((left, right) => right.width - left.width)
      .slice(0, 10);
    return {
      clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      bodyBackground: getComputedStyle(document.body).backgroundColor,
      overflowingElements,
    };
  });
  expect(
    metrics.scrollWidth,
    `${options.name} 不应出现页面级横向溢出：${JSON.stringify(metrics.overflowingElements, null, 2)}`,
  ).toBeLessThanOrEqual(metrics.clientWidth + 1);
  expect(metrics.bodyBackground, `${options.name} 应具备可见页面背景`).not.toBe("rgba(0, 0, 0, 0)");

  for (const region of options.criticalRegions) {
    await expect(region).toBeVisible();
    const box = await region.boundingBox();
    expect(box, `${options.name} 关键区域必须存在布局边界`).not.toBeNull();
    if (!box) continue;
    expect(box.width, `${options.name} 关键区域宽度必须为正数`).toBeGreaterThan(0);
    expect(box.height, `${options.name} 关键区域高度必须为正数`).toBeGreaterThan(0);
    expect(box.x, `${options.name} 关键区域左侧不得溢出视口`).toBeGreaterThanOrEqual(-1);
    expect(box.x + box.width, `${options.name} 关键区域右侧不得溢出视口`).toBeLessThanOrEqual(metrics.clientWidth + 1);
  }

  const screenshot = await page.screenshot({ animations: "disabled", caret: "hide", fullPage: true });
  expect(screenshot.byteLength, `${options.name} 视觉快照不应为空白`).toBeGreaterThan(
    options.minimumScreenshotBytes ?? 5_000,
  );
  await testInfo.attach(`${options.name}.png`, { body: screenshot, contentType: "image/png" });
}

export async function expectNoSeriousAccessibilityViolations(page: Page): Promise<void> {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const blocking: AccessibilityViolationSummary[] = result.violations
    .filter((violation) => violation.impact === "critical" || violation.impact === "serious")
    .map((violation) => ({
      id: violation.id,
      impact: violation.impact,
      help: violation.help,
      nodes: violation.nodes.map((node) => ({
        target: node.target,
        html: node.html,
        failureSummary: node.failureSummary,
      })),
    }));
  expect(blocking, `发现严重 WCAG 违规：${JSON.stringify(blocking, null, 2)}`).toEqual([]);
}
