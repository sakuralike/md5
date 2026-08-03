import type {
  RiskAlertAssignmentRequest,
  RiskAlertAssignmentResponse,
  RiskAlertDetail,
  RiskAlertKind,
  RiskAlertListResponse,
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
  return `admin-risk-alert-transition-${crypto.randomUUID()}`;
}

export function createRiskAlertAssignmentKey(): string {
  return `admin-risk-alert-assignment-${crypto.randomUUID()}`;
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
