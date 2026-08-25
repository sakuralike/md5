import { renderToString } from "@vue/server-renderer";
import { createSSRApp, defineComponent } from "vue";
import { describe, expect, it, vi } from "vitest";
import DashboardPage from "./DashboardPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/dashboard", () => ({
  getAdminDashboardSummary: vi.fn().mockResolvedValue(null),
}));

const RouterLinkStub = defineComponent({
  props: {
    to: { type: String, required: true },
  },
  template: '<a :href="to"><slot /></a>',
});

describe("DashboardPage", () => {
  it("renders every registered admin feature and its internal path", async () => {
    const app = createSSRApp(DashboardPage);
    app.component("RouterLink", RouterLinkStub);

    const html = await renderToString(app);

    expect(html).toContain("全部管理功能站内路径");
    expect(html).toContain("共 22 个入口");
    expect(html).toContain("/plugin-reviews");
    expect(html).toContain("/registration");
    expect(html).toContain("/candidates");
    expect(html).toContain("/trust-cases");
    expect(html).toContain("/hash-pool");
    expect(html).toContain("/community/settings");
    expect(html).toContain("/community/notifications");
    expect(html).toContain("/community/search-health");
    expect(html).toContain("/desktop-releases");
    expect(html).toContain("/web-announcements");
    expect(html).toContain("/role-changes");
    expect(html).toContain("/settings");
  });
});
