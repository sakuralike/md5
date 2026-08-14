import type {
  AdminCommunityNotificationOutboxListResponse,
  AdminCommunityNotificationOutboxMetrics,
  AdminCommunityNotificationReplayResponse,
  CommunityNotificationKind,
  CommunityNotificationOutboxStatus,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export interface CommunityNotificationOutboxFilters {
  status?: CommunityNotificationOutboxStatus;
  kind?: CommunityNotificationKind;
  errorCode?: string;
  page?: number;
  pageSize?: number;
}

function buildParams(filters: CommunityNotificationOutboxFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.errorCode?.trim()) params.set("error_code", filters.errorCode.trim());
  params.set("page", String(filters.page ?? 1));
  params.set("page_size", String(filters.pageSize ?? 20));
  return params;
}

export function listCommunityNotificationOutbox(
  filters: CommunityNotificationOutboxFilters,
  token: string,
): Promise<AdminCommunityNotificationOutboxListResponse> {
  return apiRequest<AdminCommunityNotificationOutboxListResponse>(
    `/admin/community/notification-outbox?${buildParams(filters).toString()}`,
    {},
    token,
  );
}

export function getCommunityNotificationOutboxMetrics(
  token: string,
): Promise<AdminCommunityNotificationOutboxMetrics> {
  return apiRequest<AdminCommunityNotificationOutboxMetrics>(
    "/admin/community/notification-outbox/metrics",
    {},
    token,
  );
}

export function replayCommunityNotificationOutbox(
  eventId: string,
  input: { reason: string; reauthToken: string },
  token: string,
  idempotencyKey: string,
): Promise<AdminCommunityNotificationReplayResponse> {
  return apiRequest<AdminCommunityNotificationReplayResponse>(
    `/admin/community/notification-outbox/${encodeURIComponent(eventId)}/replay`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ reason: input.reason, reauth_token: input.reauthToken }),
    },
    token,
  );
}

export function createCommunityNotificationReplayKey(): string {
  return `community-notification-replay-${crypto.randomUUID()}`;
}
