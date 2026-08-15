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
    expect(html).toContain('aria-label="管理主导航"');
    expect(html).toContain('aria-label="后台设置导航"');
    expect(html).toContain("仪表盘");
    expect(html).toContain("候选审核");
    expect(html).toContain("第三方 API");
    expect(html).toContain("角色审批");
    expect(html).toContain("社区配置");
    expect(html).toContain("系统配置");
    expect(html).toContain("fixed bottom-4 left-4 top-24");
    expect(html).toContain("fixed inset-x-0 top-0 z-50");
    expect(html).toContain('aria-label="系统配置二级导航"');
    expect(html).toContain("站点外观");
    expect(html).toContain("用户等级与权益");
    expect(html).toContain("发布门禁");
    expect(html).toContain("lg:pl-[18rem]");
    expect(html).toContain("focus-visible:ring-2");
    expect(html).toContain("bg-gradient-to-br from-primary to-accent");
    expect(html).toContain("backdrop-blur-2xl");
    expect(html).toContain("退出");
  });
});
