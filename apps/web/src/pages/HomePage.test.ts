import { renderToString } from "@vue/server-renderer";
import { createSSRApp, defineComponent } from "vue";
import { describe, expect, it, vi } from "vitest";
import HomePage from "./HomePage.vue";

vi.mock("../services/site", () => ({
  getHomeDiscovery: vi.fn().mockResolvedValue({
    hot_hashes: [],
    contribution_leaders: [],
    points_leaders: [],
  }),
}));

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({
    isAuthenticated: false,
    accessToken: "",
  }),
}));

describe("HomePage", () => {
  it("renders the local fingerprint workflow with Shadcn controls", async () => {
    const app = createSSRApp(HomePage);
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

    expect(html).toContain("计算压缩包指纹，精确寻找可信候选");
    expect(html).toContain("本地文件查询");
    expect(html).toContain("手工指纹查询");
    expect(html).toContain("精确查询结果");
    expect(html).toContain("选择文件或输入完整指纹后开始查询");
    expect(html).toContain('type="file"');
    expect(html).toContain('data-testid="home-search-workspace"');
    expect(html).toContain("热门哈希值");
    expect(html).toContain("用户贡献排行榜");
    expect(html).toContain("用户积分排行榜");
  });
});
