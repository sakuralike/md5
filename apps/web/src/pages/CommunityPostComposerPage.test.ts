import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunityPostComposerPage from "./CommunityPostComposerPage.vue";

vi.mock("vue-router", () => ({
  RouterLink: {
    props: ["to"],
    template: "<a><slot /></a>",
  },
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({
    accessToken: "",
    isAuthenticated: false,
    user: null,
  }),
}));

vi.mock("../services/community", () => ({
  listCommunityBoards: vi.fn().mockResolvedValue({ items: [] }),
  listCommunityGroups: vi.fn().mockResolvedValue({ items: [] }),
  createCommunityPost: vi.fn(),
  createCommunityIdempotencyKey: vi.fn(() => "synthetic-idempotency-key"),
}));

describe("CommunityPostComposerPage", () => {
  it("renders the guarded independent post composer", async () => {
    const html = await renderToString(createSSRApp(CommunityPostComposerPage));

    expect(html).toContain("发布新主题");
    expect(html).toContain("需要登录");
    expect(html).toContain("合法授权场景");
    expect(html).toContain("返回社区首页");
    expect(html).toContain('id="community-composer-title"');
  });
});
