import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import LoginPage from "./LoginPage.vue";

vi.mock("vue-router", () => ({
  RouterLink: {
    props: ["to"],
    template: "<a><slot /></a>",
  },
}));

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({
    busy: false,
    error: "",
    getRememberedLogin: () => "",
    login: vi.fn(),
  }),
}));

describe("LoginPage", () => {
  it("renders a centered user login form with Shadcn controls", async () => {
    const html = await renderToString(createSSRApp(LoginPage));

    expect(html).toContain("登录密码侦探社");
    expect(html).toMatch(/<h1[^>]*>登录密码侦探社<\/h1>/);
    expect(html).toContain("用户名或邮箱");
    expect(html).toContain("账号密码");
    expect(html).toContain("TOTP 验证码");
    expect(html).toContain("记住登录账号");
    expect(html).toContain("不会保存明文密码");
    expect(html).toContain('data-testid="user-login-form"');
    expect(html).toContain("flex flex-col gap-5");
    expect(html).toContain("欢迎回来");
    expect(html).toContain("glass-modal");
    expect(html).toContain("btn-gradient");
    expect(html).toContain('autocomplete="username"');
    expect(html).toContain("<button");
  });
});
