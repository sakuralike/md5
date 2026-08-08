import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CandidateModerationPage from "./CandidateModerationPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({
    accessToken: "synthetic-admin-token",
  }),
}));

describe("CandidateModerationPage", () => {
  it("renders the candidate moderation workbench with protected controls", async () => {
    const html = await renderToString(createSSRApp(CandidateModerationPage));

    expect(html).toContain("候选审核");
    expect(html).toContain("人工审核闭环");
    expect(html).toContain("输入 ID 或哈希片段");
    expect(html).toContain("没有符合条件的候选记录");
    expect(html).not.toContain("synthetic-admin-token");
  });
});
