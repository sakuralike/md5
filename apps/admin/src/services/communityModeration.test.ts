import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./api";
import {
  createCommunityModerationKey,
  listCommunityReports,
  moderateCommunityPost,
  resolveCommunityReport,
} from "./communityModeration";

vi.mock("./api", () => ({
  apiRequest: vi.fn(() => Promise.resolve({})),
}));

const mockedApiRequest = vi.mocked(apiRequest);

describe("community moderation service", () => {
  beforeEach(() => mockedApiRequest.mockClear());

  it("serializes report filters for the MFA review queue", async () => {
    await listCommunityReports(
      { status: "open", page: 2, pageSize: 25 },
      "mfa-access-token",
    );

    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/community/reports?page=2&page_size=25&status=open",
      {},
      "mfa-access-token",
    );
  });

  it("resolves reports with an idempotency key and minimal decision payload", async () => {
    await resolveCommunityReport(
      "report/1",
      { decision: "remove_and_lock", note: "合成治理说明" },
      "mfa-access-token",
      "community-report-stable-key",
    );

    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/community/reports/report%2F1/resolve",
      {
        method: "POST",
        headers: { "Idempotency-Key": "community-report-stable-key" },
        body: JSON.stringify({
          decision: "remove_and_lock",
          note: "合成治理说明",
        }),
      },
      "mfa-access-token",
    );
  });

  it("moderates posts without placing credentials in the request body", async () => {
    await moderateCommunityPost(
      "post/1",
      { action: "pin", note: "合成置顶说明" },
      "mfa-access-token",
      "community-post-stable-key",
    );

    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/community/posts/post%2F1/moderate",
      {
        method: "POST",
        headers: { "Idempotency-Key": "community-post-stable-key" },
        body: JSON.stringify({ action: "pin", note: "合成置顶说明" }),
      },
      "mfa-access-token",
    );
    const request = mockedApiRequest.mock.calls[0]?.[1];
    expect(String(request?.body).toLowerCase()).not.toContain("password");
  });

  it("creates namespaced keys for report and post mutations", () => {
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });
    expect(createCommunityModerationKey("report")).toBe(
      "admin-community-report-synthetic-request-id",
    );
    expect(createCommunityModerationKey("post")).toBe(
      "admin-community-post-synthetic-request-id",
    );
    vi.unstubAllGlobals();
  });
});
