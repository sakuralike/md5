import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import RegisterPage from "./RegisterPage.vue";

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({ busy: false, error: "", register: vi.fn() }),
}));

vi.mock("../services/site", () => ({
  getPublicSiteConfig: vi.fn(),
}));

describe("RegisterPage", () => {
  it("renders the governed registration form", async () => {
    const html = await renderToString(createSSRApp(RegisterPage));

    expect(html).toContain("创建账号");
    expect(html).toContain('autocomplete="new-password"');
    expect(html).toContain("读取注册策略");
  });
});
