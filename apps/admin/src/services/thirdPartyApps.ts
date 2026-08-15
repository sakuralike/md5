import type {
  ThirdPartyApp,
  ThirdPartyAppCreateRequest,
  ThirdPartyAppListResponse,
  ThirdPartyAppReviewRequest,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export function listThirdPartyApps(token: string): Promise<ThirdPartyAppListResponse> {
  return apiRequest("/admin/third-party-apps?page=1&page_size=100", {}, token);
}

export function createThirdPartyApp(
  token: string,
  payload: ThirdPartyAppCreateRequest,
): Promise<ThirdPartyApp> {
  return apiRequest(
    "/admin/third-party-apps",
    { method: "POST", body: JSON.stringify(payload) },
    token,
  );
}

export function approveThirdPartyApp(
  token: string,
  appId: string,
  payload: ThirdPartyAppReviewRequest,
): Promise<ThirdPartyApp> {
  return apiRequest(
    `/admin/third-party-apps/${encodeURIComponent(appId)}/approve`,
    { method: "POST", body: JSON.stringify(payload) },
    token,
  );
}

function mutateThirdPartyApp(token: string, appId: string, action: string): Promise<ThirdPartyApp> {
  return apiRequest(
    `/admin/third-party-apps/${encodeURIComponent(appId)}/${action}`,
    { method: "POST" },
    token,
  );
}

export function suspendThirdPartyApp(token: string, appId: string): Promise<ThirdPartyApp> {
  return mutateThirdPartyApp(token, appId, "suspend");
}

export function restoreThirdPartyApp(token: string, appId: string): Promise<ThirdPartyApp> {
  return mutateThirdPartyApp(token, appId, "restore");
}

export function revokeThirdPartyApp(token: string, appId: string): Promise<ThirdPartyApp> {
  return mutateThirdPartyApp(token, appId, "revoke");
}


export type ThirdPartyApplicationRequestStatus = "draft" | "pending_review" | "rejected" | "approved";

export interface ThirdPartyApplicationRequest {
  id: string;
  name: string;
  developer_name: string;
  description: string;
  website_url: string;
  privacy_policy_url: string;
  redirect_uris: string[];
  requested_scopes: string[];
  windows_release_info: string;
  use_case: string;
  status: ThirdPartyApplicationRequestStatus;
  resubmission_count: number;
  current_version: number;
  review_note: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

interface ThirdPartyApplicationRequestListResponse {
  items: ThirdPartyApplicationRequest[];
  page: number;
  page_size: number;
  total: number;
}

export interface ThirdPartyApplicationApprovalResult {
  application: ThirdPartyApplicationRequest;
  created_app: ThirdPartyApp;
}

export function listThirdPartyApplicationRequests(
  token: string,
): Promise<ThirdPartyApplicationRequestListResponse> {
  return apiRequest("/admin/third-party-applications/requests?page=1&page_size=100", {}, token);
}

export function approveThirdPartyApplicationRequest(
  token: string,
  requestId: string,
  payload: { review_note?: string | null; approved_scopes: string[]; trusted_verification_enabled: boolean },
): Promise<ThirdPartyApplicationApprovalResult> {
  return apiRequest(
    `/admin/third-party-applications/requests/${encodeURIComponent(requestId)}/approve`,
    { method: "POST", body: JSON.stringify(payload) },
    token,
  );
}

export function rejectThirdPartyApplicationRequest(
  token: string,
  requestId: string,
  reviewNote: string,
): Promise<ThirdPartyApplicationRequest> {
  return apiRequest(
    `/admin/third-party-applications/requests/${encodeURIComponent(requestId)}/reject`,
    { method: "POST", body: JSON.stringify({ review_note: reviewNote }) },
    token,
  );
}
