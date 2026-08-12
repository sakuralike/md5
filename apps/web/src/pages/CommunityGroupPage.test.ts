import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunityGroupPage from "./CommunityGroupPage.vue";

vi.mock("vue-router", () => ({
  RouterLink: { props: ["to"], template: "<a><slot /></a>" },
  useRoute: () => ({ params: { slug: "synthetic-lab" } }),
}));

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({ accessToken: "", isAuthenticated: false }),
}));

vi.mock("../services/community", () => ({
  getCommunityGroup: vi.fn().mockResolvedValue({
    slug: "synthetic-lab",
    name: "合成数据研究组",
    description: "仅讨论合法授权场景。",
    visibility: "approval",
    status: "active",
    member_count: 1,
    post_count: 0,
    viewer_role: null,
    viewer_membership_status: null,
    owner_username: "synthetic-owner",
    members: [],
  }),
  listCommunityPosts: vi.fn().mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 }),
  setCommunityGroupMembership: vi.fn(),
  decideCommunityGroupMember: vi.fn(),
  createCommunityIdempotencyKey: vi.fn(() => "synthetic-key"),
}));

describe("CommunityGroupPage", () => {
  it("renders the governed group shell and permission explanation", async () => {
    const html = await renderToString(createSSRApp(CommunityGroupPage));

    expect(html).toContain("合成数据研究组");
    expect(html).toContain("申请审批");
    expect(html).toContain("群组权限说明");
  });
});
