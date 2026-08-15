import type {
  AuthorizedApplicationListResponse,
  ThirdPartyAuthorizationDecisionRequest,
  ThirdPartyAuthorizationDetails,
  ThirdPartyAuthorizationRequest,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export function getThirdPartyAuthorizationRequest(
  token: string,
  request: ThirdPartyAuthorizationRequest,
): Promise<ThirdPartyAuthorizationDetails> {
  const params = new URLSearchParams({
    response_type: request.response_type,
    client_id: request.client_id,
    redirect_uri: request.redirect_uri,
    code_challenge: request.code_challenge,
    state: request.state,
    code_challenge_method: request.code_challenge_method,
  });
  if (request.scope) params.set("scope", request.scope);
  return apiRequest(`/third-party/oauth/consent?${params.toString()}`, {}, token);
}

export function submitThirdPartyAuthorization(
  token: string,
  request: ThirdPartyAuthorizationDecisionRequest,
): Promise<{ redirect_url: string }> {
  return apiRequest(
    "/third-party/oauth/consent",
    { method: "POST", body: JSON.stringify(request) },
    token,
  );
}

export function listAuthorizedApplications(
  token: string,
): Promise<AuthorizedApplicationListResponse> {
  return apiRequest("/third-party/oauth/authorized-applications", {}, token);
}

export function revokeAuthorizedApplication(token: string, appId: string): Promise<void> {
  return apiRequest(
    `/third-party/oauth/authorized-applications/${encodeURIComponent(appId)}`,
    { method: "DELETE" },
    token,
  );
}
