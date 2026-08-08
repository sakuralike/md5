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
    expect(html).toContain("管理员安全基线");
    expect(html).toContain("密钥只在本次设置流程中显示");
    expect(html).not.toContain("synthetic-secret");
  });
});
