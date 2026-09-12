import { createClientId } from "@/lib/clientId";
import type {
  AdminCommunityPostModerateRequest,
  AdminCommunityPostMutationResponse,
  AdminCommunityReportListResponse,
  AdminCommunityReportMutationResponse,
  AdminCommunityReportResolveRequest,
  CommunityReportStatus,
  AdminCommunityDirectMessageReportListResponse,
  AdminCommunityDirectMessageReportDetail,
  AdminCommunityDirectMessageReportResolveRequest,
  AdminCommunityDirectMessageReportMutationResponse,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export interface CommunityReportFilters {
  status?: CommunityReportStatus | "";
  page?: number;
  pageSize?: number;
}

export function createCommunityModerationKey(kind: "report" | "post" | "direct-message-report"): string {
  return `admin-community-${kind}-${createClientId()}`;
}

export function listCommunityReports(
  filters: CommunityReportFilters,
  token: string,
): Promise<AdminCommunityReportListResponse> {
  const params = new URLSearchParams({
    page: String(filters.page ?? 1),
    page_size: String(filters.pageSize ?? 50),
  });
  if (filters.status) params.set("status", filters.status);
  return apiRequest<AdminCommunityReportListResponse>(
    `/admin/community/reports?${params.toString()}`,
    {},
    token,
  );
}

export function resolveCommunityReport(
  reportId: string,
  payload: AdminCommunityReportResolveRequest,
  token: string,
  idempotencyKey: string,
): Promise<AdminCommunityReportMutationResponse> {
  return apiRequest<AdminCommunityReportMutationResponse>(
    `/admin/community/reports/${encodeURIComponent(reportId)}/resolve`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function moderateCommunityPost(
  postId: string,
  payload: AdminCommunityPostModerateRequest,
  token: string,
  idempotencyKey: string,
): Promise<AdminCommunityPostMutationResponse> {
  return apiRequest<AdminCommunityPostMutationResponse>(
    `/admin/community/posts/${encodeURIComponent(postId)}/moderate`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function listCommunityDirectMessageReports(
  status: "open" | "resolved" | "dismissed" | "" = "open",
  token: string,
): Promise<AdminCommunityDirectMessageReportListResponse> {
  const params = new URLSearchParams({ page: "1", page_size: "50" });
  if (status) params.set("status", status);
  return apiRequest<AdminCommunityDirectMessageReportListResponse>(
    `/admin/community/message-reports?${params.toString()}`,
    {},
    token,
  );
}

export function getCommunityDirectMessageReport(
  reportId: string,
  token: string,
): Promise<AdminCommunityDirectMessageReportDetail> {
  return apiRequest<AdminCommunityDirectMessageReportDetail>(
    `/admin/community/message-reports/${encodeURIComponent(reportId)}`,
    {},
    token,
  );
}

export function resolveCommunityDirectMessageReport(
  reportId: string,
  payload: AdminCommunityDirectMessageReportResolveRequest,
  token: string,
  idempotencyKey: string,
): Promise<AdminCommunityDirectMessageReportMutationResponse> {
  return apiRequest<AdminCommunityDirectMessageReportMutationResponse>(
    `/admin/community/message-reports/${encodeURIComponent(reportId)}/resolve`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}
