import type { CommunityPublicProfileResponse } from "@password-detective/api-contract";
import { describe, expect, it } from "vitest";
import { resolveCommunityAvatarUrl } from "./communityAvatar";

function profile(overrides: Partial<CommunityPublicProfileResponse> = {}): CommunityPublicProfileResponse {
  return {
    username: "sakura",
    display_name: "樱",
    bio: "",
    avatar_seed: "synthetic-avatar-seed",
    avatar_kind: "generated",
    avatar_url: null,
    role: "user",
    level: { code: "rookie", name: "新手侦探" },
    registered_month: "2026-08",
    stats: { post_count: 0, comment_count: 0, follower_count: 0, following_count: 0 },
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
    seo: {
      eligible: true,
      indexable: false,
      title: "樱",
      description: "",
      keywords: [],
      canonical_path: "/community/users/sakura",
      og_image_url: null,
    },
    ...overrides,
  };
}

describe("resolveCommunityAvatarUrl", () => {
  it("returns a visible deterministic built-in SVG for a generated avatar", () => {
    const avatarUrl = resolveCommunityAvatarUrl(profile());

    expect(avatarUrl).toMatch(/^data:image\/svg\+xml,/);
    expect(decodeURIComponent(avatarUrl)).toContain("<svg");
    expect(resolveCommunityAvatarUrl(profile())).toBe(avatarUrl);
  });

  it("keeps API-hosted uploads on the configured same-origin API path", () => {
    expect(
      resolveCommunityAvatarUrl(profile({
        avatar_kind: "upload",
        avatar_url: "/api/v1/site/assets/avatars/synthetic-avatar.png",
      })),
    ).toBe("/api/v1/site/assets/avatars/synthetic-avatar.png");
  });

  it("preserves externally hosted Gravatar URLs", () => {
    expect(
      resolveCommunityAvatarUrl(profile({
        avatar_kind: "gravatar",
        avatar_url: "https://www.gravatar.com/avatar/synthetic?d=identicon",
      })),
    ).toBe("https://www.gravatar.com/avatar/synthetic?d=identicon");
  });
});
