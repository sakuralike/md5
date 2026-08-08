import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createAccountAppeal,
  createAppeal,
  createReport,
  createTrustCaseSubmissionKey,
  getMyTrustCase,
  listMyTrustCases,
} from "./trustCases";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("web trust cases", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists only the selected case kind with authorization", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ items: [], page: 1, page_size: 50, total: 0 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await listMyTrustCases("access-token", "appeal");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const parsed = new URL(url, "http://synthetic.local");
    const headers = init.headers as Headers;
    expect(parsed.pathname).toContain("/trust/cases");
    expect(parsed.searchParams.get("kind")).toBe("appeal");
    expect(headers.get("Authorization")).toBe("Bearer access-token");
  });

  it("creates a report with a stable retry key", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "case-1" }));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await createReport(
      {
        candidate_id: "candidate-1",
        reason_code: "report.invalid_candidate",
        description: "合成举报说明",
      },
      "access-token",
      "report-stable-key",
    );

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(url).toContain("/trust/reports");
    expect(headers.get("Idempotency-Key")).toBe("report-stable-key");
    expect(JSON.parse(String(init.body))).toEqual({
      candidate_id: "candidate-1",
      reason_code: "report.invalid_candidate",
      description: "合成举报说明",
    });
  });

  it("creates an appeal and namespaces generated keys", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "case-2" }));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await createAppeal(
      {
        candidate_id: "candidate-2",
        related_case_id: "case-1",
        reason_code: "appeal.new_evidence",
        description: "合成申诉说明",
      },
      "access-token",
      "appeal-stable-key",
    );

    expect(createTrustCaseSubmissionKey("appeal")).toBe(
      "web-trust-appeal-synthetic-request-id",
    );
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Headers).get("Idempotency-Key")).toBe("appeal-stable-key");
  });
  it("creates a self-scoped account appeal and loads its detail", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(jsonResponse({ id: "account-case-1" })),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await createAccountAppeal(
      {
        requested_action: "review_restriction",
        reason_code: "account_appeal.restriction_incorrect",
        description: "合成账号申诉说明",
        evidence_summary: "合成证据摘要",
      },
      "access-token",
      "account-appeal-stable-key",
    );
    await getMyTrustCase("account/case 1", "access-token");

    const [createUrl, createInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(createUrl).toContain("/trust/account-appeals");
    expect((createInit.headers as Headers).get("Idempotency-Key")).toBe(
      "account-appeal-stable-key",
    );
    expect(JSON.parse(String(createInit.body))).not.toHaveProperty("target_user_id");
    const [detailUrl] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(detailUrl).toContain("/trust/cases/account%2Fcase%201");
  });
});
