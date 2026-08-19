import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunityPostPage from "./CommunityPostPage.vue";

const communitySeo = vi.hoisted(() => ({
  set: vi.fn(),
  clear: vi.fn(),
}));

vi.mock("vue-router", () => ({
  RouterLink: {
    props: ["to"],
    template: "<a><slot /></a>",
  },
  useRoute: () => ({
    path: "/community/posts/synthetic-post-id",
    params: { postId: "synthetic-post-id" },
  }),
}));

vi.mock("../composables/useCommunitySeo", () => ({
  useCommunitySeo: () => ({ ...communitySeo, current: { value: null } }),
}));

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({
    accessToken: "synthetic-access-token",
    isAuthenticated: true,
    user: { id: "synthetic-author-id", email_verified: true },
  }),
}));

vi.mock("../services/community", () => ({
  getCommunityPost: vi.fn(() => Promise.resolve({
    id: "synthetic-post-id",
    board_code: "general",
    title: "合成社区主题",
    content: "这是用于渲染验证的合成主题正文，满足详情页的最小长度要求。",
    author: { user_id: "synthetic-author-id", username: "synthetic-author", role: "user" },
    is_pinned: false,
    is_locked: false,
    reply_count: 1,
    like_count: 2,
    viewer_has_liked: false,
    viewer_has_bookmarked: false,
    version: 2,
    seo_version: 3,
    seo_title: "合成搜索标题",
    seo_description: "合成搜索描述",
    seo_keywords: ["合成", "社区"],
    seo_canonical_path: "/community/posts/synthetic-post-id",
    og_image_url: null,
    edited_at: "2026-08-12T03:00:00Z",
    last_activity_at: "2026-08-12T03:00:00Z",
    created_at: "2026-08-12T02:00:00Z",
    comments: [],
    seo: {
      eligible: true,
      indexable: false,
      title: "合成搜索标题",
      description: "合成搜索描述",
      keywords: ["合成", "社区"],
      canonical_path: "/community/posts/synthetic-post-id",
      og_image_url: null,
    },
  })),
  setCommunityCommentLike: vi.fn(),
  setCommunityPostBookmark: vi.fn(),
  setCommunityPostLike: vi.fn(),
  listCommunityComments: vi.fn(() => Promise.resolve({
    items: [{
      id: "synthetic-comment-id",
      parent_id: null,
      root_id: null,
      reply_to_user_id: null,
      content: "合成回复内容。",
      author: { user_id: "synthetic-author-id", username: "synthetic-author", role: "user" },
      like_count: 1,
      viewer_has_liked: false,
      version: 1,
      edited_at: null,
      created_at: "2026-08-12T03:10:00Z",
    }],
    next_cursor: null,
    has_more: false,
  })),
  createCommunityComment: vi.fn(),
  createCommunityIdempotencyKey: vi.fn(() => "synthetic-idempotency-key"),
  createCommunityReport: vi.fn(),
  deleteCommunityComment: vi.fn(),
  deleteCommunityPost: vi.fn(),
  updateCommunityComment: vi.fn(),
  updateCommunityPost: vi.fn(),
  updateCommunityPostSeo: vi.fn(),
}));

describe("CommunityPostPage", () => {
  it("renders independent detail governance controls after server prefetch", async () => {
    const html = await renderToString(createSSRApp(CommunityPostPage));

    expect(html).toContain("返回社区首页");
    expect(html).toContain("合成社区主题");
    expect(html).toContain("编辑主题");
    expect(html).toContain("SEO 设置");
    expect(html).toContain("编辑 SEO");
    expect(html).toContain("动态内容仍保持不索引");
    expect(html).toContain("举报主题");
    expect(html).toContain("点赞 2");
    expect(html).toContain("收藏");
    expect(html).toContain("编辑");
    expect(html).toContain("举报回复");
    expect(communitySeo.set).toHaveBeenCalledWith(expect.objectContaining({
      kind: "post",
      path: "/community/posts/synthetic-post-id",
      projection: expect.objectContaining({ eligible: true, indexable: false }),
    }));
  });
});
