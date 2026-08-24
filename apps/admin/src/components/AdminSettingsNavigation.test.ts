import { renderToString } from "@vue/server-renderer";
import { createSSRApp, defineComponent } from "vue";
import { describe, expect, it } from "vitest";
import AdminSettingsNavigation from "./AdminSettingsNavigation.vue";

const RouterLinkStub = defineComponent({
  props: {
    to: { type: String, required: true },
  },
  template: '<a :href="to"><slot /></a>',
});

describe("AdminSettingsNavigation", () => {
  it("links to the SEO workbench without exposing removed version history", async () => {
    const app = createSSRApp(AdminSettingsNavigation);
    app.component("RouterLink", RouterLinkStub);

    const html = await renderToString(app);

    expect(html).toContain("SEO 设置");
    expect(html).toContain("邀请码与邀请链接");
    expect(html).toContain("/registration");
    expect(html).toContain("/settings#seo-settings");
    expect(html).toContain("/settings#site-legal");
    expect(html).toContain("/settings#maintenance-governance");
    expect(html).toContain("/settings#session-governance");
    expect(html).not.toContain("版本历史");
    expect(html).not.toContain("/settings#version-history");
  });
});
