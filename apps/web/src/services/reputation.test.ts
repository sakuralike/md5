import { afterEach, describe, expect, it, vi } from "vitest";
import { loadTrustCenter } from "./reputation";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("web trust center", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads the private summary and all four event streams with authorization", async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("trust-profile")) {
        return Promise.resolve(
          jsonResponse({
            reputation_score: 53,
            points: { available: 1, pending: 0, reversed: 0 },
          }),
        );
      }
      return Promise.resolve(jsonResponse({ items: [], page: 1, page_size: 50, total: 0 }));
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await loadTrustCenter("access-token");

    expect(result.profile.reputation_score).toBe(53);
    expect(fetchMock).toHaveBeenCalledTimes(5);
    const paths = fetchMock.mock.calls.map(([url]) => new URL(String(url), "http://synthetic.local").pathname);
    expect(paths).toEqual(
      expect.arrayContaining([
        expect.stringContaining("/me/trust-profile"),
        expect.stringContaining("/me/points"),
        expect.stringContaining("/me/reputation"),
        expect.stringContaining("/me/feedback"),
        expect.stringContaining("/me/growth-events"),
      ]),
    );
    for (const [, init] of fetchMock.mock.calls as [string, RequestInit][]) {
      expect((init.headers as Headers).get("Authorization")).toBe("Bearer access-token");
    }
  });
});
