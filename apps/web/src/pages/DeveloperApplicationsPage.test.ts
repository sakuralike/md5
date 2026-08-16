import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import DeveloperApplicationsPage from "./DeveloperApplicationsPage.vue";

vi.mock("vue-router", () => ({
  RouterLink: { props: ["to"], template: "<a><slot /></a>" },
  useRoute: () => ({ path: "/developer/apply", query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({ accessToken: "synthetic-user-token", user: { username: "synthetic-developer" } }),
}));

vi.mock("../services/developerApplications", () => ({
  listDeveloperApplications: vi.fn().mockResolvedValue({
    items: [
      {
        id: "request-synthetic",
        name: "合成桌面应用",
        developer_name: "合成开发者",
        description: "合成申请",
        website_url: "https://client.example",
        privacy_policy_url: "https://client.example/privacy",
        redirect_uris: ["https://client.example/callback"],
        requested_scopes: ["profile:read"],
        windows_release_info: "Windows 发行信息",
        use_case: "合成验证场景",
        status: "rejected",
        resubmission_count: 1,
        current_version: 2,
        review_note: "请补充发行说明",
        reviewed_at: "2026-08-15T00:00:00Z",
        created_at: "2026-08-15T00:00:00Z",
        updated_at: "2026-08-15T00:00:00Z",
        approved_application: null,
        events: [],
      },
    ],
    page: 1,
    page_size: 20,
    total: 1,
  }),
  createDeveloperApplication: vi.fn(),
  updateDeveloperApplication: vi.fn(),
  submitDeveloperApplication: vi.fn(),
}));

describe("DeveloperApplicationsPage", () => {
  it("renders the application form and rejected request resubmission path", async () => {
    const html = await renderToString(createSSRApp(DeveloperApplicationsPage));

    expect(html).toContain("开发者应用申请");
    expect(html).toContain("OAuth 回调地址");
    expect(html).toContain("读取已授权用户的公开资料");
    expect(html).toContain("读取已公开的哈希资料");
    expect(html).toContain("读取桌面端公告");
    expect(html).toContain("检查桌面端版本更新");
    expect(html).toContain("登记与管理本机安装实例");
    expect(html).toContain("验证压缩包密码并提交回执");
    expect(html).toContain("合成桌面应用");
    expect(html).toContain("修改并重新提交");
    expect(html).toContain("只有管理员审核通过，系统才会创建可用的第三方桌面应用");
  });
});
