import { afterEach, describe, expect, it, vi } from "vitest";
import {
  consumeCommunityDirectMessageStream,
  parseDirectMessageSseEvent,
} from "./communityDirectMessageStream";

afterEach(() => vi.unstubAllGlobals());

describe("community direct message stream", () => {
  it("parses message.created without exposing message material", () => {
    const event = parseDirectMessageSseEvent(
      "message.created",
      "9",
      '{"event_id":"9","conversation_id":"c1","message_id":"m1","message_sequence":2,"sender_id":"u1","created_at":"2026-08-16T00:00:00Z","body":"must-not-leak"}',
    );

    expect(event).toEqual({
      type: "message.created",
      eventId: 9,
      conversationId: "c1",
      messageId: "m1",
      messageSequence: 2,
      senderId: "u1",
      createdAt: "2026-08-16T00:00:00Z",
    });
    expect(JSON.stringify(event)).not.toContain("body");
  });

  it("rejects malformed or unsupported domain events", () => {
    expect(() =>
      parseDirectMessageSseEvent("message.created", "bad", '{"event_id":"bad"}'),
    ).toThrow("私信实时事件游标无效");
    expect(() => parseDirectMessageSseEvent("typing", "1", "{}" )).toThrow(
      "不支持的私信实时事件",
    );
  });

  it("sends the replay cursor and dispatches ready plus unread snapshots", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            'id: 8\nevent: ready\ndata: {"event_id":"8","total_unread_count":2,"reset_required":false}\n\n',
          ),
        );
        controller.enqueue(
          encoder.encode(
            'id: 9\nevent: unread.changed\ndata: {"event_id":"9","conversation_id":"c1","conversation_unread_count":1,"total_unread_count":3,"changed_at":"2026-08-16T00:00:01Z"}\n\n',
          ),
        );
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-direct-stream-request" });
    const onOpen = vi.fn();
    const onEvent = vi.fn();

    await consumeCommunityDirectMessageStream("stream-token", {
      signal: new AbortController().signal,
      lastEventId: "7",
      handlers: { onOpen, onEvent },
    });

    expect(onOpen).toHaveBeenCalledOnce();
    expect(onEvent).toHaveBeenNthCalledWith(1, {
      type: "ready",
      eventId: 8,
      totalUnreadCount: 2,
      resetRequired: false,
    });
    expect(onEvent).toHaveBeenNthCalledWith(2, {
      type: "unread.changed",
      eventId: 9,
      conversationId: "c1",
      conversationUnreadCount: 1,
      totalUnreadCount: 3,
      changedAt: "2026-08-16T00:00:01Z",
    });
    const request = fetchMock.mock.calls[0];
    const headers = new Headers((request?.[1] as RequestInit | undefined)?.headers);
    expect(headers.get("Authorization")).toBe("Bearer stream-token");
    expect(headers.get("Last-Event-ID")).toBe("7");
    expect(headers.get("Accept")).toBe("text/event-stream");
  });
});
