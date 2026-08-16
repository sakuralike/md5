import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { createPinia } from "pinia";
import { describe, expect, it, vi } from "vitest";
import { updateCommunityDirectReadState } from "../services/community";
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
    user: { id: "viewer-id", username: "synthetic-viewer" },
  }),
}));

vi.mock("../services/community", () => ({
  createCommunityIdempotencyKey: vi.fn(() => "synthetic-idempotency-key"),
  listCommunityDirectMessages: vi.fn(() => Promise.resolve({
    items: [{
      id: "message-3",
      conversation_id: "synthetic-conversation-id",
      sender_username: "synthetic-viewer",
      body: "仅用于已读回执测试的合成消息",
      sequence: 3,
      created_at: "2026-08-16T00:00:00Z",
    }],
    next_cursor: null,
    has_more: false,
    last_read_sequence: 3,
    counterpart_last_read_sequence: 3,
    unread_count: 0,
  })),
  sendCommunityDirectMessage: vi.fn(),
  updateCommunityDirectReadState: vi.fn(),
}));

describe("CommunityConversationPage", () => {
  it("renders the conversation composer and privacy notice", async () => {
    const app = createSSRApp(CommunityConversationPage);
    app.use(createPinia());
    const html = await renderToString(app);

    expect(html).toContain("私信会话");
    expect(html).toContain("消息内容");
    expect(html).toContain("发送消息");
    expect(html).toContain("端到端加密");
    expect(html).toContain("对方已读");
    expect(updateCommunityDirectReadState).not.toHaveBeenCalled();
  });
});
