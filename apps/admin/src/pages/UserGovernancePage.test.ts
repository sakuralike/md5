import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import UserGovernancePage from "./UserGovernancePage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token", user: null }),
}));

vi.mock("../services/users", () => ({
  createAdminUser: vi.fn(),
  listAdminUsers: vi.fn(),
  getAdminUser: vi.fn(),
  reauthenticateAdmin: vi.fn(),
  changeAdminUserStatus: vi.fn(),
  revokeAdminUserSessions: vi.fn(),
  updateAdminUserProfile: vi.fn(),
}));

describe("UserGovernancePage", () => {
  it("renders the guarded governance workbench", async () => {
    const html = await renderToString(createSSRApp(UserGovernancePage));

    expect(html).toContain("用户审批工作台");
    expect(html).toContain("手动创建用户");
    expect(html).toContain("注册策略与邀请码");
    expect(html).toContain("用户名、邮箱或 UID");
    expect(html).toContain("用户等级与权益");
    expect(html).toContain('id="user-levels"');
    expect(html).toContain("直接保存当前等级配置");
    expect(html).toContain("重置当前编辑");
    expect(html).toContain("一次性再认证");
    expect(html).toContain("原因码");
    expect(html).toContain("可选 TOTP");
  });
});
