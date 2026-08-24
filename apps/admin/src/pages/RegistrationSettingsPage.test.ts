import { renderToString } from "@vue/server-renderer";
import { createSSRApp, defineComponent } from "vue";
import { describe, expect, it, vi } from "vitest";
import RegistrationSettingsPage from "./RegistrationSettingsPage.vue";

vi.mock("@/components/RegistrationManagement.vue", () => ({
  default: { template: "<div>注册策略组件</div>" },
}));

describe("RegistrationSettingsPage", () => {
  it("renders a dedicated registration and referral entry", async () => {
    const app = createSSRApp(RegistrationSettingsPage);
    app.component(
      "RouterLink",
      defineComponent({
        props: { to: { type: String, required: true } },
        template: '<a :href="to"><slot /></a>',
      }),
    );
    const html = await renderToString(app);

    expect(html).toContain("注册与邀请");
    expect(html).toContain("邀请码注册为第一优先级");
    expect(html).toContain("设置邀请奖励积分");
    expect(html).toContain("注册策略组件");
  });
});
