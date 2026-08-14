import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunityNotificationOutboxPage from "./CommunityNotificationOutboxPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/communityNotificationOutbox", () => ({
  createCommunityNotificationReplayKey: vi.fn(() => "synthetic-key"),
  getCommunityNotificationOutboxMetrics: vi.fn(),
  listCommunityNotificationOutbox: vi.fn(),
  replayCommunityNotificationOutbox: vi.fn(),
}));

vi.mock("../services/users", () => ({
  reauthenticateAdmin: vi.fn(),
}));

describe("CommunityNotificationOutboxPage", () => {
  it("renders failure metrics, filters, and fresh reauthentication controls", async () => {
    const html = await renderToString(createSSRApp(CommunityNotificationOutboxPage));

    expect(html).toContain("社区通知 Outbox 工作台");
    expect(html).toContain("24 小时失败");
    expect(html).toContain("错误代码");
    expect(html).toContain("受控单条重放");
    expect(html).toContain("当前密码");
    expect(html).toContain("TOTP 动态码");
    expect(html).not.toContain("synthetic-admin-token");
  });
});
