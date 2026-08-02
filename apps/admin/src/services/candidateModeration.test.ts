import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createTransitionKey,
  listModerationCandidates,
  transitionModerationCandidate,
} from "./candidateModeration";

const emptyList = { items: [], page: 1, page_size: 20, total: 0 };

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("candidate moderation administration", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("normalizes candidate filters into the review-list query", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(emptyList));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await listModerationCandidates(
      { status: "quarantined", query: "  abc123  ", page: 2, pageSize: 50 },
      "mfa-access-token",
    );

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const parsed = new URL(url, "http://synthetic.local");
    const headers = init.headers as Headers;
    expect(parsed.pathname).toContain("/admin/candidates");
    expect(parsed.searchParams.get("status")).toBe("quarantined");
    expect(parsed.searchParams.get("query")).toBe("abc123");
    expect(parsed.searchParams.get("page")).toBe("2");
    expect(parsed.searchParams.get("page_size")).toBe("50");
    expect(headers.get("Authorization")).toBe("Bearer mfa-access-token");
  });

  it("sends manual transitions with the stable retry key and no secret fields", async () => {
    const response = {
      candidate_id: "candidate/synthetic",
      previous_status: "pending",
      current_status: "quarantined",
      state_event_id: "event_synthetic",
      reason_code: "manual.evidence_conflict",
      request_id: "request_synthetic",
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(response));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await transitionModerationCandidate(
      "candidate/synthetic",
      {
        target_status: "quarantined",
        reason_code: "manual.evidence_conflict",
        reason_note: "合成审核说明",
      },
      "mfa-access-token",
      "moderation-transition-stable-key",
    );

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(url).toContain("/admin/candidates/candidate%2Fsynthetic/transition");
    expect(init.method).toBe("POST");
    expect(headers.get("Idempotency-Key")).toBe("moderation-transition-stable-key");
    expect(headers.get("Authorization")).toBe("Bearer mfa-access-token");
    expect(body).toEqual({
      target_status: "quarantined",
      reason_code: "manual.evidence_conflict",
      reason_note: "合成审核说明",
    });
    expect(String(init.body).toLowerCase()).not.toContain("password");
  });

  it("creates a valid namespaced idempotency key", () => {
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });
    expect(createTransitionKey()).toBe("admin-candidate-transition-synthetic-request-id");
  });
});
