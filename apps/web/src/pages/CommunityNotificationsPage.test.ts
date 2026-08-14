import { renderToString } from "@vue/server-renderer";
import { createPinia } from "pinia";
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
  getCommunityNotificationPreferences: vi.fn(() => new Promise(() => undefined)),
  listCommunityNotifications: vi.fn(() => new Promise(() => undefined)),
  markAllCommunityNotificationsRead: vi.fn(),
  markCommunityNotificationRead: vi.fn(),
  updateCommunityNotificationPreferences: vi.fn(),
}));

describe("CommunityNotificationsPage", () => {
  it("renders notification filters, preferences, and read controls", async () => {
    const app = createSSRApp(CommunityNotificationsPage);
    app.use(createPinia());
    const html = await renderToString(app);

    expect(html).toContain("社区通知中心");
    expect(html).toContain("通知类型筛选");
    expect(html).toContain("通知接收偏好");
    expect(html).toContain("提及");
    expect(html).toContain("回复");
    expect(html).toContain("关注");
    expect(html).toContain("未读 0");
    expect(html).toContain("全部已读");
    expect(html).toContain("实时通知未连接");
    expect(html).toContain("通知仅保存最小化摘要");
  });
});
