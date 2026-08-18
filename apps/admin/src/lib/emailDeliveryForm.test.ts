import type { EmailDeliverySettings } from "@password-detective/api-contract";
import { ref } from "vue";
import { describe, expect, it } from "vitest";
import {
  cloneEmailDeliveryForm,
  emailFormFromSettings,
} from "./emailDeliveryForm";

const settings: EmailDeliverySettings = {
  backend: "smtp",
  enabled: true,
  smtp_configured: true,
  sender_name: "密码侦探社",
  sender_email: "no-reply@synthetic.example.com",
  subject_prefix: "[密码侦探社]",
  footer_text: "此信为系统邮件，请不要直接回复。",
  footer_html: '<a href="https://synthetic.example.com">访问网站</a>',
  content_format: "multipart",
  smtp_host: "smtp.synthetic.example.com",
  smtp_port: 465,
  smtp_security: "ssl",
  smtp_username: "synthetic-user",
  smtp_auth_enabled: true,
  smtp_password_configured: true,
  smtp_timeout_seconds: 10,
  configuration_source: "database",
};

describe("emailDeliveryForm", () => {
  it("clones a Vue-reactive saved SMTP baseline without DataCloneError", () => {
    const baseline = ref(emailFormFromSettings(settings));

    expect(() => cloneEmailDeliveryForm(baseline.value)).not.toThrow();
    expect(cloneEmailDeliveryForm(baseline.value)).toEqual({
      enabled: true,
      sender_name: "密码侦探社",
      sender_email: "no-reply@synthetic.example.com",
      subject_prefix: "[密码侦探社]",
      footer_text: "此信为系统邮件，请不要直接回复。",
      footer_html: '<a href="https://synthetic.example.com">访问网站</a>',
      smtp_host: "smtp.synthetic.example.com",
      smtp_port: 465,
      smtp_security: "ssl",
      smtp_username: "synthetic-user",
      smtp_auth_enabled: true,
      smtp_timeout_seconds: 10,
      smtp_password: null,
      clear_smtp_password: false,
    });
  });
});
