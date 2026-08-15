import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import ThirdPartyAuthorizePage from "./ThirdPartyAuthorizePage.vue";

vi.mock("vue-router", () => ({
  useRoute: () => ({
    query: {
      client_id: "pdc_synthetic-client",
      redirect_uri: "https://client.example/callback",
      response_type: "code",
      scope: "profile:read desktop:verification",
      state: "synthetic-state-value",
      code_challenge: "synthetic-code-challenge-value",
      code_challenge_method: "S256",
    },
  }),
}));

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({ accessToken: "synthetic-user-token" }),
}));

vi.mock("../services/thirdPartyApps", () => ({
  getThirdPartyAuthorizationRequest: vi.fn().mockResolvedValue({
    client_id: "pdc_synthetic-client",
    app_name: "合成桌面工具",
    developer_name: "合成开发者",
    description: "用于验证流程的合成应用",
    redirect_uri: "https://client.example/callback",
    requested_scopes: ["profile:read", "desktop:verification"],
    approved_scopes: ["profile:read", "desktop:verification"],
    previously_authorized: false,
  }),
  submitThirdPartyAuthorization: vi.fn(),
}));

describe("ThirdPartyAuthorizePage", () => {
  it("renders the app details, scopes and consent actions", async () => {
    const html = await renderToString(createSSRApp(ThirdPartyAuthorizePage));
    expect(html).toContain("合成桌面工具请求访问");
    expect(html).toContain("profile:read");
    expect(html).toContain("desktop:verification");
    expect(html).toContain("同意授权");
    expect(html).toContain("拒绝");
  });
});
