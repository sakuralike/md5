import {
  type EmailDeliverySettings,
  type EmailDeliveryTestResponse,
  type OperationalSettingsSnapshot,
  type SettingChangeReasonCode,
  type SettingVersionDetail,
  type SettingVersionListResponse,
  type SettingVersionMutationResponse,
  type SiteLogoUploadResponse,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export interface SettingVersionCreateInput {
  expectedBaseVersionId: string | null;
  reasonCode: SettingChangeReasonCode;
  snapshot: OperationalSettingsSnapshot;
}

export interface SettingVersionPublishInput {
  expectedPublishedVersionId: string | null;
  reasonCode: SettingChangeReasonCode;
  reauthToken: string;
}

export interface SettingVersionRollbackInput {
  expectedPublishedVersionId: string;
  reasonCode: SettingChangeReasonCode;
  reauthToken: string;
}

export function listSettingVersions(
  token: string,
  page = 1,
  pageSize = 50,
): Promise<SettingVersionListResponse> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  return apiRequest<SettingVersionListResponse>(`/admin/settings/versions?${params.toString()}`, {}, token);
}

export function getSettingVersion(versionId: string, token: string): Promise<SettingVersionDetail> {
  return apiRequest<SettingVersionDetail>(
    `/admin/settings/versions/${encodeURIComponent(versionId)}`,
    {},
    token,
  );
}

export function createSettingVersion(
  input: SettingVersionCreateInput,
  token: string,
  idempotencyKey: string,
): Promise<SettingVersionMutationResponse> {
  return apiRequest<SettingVersionMutationResponse>(
    "/admin/settings/versions",
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        expected_base_version_id: input.expectedBaseVersionId,
        reason_code: input.reasonCode,
        snapshot: input.snapshot,
      }),
    },
    token,
  );
}

export function publishSettingVersion(
  versionId: string,
  input: SettingVersionPublishInput,
  token: string,
  idempotencyKey: string,
): Promise<SettingVersionMutationResponse> {
  return apiRequest<SettingVersionMutationResponse>(
    `/admin/settings/versions/${encodeURIComponent(versionId)}/publish`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        expected_published_version_id: input.expectedPublishedVersionId,
        reason_code: input.reasonCode,
        reauth_token: input.reauthToken,
      }),
    },
    token,
  );
}

export function rollbackSettingVersion(
  versionId: string,
  input: SettingVersionRollbackInput,
  token: string,
  idempotencyKey: string,
): Promise<SettingVersionMutationResponse> {
  return apiRequest<SettingVersionMutationResponse>(
    `/admin/settings/versions/${encodeURIComponent(versionId)}/rollback`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        expected_published_version_id: input.expectedPublishedVersionId,
        reason_code: input.reasonCode,
        reauth_token: input.reauthToken,
      }),
    },
    token,
  );
}


export function getEmailDeliverySettings(token: string): Promise<EmailDeliverySettings> {
  return apiRequest<EmailDeliverySettings>("/admin/settings/email-delivery", {}, token);
}

export function sendEmailDeliveryTest(
  recipient: string,
  token: string,
): Promise<EmailDeliveryTestResponse> {
  return apiRequest<EmailDeliveryTestResponse>(
    "/admin/settings/email-delivery/test",
    {
      method: "POST",
      body: JSON.stringify({ recipient }),
    },
    token,
  );
}
export function uploadSiteLogo(file: File, token: string): Promise<SiteLogoUploadResponse> {
  return apiRequest<SiteLogoUploadResponse>(
    "/admin/settings/logo",
    {
      method: "POST",
      headers: { "Content-Type": file.type },
      body: file,
    },
    token,
  );
}
