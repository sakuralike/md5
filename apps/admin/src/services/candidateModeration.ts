import { createClientId } from "@/lib/clientId";
import type {
  CandidateModerationDetail,
  CandidateModerationListResponse,
  CandidateStatus,
  CandidateTransitionRequest,
  CandidateTransitionResponse,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export interface CandidateModerationFilters {
  status?: CandidateStatus | "";
  query?: string;
  page?: number;
  pageSize?: number;
}

export function createTransitionKey(): string {
  return `admin-candidate-transition-${createClientId()}`;
}

export function listModerationCandidates(
  filters: CandidateModerationFilters,
  token: string,
): Promise<CandidateModerationListResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  const query = filters.query?.trim();
  if (query) params.set("query", query);
  params.set("page", String(filters.page ?? 1));
  params.set("page_size", String(filters.pageSize ?? 20));
  return apiRequest<CandidateModerationListResponse>(
    `/admin/candidates?${params.toString()}`,
    {},
    token,
  );
}

export function getModerationCandidate(
  candidateId: string,
  token: string,
): Promise<CandidateModerationDetail> {
  return apiRequest<CandidateModerationDetail>(
    `/admin/candidates/${encodeURIComponent(candidateId)}`,
    {},
    token,
  );
}

export function transitionModerationCandidate(
  candidateId: string,
  payload: CandidateTransitionRequest,
  token: string,
  idempotencyKey: string,
): Promise<CandidateTransitionResponse> {
  return apiRequest<CandidateTransitionResponse>(
    `/admin/candidates/${encodeURIComponent(candidateId)}/transition`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}
