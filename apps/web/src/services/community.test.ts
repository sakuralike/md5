import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createCommunityPost,
  deleteCommunityComment,
  getCommunityHome,
  getCommunityPost,
  listCommunityComments,
} from "./community";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("web community service", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses the home aggregate and encodes resource identifiers", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(jsonResponse({ items: [] })),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await getCommunityHome("security");
    await getCommunityPost("post/with space");
    await listCommunityComments("post/with space", "cursor-value", 10);

    const homeUrl = new URL(String(fetchMock.mock.calls[0]?.[0]), "http://synthetic.local");
    expect(homeUrl.pathname).toContain("/community/home");
    expect(homeUrl.searchParams.get("board_code")).toBe("security");
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain(
      "/community/posts/post%2Fwith%20space",
    );
    const commentsUrl = new URL(String(fetchMock.mock.calls[2]?.[0]), "http://synthetic.local");
    expect(commentsUrl.pathname).toContain("/community/posts/post%2Fwith%20space/comments");
    expect(commentsUrl.searchParams.get("cursor")).toBe("cursor-value");
    expect(commentsUrl.searchParams.get("limit")).toBe("10");
  });

  it("keeps idempotency and authorization headers on writes", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(jsonResponse({ id: "synthetic-post" })),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await createCommunityPost(
      {
        board_code: "general",
        title: "合成社区主题",
        content: "这是只包含合成数据的社区主题内容，用于验证发布请求。",
        rules_accepted: true,
      },
      "access-token",
      "stable-post-key",
    );
    await deleteCommunityComment("comment/with space", 3, "access-token", "stable-delete-key");

    const createHeaders = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(createHeaders.get("Authorization")).toBe("Bearer access-token");
    expect(createHeaders.get("Idempotency-Key")).toBe("stable-post-key");
    const [deleteUrl, deleteInit] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(deleteUrl).toContain(
      "/community/comments/comment%2Fwith%20space?expected_version=3",
    );
    expect((deleteInit.headers as Headers).get("Idempotency-Key")).toBe(
      "stable-delete-key",
    );
  });
});
