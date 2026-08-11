import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunityModerationPage from "./CommunityModerationPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({
    accessToken: "synthetic-admin-token",
  }),
}));

vi.mock("../services/communityModeration", () => ({
  createCommunityModerationKey: vi.fn(),
  listCommunityReports: vi.fn(),
  moderateCommunityPost: vi.fn(),
  resolveCommunityReport: vi.fn(),
}));

describe("CommunityModerationPage", () => {
  it("renders the community governance workbench without exposing credentials", async () => {
    const html = await renderToString(createSSRApp(CommunityModerationPage));

    expect(html).toContain("社区举报与主题审核");
    expect(html).toContain("举报队列");
    expect(html).toContain("请选择左侧举报查看详情并执行审核");
    expect(html).not.toContain("synthetic-admin-token");
  });
});
