import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import UserLevelsManagement from "./UserLevelsManagement.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/settings", () => ({
  getCurrentSettings: vi.fn(),
  saveCurrentSettings: vi.fn(),
}));

describe("UserLevelsManagement", () => {
  it("renders the direct current-settings level editor", async () => {
    const html = await renderToString(createSSRApp(UserLevelsManagement));

    expect(html).toContain('id="user-levels"');
    expect(html).toContain("用户等级与权益");
    expect(html).toContain("新增等级");
    expect(html).toContain("直接保存当前等级配置");
    expect(html).toContain("重置当前编辑");
    expect(html).not.toContain("配置草稿");
    expect(html).not.toContain("不可变");
    expect(html).not.toContain("发布门禁");
  });
});
