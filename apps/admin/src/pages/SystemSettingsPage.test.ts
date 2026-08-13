import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import SystemSettingsPage from "./SystemSettingsPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/settings", () => ({
  listSettingVersions: vi.fn(),
  getEmailDeliverySettings: vi.fn().mockResolvedValue({
    backend: "smtp",
    enabled: true,
    smtp_configured: true,
    sender_name: "密码侦探社",
    sender_email: "no-reply@synthetic.example.com",
    subject_prefix: "[密码侦探社]",
    footer_text: "此信为系统邮件，请不要直接回复。",
    content_format: "plain_text",
    smtp_host: "smtp.synthetic.example.com",
    smtp_port: 587,
    smtp_security: "starttls",
    smtp_username: "synthetic-user",
    smtp_auth_enabled: true,
    smtp_password_configured: true,
    smtp_timeout_seconds: 10,
    configuration_source: "deployment_environment",
  }),
  sendEmailDeliveryTest: vi.fn(),
  getSettingVersion: vi.fn(),
  createSettingVersion: vi.fn(),
  publishSettingVersion: vi.fn(),
  rollbackSettingVersion: vi.fn(),
  uploadSiteLogo: vi.fn(),
}));

vi.mock("../services/users", () => ({
  reauthenticateAdmin: vi.fn(),
}));

describe("SystemSettingsPage", () => {
  it("renders immutable settings governance controls", async () => {
    const html = await renderToString(createSSRApp(SystemSettingsPage));

    expect(html).toContain("系统配置治理工作台");
    expect(html).toContain("后台设置导航");
    expect(html).toContain("站点外观与导航");
    expect(html).toContain("导航按钮");
    expect(html).toContain("上传 Logo 图片");
    expect(html).toContain("image/png,image/jpeg,image/webp");
    expect(html).toContain("SMTP 邮件投递");
    expect(html).toContain("不可变版本历史");
    expect(html).toContain("版本差异预览");
    expect(html).toContain("用户等级与权益");
    expect(html).toContain("新增等级");
    expect(html).toContain("用户等级横向列表");
    expect(html).toContain("snap-x gap-4 overflow-x-auto");
    expect(html).toContain("发布与回滚门禁");
    expect(html).toContain("一次性再认证");
  });
});
