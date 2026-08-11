import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import ReputationPage from "./ReputationPage.vue";

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({
    accessToken: "synthetic-access-token",
  }),
}));

vi.mock("../services/reputation", () => ({
  loadTrustCenter: vi.fn(),
}));

describe("ReputationPage", () => {
  it("renders the trust center shell with Shadcn controls", async () => {
    const html = await renderToString(createSSRApp(ReputationPage));

    expect(html).toContain("用户等级、积分与信誉");
    expect(html).toContain("成长值决定长期等级权益");
    expect(html).toContain("正在加载积分与信誉记录");
    expect(html).toContain("刷新");
    expect(html).toContain("<button");
  });
});
