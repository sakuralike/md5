import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunityActivityPage from "./CommunityActivityPage.vue";

vi.mock("vue-router", () => ({
  RouterLink: { props: ["to"], template: "<a><slot /></a>" },
}));
vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({ isAuthenticated: true, accessToken: "synthetic-access-token" }),
}));
vi.mock("../services/community", () => ({
  getCommunityActivityPreferences: vi.fn(() => new Promise(() => undefined)),
  listCommunityActivity: vi.fn(() => new Promise(() => undefined)),
  updateCommunityActivityPreferences: vi.fn(),
}));

describe("CommunityActivityPage", () => {
  it("renders feed tabs and privacy controls", async () => {
    const html = await renderToString(createSSRApp(CommunityActivityPage));
    expect(html).toContain("社区动态信息流");
    expect(html).toContain("最新动态");
    expect(html).toContain("我的关注");
    expect(html).toContain("我的群组");
    expect(html).toContain("动态公开偏好");
  });
});
