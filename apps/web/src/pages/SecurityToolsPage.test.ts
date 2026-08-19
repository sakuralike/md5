import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it } from "vitest";
import SecurityToolsPage from "./SecurityToolsPage.vue";

describe("SecurityToolsPage", () => {
  it("renders both local tools and their privacy boundary", async () => {
    const html = await renderToString(createSSRApp(SecurityToolsPage));

    expect(html).toContain("通用哈希计算器");
    expect(html).toContain("随机密码生成器");
    expect(html).toContain("MD5");
    expect(html).toContain("SHA-512");
    expect(html).toContain("不会发送到服务器");
    expect(html).toContain('type="file"');
    expect(html).toContain('aria-selected="false"');
  });
});
