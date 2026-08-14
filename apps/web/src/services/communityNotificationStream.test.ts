import { afterEach, describe, expect, it, vi } from "vitest";
import { consumeCommunityNotificationStream } from "./communityNotificationStream";

afterEach(() => vi.unstubAllGlobals());

describe("community notification stream", () => {
  it("sends the replay cursor and parses ready plus notification events", async () => {
    const encoder = new TextEncoder();
    const body = [
      'id: event-ready\nevent: ready\ndata: {"event_id":"event-ready","unread_count":2}\n\n',
      'id: event-next\nevent: notification\ndata: {"event_id":"event-next","notification":{"id":"notice-1","kind":"reply","source_type":"comment","source_id":"comment-1","post_id":"post-1","comment_id":"comment-1","preview":"合成回复通知","actor":{"user_id":"actor-1","username":"actor","role":"user"},"read_at":null,"created_at":"2026-08-14T00:00:00Z"},"unread_count":3}\n\n',
    ];
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const chunk of body) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-stream-request" });
    const onOpen = vi.fn();
    const onReady = vi.fn();
    const onNotification = vi.fn();

    await consumeCommunityNotificationStream("stream-token", {
      signal: new AbortController().signal,
      lastEventId: "event-before",
      handlers: { onOpen, onReady, onNotification },
    });

    expect(onOpen).toHaveBeenCalledOnce();
    expect(onReady).toHaveBeenCalledWith({ event_id: "event-ready", unread_count: 2 });
    expect(onNotification).toHaveBeenCalledWith(
      expect.objectContaining({ event_id: "event-next", unread_count: 3 }),
    );
    const request = fetchMock.mock.calls[0];
    const headers = new Headers((request?.[1] as RequestInit | undefined)?.headers);
    expect(headers.get("Authorization")).toBe("Bearer stream-token");
    expect(headers.get("Last-Event-ID")).toBe("event-before");
    expect(headers.get("Accept")).toBe("text/event-stream");
  });
});
