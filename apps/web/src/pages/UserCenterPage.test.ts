import { renderToString } from "@vue/server-renderer";
import { createSSRApp, defineComponent } from "vue";
import { describe, expect, it, vi } from "vitest";
import UserCenterPage from "./UserCenterPage.vue";

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({
    user: {
      id: "user-1",
      username: "sakura",
      email: "sakura@example.test",
      email_verified: true,
      status: "active",
      role: "user",
      reputation_score: 50,
      totp_enabled: false,
      created_at: "2026-08-01T00:00:00Z",
    },
    accessToken: "token",
  }),
}));

vi.mock("../services/reputation", () => ({
  loadTrustCenter: vi.fn().mockResolvedValue(null),
}));

describe("UserCenterPage", () => {
  it("renders the independent account workspace and quick entries", async () => {
    const app = createSSRApp(UserCenterPage);
    app.component(
      "RouterLink",
      defineComponent({
        props: {
          to: {
            type: [String, Object],
            required: true,
          },
        },
        template: "<a><slot /></a>",
      }),
    );

    const html = await renderToString(app);

    expect(html).toContain("用户中心");
    expect(html).toContain("sakura");
    expect(html).toContain("sakura@example.test");
    expect(html).toContain("快捷入口");
    expect(html).toContain("个人资料");
    expect(html).toContain("账号安全");
    expect(html).toContain("打开 个人资料");
  });
});

