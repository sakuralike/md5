import type { CommunityDirectStreamEvent } from "@password-detective/api-contract";
import { apiStreamRequest } from "./api";

interface CommunityDirectMessageStreamHandlers {
  onOpen: () => void;
  onEvent: (event: CommunityDirectStreamEvent) => void;
}

interface ParsedSseEvent {
  id: string | null;
  event: string;
  data: string;
}

type JsonRecord = Record<string, unknown>;

export async function consumeCommunityDirectMessageStream(
  accessToken: string,
  options: {
    signal: AbortSignal;
    lastEventId: string | null;
    handlers: CommunityDirectMessageStreamHandlers;
  },
): Promise<void> {
  const response = await apiStreamRequest("/community/direct-messages/stream", accessToken, {
    signal: options.signal,
    lastEventId: options.lastEventId,
  });
  if (!response.body) throw new Error("私信实时连接没有返回可读取的数据流");
  options.handlers.onOpen();
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (!options.signal.aborted) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done }).replaceAll("\r\n", "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const parsed = parseSseBlock(block);
        if (parsed) {
          options.handlers.onEvent(
            parseDirectMessageSseEvent(parsed.event, parsed.id, parsed.data),
          );
        }
        boundary = buffer.indexOf("\n\n");
      }
      if (done) break;
    }
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

export function parseDirectMessageSseEvent(
  eventName: string,
  sseEventId: string | null,
  rawData: string,
): CommunityDirectStreamEvent {
  const payload = parseRecord(rawData);
  const eventId = parseEventId(sseEventId ?? readString(payload, "event_id"));
  const payloadEventId = readOptionalString(payload, "event_id");
  if (payloadEventId !== null && parseEventId(payloadEventId) !== eventId) {
    throw new Error("私信实时事件游标不一致");
  }

  if (eventName === "ready") {
    return {
      type: "ready",
      eventId,
      totalUnreadCount: readNonNegativeInteger(payload, "total_unread_count"),
      resetRequired: readBoolean(payload, "reset_required"),
    };
  }
  if (eventName === "message.created") {
    return {
      type: "message.created",
      eventId,
      conversationId: readString(payload, "conversation_id"),
      messageId: readString(payload, "message_id"),
      messageSequence: readNonNegativeInteger(payload, "message_sequence"),
      senderId: readString(payload, "sender_id"),
      createdAt: readString(payload, "created_at"),
    };
  }
  if (eventName === "conversation.read") {
    return {
      type: "conversation.read",
      eventId,
      conversationId: readString(payload, "conversation_id"),
      readerId: readString(payload, "reader_id"),
      lastReadSequence: readNonNegativeInteger(payload, "last_read_sequence"),
      readAt: readString(payload, "read_at"),
    };
  }
  if (eventName === "unread.changed") {
    return {
      type: "unread.changed",
      eventId,
      conversationId: readString(payload, "conversation_id"),
      conversationUnreadCount: readNonNegativeInteger(
        payload,
        "conversation_unread_count",
      ),
      totalUnreadCount: readNonNegativeInteger(payload, "total_unread_count"),
      changedAt: readString(payload, "changed_at"),
    };
  }
  throw new Error(`不支持的私信实时事件: ${eventName}`);
}

function parseSseBlock(block: string): ParsedSseEvent | null {
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

function parseRecord(rawData: string): JsonRecord {
  let value: unknown;
  try {
    value = JSON.parse(rawData) as unknown;
  } catch {
    throw new Error("私信实时事件不是有效 JSON");
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("私信实时事件负载必须是对象");
  }
  return value as JsonRecord;
}

function parseEventId(value: string): number {
  if (!/^\d+$/.test(value)) throw new Error("私信实时事件游标无效");
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 0) {
    throw new Error("私信实时事件游标无效");
  }
  return parsed;
}

function readOptionalString(record: JsonRecord, key: string): string | null {
  const value = record[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function readString(record: JsonRecord, key: string): string {
  const value = readOptionalString(record, key);
  if (value === null) throw new Error(`私信实时事件字段无效: ${key}`);
  return value;
}

function readNonNegativeInteger(record: JsonRecord, key: string): number {
  const value = record[key];
  if (!Number.isSafeInteger(value) || typeof value !== "number" || value < 0) {
    throw new Error(`私信实时事件字段无效: ${key}`);
  }
  return value;
}

function readBoolean(record: JsonRecord, key: string): boolean {
  const value = record[key];
  if (typeof value !== "boolean") throw new Error(`私信实时事件字段无效: ${key}`);
  return value;
}
