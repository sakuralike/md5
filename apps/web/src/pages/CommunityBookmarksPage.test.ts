import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunityBookmarksPage from "./CommunityBookmarksPage.vue";

vi.mock("vue-router", () => ({
  RouterLink: {
    props: ["to"],
    template: "<a><slot /></a>",
  },
}));

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({
    accessToken: "synthetic-access-token",
  }),
}));

vi.mock("../services/community", () => ({
  createCommunityIdempotencyKey: vi.fn(() => "synthetic-idempotency-key"),
  listCommunityBookmarks: vi.fn(() => Promise.resolve({
    items: [{
      post_id: "synthetic-post-id",
      bookmarked_at: "2026-08-12T08:00:00Z",
      post: {
        id: "synthetic-post-id",
        board_code: "general",
        title: "合成收藏主题",
        content_preview: "用于收藏列表渲染测试的合成主题摘要。",
        author: { user_id: "synthetic-author-id", username: "synthetic-author", role: "user" },
        is_pinned: false,
        is_locked: false,
        reply_count: 3,
        like_count: 5,
        version: 1,
        edited_at: null,
        last_activity_at: "2026-08-12T08:00:00Z",
        created_at: "2026-08-12T07:00:00Z",
      },
    }],
    next_cursor: null,
    has_more: false,
  })),
  setCommunityPostBookmark: vi.fn(),
}));

describe("CommunityBookmarksPage", () => {
  it("renders private bookmark cards after server prefetch", async () => {
    const app = createSSRApp(CommunityBookmarksPage);
    const html = await renderToString(app);

    expect(html).toContain("我的社区收藏");
    expect(html).toContain("收藏列表仅本人可见");
    expect(html).toContain("已收藏主题");
  });
});
