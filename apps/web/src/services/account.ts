import type {
  AuthorizationDeclaration,
  AuthorizationDeclarationCreateRequest,
  AuthorizationDeclarationListResponse,
  MessageResponse,
  PasswordChangeRequest,
  PrivacyDeletionCreateRequest,
  PrivacyDeletionRequest,
  PrivacyExport,
  RevealHistoryResponse,
  ProfileUpdateRequest,
  ReauthenticationRequest,
  ReauthenticationResponse,
  Session,
  TotpCodeRequest,
  TotpDisableRequest,
  TotpSetupResponse,
  User,
} from "@password-detective/api-contract";
import { apiFileRequest, apiRequest } from "./api";

function idempotencyHeaders(): HeadersInit {
  return { "Idempotency-Key": crypto.randomUUID() };
}

export function loadProfile(accessToken: string): Promise<User> {
  return apiRequest<User>("/me/profile", {}, accessToken);
}

export function updateProfile(
  accessToken: string,
  payload: ProfileUpdateRequest,
): Promise<User> {
  return apiRequest<User>(
    "/me/profile",
    { method: "PATCH", headers: idempotencyHeaders(), body: JSON.stringify(payload) },
    accessToken,
  );
}

export function reauthenticate(
  accessToken: string,
  payload: ReauthenticationRequest,
): Promise<ReauthenticationResponse> {
  return apiRequest<ReauthenticationResponse>(
    "/me/security/reauthenticate",
    { method: "POST", body: JSON.stringify(payload) },
    accessToken,
  );
}

export function changePassword(
  accessToken: string,
  payload: PasswordChangeRequest,
): Promise<MessageResponse> {
  return apiRequest<MessageResponse>(
    "/me/security/password/change",
    { method: "POST", headers: idempotencyHeaders(), body: JSON.stringify(payload) },
    accessToken,
  );
}

export function beginTotpSetup(accessToken: string): Promise<TotpSetupResponse> {
  return apiRequest<TotpSetupResponse>(
    "/me/security/totp/setup",
    { method: "POST" },
    accessToken,
  );
}

export function confirmTotp(
  accessToken: string,
  payload: TotpCodeRequest,
): Promise<MessageResponse> {
  return apiRequest<MessageResponse>(
    "/me/security/totp/confirm",
    { method: "POST", headers: idempotencyHeaders(), body: JSON.stringify(payload) },
    accessToken,
  );
}

export function disableTotp(
  accessToken: string,
  payload: TotpDisableRequest,
): Promise<MessageResponse> {
  return apiRequest<MessageResponse>(
    "/me/security/totp",
    { method: "DELETE", headers: idempotencyHeaders(), body: JSON.stringify(payload) },
    accessToken,
  );
}

export function listSessions(accessToken: string): Promise<Session[]> {
  return apiRequest<Session[]>("/me/security/sessions", {}, accessToken);
}

export function revokeSession(accessToken: string, id: string): Promise<MessageResponse> {
  return apiRequest<MessageResponse>(
    `/me/security/sessions/${encodeURIComponent(id)}`,
    { method: "DELETE" },
    accessToken,
  );
}

export function listRevealHistory(accessToken: string): Promise<RevealHistoryResponse> {
  return apiRequest<RevealHistoryResponse>("/me/reveals", {}, accessToken);
}

export function listAuthorizationDeclarations(
  accessToken: string,
): Promise<AuthorizationDeclarationListResponse> {
  return apiRequest<AuthorizationDeclarationListResponse>(
    "/me/authorization-declarations",
    {},
    accessToken,
  );
}

export function confirmAuthorizationDeclaration(
  accessToken: string,
  payload: AuthorizationDeclarationCreateRequest,
): Promise<AuthorizationDeclaration> {
  return apiRequest<AuthorizationDeclaration>(
    "/me/authorization-declarations",
    { method: "POST", headers: idempotencyHeaders(), body: JSON.stringify(payload) },
    accessToken,
  );
}

export function requestPrivacyExport(accessToken: string): Promise<PrivacyExport> {
  return apiRequest<PrivacyExport>(
    "/me/privacy/exports",
    { method: "POST", headers: idempotencyHeaders() },
    accessToken,
  );
}

export function getPrivacyExport(
  accessToken: string,
  exportId: string,
): Promise<PrivacyExport> {
  return apiRequest<PrivacyExport>(
    `/me/privacy/exports/${encodeURIComponent(exportId)}`,
    {},
    accessToken,
  );
}

export function downloadPrivacyExport(
  accessToken: string,
  exportId: string,
  token: string,
): Promise<{ blob: Blob; filename: string }> {
  return apiFileRequest(
    `/me/privacy/exports/${encodeURIComponent(exportId)}/download`,
    { method: "POST", body: JSON.stringify({ token }) },
    accessToken,
  );
}

export function requestAccountDeletion(
  accessToken: string,
  payload: PrivacyDeletionCreateRequest,
): Promise<PrivacyDeletionRequest> {
  return apiRequest<PrivacyDeletionRequest>(
    "/me/privacy/deletion-requests",
    { method: "POST", headers: idempotencyHeaders(), body: JSON.stringify(payload) },
    accessToken,
  );
}

export function getCurrentDeletionRequest(
  accessToken: string,
): Promise<PrivacyDeletionRequest | null> {
  return apiRequest<PrivacyDeletionRequest | null>(
    "/me/privacy/deletion-requests/current",
    {},
    accessToken,
  );
}

export function cancelAccountDeletion(
  accessToken: string,
  requestId: string,
): Promise<PrivacyDeletionRequest> {
  return apiRequest<PrivacyDeletionRequest>(
    `/me/privacy/deletion-requests/${encodeURIComponent(requestId)}/cancel`,
    { method: "POST", headers: idempotencyHeaders() },
    accessToken,
  );
}
