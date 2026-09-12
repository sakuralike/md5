import { expect, test } from "@playwright/test";
import { expectNoBrowserErrors, observeBrowserErrors } from "./support/browser_assertions";
import { loginWorkflowAdmin } from "./support/admin_session";

test.use({ screenshot: "off", trace: "off" });
test.setTimeout(60_000);

test("Admin SEO 工作台支持直接保存和重置当前编辑", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  await loginWorkflowAdmin(page);
  await page.goto("/settings#seo-settings");

  const seoSection = page.locator("#seo-settings");
  await expect(seoSection.getByRole("heading", { name: "SEO 设置" })).toBeVisible();
  await expect(seoSection.getByText("直接保存", { exact: true })).toBeVisible();

  const homeTitle = page.locator("#seo-home-title");
  const keywords = page.locator("#seo-keywords");
  const description = page.locator("#seo-description");
  const original = {
    homeTitle: await homeTitle.inputValue(),
    keywords: await keywords.inputValue(),
    description: await description.inputValue(),
  };

  try {
    await homeTitle.fill("合成 SEO 临时标题");
    await keywords.fill("合成关键词, SEO, SEO");
    await description.fill("合成 SEO 保存验收描述，不包含真实站点信息。");
    await seoSection.getByRole("button", { name: "重置 SEO 编辑", exact: true }).click();
    await expect(homeTitle).toHaveValue(original.homeTitle);
    await expect(keywords).toHaveValue(original.keywords);
    await expect(description).toHaveValue(original.description);
    await expect(seoSection.getByText("已恢复到当前已保存的 SEO 设置。", { exact: true })).toBeVisible();

    await homeTitle.fill("合成 SEO 已保存标题");
    await keywords.fill("合成关键词, SEO, SEO");
    await description.fill("合成 SEO 保存验收描述，不包含真实站点信息。");
    await seoSection.getByRole("button", { name: "保存 SEO 设置", exact: true }).click();
    await expect(seoSection.getByText("SEO 设置已直接保存并立即生效。", { exact: true })).toBeVisible();
    await expect(homeTitle).toHaveValue("合成 SEO 已保存标题");
    await expect(keywords).toHaveValue("合成关键词, SEO");
  } finally {
    await homeTitle.fill(original.homeTitle);
    await keywords.fill(original.keywords);
    await description.fill(original.description);
    await seoSection.getByRole("button", { name: "保存 SEO 设置", exact: true }).click();
    await expect(seoSection.getByText("SEO 设置已直接保存并立即生效。", { exact: true })).toBeVisible();
  }

  expectNoBrowserErrors(browserErrors);
});
