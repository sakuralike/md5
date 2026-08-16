import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import CommunityConversationPage from "./CommunityConversationPage.vue";

vi.mock("vue-router", () => ({
  RouterLink: {
    props: ["to"],
    template: "<a><slot /></a>",
  },
  useRoute: () => ({ params: { conversationId: "synthetic-conversation-id" } }),
}));

vi.mock("../stores/auth", () => ({
  useAuthStore: () => ({
    accessToken: "synthetic-access-token",
    user: { username: "synthetic-viewer" },
  }),
}));

vi.mock("../services/community", () => ({
  createCommunityIdempotencyKey: vi.fn(() => "synthetic-idempotency-key"),
  listCommunityDirectMessages: vi.fn(() => Promise.resolve({
    items: [],
    next_cursor: null,
    has_more: false,
  })),
  sendCommunityDirectMessage: vi.fn(),
  updateCommunityDirectReadState: vi.fn(),
}));

describe("CommunityConversationPage", () => {
  it("renders the conversation composer and privacy notice", async () => {
    const html = await renderToString(createSSRApp(CommunityConversationPage));

    expect(html).toContain("私信会话");
    expect(html).toContain("消息内容");
    expect(html).toContain("发送消息");
    expect(html).toContain("端到端加密");
  });
});
