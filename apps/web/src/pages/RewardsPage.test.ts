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
    expect(html).toContain("订单、扣积分和履约功能将在目录治理稳定后开放");
    expect(html).toContain("刷新");
  });
});
