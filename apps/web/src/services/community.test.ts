import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createCommunityPost,
  deleteCommunityComment,
  getCommunityHome,
  getCommunityPost,
  listCommunityComments,
  listCommunityNotifications,
  markAllCommunityNotificationsRead,
  markCommunityNotificationRead,
  listCommunityBookmarks,
  setCommunityCommentLike,
  setCommunityPostBookmark,
  setCommunityPostLike,
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

  it("keeps notification reads authenticated and idempotent", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(jsonResponse({ items: [], unread_count: 0 })),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await listCommunityNotifications("access-token", {
      cursor: "notification-cursor",
      limit: 15,
      unreadOnly: true,
    });
    await markCommunityNotificationRead(
      "notification/with space",
      "access-token",
      "stable-notification-key",
    );
    await markAllCommunityNotificationsRead(
      "access-token",
      "stable-notifications-all-key",
    );

    const listUrl = new URL(String(fetchMock.mock.calls[0]?.[0]), "http://synthetic.local");
    expect(listUrl.pathname).toContain("/community/notifications");
    expect(listUrl.searchParams.get("cursor")).toBe("notification-cursor");
    expect(listUrl.searchParams.get("limit")).toBe("15");
    expect(listUrl.searchParams.get("unread_only")).toBe("true");
    expect((fetchMock.mock.calls[0]?.[1]?.headers as Headers).get("Authorization")).toBe(
      "Bearer access-token",
    );

    const [readUrl, readInit] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(readUrl).toContain("/community/notifications/notification%2Fwith%20space/read");
    expect((readInit.headers as Headers).get("Idempotency-Key")).toBe(
      "stable-notification-key",
    );
    const [, readAllInit] = fetchMock.mock.calls[2] as [string, RequestInit];
    expect((readAllInit.headers as Headers).get("Idempotency-Key")).toBe(
      "stable-notifications-all-key",
    );
  });


  it("sends authenticated idempotent like bookmark and list requests", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        jsonResponse({
          post_id: "synthetic-post/id",
          like_count: 1,
          viewer_has_liked: true,
          viewer_has_bookmarked: false,
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await setCommunityPostLike(
      "synthetic-post/id",
      true,
      "synthetic-token",
      "synthetic-like-key",
    );
    await setCommunityCommentLike(
      "synthetic-comment/id",
      false,
      "synthetic-token",
      "synthetic-unlike-key",
    );
    await setCommunityPostBookmark(
      "synthetic-post/id",
      true,
      "synthetic-token",
      "synthetic-bookmark-key",
    );
    await listCommunityBookmarks("synthetic-token", { cursor: "next/value", limit: 10 });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/v1/community/posts/synthetic-post%2Fid/like",
      expect.objectContaining({ method: "PUT" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/v1/community/comments/synthetic-comment%2Fid/like",
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/v1/community/posts/synthetic-post%2Fid/bookmark",
      expect.objectContaining({ method: "PUT" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/api/v1/community/bookmarks?limit=10&cursor=next%2Fvalue",
      expect.any(Object),
    );
    for (const call of fetchMock.mock.calls) {
      const headers = new Headers(call[1]?.headers);
      expect(headers.get("Authorization")).toBe("Bearer synthetic-token");
    }
  });

});
