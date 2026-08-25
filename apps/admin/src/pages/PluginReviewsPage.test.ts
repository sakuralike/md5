import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import PluginReviewsPage from "./PluginReviewsPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/pluginReviews", () => ({
  listPluginReviews: vi.fn().mockResolvedValue({ items: [], page: 1, page_size: 100, total: 0 }),
  listPluginReports: vi.fn().mockResolvedValue({ items: [], page: 1, page_size: 100, total: 0 }),
  getPluginReview: vi.fn(), approvePluginVersion: vi.fn(), rejectPluginVersion: vi.fn(),
  publishPluginVersion: vi.fn(), yankPluginVersion: vi.fn(), revokePluginVersion: vi.fn(),
  resolvePluginReport: vi.fn(),
}));

describe("PluginReviewsPage", () => {
  it("renders the controlled plugin review workbench", async () => {
    const html = await renderToString(createSSRApp(PluginReviewsPage));
    expect(html).toContain("插件审核工作台");
    expect(html).toContain("审核队列");
    expect(html).toContain("版本审核详情");
    expect(html).toContain("用户举报");
    expect(html).not.toContain("synthetic-admin-token");
  });
});
