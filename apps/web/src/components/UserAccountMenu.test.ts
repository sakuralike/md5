import type { User } from "@password-detective/api-contract";
import { renderToString } from "@vue/server-renderer";
import { createSSRApp, defineComponent } from "vue";
import { describe, expect, it, vi } from "vitest";
import UserAccountMenu from "./UserAccountMenu.vue";

const user: User = {
  id: "user-1",
  username: "sakura",
  email: "sakura@example.test",
  email_verified: true,
  status: "active",
  role: "user",
  reputation_score: 50,
  totp_enabled: false,
  created_at: "2026-08-01T00:00:00Z",
};


vi.mock("@/components/ui/dropdown-menu", () => {
  const passthrough = (tag: string) => defineComponent({
    inheritAttrs: false,
    template: `<${tag} v-bind="$attrs"><slot /></${tag}>`,
  });
  return {
    DropdownMenu: passthrough("div"),
    DropdownMenuContent: passthrough("div"),
    DropdownMenuItem: passthrough("div"),
    DropdownMenuLabel: passthrough("div"),
    DropdownMenuSeparator: defineComponent({ template: "<hr />" }),
    DropdownMenuTrigger: passthrough("div"),
  };
});

vi.mock("vue-router", async () => {
  const actual = await vi.importActual<typeof import("vue-router")>("vue-router");
  return {
    ...actual,
    RouterLink: defineComponent({
      props: { to: { type: [String, Object], required: true } },
      template: "<a><slot /></a>",
    }),
  };
});

describe("UserAccountMenu", () => {
  it("renders the avatar trigger and account actions", async () => {
    const app = createSSRApp(UserAccountMenu, {
      user,
      defaultOpen: true,
      unreadCount: 128,
      notificationStatus: "connected",
    });
    app.component(
      "RouterLink",
      defineComponent({
        props: { to: { type: [String, Object], required: true } },
        template: "<a><slot /></a>",
      }),
    );
    const html = await renderToString(app);

    expect(html).toContain("打开 sakura 的账户菜单");
    expect(html).toContain("用户中心");
    expect(html).toContain("社区通知");
    expect(html).toContain("99+");
    expect(html).toContain("实时连接正常");
    expect(html).toContain("退出登录");
    expect(html).toContain("sakura@example.test");
  });
});

