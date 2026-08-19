import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it } from "vitest";
import MaintenancePage from "./MaintenancePage.vue";

describe("MaintenancePage", () => {
  it("renders the public message and contact without exposing internal settings", async () => {
    const app = createSSRApp(MaintenancePage, {
      siteName: "合成侦探站",
      siteLogoUrl: "",
      contactEmail: "contact@synthetic.example.com",
      maintenance: { active: true, message: "合成维护提示" },
    });

    const html = await renderToString(app);

    expect(html).toContain("合成侦探站");
    expect(html).toContain("系统维护中");
    expect(html).toContain("合成维护提示");
    expect(html).toContain("mailto:contact@synthetic.example.com");
    expect(html).not.toContain("allowed_ip");
  });
});
