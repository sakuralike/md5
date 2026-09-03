import { storeToRefs } from "pinia";
import { onBeforeUnmount, watch } from "vue";
import { listCommunityNotifications } from "../services/community";
import { consumeCommunityNotificationStream } from "../services/communityNotificationStream";
import { useAuthStore } from "../stores/auth";
import { useCommunityNotificationsStore } from "../stores/communityNotifications";

const MAX_RECONNECT_DELAY_MS = 30_000;

export function useCommunityNotificationStream() {
  const auth = useAuthStore();
  const notifications = useCommunityNotificationsStore();
  const { unreadCount, status, latestNotification, eventRevision } = storeToRefs(notifications);
  let controller: AbortController | null = null;
  let generation = 0;
  let reconnectAttempt = 0;

  function cursorKey(userId: string): string {
    return `community-notification-last-event:${userId}`;
  }

  function stop(): void {
    generation += 1;
    controller?.abort();
    controller = null;
    reconnectAttempt = 0;
    notifications.setStatus("idle");
  }

  async function refreshUnreadCount(): Promise<void> {
    if (!auth.isAuthenticated || !auth.accessToken) {
      notifications.setUnreadCount(0);
      return;
    }
    try {
      const response = await listCommunityNotifications(auth.accessToken, {
        limit: 1,
        unreadOnly: true,
      });
      notifications.setUnreadCount(response.unread_count);
    } catch {
      // 实时连接仍会继续重试，避免全局导航因一次请求失败而中断。
    }
  }

  async function start(): Promise<void> {
    stop();
    if (!auth.isAuthenticated || !auth.accessToken || !auth.user) {
      notifications.reset();
      return;
    }
    const currentGeneration = generation;
    const userId = auth.user.id;
    const token = auth.accessToken;
    controller = new AbortController();
    const activeController = controller;
    notifications.setStatus(navigator.onLine ? "connecting" : "offline");
    await refreshUnreadCount();
    if (currentGeneration !== generation || activeController.signal.aborted) return;
    while (
      currentGeneration === generation &&
      !activeController.signal.aborted &&
      auth.isAuthenticated
    ) {
      if (!navigator.onLine) {
        notifications.setStatus("offline");
        await delay(1_000, activeController.signal);
        continue;
      }
      try {
        await consumeCommunityNotificationStream(token, {
          signal: activeController.signal,
          lastEventId: sessionStorage.getItem(cursorKey(userId)),
          handlers: {
            onOpen: () => {
              if (currentGeneration !== generation || activeController.signal.aborted) return;
              notifications.setStatus("connected");
              reconnectAttempt = 0;
            },
            onReady: (payload) => {
              if (currentGeneration !== generation || activeController.signal.aborted) return;
              notifications.setUnreadCount(payload.unread_count);
              if (payload.event_id) sessionStorage.setItem(cursorKey(userId), payload.event_id);
            },
            onNotification: (payload) => {
              if (currentGeneration !== generation || activeController.signal.aborted) return;
              notifications.receive(payload.notification, payload.unread_count);
              sessionStorage.setItem(cursorKey(userId), payload.event_id);
            },
          },
        });
        if (!activeController.signal.aborted) throw new Error("通知实时连接已结束");
      } catch (error) {
        if (activeController.signal.aborted || currentGeneration !== generation) return;
        notifications.setStatus(navigator.onLine ? "reconnecting" : "offline");
        reconnectAttempt += 1;
        const reconnectDelay = Math.min(
          MAX_RECONNECT_DELAY_MS,
          1_000 * 2 ** Math.min(reconnectAttempt - 1, 5),
        );
        if (error instanceof SyntaxError) sessionStorage.removeItem(cursorKey(userId));
        await delay(reconnectDelay, activeController.signal);
      }
    }
  }

  function handleOnline(): void {
    if (auth.isAuthenticated) void start();
  }

  function handleOffline(): void {
    notifications.setStatus("offline");
    controller?.abort();
    controller = null;
    if (auth.isAuthenticated) window.setTimeout(() => void start(), 0);
  }

  watch(
    () => [auth.isAuthenticated, auth.accessToken, auth.user?.id] as const,
    () => void start(),
    { immediate: true },
  );
  window.addEventListener("online", handleOnline);
  window.addEventListener("offline", handleOffline);
  onBeforeUnmount(() => {
    stop();
    window.removeEventListener("online", handleOnline);
    window.removeEventListener("offline", handleOffline);
  });

  return { unreadCount, status, latestNotification, eventRevision, refreshUnreadCount };
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
