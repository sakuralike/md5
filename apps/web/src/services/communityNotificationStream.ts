import type {
  CommunityNotificationStreamEvent,
  CommunityNotificationStreamReady,
} from "@password-detective/api-contract";
import { apiStreamRequest } from "./api";

interface CommunityNotificationStreamHandlers {
  onOpen: () => void;
  onReady: (payload: CommunityNotificationStreamReady) => void;
  onNotification: (payload: CommunityNotificationStreamEvent) => void;
}

interface ParsedSseEvent {
  id: string | null;
  event: string;
  data: string;
}

export async function consumeCommunityNotificationStream(
  accessToken: string,
  options: {
    signal: AbortSignal;
    lastEventId: string | null;
    handlers: CommunityNotificationStreamHandlers;
  },
): Promise<void> {
  const response = await apiStreamRequest("/community/notifications/stream", accessToken, {
    signal: options.signal,
    lastEventId: options.lastEventId,
  });
  if (!response.body) throw new Error("通知实时连接没有返回可读取的数据流");
  options.handlers.onOpen();
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (!options.signal.aborted) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replaceAll("\r\n", "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const event = parseSseEvent(block);
      if (event) dispatchEvent(event, options.handlers);
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
}

function parseSseEvent(block: string): ParsedSseEvent | null {
  if (!block || block.startsWith(":")) return null;
  let id: string | null = null;
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("id:")) id = line.slice(3).trim();
    else if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (data.length === 0) return null;
  return { id, event, data: data.join("\n") };
}

function dispatchEvent(
  event: ParsedSseEvent,
  handlers: CommunityNotificationStreamHandlers,
): void {
  if (event.event === "ready") {
    handlers.onReady(JSON.parse(event.data) as CommunityNotificationStreamReady);
    return;
  }
  if (event.event === "notification") {
    const payload = JSON.parse(event.data) as CommunityNotificationStreamEvent;
    handlers.onNotification({ ...payload, event_id: event.id ?? payload.event_id });
  }
}
