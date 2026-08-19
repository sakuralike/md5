import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./api";
import {
  getCurrentSettings,
  getEmailDeliverySettings,
  saveCurrentSettings,
  sendEmailDeliveryTest,
  uploadSiteLogo,
} from "./settings";

vi.mock("./api", () => ({
  apiRequest: vi.fn((path: string) => Promise.resolve({ path })),
}));

const mockedApiRequest = vi.mocked(apiRequest);
const snapshot = {
  site_name: "密码侦探社",
  site_logo_url: "",
  site_navigation: [
    { label: "首页", path: "/", enabled: true, requires_auth: false },
    { label: "社区", path: "/community", enabled: true, requires_auth: false },
  ],
  icp_record: "",
  public_security_record: "",
  copyright_text: "",
  public_contact_email: "",
  maintenance_enabled: false,
  maintenance_message: "系统正在维护，请稍后再试。",
  maintenance_allowed_ip_cidrs: [],
  max_active_sessions: 0,
  session_overflow_policy: "deny_new" as const,
  daily_reveal_quota: 20,
  reauthentication_ttl_minutes: 5,
  privacy_deletion_grace_hours: 72,
  desktop_min_client_version: "1.2.3",
  desktop_update_download_cache_seconds: 3600,
  user_levels: [
    {
      code: "rookie",
      name: "新手侦探",
      description: "合成测试等级",
      min_growth_points: 0,
      daily_reveal_quota: 20,
      can_submit: true,
    },
  ],
};

describe("admin settings service", () => {
  beforeEach(() => mockedApiRequest.mockClear());

  it("reads the current directly persisted settings", async () => {
    await getCurrentSettings("synthetic-admin-token");
    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/settings/current",
      {},
      "synthetic-admin-token",
    );
  });

  it("saves the full current settings snapshot with idempotency", async () => {
    await saveCurrentSettings(snapshot, "synthetic-admin-token", "synthetic-settings-idempotency-1");
    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/settings/current",
      {
        method: "PUT",
        headers: { "Idempotency-Key": "synthetic-settings-idempotency-1" },
        body: JSON.stringify(snapshot),
      },
      "synthetic-admin-token",
    );
  });

  it("reads deployment-backed SMTP settings without exposing the password", async () => {
    await getEmailDeliverySettings("synthetic-admin-token");
    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/settings/email-delivery",
      {},
      "synthetic-admin-token",
    );
  });

  it("sends a test email through the protected admin endpoint", async () => {
    await sendEmailDeliveryTest("operator@synthetic.example.com", "synthetic-admin-token");
    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/settings/email-delivery/test",
      {
        method: "POST",
        body: JSON.stringify({ recipient: "operator@synthetic.example.com" }),
      },
      "synthetic-admin-token",
    );
  });

  it("uploads a validated logo file as a raw image body", async () => {
    const file = new File([new Uint8Array([137, 80, 78, 71])], "brand.png", {
      type: "image/png",
    });
    await uploadSiteLogo(file, "synthetic-admin-token");
    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/settings/logo",
      {
        method: "POST",
        headers: { "Content-Type": "image/png" },
        body: file,
      },
      "synthetic-admin-token",
    );
  });
});
