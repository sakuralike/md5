import { createClientId } from "@/lib/clientId";
import type {
  RiskAlertAssignmentRequest,
  RiskAlertAssignmentResponse,
  RiskAlertDetail,
  RiskAlertKind,
  RiskAlertListResponse,
  RiskAlertNotificationKind,
  RiskAlertNotificationListResponse,
  RiskAlertNotificationMetricsResponse,
  RiskAlertNotificationReplayRequest,
  RiskAlertNotificationReplayResponse,
  RiskAlertNotificationStatus,
  RiskAlertOperator,
  RiskAlertSeverity,
  RiskAlertStatus,
  RiskAlertTransitionRequest,
  RiskAlertTransitionResponse,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export interface RiskAlertFilters {
  kind?: RiskAlertKind | "";
  severity?: RiskAlertSeverity | "";
  status?: RiskAlertStatus | "";
  assignedToId?: string;
  overdue?: boolean;
  query?: string;
  page?: number;
  pageSize?: number;
}

export function createRiskAlertTransitionKey(): string {
  return `admin-risk-alert-transition-${createClientId()}`;
}

export function createRiskAlertAssignmentKey(): string {
  return `admin-risk-alert-assignment-${createClientId()}`;
}

export function createRiskAlertNotificationReplayKey(): string {
  return `admin-risk-alert-notification-replay-${createClientId()}`;
}

export function listRiskAlerts(
  filters: RiskAlertFilters,
  token: string,
): Promise<RiskAlertListResponse> {
  const params = new URLSearchParams();
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.severity) params.set("severity", filters.severity);
  if (filters.status) params.set("status", filters.status);
  if (filters.assignedToId) params.set("assigned_to_id", filters.assignedToId);
  if (filters.overdue !== undefined) params.set("overdue", String(filters.overdue));
  const query = filters.query?.trim();
  if (query) params.set("query", query);
  params.set("page", String(filters.page ?? 1));
  params.set("page_size", String(filters.pageSize ?? 20));
  return apiRequest<RiskAlertListResponse>(`/admin/risk-alerts?${params.toString()}`, {}, token);
}

export function listRiskAlertOperators(token: string): Promise<RiskAlertOperator[]> {
  return apiRequest<RiskAlertOperator[]>("/admin/risk-alerts/operators", {}, token);
}

export function getRiskAlert(alertId: string, token: string): Promise<RiskAlertDetail> {
  return apiRequest<RiskAlertDetail>(
    `/admin/risk-alerts/${encodeURIComponent(alertId)}`,
    {},
    token,
  );
}

export function assignRiskAlert(
  alertId: string,
  payload: RiskAlertAssignmentRequest,
  token: string,
  idempotencyKey: string,
): Promise<RiskAlertAssignmentResponse> {
  return apiRequest<RiskAlertAssignmentResponse>(
    `/admin/risk-alerts/${encodeURIComponent(alertId)}/assign`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function transitionRiskAlert(
  alertId: string,
  payload: RiskAlertTransitionRequest,
  token: string,
  idempotencyKey: string,
): Promise<RiskAlertTransitionResponse> {
  return apiRequest<RiskAlertTransitionResponse>(
    `/admin/risk-alerts/${encodeURIComponent(alertId)}/transition`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}


export interface RiskAlertNotificationFilters {
  status?: RiskAlertNotificationStatus | "";
  kind?: RiskAlertNotificationKind | "";
  provider?: string;
  page?: number;
  pageSize?: number;
}

export function getRiskAlertNotificationMetrics(
  token: string,
): Promise<RiskAlertNotificationMetricsResponse> {
  return apiRequest<RiskAlertNotificationMetricsResponse>(
    "/admin/risk-alerts/notification-deliveries/metrics",
    {},
    token,
  );
}

export function listRiskAlertNotifications(
  filters: RiskAlertNotificationFilters,
  token: string,
): Promise<RiskAlertNotificationListResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.kind) params.set("kind", filters.kind);
  const provider = filters.provider?.trim();
  if (provider) params.set("provider", provider);
  params.set("page", String(filters.page ?? 1));
  params.set("page_size", String(filters.pageSize ?? 20));
  return apiRequest<RiskAlertNotificationListResponse>(
    `/admin/risk-alerts/notification-deliveries?${params.toString()}`,
    {},
    token,
  );
}

export function replayRiskAlertNotification(
  notificationId: string,
  payload: RiskAlertNotificationReplayRequest,
  token: string,
  idempotencyKey: string,
): Promise<RiskAlertNotificationReplayResponse> {
  return apiRequest<RiskAlertNotificationReplayResponse>(
    `/admin/risk-alerts/notification-deliveries/${encodeURIComponent(notificationId)}/replay`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}
