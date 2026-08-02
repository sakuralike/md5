import type {
  RiskAlertDetail,
  RiskAlertKind,
  RiskAlertListResponse,
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
  query?: string;
  page?: number;
  pageSize?: number;
}

export function createRiskAlertTransitionKey(): string {
  return `admin-risk-alert-transition-${crypto.randomUUID()}`;
}

export function listRiskAlerts(
  filters: RiskAlertFilters,
  token: string,
): Promise<RiskAlertListResponse> {
  const params = new URLSearchParams();
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.severity) params.set("severity", filters.severity);
  if (filters.status) params.set("status", filters.status);
  const query = filters.query?.trim();
  if (query) params.set("query", query);
  params.set("page", String(filters.page ?? 1));
  params.set("page_size", String(filters.pageSize ?? 20));
  return apiRequest<RiskAlertListResponse>(`/admin/risk-alerts?${params.toString()}`, {}, token);
}

export function getRiskAlert(alertId: string, token: string): Promise<RiskAlertDetail> {
  return apiRequest<RiskAlertDetail>(
    `/admin/risk-alerts/${encodeURIComponent(alertId)}`,
    {},
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
