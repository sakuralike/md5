import type {
  CommunityNotificationResponse,
  CommunityNotificationStreamStatus,
} from "@password-detective/api-contract";
import { defineStore } from "pinia";
import { ref, shallowRef } from "vue";

export function mergeCommunityNotificationItems(
  existing: CommunityNotificationResponse[],
  incoming: CommunityNotificationResponse[],
): CommunityNotificationResponse[] {
  const byId = new Map<string, CommunityNotificationResponse>();
  for (const item of existing) byId.set(item.id, item);
  for (const item of incoming) byId.set(item.id, item);
  return [...byId.values()].sort((left, right) => {
    const createdDifference = Date.parse(right.created_at) - Date.parse(left.created_at);
    return createdDifference !== 0 ? createdDifference : right.id.localeCompare(left.id);
  });
}

export const useCommunityNotificationsStore = defineStore("community-notifications", () => {
  const unreadCount = ref(0);
  const status = ref<CommunityNotificationStreamStatus>("idle");
  const latestNotification = shallowRef<CommunityNotificationResponse | null>(null);
  const eventRevision = ref(0);

  function setUnreadCount(value: number): void {
    unreadCount.value = Math.max(0, Math.trunc(value));
  }

  function setStatus(value: CommunityNotificationStreamStatus): void {
    status.value = value;
  }

  function receive(notification: CommunityNotificationResponse, nextUnreadCount: number): void {
    latestNotification.value = { ...notification };
    setUnreadCount(nextUnreadCount);
    eventRevision.value += 1;
  }

  function reset(): void {
    unreadCount.value = 0;
    status.value = "idle";
    latestNotification.value = null;
    eventRevision.value += 1;
  }

  return {
    unreadCount,
    status,
    latestNotification,
    eventRevision,
    setUnreadCount,
    setStatus,
    receive,
    reset,
  };
});
