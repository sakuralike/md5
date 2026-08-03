import { afterEach, describe, expect, it, vi } from "vitest";
import {
  assignRiskAlert,
  createRiskAlertAssignmentKey,
  createRiskAlertTransitionKey,
  listRiskAlertOperators,
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
        assignedToId: "operator-1",
        overdue: true,
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
    expect(parsed.searchParams.get("assigned_to_id")).toBe("operator-1");
    expect(parsed.searchParams.get("overdue")).toBe("true");
    expect(parsed.searchParams.get("query")).toBe("candidate-1");
    expect(headers.get("Authorization")).toBe("Bearer mfa-token");
  });

  it("loads eligible operators", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);

    await listRiskAlertOperators("mfa-token");

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/admin/risk-alerts/operators");
  });

  it("sends an idempotent assignment request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ current_assignee_id: "op-1" }));
    vi.stubGlobal("fetch", fetchMock);

    await assignRiskAlert(
      "alert/synthetic",
      { assignee_id: "op-1", assignment_note: "合成指派说明" },
      "mfa-token",
      "risk-alert-assignment-key",
    );

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(url).toContain("/admin/risk-alerts/alert%2Fsynthetic/assign");
    expect(headers.get("Idempotency-Key")).toBe("risk-alert-assignment-key");
    expect(JSON.parse(String(init.body))).toEqual({
      assignee_id: "op-1",
      assignment_note: "合成指派说明",
    });
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

  it("creates namespaced idempotency keys", () => {
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });
    expect(createRiskAlertTransitionKey()).toBe(
      "admin-risk-alert-transition-synthetic-request-id",
    );
    expect(createRiskAlertAssignmentKey()).toBe(
      "admin-risk-alert-assignment-synthetic-request-id",
    );
  });
});
