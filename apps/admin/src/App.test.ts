import { renderToString } from "@vue/server-renderer";
import { createSSRApp, defineComponent } from "vue";
import { describe, expect, it, vi } from "vitest";
import App from "./App.vue";

const logout = vi.fn();

vi.mock("./stores/auth", () => ({
  useAdminAuthStore: () => ({
    isAuthenticated: true,
    logout,
  }),
}));

const RouterLinkStub = defineComponent({
  props: {
    to: { type: String, required: true },
  },
  template: '<a :href="to"><slot /></a>',
});

const RouterViewStub = defineComponent({
  template: "<section>路由内容</section>",
});

describe("App", () => {
  it("renders responsive governed navigation with an accessible label", async () => {
    const app = createSSRApp(App);
    app.component("RouterLink", RouterLinkStub);
    app.component("RouterView", RouterViewStub);

    const html = await renderToString(app);

    expect(html).toContain('href="#main-content"');
    expect(html).toContain("跳到主要内容");
    expect(html).toContain('id="main-content"');
    expect(html).toContain('tabindex="-1"');
    expect(html).toContain('aria-label="管理导航"');
    expect(html).toContain("候选审核");
    expect(html).toContain("角色审批");
    expect(html).toContain("社区配置");
    expect(html).toContain("系统配置");
    expect(html).toContain("overflow-x-auto");
    expect(html).toContain("focus-visible:ring-2");
    expect(html).toContain("退出");
  });
});
