import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import UserLevelsManagement from "./UserLevelsManagement.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/settings", () => ({
  listSettingVersions: vi.fn(),
  getSettingVersion: vi.fn(),
  createSettingVersion: vi.fn(),
}));

describe("UserLevelsManagement", () => {
  it("renders the user-approval-owned level editor", async () => {
    const html = await renderToString(createSSRApp(UserLevelsManagement));

    expect(html).toContain('id="user-levels"');
    expect(html).toContain("用户等级与权益");
    expect(html).toContain("新增等级");
    expect(html).toContain("生成配置草稿");
  });
});
