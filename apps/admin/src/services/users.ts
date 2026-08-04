import {
  type AdminReauthenticationResponse,
  type AdminSessionRevocationReasonCode,
  type AdminUserDetail,
  type AdminUserListResponse,
  type AdminUserSessionRevocationResponse,
  type AdminUserStatusChangeResponse,
  type AdminUserStatusReasonCode,
  type UserRole,
  type UserStatus,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export interface AdminUserFilters {
  status?: UserStatus;
  role?: UserRole;
  query?: string;
  page?: number;
  pageSize?: number;
}

function buildParams(filters: AdminUserFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.role) params.set("role", filters.role);
  if (filters.query?.trim()) params.set("query", filters.query.trim());
  params.set("page", String(filters.page ?? 1));
  params.set("page_size", String(filters.pageSize ?? 20));
  return params;
}

export function listAdminUsers(
  filters: AdminUserFilters,
  token: string,
): Promise<AdminUserListResponse> {
  return apiRequest<AdminUserListResponse>(`/admin/users?${buildParams(filters).toString()}`, {}, token);
}

export function getAdminUser(userId: string, token: string): Promise<AdminUserDetail> {
  return apiRequest<AdminUserDetail>(`/admin/users/${encodeURIComponent(userId)}`, {}, token);
}

export interface AdminReauthenticationInput {
  currentPassword: string;
  totpCode: string;
  purpose?: "admin_user_governance" | "admin_settings_governance";
}

export interface AdminUserStatusChangeInput {
  expectedStatus: UserStatus;
  status: "active" | "disabled";
  reasonCode: AdminUserStatusReasonCode;
  reauthToken: string;
}

export interface AdminUserSessionRevocationInput {
  expectedActiveSessionCount: number;
  reasonCode: AdminSessionRevocationReasonCode;
  reauthToken: string;
}

export function reauthenticateAdmin(
  input: AdminReauthenticationInput,
  token: string,
): Promise<AdminReauthenticationResponse> {
  return apiRequest<AdminReauthenticationResponse>(
    "/admin/auth/reauthenticate",
    {
      method: "POST",
      body: JSON.stringify({
        current_password: input.currentPassword,
        totp_code: input.totpCode,
        ...(input.purpose ? { purpose: input.purpose } : {}),
      }),
    },
    token,
  );
}

export function changeAdminUserStatus(
  userId: string,
  input: AdminUserStatusChangeInput,
  token: string,
  idempotencyKey: string,
): Promise<AdminUserStatusChangeResponse> {
  return apiRequest<AdminUserStatusChangeResponse>(
    `/admin/users/${encodeURIComponent(userId)}/status`,
    {
      method: "PATCH",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        expected_status: input.expectedStatus,
        status: input.status,
        reason_code: input.reasonCode,
        reauth_token: input.reauthToken,
      }),
    },
    token,
  );
}

export function revokeAdminUserSessions(
  userId: string,
  input: AdminUserSessionRevocationInput,
  token: string,
  idempotencyKey: string,
): Promise<AdminUserSessionRevocationResponse> {
  return apiRequest<AdminUserSessionRevocationResponse>(
    `/admin/users/${encodeURIComponent(userId)}/sessions/revoke`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        expected_active_session_count: input.expectedActiveSessionCount,
        reason_code: input.reasonCode,
        reauth_token: input.reauthToken,
      }),
    },
    token,
  );
}
