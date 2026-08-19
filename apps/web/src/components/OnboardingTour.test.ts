import { renderToString } from "@vue/server-renderer";
import { createSSRApp, defineComponent } from "vue";
import { describe, expect, it } from "vitest";
import OnboardingTour from "./OnboardingTour.vue";

describe("OnboardingTour", () => {
  it("renders an accessible, non-modal tour that can be permanently dismissed", async () => {
    const app = createSSRApp(OnboardingTour, { initialOpen: true, autoOpen: false });
    app.component(
      "RouterLink",
      defineComponent({
        props: { to: { type: [String, Object], required: true } },
        template: "<a><slot /></a>",
      }),
    );

    const html = await renderToString(app);

    expect(html).toContain("新手引导");
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="false"');
    expect(html).toContain("跳过");
    expect(html).toContain("不再提示");
    expect(html).toContain("不上传服务器");
  });
});
