import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import RewardOrdersPage from "./RewardOrdersPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/rewards", () => ({
  createRewardCatalogKey: vi.fn(() => "synthetic-reward-key"),
  listAdminRewardOrders: vi.fn(),
  getAdminRewardOrder: vi.fn(),
  getRewardOperationsStats: vi.fn(),
  retryAdminRewardOrder: vi.fn(),
  compensateAdminRewardOrder: vi.fn(),
}));

describe("RewardOrdersPage", () => {
  it("renders order operations and failure governance controls", async () => {
    const html = await renderToString(createSSRApp(RewardOrdersPage));
    expect(html).toContain("兑换订单工作台");
    expect(html).toContain("失败订单执行受控重试或补偿");
    expect(html).toContain("订单队列");
    expect(html).not.toContain("synthetic-admin-token");
  });
});
