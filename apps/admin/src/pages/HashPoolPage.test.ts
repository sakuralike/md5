import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import HashPoolPage from "./HashPoolPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/hashPool", () => ({ listHashPool: vi.fn() }));

describe("HashPoolPage", () => {
  it("renders the verified hash-pool workbench without secret material", async () => {
    const html = await renderToString(createSSRApp(HashPoolPage));
    expect(html).toContain("总哈希池");
    expect(html).toContain("最小披露");
    expect(html).toContain("输入哈希片段进行检索");
    expect(html).toContain("没有符合条件的已验证记录");
    expect(html).not.toContain("synthetic-admin-token");
  });
});
