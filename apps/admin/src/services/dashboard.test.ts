import { afterEach, describe, expect, it, vi } from "vitest";
import { getAdminDashboardSummary } from "./dashboard";

function jsonResponse(body: object): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("admin dashboard service", () => {
  it("requests the selected observation window with the MFA token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        window_hours: 72,
        window_started_at: "2026-08-01T00:00:00Z",
        generated_at: "2026-08-03T00:00:00Z",
        search_count: 8,
        search_hit_count: 2,
        search_hit_rate: 0.25,
        contribution_count: 3,
        candidate_count: 4,
        verified_candidate_count: 1,
        candidate_verification_rate: 0.25,
        quarantined_candidate_count: 1,
        audited_operation_count: 10,
        audited_error_count: 1,
        audited_error_rate: 0.1,
        queue_backlog: {
          pending_candidates: 1,
          active_trust_cases: 1,
          active_risk_alerts: 1,
          pending_privacy_exports: 0,
          pending_deletion_requests: 0,
          total: 3,
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await getAdminDashboardSummary("synthetic-mfa-token", 72);

    expect(result.search_hit_rate).toBe(0.25);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/admin/dashboard/summary?window_hours=72");
    const headers = init.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer synthetic-mfa-token");
  });
});
