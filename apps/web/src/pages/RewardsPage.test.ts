import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import RewardsPage from "./RewardsPage.vue";

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({ accessToken: "", isAuthenticated: false }),
}));

vi.mock("../services/rewards", () => ({
  getRewardCatalog: vi.fn(),
}));

describe("RewardsPage", () => {
  it("renders a catalog-first marketplace shell", async () => {
    const html = await renderToString(createSSRApp(RewardsPage));

    expect(html).toContain("积分商城");
    expect(html).toContain("虚拟权益目录");
    expect(html).toContain("使用已结算积分兑换虚拟权益，订单和发放状态可以在当前页面追踪");
    expect(html).toContain("刷新");
  });
});
