import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import StatisticsPage from "./StatisticsPage.vue";

vi.mock("../services/site", () => ({
  getAlgorithmDistribution: vi.fn(),
}));

describe("StatisticsPage", () => {
  it("renders the privacy-bounded algorithm distribution surface", async () => {
    const html = await renderToString(createSSRApp(StatisticsPage));

    expect(html).toContain("算法分布");
    expect(html).toContain("已验证公开档案");
    expect(html).toContain("候选密码");
  });
});
