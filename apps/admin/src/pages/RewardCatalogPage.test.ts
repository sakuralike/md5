import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import RewardCatalogPage from "./RewardCatalogPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/rewards", () => ({
  createRewardCatalogKey: vi.fn(() => "synthetic-reward-key"),
  listAdminRewardCatalog: vi.fn().mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 }),
  createAdminRewardCatalog: vi.fn(),
  updateAdminRewardCatalog: vi.fn(),
}));

describe("RewardCatalogPage", () => {
  it("renders virtual catalog governance controls", async () => {
    const html = await renderToString(createSSRApp(RewardCatalogPage));

    expect(html).toContain("虚拟商品目录");
    expect(html).toContain("创建虚拟商品");
    expect(html).toContain("商品代码创建后不可修改");
    expect(html).toContain('id="reward-create-cost"');
    expect(html).not.toContain("synthetic-admin-token");
  });
});
