import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import DeveloperPluginsPage from "./DeveloperPluginsPage.vue";

vi.mock("../stores/auth", () => ({ useAuthStore: () => ({ accessToken: "synthetic-token" }) }));
vi.mock("../services/developerPlugins", () => ({
  listDeveloperPlugins: vi.fn().mockResolvedValue([]), createDeveloperPlugin: vi.fn(),
  registerPluginSigningKey: vi.fn(), createPluginVersion: vi.fn(), uploadPluginPackage: vi.fn(),
  finalizePluginVersion: vi.fn(), submitPluginVersion: vi.fn(), getPluginReviewReport: vi.fn(), withdrawPluginVersion: vi.fn(),
}));
vi.mock("../services/developerApplications", () => ({
  listDeveloperApplications: vi.fn().mockResolvedValue({ items: [], page: 1, page_size: 100, total: 0 }),
}));

describe("DeveloperPluginsPage", () => {
  it("renders the plugin submission workflow", async () => {
    const html = await renderToString(createSSRApp(DeveloperPluginsPage));
    expect(html).toContain("桌面插件开发者中心");
    expect(html).toContain("Ed25519 公钥 Base64");
    expect(html).toContain("申请权限");
    expect(html).toContain("关联第三方应用");
    expect(html).toContain("自动审核报告");
    expect(html).toContain("创建、上传并提交审核");
    expect(html).not.toContain("synthetic-token");
  });
});
