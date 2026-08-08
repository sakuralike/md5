import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import LoginPage from "./LoginPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({
    busy: false,
    error: "",
    login: vi.fn(),
  }),
}));

describe("LoginPage", () => {
  it("renders the admin login workflow with Shadcn controls", async () => {
    const html = await renderToString(createSSRApp(LoginPage));

    expect(html).toContain("管理端登录");
    expect(html).toContain("用户名或邮箱");
    expect(html).toContain("密码");
    expect(html).toContain("动态验证码");
    expect(html).toContain("登录管理端");
    expect(html).toContain("<button");
    expect(html).toContain('autocomplete="username"');
  });
});
