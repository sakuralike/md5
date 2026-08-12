import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunityHomePage from "./CommunityHomePage.vue";

vi.mock("vue-router", () => ({
  RouterLink: {
    props: ["to"],
    template: "<a><slot /></a>",
  },
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("../services/community", () => ({
  getCommunityHome: vi.fn(),
}));

describe("CommunityHomePage", () => {
  it("renders the independent community home entry points", async () => {
    const html = await renderToString(createSSRApp(CommunityHomePage));

    expect(html).toContain("社区首页");
    expect(html).toContain("社区板块");
    expect(html).toContain("发布新主题");
    expect(html).toContain("点击主题进入独立详情页");
  });
});
