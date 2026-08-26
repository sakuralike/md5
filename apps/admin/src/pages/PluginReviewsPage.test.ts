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
  getPluginReviewMetrics: vi.fn().mockResolvedValue({
    generated_at: "2026-08-26T00:00:00Z",
    review_run_counts: {},
    version_status_counts: {},
    dynamic_task_counts: {},
    runner_status_counts: {},
    runner_capacity_by_architecture: {},
    runner_active_by_architecture: {},
    queue_depth_by_architecture: {},
    oldest_queued_seconds: null,
    average_review_seconds: null,
    p95_review_seconds: null,
    completed_last_24_hours: 0,
    install_events_last_24_hours: 0,
  }),
  getPluginReview: vi.fn(), approvePluginVersion: vi.fn(), rejectPluginVersion: vi.fn(),
  publishPluginVersion: vi.fn(), yankPluginVersion: vi.fn(), revokePluginVersion: vi.fn(),
  resolvePluginReport: vi.fn(), rerunPluginStaticReview: vi.fn(),
}));

describe("PluginReviewsPage", () => {
  it("renders the controlled plugin review workbench", async () => {
    const html = await renderToString(createSSRApp(PluginReviewsPage));
    expect(html).toContain("插件商城管理");
    expect(html).toContain("审核队列");
    expect(html).toContain("版本审核详情");
    expect(html).toContain("用户举报");
    expect(html).toContain("Windows 动态审核执行器");
    expect(html).not.toContain("synthetic-admin-token");
  });
});
