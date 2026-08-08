import { renderToString } from "@vue/server-renderer";
import { createSSRApp, defineComponent } from "vue";
import { describe, expect, it, vi } from "vitest";
import TrustCasesPage from "./TrustCasesPage.vue";

vi.mock("vue-router", () => ({
  useRoute: () => ({
    query: {},
  }),
}));

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({
    accessToken: "synthetic-access-token",
  }),
}));

vi.mock("../services/trustCases", () => ({
  createAppeal: vi.fn(),
  createReport: vi.fn(),
  createTrustCaseSubmissionKey: vi.fn(() => "synthetic-idempotency-key"),
  listMyTrustCases: vi.fn(),
}));

describe("TrustCasesPage", () => {
  it("renders the report and appeal workflow with Shadcn controls", async () => {
    const app = createSSRApp(TrustCasesPage);
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

    expect(html).toContain("举报与申诉");
    expect(html).toContain("提交举报");
    expect(html).toContain("发起申诉");
    expect(html).toContain("候选 ID");
    expect(html).toContain("原因");
    expect(html).toContain("我的案件");
    expect(html).toContain("正在加载案件");
  });
});
