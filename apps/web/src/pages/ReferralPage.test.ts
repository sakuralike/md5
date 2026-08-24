import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import ReferralPage from "./ReferralPage.vue";

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({ accessToken: "synthetic-access-token" }),
}));

vi.mock("../services/referrals", () => ({
  getMyReferralProfile: vi.fn(),
}));

vi.mock("../services/site", () => ({
  getPublicSiteConfig: vi.fn(),
}));

describe("ReferralPage", () => {
  it("renders the referral reward workspace", async () => {
    const html = await renderToString(createSSRApp(ReferralPage));

    expect(html).toContain("邀请好友注册");
    expect(html).toContain("正在加载邀请信息");
  });
});
