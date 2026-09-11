import { readFileSync } from "node:fs";
import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import TotpSetupPage from "./TotpSetupPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({
    beginTotpSetup: vi.fn(),
    confirmTotpSetup: vi.fn(),
  }),
}));

describe("TotpSetupPage", () => {
  it("renders the TOTP enrollment shell without exposing setup data during SSR", async () => {
    const html = await renderToString(createSSRApp(TotpSetupPage));

    expect(html).toContain("绑定 TOTP");
    expect(html).toContain("可选安全增强");
    expect(html).toContain("TOTP 默认关闭");
    expect(html).toContain("密钥只在本次设置流程中显示");
    expect(html).not.toContain("synthetic-secret");
  });

  it("uses semantic destructive tokens instead of the removed legacy error class", () => {
    const source = readFileSync(new URL("./TotpSetupPage.vue", import.meta.url), "utf8");

    expect(source).not.toMatch(/class="error"/u);
    expect(source).toContain("border-destructive/40");
    expect(source).toContain("bg-destructive/10");
    expect(source).toContain("text-destructive");
  });
});
