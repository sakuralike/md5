import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import SystemSettingsPage from "./SystemSettingsPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/settings", () => ({
  listSettingVersions: vi.fn(),
  getSettingVersion: vi.fn(),
  createSettingVersion: vi.fn(),
  publishSettingVersion: vi.fn(),
  rollbackSettingVersion: vi.fn(),
}));

vi.mock("../services/users", () => ({
  reauthenticateAdmin: vi.fn(),
}));

describe("SystemSettingsPage", () => {
  it("renders immutable settings governance controls", async () => {
    const html = await renderToString(createSSRApp(SystemSettingsPage));

    expect(html).toContain("系统配置治理工作台");
    expect(html).toContain("不可变版本历史");
    expect(html).toContain("版本差异预览");
    expect(html).toContain("用户等级与权益");
    expect(html).toContain("新增等级");
    expect(html).toContain("发布与回滚门禁");
    expect(html).toContain("一次性再认证");
  });
});
