import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createCommunityDirectConversation,
  createCommunityPost,
  deleteCommunityComment,
  getCommunityActivityPreferences,
  getCommunityHome,
  getCommunityNotificationPreferences,
  getCommunityPost,
  listCommunityActivity,
  listCommunityComments,
  listCommunityDirectConversations,
  listCommunityDirectMessages,
  listCommunityNotifications,
  markAllCommunityNotificationsRead,
  markCommunityNotificationRead,
  searchCommunity,
  sendCommunityDirectMessage,
  reportCommunityDirectMessage,
  listCommunityBookmarks,
  setCommunityCommentLike,
  setCommunityPostBookmark,
  setCommunityPostLike,
  updateCommunityActivityPreferences,
  updateCommunityDirectMemberState,
  updateCommunityDirectReadState,
  updateCommunityNotificationPreferences,
  updateCommunityGroupSeo,
  updateCommunityPostSeo,
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

  it("encodes activity feeds, notification filters, and preference updates", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(jsonResponse({ items: [], unread_count: 0 })),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await listCommunityActivity("following", "access-token", {
      cursor: "activity-cursor",
      limit: 12,
    });
    await listCommunityNotifications("access-token", { kind: "reply", limit: 9 });
    await getCommunityActivityPreferences("access-token");
    await updateCommunityActivityPreferences(
      { share_group_joins: false, share_follows: true },
      "access-token",
    );
    await getCommunityNotificationPreferences("access-token");
    await updateCommunityNotificationPreferences(
      {
        items: [
          { kind: "follow", in_app_enabled: false, email_digest_enabled: true },
        ],
      },
      "access-token",
    );

    const activityUrl = new URL(String(fetchMock.mock.calls[0]?.[0]), "http://synthetic.local");
    expect(activityUrl.searchParams.get("feed")).toBe("following");
    expect(activityUrl.searchParams.get("cursor")).toBe("activity-cursor");
    expect(activityUrl.searchParams.get("limit")).toBe("12");
    expect((fetchMock.mock.calls[0]?.[1]?.headers as Headers).get("Authorization")).toBe(
      "Bearer access-token",
    );

    const notificationUrl = new URL(
      String(fetchMock.mock.calls[1]?.[0]),
      "http://synthetic.local",
    );
    expect(notificationUrl.searchParams.get("kind")).toBe("reply");
    expect(notificationUrl.searchParams.get("limit")).toBe("9");

    const activityUpdate = fetchMock.mock.calls[3]?.[1] as RequestInit;
    expect(activityUpdate.method).toBe("PUT");
    expect(activityUpdate.body).toBe(
      JSON.stringify({ share_group_joins: false, share_follows: true }),
    );
    const notificationUpdate = fetchMock.mock.calls[5]?.[1] as RequestInit;
    expect(notificationUpdate.method).toBe("PUT");
    expect(notificationUpdate.body).toBe(
      JSON.stringify({
        items: [
          { kind: "follow", in_app_enabled: false, email_digest_enabled: true },
        ],
      }),
    );
  });

  it("encodes a community search query and repeated result types", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(jsonResponse({ items: [], provider: { mode: "test", degraded: false } })),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await searchCommunity({
      query: "recover guide",
      types: ["post", "group"],
      page: 2,
    });

    const url = new URL(String(fetchMock.mock.calls[0]?.[0]), "http://synthetic.local");
    expect(url.pathname).toContain("/community/search");
    expect(url.search).toBe("?q=recover+guide&types=post&types=group&page=2&page_size=20");
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

  it("updates community post SEO with optimistic concurrency and idempotency", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(jsonResponse({ id: "synthetic-post", seo_version: 4 })),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await updateCommunityPostSeo(
      "post/with space",
      {
        seo_title: "合成 SEO 标题",
        seo_description: null,
        seo_keywords: ["合成", "SEO"],
        seo_canonical_path: "/community/posts/synthetic-post",
        og_image_url: null,
        expected_seo_version: 3,
      },
      "access-token",
      "stable-post-seo-key",
    );

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/community/posts/post%2Fwith%20space/seo");
    expect(init.method).toBe("PATCH");
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer access-token");
    expect((init.headers as Headers).get("Idempotency-Key")).toBe("stable-post-seo-key");
    expect(JSON.parse(String(init.body))).toEqual({
      seo_title: "合成 SEO 标题",
      seo_description: null,
      seo_keywords: ["合成", "SEO"],
      seo_canonical_path: "/community/posts/synthetic-post",
      og_image_url: null,
      expected_seo_version: 3,
    });
  });

  it("updates community group SEO with optimistic concurrency and idempotency", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(jsonResponse({ slug: "synthetic-lab", seo_version: 2 })),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await updateCommunityGroupSeo(
      "group/with space",
      {
        seo_title: "合成群组搜索标题",
        seo_description: null,
        seo_keywords: ["合成", "群组"],
        seo_canonical_path: "/community/groups/synthetic-lab",
        og_image_url: null,
        expected_seo_version: 1,
      },
      "access-token",
      "stable-group-seo-key",
    );

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/community/groups/group%2Fwith%20space/seo");
    expect(init.method).toBe("PATCH");
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer access-token");
    expect((init.headers as Headers).get("Idempotency-Key")).toBe("stable-group-seo-key");
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

  it("reports a direct message with an encoded id and idempotency header", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(jsonResponse({ id: "report-1", message_id: "message-1", status: "open" })),
    );
    vi.stubGlobal("fetch", fetchMock);
    await reportCommunityDirectMessage(
      "message/with space",
      { reason: "harassment", details: "合成私信举报最小披露说明。" },
      "access-token",
      "direct-report-key",
    );
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/community/messages/message%2Fwith%20space/reports");
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer access-token");
    expect((init.headers as Headers).get("Idempotency-Key")).toBe("direct-report-key");
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

  it("encodes authenticated private message reads and idempotent writes", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(jsonResponse({ items: [], next_cursor: null, has_more: false })),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await createCommunityDirectConversation(
      { recipient_username: "recipient/name" },
      "access-token",
      "conversation-key",
    );
    await listCommunityDirectConversations("access-token", {
      cursor: "conversation/cursor",
      includeArchived: true,
      limit: 12,
    });
    await listCommunityDirectMessages(
      "conversation/with space",
      "access-token",
      { cursor: "message/cursor", limit: 15 },
    );
    await sendCommunityDirectMessage(
      "conversation/with space",
      { body: "合成私信正文", client_message_id: "client-message-id" },
      "access-token",
      "message-key",
    );
    await updateCommunityDirectReadState(
      "conversation/with space",
      { last_read_sequence: 9 },
      "access-token",
      "read-key",
    );
    await updateCommunityDirectMemberState(
      "conversation/with space",
      { archived: true },
      "access-token",
      "member-key",
    );

    const createInit = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(createInit.method).toBe("POST");
    expect(new Headers(createInit.headers).get("Idempotency-Key")).toBe("conversation-key");

    const listUrl = new URL(String(fetchMock.mock.calls[1]?.[0]), "http://synthetic.local");
    expect(listUrl.searchParams.get("cursor")).toBe("conversation/cursor");
    expect(listUrl.searchParams.get("include_archived")).toBe("true");
    expect(listUrl.searchParams.get("limit")).toBe("12");

    expect(String(fetchMock.mock.calls[2]?.[0])).toContain(
      "/community/direct-conversations/conversation%2Fwith%20space/messages",
    );
    const messageListUrl = new URL(String(fetchMock.mock.calls[2]?.[0]), "http://synthetic.local");
    expect(messageListUrl.searchParams.get("cursor")).toBe("message/cursor");
    expect(messageListUrl.searchParams.get("limit")).toBe("15");

    const sendInit = fetchMock.mock.calls[3]?.[1] as RequestInit;
    expect(sendInit.method).toBe("POST");
    expect(new Headers(sendInit.headers).get("Idempotency-Key")).toBe("message-key");
    expect(sendInit.body).toBe(JSON.stringify({
      body: "合成私信正文",
      client_message_id: "client-message-id",
    }));

    const readInit = fetchMock.mock.calls[4]?.[1] as RequestInit;
    expect(readInit.method).toBe("PATCH");
    expect(new Headers(readInit.headers).get("Idempotency-Key")).toBe("read-key");

    const memberInit = fetchMock.mock.calls[5]?.[1] as RequestInit;
    expect(memberInit.method).toBe("PATCH");
    expect(new Headers(memberInit.headers).get("Idempotency-Key")).toBe("member-key");

    for (const call of fetchMock.mock.calls) {
      expect(new Headers(call[1]?.headers).get("Authorization")).toBe("Bearer access-token");
    }
  });
});
