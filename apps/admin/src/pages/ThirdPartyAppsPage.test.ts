import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import ThirdPartyAppsPage from "./ThirdPartyAppsPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/thirdPartyApps", () => ({
  listThirdPartyApps: vi.fn().mockResolvedValue({
    items: [
      {
        id: "app-synthetic",
        client_id: "pdc_synthetic-client",
        name: "合成桌面工具",
        developer_name: "合成开发者",
        description: "合成描述",
        status: "pending_review",
        application_source: "admin",
        requested_scopes: ["profile:read", "desktop:verification"],
        approved_scopes: [],
        redirect_uris: ["https://client.example/callback"],
        trusted_verification_enabled: false,
        request_count: 0,
        last_used_at: null,
        reviewed_at: null,
        created_at: "2026-08-15T00:00:00Z",
        updated_at: "2026-08-15T00:00:00Z",
        revoked_at: null,
        management_secret: null,
      },
    ],
    page: 1,
    page_size: 20,
    total: 1,
  }),
  createThirdPartyApp: vi.fn(),
  approveThirdPartyApp: vi.fn(),
  suspendThirdPartyApp: vi.fn(),
  restoreThirdPartyApp: vi.fn(),
  revokeThirdPartyApp: vi.fn(),
}));

describe("ThirdPartyAppsPage", () => {
  it("renders governance controls and trusted verification review", async () => {
    const html = await renderToString(createSSRApp(ThirdPartyAppsPage));
    expect(html).toContain("第三方应用治理");
    expect(html).toContain("创建应用");
    expect(html).toContain("可信验证直入总哈希池");
    expect(html).toContain("审核通过");
    expect(html).toContain("暂停应用");
  });
});
