import { afterEach, describe, expect, it, vi } from "vitest";
import { getHashComments } from "./hashDetails";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("web hash detail service", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("encodes comment cursor pagination parameters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ items: [], next_cursor: null, has_more: false }),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await getHashComments("sha/256", "digest with space", "cursor/value", 12, "token");

    const url = new URL(String(fetchMock.mock.calls[0]?.[0]), "http://synthetic.local");
    expect(url.pathname).toContain("/hashes/sha%2F256/digest%20with%20space/comments");
    expect(url.searchParams.get("cursor")).toBe("cursor/value");
    expect(url.searchParams.get("limit")).toBe("12");
    expect((fetchMock.mock.calls[0]?.[1]?.headers as Headers).get("Authorization")).toBe(
      "Bearer token",
    );
  });
});
