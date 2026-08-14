import type { CommunityNotificationResponse } from "@password-detective/api-contract";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import {
  mergeCommunityNotificationItems,
  useCommunityNotificationsStore,
} from "./communityNotifications";

function notification(
  id: string,
  createdAt: string,
  readAt: string | null = null,
): CommunityNotificationResponse {
  return {
    id,
    kind: "mention",
    source_type: "post",
    source_id: `source-${id}`,
    post_id: `post-${id}`,
    comment_id: null,
    preview: `synthetic preview ${id}`,
    actor: {
      user_id: `actor-${id}`,
      username: `actor_${id}`,
      role: "user",
    },
    read_at: readAt,
    created_at: createdAt,
  };
}

describe("community notifications store", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it("deduplicates incoming notifications and keeps newest items first", () => {
    const oldItem = notification("same", "2026-08-14T01:00:00Z");
    const refreshedItem = {
      ...notification("same", "2026-08-14T01:00:00Z"),
      preview: "refreshed preview",
    };
    const newestItem = notification("new", "2026-08-14T02:00:00Z");

    const result = mergeCommunityNotificationItems([oldItem], [refreshedItem, newestItem]);

    expect(result.map((item) => item.id)).toEqual(["new", "same"]);
    expect(result[1]?.preview).toBe("refreshed preview");
  });

  it("shares stream unread state and emits a revision for each event", () => {
    const store = useCommunityNotificationsStore();
    const item = notification("event-1", "2026-08-14T03:00:00Z");

    store.receive(item, 4);

    expect(store.unreadCount).toBe(4);
    expect(store.latestNotification?.id).toBe("event-1");
    expect(store.eventRevision).toBe(1);

    store.setUnreadCount(-2);
    expect(store.unreadCount).toBe(0);
  });
});
