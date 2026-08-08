import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import TrustCasesPage from "./TrustCasesPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({
    accessToken: "synthetic-admin-token",
  }),
}));

describe("TrustCasesPage", () => {
  it("renders the trust case workbench with Shadcn filter controls", async () => {
    const html = await renderToString(createSSRApp(TrustCasesPage));

    expect(html).toContain("举报与申诉");
    expect(html).toContain("COMMUNITY TRUST");
    expect(html).toContain("案件 ID、候选 ID 或用户名");
    expect(html).toContain("当前筛选条件下没有案件");
    expect(html).not.toContain("synthetic-admin-token");
  });
});
