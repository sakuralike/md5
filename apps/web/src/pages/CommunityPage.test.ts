import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunityPage from "./CommunityPage.vue";

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({
    accessToken: "",
    isAuthenticated: false,
    user: null,
  }),
}));

vi.mock("../services/community", () => ({
  listCommunityBoards: vi.fn(),
  listCommunityPosts: vi.fn(),
  getCommunityPost: vi.fn(),
  createCommunityPost: vi.fn(),
  createCommunityComment: vi.fn(),
  createCommunityIdempotencyKey: vi.fn(),
}));

describe("CommunityPage", () => {
  it("renders the public community shell and safety rules", async () => {
    const html = await renderToString(createSSRApp(CommunityPage));

    expect(html).toContain("社区协作中心");
    expect(html).toContain("公开阅读");
    expect(html).toContain("验证后发言");
    expect(html).toContain("请勿发布真实密码、令牌或个人信息");
    expect(html).toContain("发布新主题");
  });
});
