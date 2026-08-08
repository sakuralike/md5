import {
  type RoleChangeMutationResponse,
  type RoleChangeReasonCode,
  type RoleChangeRequestListResponse,
  type RoleChangeRequestStatus,
  type RoleChangeReviewReasonCode,
  type UserRole,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export interface RoleChangeFilters {
  status?: RoleChangeRequestStatus;
  page?: number;
  pageSize?: number;
}

function buildParams(filters: RoleChangeFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  params.set("page", String(filters.page ?? 1));
  params.set("page_size", String(filters.pageSize ?? 20));
  return params;
}

export interface RoleChangeCreateInput {
  expectedRole: UserRole;
  requestedRole: UserRole;
  reasonCode: RoleChangeReasonCode;
  reauthToken: string;
}

export interface RoleChangeReviewInput {
  reasonCode: RoleChangeReviewReasonCode;
  reauthToken: string;
  expectedStatus?: RoleChangeRequestStatus;
}

export function listRoleChangeRequests(
  filters: RoleChangeFilters,
  token: string,
): Promise<RoleChangeRequestListResponse> {
  return apiRequest<RoleChangeRequestListResponse>(
    `/admin/role-change-requests?${buildParams(filters).toString()}`,
    {},
    token,
  );
}

export function createRoleChangeRequest(
  userId: string,
  input: RoleChangeCreateInput,
  token: string,
  idempotencyKey: string,
): Promise<RoleChangeMutationResponse> {
  return apiRequest<RoleChangeMutationResponse>(
    `/admin/users/${encodeURIComponent(userId)}/role-change-requests`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        expected_role: input.expectedRole,
        requested_role: input.requestedRole,
        reason_code: input.reasonCode,
        reauth_token: input.reauthToken,
      }),
    },
    token,
  );
}

function reviewRoleChange(
  action: "approve" | "reject",
  requestId: string,
  input: RoleChangeReviewInput,
  token: string,
  idempotencyKey: string,
): Promise<RoleChangeMutationResponse> {
  return apiRequest<RoleChangeMutationResponse>(
    `/admin/role-change-requests/${encodeURIComponent(requestId)}/${action}`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        expected_status: input.expectedStatus ?? "pending",
        reason_code: input.reasonCode,
        reauth_token: input.reauthToken,
      }),
    },
    token,
  );
}

export function approveRoleChangeRequest(
  requestId: string,
  input: RoleChangeReviewInput,
  token: string,
  idempotencyKey: string,
): Promise<RoleChangeMutationResponse> {
  return reviewRoleChange("approve", requestId, input, token, idempotencyKey);
}

export function rejectRoleChangeRequest(
  requestId: string,
  input: RoleChangeReviewInput,
  token: string,
  idempotencyKey: string,
): Promise<RoleChangeMutationResponse> {
  return reviewRoleChange("reject", requestId, input, token, idempotencyKey);
}
