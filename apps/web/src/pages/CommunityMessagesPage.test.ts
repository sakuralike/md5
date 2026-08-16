import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunityMessagesPage from "./CommunityMessagesPage.vue";

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
  listCommunityDirectConversations: vi.fn(() => Promise.resolve({
    items: [],
    next_cursor: null,
    has_more: false,
  })),
  updateCommunityDirectMemberState: vi.fn(),
}));

describe("CommunityMessagesPage", () => {
  it("renders the private message inbox and safe empty state", async () => {
    const html = await renderToString(createSSRApp(CommunityMessagesPage));

    expect(html).toContain("私信收件箱");
    expect(html).toContain("暂无私信会话");
    expect(html).toContain("仅会话成员可见");
  });
});
