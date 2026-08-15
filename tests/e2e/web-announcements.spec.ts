import { expect, test } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import {
  clearWebAnnouncementDismissals,
  focusWebAnnouncement,
  isolateWebAnnouncement,
  publishWebAnnouncementForBrowser,
} from "./support/web_announcements";

test.use({ screenshot: "off", trace: "off" });

test("Web 公告弹窗展示倒计时并按后台配置自动关闭", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const title = `Web 自动关闭验收-${Date.now()}`;
  const announcement = await publishWebAnnouncementForBrowser(page.request, title, 1);
  await clearWebAnnouncementDismissals(page);
  await isolateWebAnnouncement(page, title);
  await page.goto("/");

  const popup = page.getByRole("complementary", { name: "网站公告" });
  await expect(popup).toBeVisible();
  await expect(popup).toContainText(title);
  await expect(popup).toContainText("将在 1 秒后自动关闭");
  await expect(popup).toBeHidden({ timeout: 5_000 });

  const publicResponse = await page.request.get(
    "http://127.0.0.1:18100/api/v1/web/announcements?limit=10",
  );
  expect(publicResponse.status()).toBe(200);
  const publicBody = (await publicResponse.json()) as {
    items: Array<{ id: string; title: string; auto_close_seconds: number | null }>;
  };
  expect(publicBody.items).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        id: announcement.id,
        title,
        auto_close_seconds: 1,
      }),
    ]),
  );
  expectNoBrowserErrors(browserErrors);
});

test("Web 公告手动关闭后在当前浏览器上下文保持关闭", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const title = `Web 手动关闭验收-${Date.now()}`;
  await publishWebAnnouncementForBrowser(page.request, title, null);
  await clearWebAnnouncementDismissals(page);
  await isolateWebAnnouncement(page, title);
  await page.goto("/");

  const popup = page.getByRole("complementary", { name: "网站公告" });
  await focusWebAnnouncement(page, title);
  await expect(popup).toBeVisible();
  await expect(popup).toContainText(title);
  await expect(popup).not.toContainText("秒后自动关闭");
  await popup.getByRole("button", { name: "关闭公告" }).click();
  await expect(popup).toBeHidden();

  await page.reload();
  await expect(
    page.getByRole("complementary", { name: "网站公告" }).getByText(title, { exact: true }),
  ).toHaveCount(0);
  expectNoBrowserErrors(browserErrors);
});


test("Web 公告图片真实加载并点击图片打开后台配置外链", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  const title = `Web 图片点击验收-${Date.now()}`;
  const actionUrl = "http://127.0.0.1:15173/announcement-target";
  await publishWebAnnouncementForBrowser(page.request, title, null, {
    withImage: true,
    actionLabel: "打开验收页",
    actionUrl,
  });
  await clearWebAnnouncementDismissals(page);
  await isolateWebAnnouncement(page, title);
  await page.goto("/");

  const popup = page.getByRole("complementary", { name: "网站公告" });
  await focusWebAnnouncement(page, title);
  await expect(popup).toBeVisible();
  await expect(popup).toContainText(title);
  const image = popup.getByAltText(title);
  await expect(image).toBeVisible();
  await expect(image).toHaveAttribute("src", /\/api\/v1\/web\/announcements\/assets\//u);
  await expect.poll(async () => image.evaluate((element) => (element as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);

  const [targetPage] = await Promise.all([
    page.waitForEvent("popup"),
    image.click(),
  ]);
  await targetPage.waitForLoadState("domcontentloaded");
  expect(targetPage.url()).toBe(actionUrl);
  await targetPage.close();
  await popup.getByRole("button", { name: "关闭公告" }).click();
  await expect(popup).toBeHidden();
  expectNoBrowserErrors(browserErrors);
});
