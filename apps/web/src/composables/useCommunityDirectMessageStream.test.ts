import { createPinia, setActivePinia } from "pinia";
import { effectScope, reactive } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useCommunityDirectMessageStream } from "./useCommunityDirectMessageStream";

const auth = reactive({
  isAuthenticated: true,
  accessToken: "token-a",
  user: { id: "user-a", username: "alice" } as { id: string; username: string } | null,
});
const streamCalls: Array<{ token: string; signal: AbortSignal; lastEventId: string | null }> = [];

vi.mock("../stores/auth", () => ({ useAuthStore: () => auth }));
vi.mock("../services/communityDirectMessageStream", () => ({
  consumeCommunityDirectMessageStream: vi.fn(
    (
      token: string,
      options: {
        signal: AbortSignal;
        lastEventId: string | null;
        handlers: { onOpen: () => void };
      },
    ) => {
      streamCalls.push({ token, signal: options.signal, lastEventId: options.lastEventId });
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
});
