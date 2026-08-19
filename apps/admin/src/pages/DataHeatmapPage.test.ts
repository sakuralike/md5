import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import DataHeatmapPage from "./DataHeatmapPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/analytics", () => ({
  getCommunityHeatmap: vi.fn(),
}));

describe("DataHeatmapPage", () => {
  it("renders the privacy-bounded heatmap workspace", async () => {
    const html = await renderToString(createSSRApp(DataHeatmapPage));

    expect(html).toContain("数据热度图");
    expect(html).toContain("管理员聚合");
    expect(html).toContain("不包含 IP、地理位置、用户、哈希");
    expect(html).not.toContain("synthetic-admin-token");
  });
});
