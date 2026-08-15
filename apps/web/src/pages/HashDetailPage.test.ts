import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import HashDetailPage from "./HashDetailPage.vue";

vi.mock("vue-router", () => ({
  RouterLink: { props: ["to"], template: "<a><slot /></a>" },
  useRoute: () => ({ params: { algorithm: "sha256", digest: "a".repeat(64) } }),
}));

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({ accessToken: "synthetic-token", isAuthenticated: true }),
}));

vi.mock("../services/hashDetails", () => ({
  getHashDetail: vi.fn(() => Promise.resolve({
    algorithm: "sha256",
    digest: "a".repeat(64),
    matched: true,
    archive: {
      id: "synthetic-archive",
      optional_size: 1024,
      optional_format: "zip",
      fingerprints: [],
      candidate_count: 1,
      status_counts: { verified: 1 },
      candidates: [{
        id: "synthetic-candidate",
        status: "verified",
        confidence_score: 0.9,
        masked_secret: "••••••••",
        submission_count: 2,
        success_evidence_count: 2,
        failure_evidence_count: 0,
        my_feedback: null,
        last_verified_at: null,
      }],
    },
    like_count: 3,
    viewer_has_liked: true,
    vote_counts: { useful: 2, not_useful: 1 },
    viewer_vote: "useful",
    comment_count: 21,
    comments: [{
      id: "synthetic-comment",
      parent_id: null,
      content: "合成验证说明",
      author: { user_id: "synthetic-user", username: "synthetic-user", role: "user" },
      like_count: 1,
      viewer_has_liked: false,
      created_at: "2026-08-13T00:00:00Z",
    }],
    comments_next_cursor: "synthetic-next-cursor",
  })),
  getHashComments: vi.fn(() => Promise.resolve({ items: [], next_cursor: null, has_more: false })),
  setHashLike: vi.fn(),
  voteHash: vi.fn(),
  createHashComment: vi.fn(),
  setHashCommentLike: vi.fn(),
}));

describe("HashDetailPage", () => {
  it("renders hash metadata and community interactions", async () => {
    const html = await renderToString(createSSRApp(HashDetailPage));
    expect(html).toContain("哈希值详情");
    expect(html).toContain("a".repeat(64));
    expect(html).toContain("点赞");
    expect(html).toContain("有帮助");
    expect(html).toContain("评论与讨论");
    expect(html).toContain("合成验证说明");
    expect(html).toContain("21 条评论");
    expect(html).toContain("加载更多评论");
  });
});
