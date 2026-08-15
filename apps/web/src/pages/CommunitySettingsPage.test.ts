import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunitySettingsPage from "./CommunitySettingsPage.vue";

vi.mock("vue-router", () => ({
  RouterLink: { props: ["to"], template: "<a><slot /></a>" },
}));

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({ accessToken: "synthetic-access-token" }),
}));

vi.mock("../services/community", () => ({
  createCommunityIdempotencyKey: vi.fn(() => "synthetic-idempotency-key"),
  getCommunityOwnProfile: vi.fn(() => Promise.resolve({
    username: "synthetic-owner",
    display_name: "合成资料所有者",
    bio: "合成公开简介",
    avatar_seed: "synthetic-avatar-seed",
    avatar_kind: "generated",
    avatar_url: null,
    gravatar_enabled: false,
    role: "user",
    level: { code: "rookie", name: "新手侦探" },
    registered_month: "2026-08",
    stats: { post_count: 0, comment_count: 0, follower_count: 0, following_count: 0 },
    relationship: { viewer_is_self: true },
    recent_posts: [],
    recent_comments: [],
    follower_visibility: "public",
    following_visibility: "public",
    message_policy: "following",
    mention_policy: "everyone",
  })),
  uploadCommunityAvatar: vi.fn(),
  updateCommunityOwnProfile: vi.fn(),
  updateCommunityPrivacy: vi.fn(),
}));

describe("CommunitySettingsPage", () => {
  it("renders editable profile and privacy boundaries", async () => {
    const html = await renderToString(createSSRApp(CommunitySettingsPage));
    expect(html).toContain("社区资料与隐私");
    expect(html).toContain("用户名");
    expect(html).toContain("谁可以提及我");
    expect(html).toContain("注册后不可修改");
    expect(html).toContain("头像来源");
    expect(html).toContain("上传头像");
    expect(html).toContain("Gravatar 仅在你主动开启后使用");
  });
});
