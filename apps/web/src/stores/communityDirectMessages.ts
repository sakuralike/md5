import type {
  CommunityDirectStreamEvent,
  CommunityDirectStreamStatus,
} from "@password-detective/api-contract";
import { defineStore } from "pinia";
import { reactive, ref } from "vue";

export const useCommunityDirectMessagesStore = defineStore(
  "community-direct-messages",
  () => {
    const status = ref<CommunityDirectStreamStatus>("idle");
    const latestEventId = ref(0);
    const totalUnreadCount = ref(0);
    const conversationUnread = reactive<Record<string, number>>({});
    const counterpartReadSequence = reactive<Record<string, number>>({});
    const conversationRevision = reactive<Record<string, number>>({});
    const resetRevision = ref(0);

    function setStatus(nextStatus: CommunityDirectStreamStatus): void {
      status.value = nextStatus;
    }

    function apply(event: CommunityDirectStreamEvent, currentUserId?: string): boolean {
      if (event.type === "ready") {
        if (event.eventId < latestEventId.value && !event.resetRequired) return false;
        if (event.resetRequired) {
          clearRecord(conversationUnread);
          clearRecord(counterpartReadSequence);
          clearRecord(conversationRevision);
          resetRevision.value += 1;
        }
        latestEventId.value = event.eventId;
        totalUnreadCount.value = event.totalUnreadCount;
        return true;
      }
      if (event.eventId <= latestEventId.value) return false;
      latestEventId.value = event.eventId;

      if (event.type === "unread.changed") {
        conversationUnread[event.conversationId] = event.conversationUnreadCount;
        totalUnreadCount.value = event.totalUnreadCount;
      } else if (
        event.type === "conversation.read" &&
        (currentUserId === undefined || event.readerId !== currentUserId)
      ) {
        counterpartReadSequence[event.conversationId] = Math.max(
          counterpartReadSequence[event.conversationId] ?? 0,
          event.lastReadSequence,
        );
      }
      conversationRevision[event.conversationId] =
        (conversationRevision[event.conversationId] ?? 0) + 1;
      return true;
    }

    function resetRuntime(): void {
      status.value = "idle";
    }

    function resetSnapshots(): void {
      latestEventId.value = 0;
      totalUnreadCount.value = 0;
      clearRecord(conversationUnread);
      clearRecord(counterpartReadSequence);
      clearRecord(conversationRevision);
      resetRevision.value += 1;
    }

    return {
      status,
      latestEventId,
      totalUnreadCount,
      conversationUnread,
      counterpartReadSequence,
      conversationRevision,
      resetRevision,
      setStatus,
      apply,
      resetRuntime,
      resetSnapshots,
    };
  },
);

function clearRecord(record: Record<string, number>): void {
  for (const key of Object.keys(record)) delete record[key];
}
