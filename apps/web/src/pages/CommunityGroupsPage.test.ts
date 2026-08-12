import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunityGroupsPage from "./CommunityGroupsPage.vue";

vi.mock("vue-router", () => ({ RouterLink: { props: ["to"], template: "<a><slot /></a>" }, useRouter: () => ({ push: vi.fn() }) }));
vi.mock("../stores/auth", () => ({ useAuthStore: () => ({ accessToken: "", isAuthenticated: false }) }));
vi.mock("../services/community", () => ({ listCommunityGroups: vi.fn(), createCommunityGroup: vi.fn(), createCommunityIdempotencyKey: vi.fn(() => "synthetic-key") }));

describe("CommunityGroupsPage", () => {
  it("renders group visibility and governance explanations", async () => {
    const html = await renderToString(createSSRApp(CommunityGroupsPage));
    expect(html).toContain("群组目录");
    expect(html).toContain("私密群组仅接受邀请");
    expect(html).toContain("群主退出前必须先转让身份");
    expect(html).toContain('id="group-slug"');
  });
});
