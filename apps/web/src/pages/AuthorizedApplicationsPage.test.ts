import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import AuthorizedApplicationsPage from "./AuthorizedApplicationsPage.vue";

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({ accessToken: "synthetic-user-token" }),
}));

vi.mock("../services/thirdPartyApps", () => ({
  listAuthorizedApplications: vi.fn().mockResolvedValue({
    items: [
      {
        app_id: "app-synthetic",
        client_id: "pdc_synthetic-client",
        app_name: "合成桌面工具",
        developer_name: "合成开发者",
        scopes: ["profile:read"],
        authorized_at: "2026-08-15T00:00:00Z",
        last_used_at: null,
      },
    ],
  }),
  revokeAuthorizedApplication: vi.fn(),
}));

describe("AuthorizedApplicationsPage", () => {
  it("renders authorized apps and a revoke action", async () => {
    const html = await renderToString(createSSRApp(AuthorizedApplicationsPage));
    expect(html).toContain("已授权应用");
    expect(html).toContain("合成桌面工具");
    expect(html).toContain("撤销授权");
  });
});
