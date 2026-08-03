import { afterEach, describe, expect, it, vi } from "vitest";
import { downloadAdminAuditLogs, getAdminAuditLog, listAdminAuditLogs } from "./auditLogs";

function jsonResponse(body: object): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("admin audit log service", () => {
  it("serializes list filters and requests a selected detail", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ items: [], page: 2, page_size: 50, total: 0 }))
      .mockResolvedValueOnce(
        jsonResponse({
          id: "audit-synthetic-1",
          actor_id: null,
          actor_username: null,
          actor_role: null,
          action: "synthetic.action",
          target_type: "synthetic",
          target_id: null,
          result: "success",
          ip_prefix: null,
          request_id: "synthetic-request",
          details: {},
          created_at: "2026-08-03T00:00:00Z",
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await listAdminAuditLogs(
      {
        action: " synthetic.action ",
        result: "success",
        targetType: "synthetic",
        query: "operator",
        createdFrom: "2026-08-01T00:00:00Z",
        page: 2,
        pageSize: 50,
      },
      "synthetic-mfa-token",
    );
    await getAdminAuditLog("audit/synthetic", "synthetic-mfa-token");

    const [listUrl, listInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(listUrl).toContain("action=synthetic.action");
    expect(listUrl).toContain("target_type=synthetic");
    expect(listUrl).toContain("page=2");
    expect((listInit.headers as Headers).get("Authorization")).toBe(
      "Bearer synthetic-mfa-token",
    );
    expect(fetchMock.mock.calls[1]?.[0]).toContain("/admin/audit-logs/audit%2Fsynthetic");
  });

  it("downloads the filtered CSV with server filename and row count", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("\ufeffid,action\nsynthetic,synthetic.action", {
        status: 200,
        headers: {
          "Content-Type": "text/csv; charset=utf-8",
          "Content-Disposition": 'attachment; filename="audit-logs-synthetic.csv"',
          "X-Exported-Rows": "1",
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await downloadAdminAuditLogs(
      { action: "synthetic.action", page: 8, pageSize: 100 },
      "synthetic-mfa-token",
    );

    expect(result.filename).toBe("audit-logs-synthetic.csv");
    expect(result.rowCount).toBe(1);
    expect(await result.blob.text()).toContain("synthetic.action");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("action=synthetic.action");
    expect(url).not.toContain("page=");
    expect((init.headers as Headers).get("Authorization")).toBe(
      "Bearer synthetic-mfa-token",
    );
  });
});
