import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./api";
import {
  createSettingVersion,
  listSettingVersions,
  publishSettingVersion,
  rollbackSettingVersion,
} from "./settings";

vi.mock("./api", () => ({
  apiRequest: vi.fn((path: string) => Promise.resolve({ path })),
}));

const mockedApiRequest = vi.mocked(apiRequest);
const snapshot = {
  daily_reveal_quota: 20,
  reauthentication_ttl_minutes: 5,
  privacy_deletion_grace_hours: 72,
  desktop_min_client_version: "1.2.3",
  desktop_update_download_cache_seconds: 3600,
};

describe("admin settings service", () => {
  beforeEach(() => mockedApiRequest.mockClear());

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
