import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import RoleChangesPage from "./RoleChangesPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/roleChanges", () => ({
  listRoleChangeRequests: vi.fn(),
  createRoleChangeRequest: vi.fn(),
  approveRoleChangeRequest: vi.fn(),
  rejectRoleChangeRequest: vi.fn(),
}));

vi.mock("../services/users", () => ({
  reauthenticateAdmin: vi.fn(),
}));

describe("RoleChangesPage", () => {
  it("renders the dual-control approval workbench and its queue states", async () => {
    const html = await renderToString(createSSRApp(RoleChangesPage));
    expect(html).toContain("角色变更审批工作台");
    expect(html).toContain("双人复核");
    expect(html).toContain("创建角色变更请求");
    expect(html).toContain("批准选中");
    expect(html).toContain("拒绝选中");
    expect(html).toContain("浏览器不会保存凭据");
    expect(html).toContain("暂无角色变更请求");
    expect(html).toContain("上一页");
    expect(html).toContain("下一页");
  });
});
