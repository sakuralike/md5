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
