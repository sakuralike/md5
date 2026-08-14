import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./api";
import {
  createCommunityNotificationReplayKey,
  getCommunityNotificationOutboxMetrics,
  listCommunityNotificationOutbox,
  replayCommunityNotificationOutbox,
} from "./communityNotificationOutbox";

vi.mock("@/lib/clientId", () => ({
  createClientId: () => "synthetic-client-id",
}));

vi.mock("./api", () => ({
  apiRequest: vi.fn((path: string) => Promise.resolve({ path })),
}));

const mockedApiRequest = vi.mocked(apiRequest);

describe("community notification outbox service", () => {
  beforeEach(() => mockedApiRequest.mockClear());

  it("loads metrics and encodes failure filters", async () => {
    await getCommunityNotificationOutboxMetrics("synthetic-admin-token");
    await listCommunityNotificationOutbox(
      {
        status: "failed",
        kind: "follow",
        errorCode: " community.notification_dispatch_failed ",
        page: 2,
        pageSize: 25,
      },
      "synthetic-admin-token",
    );

    expect(mockedApiRequest).toHaveBeenNthCalledWith(
      1,
      "/admin/community/notification-outbox/metrics",
      {},
      "synthetic-admin-token",
    );
    expect(mockedApiRequest).toHaveBeenNthCalledWith(
      2,
      "/admin/community/notification-outbox?status=failed&kind=follow&error_code=community.notification_dispatch_failed&page=2&page_size=25",
      {},
      "synthetic-admin-token",
    );
  });

  it("creates an HTTP-safe replay idempotency key through the shared client id helper", () => {
    expect(createCommunityNotificationReplayKey()).toBe(
      "community-notification-replay-synthetic-client-id",
    );
  });

  it("replays one event with reauthentication and idempotency", async () => {
    await replayCommunityNotificationOutbox(
      "event/with-slash",
      { reason: "合成故障已排除", reauthToken: "synthetic-reauth-token" },
      "synthetic-admin-token",
      "synthetic-replay-key",
    );

    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/community/notification-outbox/event%2Fwith-slash/replay",
      {
        method: "POST",
        headers: { "Idempotency-Key": "synthetic-replay-key" },
        body: JSON.stringify({
          reason: "合成故障已排除",
          reauth_token: "synthetic-reauth-token",
        }),
      },
      "synthetic-admin-token",
    );
  });
});
