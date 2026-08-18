import {
  type EmailDeliverySettings,
  type EmailDeliverySettingsUpdate,
} from "@password-detective/api-contract";
import { toRaw } from "vue";

export function emailFormFromSettings(
  settings: EmailDeliverySettings,
): EmailDeliverySettingsUpdate {
  return {
    enabled: settings.enabled,
    sender_name: settings.sender_name,
    sender_email: settings.sender_email,
    subject_prefix: settings.subject_prefix,
    footer_text: settings.footer_text,
    footer_html: settings.footer_html,
    smtp_host: settings.smtp_host,
    smtp_port: settings.smtp_port,
    smtp_security: settings.smtp_security,
    smtp_username: settings.smtp_username,
    smtp_auth_enabled: settings.smtp_auth_enabled,
    smtp_timeout_seconds: settings.smtp_timeout_seconds,
    smtp_password: null,
    clear_smtp_password: false,
  };
}

export function cloneEmailDeliveryForm(
  form: EmailDeliverySettingsUpdate,
): EmailDeliverySettingsUpdate {
  const snapshot = toRaw(form);
  return {
    ...snapshot,
    smtp_password: snapshot.smtp_password ?? null,
    clear_smtp_password: snapshot.clear_smtp_password,
  };
}
