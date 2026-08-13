import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./api";
import {
  createSettingVersion,
  getEmailDeliverySettings,
  listSettingVersions,
  publishSettingVersion,
  rollbackSettingVersion,
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

  it("lists immutable versions with pagination", async () => {
    await listSettingVersions("synthetic-admin-token", 2, 25);
    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/settings/versions?page=2&page_size=25",
      {},
      "synthetic-admin-token",
    );
  });

  it("creates a draft with optimistic base state and idempotency", async () => {
    await createSettingVersion(
      { expectedBaseVersionId: "base-version", reasonCode: "product_policy", snapshot },
      "synthetic-admin-token",
      "synthetic-settings-idempotency-1",
    );
    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/settings/versions",
      {
        method: "POST",
        headers: { "Idempotency-Key": "synthetic-settings-idempotency-1" },
        body: JSON.stringify({
          expected_base_version_id: "base-version",
          reason_code: "product_policy",
          snapshot,
        }),
      },
      "synthetic-admin-token",
    );
  });

  it("publishes and rolls back with one-time reauthentication grants", async () => {
    await publishSettingVersion(
      "draft/version",
      {
        expectedPublishedVersionId: "published-version",
        reasonCode: "security_hardening",
        reauthToken: "synthetic-reauth-token",
      },
      "synthetic-admin-token",
      "synthetic-settings-idempotency-2",
    );
    await rollbackSettingVersion(
      "historical-version",
      {
        expectedPublishedVersionId: "published-version",
        reasonCode: "rollback",
        reauthToken: "synthetic-rollback-token",
      },
      "synthetic-admin-token",
      "synthetic-settings-idempotency-3",
    );

    expect(mockedApiRequest).toHaveBeenNthCalledWith(
      1,
      "/admin/settings/versions/draft%2Fversion/publish",
      expect.objectContaining({
        headers: { "Idempotency-Key": "synthetic-settings-idempotency-2" },
      }),
      "synthetic-admin-token",
    );
    expect(mockedApiRequest).toHaveBeenNthCalledWith(
      2,
      "/admin/settings/versions/historical-version/rollback",
      expect.objectContaining({
        headers: { "Idempotency-Key": "synthetic-settings-idempotency-3" },
      }),
      "synthetic-admin-token",
    );
  });
});
