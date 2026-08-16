import { storeToRefs } from "pinia";
import { onScopeDispose, watch } from "vue";
import { consumeCommunityDirectMessageStream } from "../services/communityDirectMessageStream";
import { useAuthStore } from "../stores/auth";
import { useCommunityDirectMessagesStore } from "../stores/communityDirectMessages";

const MAX_RECONNECT_DELAY_MS = 30_000;

export function useCommunityDirectMessageStream() {
  const auth = useAuthStore();
  const directMessages = useCommunityDirectMessagesStore();
  const { status, totalUnreadCount, conversationRevision, resetRevision } =
    storeToRefs(directMessages);
  let controller: AbortController | null = null;
  let generation = 0;
  let reconnectAttempt = 0;

  function cursorKey(userId: string): string {
    return `community-direct-message-last-event:${userId}`;
  }

  function stop(): void {
    generation += 1;
    controller?.abort();
    controller = null;
    reconnectAttempt = 0;
    directMessages.resetRuntime();
  }

  async function start(userId: string, accessToken: string): Promise<void> {
    const currentGeneration = generation;
    controller = new AbortController();
    const activeController = controller;
    directMessages.setStatus(navigator.onLine ? "connecting" : "offline");

    while (currentGeneration === generation && !activeController.signal.aborted) {
      if (!navigator.onLine) {
        directMessages.setStatus("offline");
        await delay(1_000, activeController.signal);
        continue;
      }
      try {
        await consumeCommunityDirectMessageStream(accessToken, {
          signal: activeController.signal,
          lastEventId: sessionStorage.getItem(cursorKey(userId)),
          handlers: {
            onOpen: () => {
              directMessages.setStatus("connected");
              reconnectAttempt = 0;
            },
            onEvent: (event) => {
              if (!directMessages.apply(event, userId)) return;
              sessionStorage.setItem(cursorKey(userId), String(event.eventId));
            },
          },
        });
        if (!activeController.signal.aborted) throw new Error("私信实时连接已结束");
      } catch {
        if (activeController.signal.aborted || currentGeneration !== generation) return;
        directMessages.setStatus(navigator.onLine ? "reconnecting" : "offline");
        reconnectAttempt += 1;
        const reconnectDelay = Math.min(
          MAX_RECONNECT_DELAY_MS,
          1_000 * 2 ** Math.min(reconnectAttempt - 1, 5),
        );
        await delay(reconnectDelay, activeController.signal);
      }
    }
  }

  function handleOnline(): void {
    const userId = auth.user?.id;
    if (auth.isAuthenticated && userId && auth.accessToken) {
      stop();
      void start(userId, auth.accessToken);
    }
  }

  function handleOffline(): void {
    directMessages.setStatus("offline");
    controller?.abort();
    controller = null;
  }

  watch(
    () => [auth.isAuthenticated, auth.accessToken, auth.user?.id ?? ""] as const,
    ([isAuthenticated, accessToken, userId], previous) => {
      const previousUserId = previous?.[2] ?? "";
      stop();
      if (previousUserId !== userId) directMessages.resetSnapshots();
      if (!isAuthenticated || !accessToken || !userId) return;
      void start(userId, accessToken);
    },
    { immediate: true },
  );

  window.addEventListener("online", handleOnline);
  window.addEventListener("offline", handleOffline);
  onScopeDispose(() => {
    stop();
    window.removeEventListener("online", handleOnline);
    window.removeEventListener("offline", handleOffline);
  });

  return {
    status,
    totalUnreadCount,
    conversationRevision,
    resetRevision,
    stop,
  };
}

function delay(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timeout = window.setTimeout(resolve, milliseconds);
    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timeout);
        resolve();
      },
      { once: true },
    );
  });
}
