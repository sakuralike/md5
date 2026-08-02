import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createRiskAlertTransitionKey,
  listRiskAlerts,
  transitionRiskAlert,
} from "./riskAlerts";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("risk-alert administration", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("normalizes risk queue filters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ items: [], page: 1, page_size: 50, total: 0 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await listRiskAlerts(
      {
        kind: "failure_surge",
        severity: "high",
        status: "open",
        query: "  candidate-1  ",
        pageSize: 50,
      },
      "mfa-token",
    );

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const parsed = new URL(url, "http://synthetic.local");
    const headers = init.headers as Headers;
    expect(parsed.pathname).toContain("/admin/risk-alerts");
    expect(parsed.searchParams.get("kind")).toBe("failure_surge");
    expect(parsed.searchParams.get("severity")).toBe("high");
    expect(parsed.searchParams.get("status")).toBe("open");
    expect(parsed.searchParams.get("query")).toBe("candidate-1");
    expect(headers.get("Authorization")).toBe("Bearer mfa-token");
  });

  it("sends a controlled transition with a stable retry key", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ current_status: "resolved" }));
    vi.stubGlobal("fetch", fetchMock);

    await transitionRiskAlert(
      "alert/synthetic",
      {
        target_status: "resolved",
        resolution_code: "admin.mitigated",
        resolution_note: "合成处置说明",
      },
      "mfa-token",
      "risk-alert-stable-key",
    );

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(url).toContain("/admin/risk-alerts/alert%2Fsynthetic/transition");
    expect(headers.get("Idempotency-Key")).toBe("risk-alert-stable-key");
    expect(JSON.parse(String(init.body))).toEqual({
      target_status: "resolved",
      resolution_code: "admin.mitigated",
      resolution_note: "合成处置说明",
    });
  });

  it("creates a namespaced idempotency key", () => {
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });
    expect(createRiskAlertTransitionKey()).toBe(
      "admin-risk-alert-transition-synthetic-request-id",
    );
  });
});
