import { afterEach, describe, expect, it, vi } from "vitest";
import {
  assignTrustCase,
  createTrustCaseAssignKey,
  createTrustCaseReopenKey,
  createTrustCaseTransitionKey,
  listTrustCases,
  reopenTrustCase,
  transitionTrustCase,
} from "./trustCases";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("trust-case administration", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("normalizes queue filters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ items: [], page: 2, page_size: 50, total: 0 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await listTrustCases(
      { kind: "appeal", status: "open", query: "  user_1  ", page: 2, pageSize: 50 },
      "mfa-token",
    );

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const parsed = new URL(url, "http://synthetic.local");
    const headers = init.headers as Headers;
    expect(parsed.pathname).toContain("/admin/trust-cases");
    expect(parsed.searchParams.get("kind")).toBe("appeal");
    expect(parsed.searchParams.get("status")).toBe("open");
    expect(parsed.searchParams.get("query")).toBe("user_1");
    expect(headers.get("Authorization")).toBe("Bearer mfa-token");
  });

  it("sends controlled resolution with a stable retry key", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ current_status: "resolved" }));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await transitionTrustCase(
      "case/synthetic",
      {
        expected_version: 3,
        target_status: "resolved",
        resolution_code: "admin.appeal_upheld",
        resolution_note: "合成处理说明",
      },
      "mfa-token",
      "trust-case-stable-key",
    );

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(url).toContain("/admin/trust-cases/case%2Fsynthetic/transition");
    expect(headers.get("Idempotency-Key")).toBe("trust-case-stable-key");
    expect(JSON.parse(String(init.body))).toEqual({
      expected_version: 3,
      target_status: "resolved",
      resolution_code: "admin.appeal_upheld",
      resolution_note: "合成处理说明",
    });
  });

  it("sends assignment and reopen commands with optimistic versions", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ version: 2 }))
      .mockResolvedValueOnce(jsonResponse({ version: 3 }));
    vi.stubGlobal("fetch", fetchMock);

    await assignTrustCase(
      "case/synthetic",
      {
        expected_version: 1,
        assignee_id: "moderator-id",
        reason_code: "admin.assigned",
        note: "合成指派说明",
      },
      "mfa-token",
      "assign-key",
    );
    await reopenTrustCase(
      "case/synthetic",
      { expected_version: 2, reason_code: "admin.reopened" },
      "mfa-token",
      "reopen-key",
    );

    expect(fetchMock.mock.calls[0][0]).toContain("/assign");
    expect(((fetchMock.mock.calls[0][1] as RequestInit).headers as Headers).get("Idempotency-Key")).toBe(
      "assign-key",
    );
    expect(fetchMock.mock.calls[1][0]).toContain("/reopen");
    expect(((fetchMock.mock.calls[1][1] as RequestInit).headers as Headers).get("Idempotency-Key")).toBe(
      "reopen-key",
    );
  });

  it("creates a namespaced idempotency key", () => {
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });
    expect(createTrustCaseTransitionKey()).toBe(
      "admin-trust-case-transition-synthetic-request-id",
    );
    expect(createTrustCaseAssignKey()).toBe(
      "admin-trust-case-assign-synthetic-request-id",
    );
    expect(createTrustCaseReopenKey()).toBe(
      "admin-trust-case-reopen-synthetic-request-id",
    );
  });
});
