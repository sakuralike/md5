import {
  type EmailDeliverySettings,
  type EmailDeliverySettingsUpdate,
  type EmailDeliveryTestResponse,
  type OperationalSettingsResponse,
  type OperationalSettingsSnapshot,
  type SeoSettings,
  type SeoSettingsResponse,
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

export function getSeoSettings(token: string): Promise<SeoSettingsResponse> {
  return apiRequest<SeoSettingsResponse>("/admin/settings/seo", {}, token);
}

export function saveSeoSettings(
  payload: SeoSettings,
  token: string,
  idempotencyKey: string,
): Promise<SeoSettingsResponse> {
  return apiRequest<SeoSettingsResponse>(
    "/admin/settings/seo",
    {
      method: "PUT",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function getEmailDeliverySettings(token: string): Promise<EmailDeliverySettings> {
  return apiRequest<EmailDeliverySettings>("/admin/settings/email-delivery", {}, token);
}

export function saveEmailDeliverySettings(
  payload: EmailDeliverySettingsUpdate,
  token: string,
  idempotencyKey: string,
): Promise<EmailDeliverySettings> {
  return apiRequest<EmailDeliverySettings>(
    "/admin/settings/email-delivery",
    {
      method: "PUT",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
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
