import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import RiskAlertsPage from "./RiskAlertsPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({
    accessToken: "synthetic-admin-token",
  }),
}));

describe("RiskAlertsPage", () => {
  it("renders the risk operations shell without exposing the admin token", async () => {
    const html = await renderToString(createSSRApp(RiskAlertsPage));

    expect(html).toContain("风险告警");
    expect(html).toContain("RISK OPERATIONS");
    expect(html).toContain("输入合成候选 ID");
    expect(html).toContain("当前筛选条件下没有风险告警");
    expect(html).not.toContain("synthetic-admin-token");
  });
});
