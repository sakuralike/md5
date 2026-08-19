import type {
  RegistrationInvite,
  RegistrationInviteCreated,
  RegistrationInviteListResponse,
  RegistrationPolicy,
  RegistrationMode,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export function getRegistrationPolicy(token: string): Promise<RegistrationPolicy> {
  return apiRequest<RegistrationPolicy>("/admin/registration/policy", {}, token);
}

export function saveRegistrationPolicy(
  mode: RegistrationMode,
  token: string,
): Promise<RegistrationPolicy> {
  return apiRequest<RegistrationPolicy>(
    "/admin/registration/policy",
    { method: "PUT", body: JSON.stringify({ mode }) },
    token,
  );
}

export function listRegistrationInvites(token: string): Promise<RegistrationInviteListResponse> {
  return apiRequest<RegistrationInviteListResponse>("/admin/registration/invites", {}, token);
}

export interface RegistrationInviteCreateInput {
  label: string;
  maxUses: number;
  expiresAt?: string;
}

export function createRegistrationInvite(
  input: RegistrationInviteCreateInput,
  token: string,
): Promise<RegistrationInviteCreated> {
  return apiRequest<RegistrationInviteCreated>(
    "/admin/registration/invites",
    {
      method: "POST",
      body: JSON.stringify({
        label: input.label,
        max_uses: input.maxUses,
        expires_at: input.expiresAt ?? null,
      }),
    },
    token,
  );
}

export function revokeRegistrationInvite(
  inviteId: string,
  token: string,
): Promise<RegistrationInvite> {
  return apiRequest<RegistrationInvite>(
    `/admin/registration/invites/${encodeURIComponent(inviteId)}/revoke`,
    { method: "POST" },
    token,
  );
}
