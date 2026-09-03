import { createPinia, setActivePinia } from "pinia";
import { effectScope, reactive } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useCommunityDirectMessageStream } from "./useCommunityDirectMessageStream";
import { useCommunityDirectMessagesStore } from "../stores/communityDirectMessages";

const auth = reactive({
  isAuthenticated: true,
  accessToken: "token-a",
  user: { id: "user-a", username: "alice" } as { id: string; username: string } | null,
});
const streamCalls: Array<{
  token: string;
  signal: AbortSignal;
  lastEventId: string | null;
  handlers: { onOpen: () => void; onEvent: (event: unknown) => void };
}> = [];

vi.mock("../stores/auth", () => ({ useAuthStore: () => auth }));
vi.mock("../services/communityDirectMessageStream", () => ({
  consumeCommunityDirectMessageStream: vi.fn(
    (
      token: string,
      options: {
        signal: AbortSignal;
        lastEventId: string | null;
        handlers: { onOpen: () => void; onEvent: (event: unknown) => void };
      },
    ) => {
      streamCalls.push({
        token,
        signal: options.signal,
        lastEventId: options.lastEventId,
        handlers: options.handlers,
      });
      options.handlers.onOpen();
      return new Promise<void>((resolve) => {
        options.signal.addEventListener("abort", () => resolve(), { once: true });
      });
    },
  ),
}));

const storage = new Map<string, string>();

beforeEach(() => {
  setActivePinia(createPinia());
  auth.isAuthenticated = true;
  auth.accessToken = "token-a";
  auth.user = { id: "user-a", username: "alice" };
  streamCalls.length = 0;
  storage.clear();
  storage.set("community-direct-message-last-event:user-a", "7");
  vi.stubGlobal("sessionStorage", {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
  });
  vi.stubGlobal("navigator", { onLine: true });
  vi.stubGlobal("window", {
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    setTimeout,
    clearTimeout,
  });
});

afterEach(() => vi.unstubAllGlobals());

async function flushAsyncWork(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

describe("useCommunityDirectMessageStream", () => {
  it("closes the previous stream when the authenticated user changes", async () => {
    const scope = effectScope();
    const stream = scope.run(() => useCommunityDirectMessageStream());
    await flushAsyncWork();

    expect(streamCalls[0]?.lastEventId).toBe("7");
    const firstSignal = streamCalls[0]?.signal;
    auth.accessToken = "token-b";
    auth.user = { id: "user-b", username: "bob" };
    await flushAsyncWork();

    expect(firstSignal?.aborted).toBe(true);
    expect(streamCalls[1]?.token).toBe("token-b");
    expect(streamCalls[1]?.lastEventId).toBeNull();

    stream?.stop();
    scope.stop();
    expect(streamCalls[1]?.signal.aborted).toBe(true);
  });

  it("ignores events delivered by a stream invalidated during an auth change", async () => {
    const scope = effectScope();
    scope.run(() => useCommunityDirectMessageStream());
    await flushAsyncWork();

    const staleHandlers = streamCalls[0]?.handlers;
    expect(staleHandlers).toBeDefined();
    auth.accessToken = "token-b";
    auth.user = { id: "user-b", username: "bob" };
    await flushAsyncWork();

    staleHandlers?.onEvent({
      type: "unread.changed",
      eventId: 99,
      conversationId: "stale-conversation",
      conversationUnreadCount: 99,
      totalUnreadCount: 99,
      changedAt: "2026-09-03T00:00:00Z",
    });

    expect(useCommunityDirectMessagesStore().totalUnreadCount).toBe(0);
    scope.stop();
  });
});
