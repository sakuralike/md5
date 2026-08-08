import type {
  AccountAppealCreateRequest,
  AppealCreateRequest,
  ReportCreateRequest,
  TrustCaseDetail,
  TrustCaseKind,
  TrustCaseListResponse,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export function createTrustCaseSubmissionKey(kind: TrustCaseKind): string {
  return `web-trust-${kind}-${crypto.randomUUID()}`;
}

export function listMyTrustCases(
  token: string,
  kind?: TrustCaseKind | "",
): Promise<TrustCaseListResponse> {
  const params = new URLSearchParams({ page: "1", page_size: "50" });
  if (kind) params.set("kind", kind);
  return apiRequest<TrustCaseListResponse>(`/trust/cases?${params.toString()}`, {}, token);
}

export function createReport(
  payload: ReportCreateRequest,
  token: string,
  idempotencyKey: string,
): Promise<TrustCaseDetail> {
  return apiRequest<TrustCaseDetail>(
    "/trust/reports",
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function createAppeal(
  payload: AppealCreateRequest,
  token: string,
  idempotencyKey: string,
): Promise<TrustCaseDetail> {
  return apiRequest<TrustCaseDetail>(
    "/trust/appeals",
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function createAccountAppeal(
  payload: AccountAppealCreateRequest,
  token: string,
  idempotencyKey: string,
): Promise<TrustCaseDetail> {
  return apiRequest<TrustCaseDetail>(
    "/trust/account-appeals",
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function getMyTrustCase(caseId: string, token: string): Promise<TrustCaseDetail> {
  return apiRequest<TrustCaseDetail>(
    `/trust/cases/${encodeURIComponent(caseId)}`,
    {},
    token,
  );
}
