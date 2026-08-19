import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunityGroupPage from "./CommunityGroupPage.vue";

const communitySeo = vi.hoisted(() => ({
  set: vi.fn(),
  clear: vi.fn(),
}));

vi.mock("vue-router", () => ({
  RouterLink: { props: ["to"], template: "<a><slot /></a>" },
  useRoute: () => ({
    path: "/community/groups/synthetic-lab",
    params: { slug: "synthetic-lab" },
  }),
}));

vi.mock("../composables/useCommunitySeo", () => ({
  useCommunitySeo: () => ({ ...communitySeo, current: { value: null } }),
}));

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({
    accessToken: "synthetic-access-token",
    isAuthenticated: true,
    user: { id: "synthetic-owner-id", role: "user" },
  }),
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
    viewer_role: "owner",
    viewer_membership_status: "active",
    seo_version: 1,
    seo_title: null,
    seo_description: null,
    seo_keywords: null,
    seo_canonical_path: null,
    og_image_url: null,
    seo: {
      eligible: false,
      indexable: false,
      title: null,
      description: null,
      keywords: [],
      canonical_path: null,
      og_image_url: null,
    },
    owner_username: "synthetic-owner",
    members: [],
  }),
  listCommunityPosts: vi.fn().mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 }),
  setCommunityGroupMembership: vi.fn(),
  decideCommunityGroupMember: vi.fn(),
  createCommunityIdempotencyKey: vi.fn(() => "synthetic-key"),
  updateCommunityGroupSeo: vi.fn(),
}));

describe("CommunityGroupPage", () => {
  it("renders the governed group shell and permission explanation", async () => {
    const html = await renderToString(createSSRApp(CommunityGroupPage));

    expect(html).toContain("合成数据研究组");
    expect(html).toContain("申请审批");
    expect(html).toContain("群组权限说明");
    expect(html).toContain("群组 SEO");
    expect(html).toContain("编辑 SEO");
    expect(html).toContain("动态内容仍保持不索引");
    expect(communitySeo.set).toHaveBeenCalledWith(expect.objectContaining({
      kind: "group",
      path: "/community/groups/synthetic-lab",
      projection: expect.objectContaining({ eligible: false, indexable: false }),
    }));
  });
});
