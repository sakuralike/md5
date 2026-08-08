import type {
  TrustCaseAssignRequest,
  TrustCaseAssignResponse,
  TrustCaseDetail,
  TrustCaseKind,
  TrustCaseListResponse,
  TrustCaseNotification,
  TrustCaseNotificationReplayRequest,
  TrustCaseResolveRequest,
  TrustCaseResolveResponse,
  TrustCaseReopenRequest,
  TrustCaseReopenResponse,
  TrustCaseStatus,
  TrustCaseTransitionRequest,
  TrustCaseTransitionResponse,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export interface TrustCaseFilters {
  kind?: TrustCaseKind | "";
  status?: TrustCaseStatus | "";
  query?: string;
  page?: number;
  pageSize?: number;
}

export function createTrustCaseTransitionKey(): string {
  return `admin-trust-case-transition-${crypto.randomUUID()}`;
}

export function createTrustCaseAssignKey(): string {
  return `admin-trust-case-assign-${crypto.randomUUID()}`;
}

export function createTrustCaseReopenKey(): string {
  return `admin-trust-case-reopen-${crypto.randomUUID()}`;
}

export function createTrustCaseResolveKey(): string {
  return `admin-trust-case-resolve-${crypto.randomUUID()}`;
}

export function createTrustCaseNotificationReplayKey(): string {
  return `admin-trust-case-notification-replay-${crypto.randomUUID()}`;
}

export function listTrustCases(
  filters: TrustCaseFilters,
  token: string,
): Promise<TrustCaseListResponse> {
  const params = new URLSearchParams();
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.status) params.set("status", filters.status);
  const query = filters.query?.trim();
  if (query) params.set("query", query);
  params.set("page", String(filters.page ?? 1));
  params.set("page_size", String(filters.pageSize ?? 20));
  return apiRequest<TrustCaseListResponse>(`/admin/trust-cases?${params.toString()}`, {}, token);
}

export function getTrustCase(caseId: string, token: string): Promise<TrustCaseDetail> {
  return apiRequest<TrustCaseDetail>(
    `/admin/trust-cases/${encodeURIComponent(caseId)}`,
    {},
    token,
  );
}

export function transitionTrustCase(
  caseId: string,
  payload: TrustCaseTransitionRequest,
  token: string,
  idempotencyKey: string,
): Promise<TrustCaseTransitionResponse> {
  return apiRequest<TrustCaseTransitionResponse>(
    `/admin/trust-cases/${encodeURIComponent(caseId)}/transition`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}


export function assignTrustCase(
  caseId: string,
  payload: TrustCaseAssignRequest,
  token: string,
  idempotencyKey: string,
): Promise<TrustCaseAssignResponse> {
  return apiRequest<TrustCaseAssignResponse>(
    `/admin/trust-cases/${encodeURIComponent(caseId)}/assign`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function reopenTrustCase(
  caseId: string,
  payload: TrustCaseReopenRequest,
  token: string,
  idempotencyKey: string,
): Promise<TrustCaseReopenResponse> {
  return apiRequest<TrustCaseReopenResponse>(
    `/admin/trust-cases/${encodeURIComponent(caseId)}/reopen`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function resolveTrustCase(
  caseId: string,
  payload: TrustCaseResolveRequest,
  token: string,
  idempotencyKey: string,
): Promise<TrustCaseResolveResponse> {
  return apiRequest<TrustCaseResolveResponse>(
    `/admin/trust-cases/${encodeURIComponent(caseId)}/resolve`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function replayTrustCaseNotification(
  notificationId: string,
  payload: TrustCaseNotificationReplayRequest,
  token: string,
  idempotencyKey: string,
): Promise<TrustCaseNotification> {
  return apiRequest<TrustCaseNotification>(
    `/admin/trust-cases/notifications/${encodeURIComponent(notificationId)}/replay`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}
