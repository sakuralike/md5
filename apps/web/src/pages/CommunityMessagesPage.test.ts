import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { createPinia } from "pinia";
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
    items: [{
      id: "conversation-1",
      counterpart_username: "synthetic-peer",
      counterpart_display_name: "Synthetic Peer",
      counterpart_avatar_seed: "synthetic-seed",
      counterpart_avatar_url: null,
      last_message_at: "2026-08-16T00:00:00Z",
      unread_count: 3,
      last_read_sequence: 0,
      archived_at: null,
      muted_until: null,
      created_at: "2026-08-16T00:00:00Z",
      updated_at: "2026-08-16T00:00:00Z",
    }],
    next_cursor: null,
    has_more: false,
  })),
  updateCommunityDirectMemberState: vi.fn(),
}));

describe("CommunityMessagesPage", () => {
  it("renders the private message inbox and safe empty state", async () => {
    const app = createSSRApp(CommunityMessagesPage);
    app.use(createPinia());
    const html = await renderToString(app);

    expect(html).toContain("私信收件箱");
    expect(html).toContain("Synthetic Peer");
    expect(html).toContain("未读 3");
    expect(html).toContain("仅会话成员可见");
  });
});
