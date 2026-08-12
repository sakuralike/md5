import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunityConfigurationPage from "./CommunityConfigurationPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/communityConfiguration", () => ({
  createCommunityConfigurationKey: vi.fn(() => "synthetic-key"),
  listCommunityBoards: vi.fn().mockResolvedValue({ items: [] }),
  createCommunityBoard: vi.fn(),
  updateCommunityBoard: vi.fn(),
}));

describe("CommunityConfigurationPage", () => {
  it("renders board permissions, lifecycle effects, and creation controls", async () => {
    const html = await renderToString(createSSRApp(CommunityConfigurationPage));

    expect(html).toContain("社区板块配置工作台");
    expect(html).toContain("最低发帖角色");
    expect(html).toContain("只读状态");
    expect(html).toContain("逻辑停用");
    expect(html).toContain("新增板块");
    expect(html).not.toContain("synthetic-admin-token");
  });
});
