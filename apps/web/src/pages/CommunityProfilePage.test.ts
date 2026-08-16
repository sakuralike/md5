import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunityProfilePage from "./CommunityProfilePage.vue";

vi.mock("vue-router", () => ({
  RouterLink: { props: ["to"], template: "<a><slot /></a>" },
  useRoute: () => ({ params: { username: "synthetic-user" } }),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({ accessToken: "synthetic-access-token", isAuthenticated: true }),
}));

vi.mock("../services/community", () => ({
  createCommunityDirectConversation: vi.fn(),
  createCommunityIdempotencyKey: vi.fn(() => "synthetic-idempotency-key"),
  getCommunityPublicProfile: vi.fn(() => Promise.resolve({
    username: "synthetic-user",
    display_name: "合成社区用户",
    bio: "只含合成公开资料。",
    avatar_seed: "synthetic-avatar-seed",
    role: "user",
    level: { code: "rookie", name: "新手侦探" },
    registered_month: "2026-08",
    stats: { post_count: 2, comment_count: 3, follower_count: 4, following_count: 5 },
    relationship: {
      viewer_is_self: false,
      viewer_is_following: false,
      follows_viewer: false,
      viewer_is_blocking: false,
      viewer_is_blocked: false,
      viewer_is_muting: false,
    },
    recent_posts: [],
    recent_comments: [],
  })),
  setCommunityUserRelation: vi.fn(),
}));

describe("CommunityProfilePage", () => {
  it("renders a privacy-minimized public profile", async () => {
    const html = await renderToString(createSSRApp(CommunityProfilePage));
    expect(html).toContain("合成社区用户");
    expect(html).toContain("新手侦探");
    expect(html).toContain("加入于 2026-08");
    expect(html).toContain("发送私信");
    expect(html).not.toContain("example.com");
  });
});
