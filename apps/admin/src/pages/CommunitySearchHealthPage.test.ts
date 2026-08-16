import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunitySearchHealthPage from "./CommunitySearchHealthPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/communitySearch", () => ({
  getCommunitySearchHealth: vi.fn(),
}));

describe("CommunitySearchHealthPage", () => {
  it("renders search provider health without a result browser", async () => {
    const html = await renderToString(createSSRApp(CommunitySearchHealthPage));

    expect(html).toContain("社区搜索健康");
    expect(html).not.toContain("搜索结果");
  });
});
