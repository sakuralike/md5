import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import AuditPage from "./AuditPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/auditLogs", () => ({
  listAdminAuditLogs: vi.fn(),
  getAdminAuditLog: vi.fn(),
  downloadAdminAuditLogs: vi.fn(),
}));

describe("AuditPage", () => {
  it("renders the audit workbench controls", async () => {
    const html = await renderToString(createSSRApp(AuditPage));

    expect(html).toContain("审计日志");
    expect(html).toContain("综合搜索");
    expect(html).toContain("导出 CSV");
    expect(html).toContain("脱敏详情");
  });
});
