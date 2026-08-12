import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunityNotificationsPage from "./CommunityNotificationsPage.vue";

vi.mock("vue-router", () => ({
  RouterLink: {
    props: ["to"],
    template: "<a><slot /></a>",
  },
}));

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({ accessToken: "synthetic-access-token" }),
}));

vi.mock("../services/community", () => ({
  createCommunityIdempotencyKey: vi.fn(() => "synthetic-idempotency-key"),
  listCommunityNotifications: vi.fn(() => new Promise(() => undefined)),
  markAllCommunityNotificationsRead: vi.fn(),
  markCommunityNotificationRead: vi.fn(),
}));

describe("CommunityNotificationsPage", () => {
  it("renders the mention inbox and read controls", async () => {
    const html = await renderToString(createSSRApp(CommunityNotificationsPage));

    expect(html).toContain("社区通知中心");
    expect(html).toContain("提及我的内容");
    expect(html).toContain("未读 0");
    expect(html).toContain("全部已读");
    expect(html).toContain("通知仅保存最小化摘要");
  });
});
