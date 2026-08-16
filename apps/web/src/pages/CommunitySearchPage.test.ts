import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunitySearchPage from "./CommunitySearchPage.vue";

vi.mock("vue-router", () => ({
  RouterLink: { props: ["to"], template: "<a><slot /></a>" },
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({ accessToken: "", isAuthenticated: false }),
}));

vi.mock("../services/community", () => ({
  searchCommunity: vi.fn(),
}));

describe("CommunitySearchPage", () => {
  it("renders query input, type filters, and an empty-result state", async () => {
    const html = await renderToString(createSSRApp(CommunitySearchPage));

    expect(html).toContain("搜索社区");
    expect(html).toContain("主题");
    expect(html).toContain("没有找到公开结果");
  });
});
