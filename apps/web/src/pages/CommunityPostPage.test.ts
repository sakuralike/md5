import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunityPostPage from "./CommunityPostPage.vue";

vi.mock("vue-router", () => ({
  RouterLink: {
    props: ["to"],
    template: "<a><slot /></a>",
  },
  useRoute: () => ({ params: { postId: "synthetic-post-id" } }),
}));

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({
    accessToken: "",
    isAuthenticated: false,
    user: null,
  }),
}));

vi.mock("../services/community", () => ({
  getCommunityPost: vi.fn(),
  listCommunityComments: vi.fn(),
  createCommunityComment: vi.fn(),
  createCommunityIdempotencyKey: vi.fn(() => "synthetic-idempotency-key"),
}));

describe("CommunityPostPage", () => {
  it("renders the independent post detail loading shell", async () => {
    const html = await renderToString(createSSRApp(CommunityPostPage));

    expect(html).toContain("返回社区首页");
    expect(html).toContain("正在加载主题");
    expect(html).toContain("发布新主题");
  });
});
