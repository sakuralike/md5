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
  listThirdPartyApplicationRequests: vi.fn().mockResolvedValue({
    items: [
      {
        id: "request-synthetic",
        name: "合成开发者桌面端",
        developer_name: "合成开发者",
        description: "合成自助申请",
        website_url: "https://client.example",
        privacy_policy_url: "https://client.example/privacy",
        redirect_uris: ["https://client.example/callback"],
        requested_scopes: ["profile:read", "desktop:verification"],
        windows_release_info: "Windows 发行信息",
        use_case: "验证合成压缩包",
        status: "pending_review",
        resubmission_count: 0,
        current_version: 1,
        review_note: null,
        reviewed_at: null,
        created_at: "2026-08-15T00:00:00Z",
        updated_at: "2026-08-15T00:00:00Z",
      },
    ],
    page: 1,
    page_size: 100,
    total: 1,
  }),
  createThirdPartyApp: vi.fn(),
  approveThirdPartyApp: vi.fn(),
  suspendThirdPartyApp: vi.fn(),
  restoreThirdPartyApp: vi.fn(),
  revokeThirdPartyApp: vi.fn(),
  approveThirdPartyApplicationRequest: vi.fn(),
  rejectThirdPartyApplicationRequest: vi.fn(),
}));

describe("ThirdPartyAppsPage", () => {
  it("renders governance controls and trusted verification review", async () => {
    const html = await renderToString(createSSRApp(ThirdPartyAppsPage));
    expect(html).toContain("第三方应用治理");
    expect(html).toContain("读取已授权用户的公开资料");
    expect(html).toContain("读取已公开的哈希资料");
    expect(html).toContain("读取桌面端公告");
    expect(html).toContain("检查桌面端版本更新");
    expect(html).toContain("登记与管理本机安装实例");
    expect(html).toContain("验证压缩包密码并提交回执");
    expect(html).toContain("创建应用");
    expect(html).toContain("可信验证直入总哈希池");
    expect(html).toContain("审核通过并创建应用");
    expect(html).toContain("合成开发者桌面端");
    expect(html).toContain("暂停应用");
  });
});
