import { afterEach, describe, expect, it, vi } from "vitest";
import { listHashPool } from "./hashPool";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("hash pool administration", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("normalizes hash-pool filters and authenticates the request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        overview: {
          verified_candidates: 0,
          unique_archives: 0,
          unique_fingerprints: 0,
          pending_candidates: 0,
          quarantined_candidates: 0,
        },
        items: [],
        page: 2,
        page_size: 50,
        total: 0,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await listHashPool(
      { query: "  abc123  ", algorithm: "sha256", page: 2, pageSize: 50 },
      "synthetic-admin-token",
    );

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const parsed = new URL(url, "http://synthetic.local");
    const headers = init.headers as Headers;
    expect(parsed.pathname).toContain("/admin/hash-pool");
    expect(parsed.searchParams.get("query")).toBe("abc123");
    expect(parsed.searchParams.get("algorithm")).toBe("sha256");
    expect(parsed.searchParams.get("page")).toBe("2");
    expect(parsed.searchParams.get("page_size")).toBe("50");
    expect(headers.get("Authorization")).toBe("Bearer synthetic-admin-token");
  });
});
