import {
  type EmailDeliverySettings,
  type EmailDeliveryTestResponse,
  type OperationalSettingsResponse,
  type OperationalSettingsSnapshot,
  type SiteLogoUploadResponse,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export function getCurrentSettings(token: string): Promise<OperationalSettingsResponse> {
  return apiRequest<OperationalSettingsResponse>("/admin/settings/current", {}, token);
}

export function saveCurrentSettings(
  snapshot: OperationalSettingsSnapshot,
  token: string,
  idempotencyKey: string,
): Promise<OperationalSettingsResponse> {
  return apiRequest<OperationalSettingsResponse>(
    "/admin/settings/current",
    {
      method: "PUT",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(snapshot),
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
