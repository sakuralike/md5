import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import SystemSettingsPage from "./SystemSettingsPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/settings", () => ({
  getCurrentSettings: vi.fn().mockResolvedValue({
    settings: {
      site_name: "密码侦探社",
      site_logo_url: "",
      site_navigation: [],
      icp_record: "",
      public_security_record: "",
      copyright_text: "",
      public_contact_email: "",
      maintenance_enabled: false,
      maintenance_message: "系统正在维护，请稍后再试。",
      maintenance_allowed_ip_cidrs: [],
      max_active_sessions: 0,
      session_overflow_policy: "deny_new",
      referral_reward_points: 10,
      daily_reveal_quota: 20,
      reauthentication_ttl_minutes: 5,
      privacy_deletion_grace_hours: 72,
      desktop_min_client_version: "1.0.0",
      desktop_update_download_cache_seconds: 3600,
      user_levels: [],
    },
    updated_at: null,
    updated_by: null,
  }),
  saveCurrentSettings: vi.fn(),
  getEmailDeliverySettings: vi.fn().mockResolvedValue({
    backend: "smtp",
    enabled: true,
    smtp_configured: true,
    sender_name: "密码侦探社",
    sender_email: "no-reply@synthetic.example.com",
    subject_prefix: "[密码侦探社]",
    footer_text: "此信为系统邮件，请不要直接回复。",
    footer_html: "",
    content_format: "multipart",
    smtp_host: "smtp.synthetic.example.com",
    smtp_port: 587,
    smtp_security: "starttls",
    smtp_username: "synthetic-user",
    smtp_auth_enabled: true,
    smtp_password_configured: true,
    smtp_timeout_seconds: 10,
    configuration_source: "deployment_environment",
  }),
  getSeoSettings: vi.fn().mockResolvedValue({
    settings: {
      enabled: false,
      indexing_enabled: false,
      home_title: "密码侦探社",
      keywords: [],
      description: "",
      title_separator: "-",
      default_image_url: "",
      open_graph_enabled: false,
      sitemap_enabled: false,
    },
    updated_at: null,
    updated_by: null,
  }),
  saveSeoSettings: vi.fn(),
  sendEmailDeliveryTest: vi.fn(),
  uploadSiteLogo: vi.fn(),
}));

describe("SystemSettingsPage", () => {
  it("renders direct current-settings save controls", async () => {
    const html = await renderToString(createSSRApp(SystemSettingsPage));

    expect(html).toContain("系统配置工作台");
    expect(html).toContain("站点品牌");
    expect(html).toContain("站点导航");
    expect(html).toContain("手动输入路径");
    expect(html).toContain("选择现有页面");
    expect(html).toContain("顶部导航仅显示这里保存并启用的菜单项");
    expect(html).toContain("备案与联系信息");
    expect(html).toContain('id="maintenance-governance"');
    expect(html).toContain("维护 IP 白名单");
    expect(html).toContain('id="session-governance"');
    expect(html).toContain("同时登录设备数");
    expect(html).toContain('id="referral-reward-points"');
    expect(html).toContain("邀请注册奖励积分");
    expect(html).not.toContain("用户等级规则");
    expect(html).not.toContain("用户等级与权益");
    expect(html).not.toContain('id="user-levels"');
    expect(html).toContain("上传 Logo 图片");
    expect(html).toContain("image/png,image/jpeg,image/webp");
    expect(html).toContain("SMTP 邮件投递");
    expect(html).toContain("SEO 设置");
    expect(html).toContain('id="seo-settings"');
    expect(html).toContain("搜索结果预览");
    expect(html).toContain("保存 SEO 设置");
    expect(html).toContain("重置 SEO 编辑");
    expect(html).toContain("直接保存设置");
    expect(html).toContain("当前配置将立即生效");
    expect(html).toContain("保存设置");
    expect(html).toContain("重置当前编辑");
    expect(html).toContain('data-layout="stacked-settings-regions"');
    expect(html).not.toContain("编辑中的字段差异");
    expect(html).not.toContain("版本历史仅供查看");
    expect(html).not.toContain("系统配置分区");
    expect(html).not.toContain("不可变版本历史");
    expect(html).not.toContain("版本差异预览");
    expect(html).not.toContain("发布与回滚门禁");
    expect(html).not.toContain("一次性再认证");
    expect(html).not.toContain("发布选中草稿");
    expect(html).not.toContain("回滚到选中历史版本");
  });
});
