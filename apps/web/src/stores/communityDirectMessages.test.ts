import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useCommunityDirectMessagesStore } from "./communityDirectMessages";

describe("community direct messages store", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it("does not move receipt or cursor backwards", () => {
    const store = useCommunityDirectMessagesStore();
    store.apply({
      type: "conversation.read",
      eventId: 8,
      conversationId: "c1",
      readerId: "peer",
      lastReadSequence: 5,
      readAt: "2026-08-16T00:00:00Z",
    });
    store.apply({
      type: "conversation.read",
      eventId: 7,
      conversationId: "c1",
      readerId: "peer",
      lastReadSequence: 3,
      readAt: "2026-08-16T00:00:01Z",
    });

    expect(store.latestEventId).toBe(8);
    expect(store.counterpartReadSequence.c1).toBe(5);
  });

  it("applies authoritative unread snapshots and ignores duplicates", () => {
    const store = useCommunityDirectMessagesStore();
    const event = {
      type: "unread.changed" as const,
      eventId: 4,
      conversationId: "c1",
      conversationUnreadCount: 2,
      totalUnreadCount: 5,
      changedAt: "2026-08-16T00:00:00Z",
    };

    expect(store.apply(event)).toBe(true);
    expect(store.apply(event)).toBe(false);
    expect(store.totalUnreadCount).toBe(5);
    expect(store.conversationUnread.c1).toBe(2);
  });

  it("increments conversation refresh only for accepted events", () => {
    const store = useCommunityDirectMessagesStore();
    const created = {
      type: "message.created" as const,
      eventId: 2,
      conversationId: "c1",
      messageId: "m1",
      messageSequence: 1,
      senderId: "peer",
      createdAt: "2026-08-16T00:00:00Z",
    };

    store.apply(created);
    store.apply(created);

    expect(store.conversationRevision.c1).toBe(1);
  });

  it("clears stale snapshots when the server requires a reset", () => {
    const store = useCommunityDirectMessagesStore();
    store.apply({
      type: "unread.changed",
      eventId: 3,
      conversationId: "c1",
      conversationUnreadCount: 2,
      totalUnreadCount: 2,
      changedAt: "2026-08-16T00:00:00Z",
    });

    store.apply({
      type: "ready",
      eventId: 8,
      totalUnreadCount: 1,
      resetRequired: true,
    });

    expect(store.latestEventId).toBe(8);
    expect(store.totalUnreadCount).toBe(1);
    expect(store.conversationUnread).toEqual({});
    expect(store.conversationRevision).toEqual({});
    expect(store.resetRevision).toBe(1);
  });

  it("only increments message refresh revisions for created messages", () => {
    const store = useCommunityDirectMessagesStore();

    store.apply({
      type: "message.created",
      eventId: 1,
      conversationId: "conversation-a",
      messageId: "message-a",
      messageSequence: 1,
      senderId: "sender-a",
      createdAt: "2026-08-16T00:00:00Z",
    });
    store.apply({
      type: "conversation.read",
      eventId: 2,
      conversationId: "conversation-a",
      readerId: "reader-a",
      lastReadSequence: 1,
      readAt: "2026-08-16T00:01:00Z",
    });
    store.apply({
      type: "unread.changed",
      eventId: 3,
      conversationId: "conversation-a",
      conversationUnreadCount: 0,
      totalUnreadCount: 0,
      changedAt: "2026-08-16T00:01:00Z",
    });

    expect(store.conversationMessageRevision["conversation-a"]).toBe(1);
    expect(store.conversationRevision["conversation-a"]).toBe(3);
  });
});
