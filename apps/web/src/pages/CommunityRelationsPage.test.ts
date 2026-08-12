import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunityRelationsPage from "./CommunityRelationsPage.vue";

vi.mock("vue-router", () => ({
  RouterLink: { props: ["to"], template: "<a><slot /></a>" },
  useRoute: () => ({ params: { username: "synthetic-user" }, meta: { direction: "followers" } }),
}));

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({ accessToken: "", isAuthenticated: false }),
}));

vi.mock("../services/community", () => ({
  listCommunityRelations: vi.fn(() => Promise.resolve({
    items: [{
      username: "synthetic-follower",
      display_name: "合成关注者",
      avatar_seed: "synthetic-avatar-seed",
      role: "user",
      level: { code: "rookie", name: "新手侦探" },
    }],
    next_cursor: null,
    has_more: false,
  })),
}));

describe("CommunityRelationsPage", () => {
  it("renders a public follower list", async () => {
    const html = await renderToString(createSSRApp(CommunityRelationsPage));
    expect(html).toContain("关注者");
    expect(html).toContain("合成关注者");
    expect(html).toContain("synthetic-follower");
  });
});
