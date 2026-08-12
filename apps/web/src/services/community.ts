import type {
  CommunityBoardListResponse,
  CommunityBookmarkListResponse,
  CommunityBoardCode,
  CommunityCommentCreateRequest,
  CommunityCommentLikeResponse,
  CommunityCommentListResponse,
  CommunityCommentUpdateRequest,
  CommunityHomeResponse,
  CommunityNotificationListResponse,
  CommunityNotificationReadResponse,
  CommunityPostCreateRequest,
  CommunityPostInteractionResponse,
  CommunityPostUpdateRequest,
  CommunityPostDetail,
  CommunityPostListResponse,
  CommunityReportCreateRequest,
  CommunityReportResponse,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export function createCommunityIdempotencyKey(
  kind:
    | "post"
    | "post-update"
    | "post-delete"
    | "comment"
    | "comment-update"
    | "comment-delete"
    | "report"
    | "post-like"
    | "post-unlike"
    | "comment-like"
    | "comment-unlike"
    | "post-bookmark"
    | "post-unbookmark"
    | "notification-read"
    | "notifications-read-all",
): string {
  return `web-community-${kind}-${crypto.randomUUID()}`;
}

export function listCommunityBoards(): Promise<CommunityBoardListResponse> {
  return apiRequest<CommunityBoardListResponse>("/community/boards");
}

export function getCommunityHome(
  boardCode?: CommunityBoardCode,
): Promise<CommunityHomeResponse> {
  const params = new URLSearchParams({ page_size: "50" });
  if (boardCode) params.set("board_code", boardCode);
  return apiRequest<CommunityHomeResponse>(`/community/home?${params.toString()}`);
}

export function listCommunityPosts(
  boardCode?: CommunityBoardCode,
): Promise<CommunityPostListResponse> {
  const params = new URLSearchParams({ page: "1", page_size: "50" });
  if (boardCode) params.set("board_code", boardCode);
  return apiRequest<CommunityPostListResponse>(`/community/posts?${params.toString()}`);
}

export function getCommunityPost(
  postId: string,
  token?: string,
): Promise<CommunityPostDetail> {
  return apiRequest<CommunityPostDetail>(
    `/community/posts/${encodeURIComponent(postId)}`,
    {},
    token,
  );
}

export function createCommunityPost(
  payload: CommunityPostCreateRequest,
  token: string,
  idempotencyKey: string,
): Promise<CommunityPostDetail> {
  return apiRequest<CommunityPostDetail>(
    "/community/posts",
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function listCommunityComments(
  postId: string,
  cursor?: string,
  limit = 20,
  token?: string,
): Promise<CommunityCommentListResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  return apiRequest<CommunityCommentListResponse>(
    `/community/posts/${encodeURIComponent(postId)}/comments?${params.toString()}`,
    {},
    token,
  );
}

export function updateCommunityPost(
  postId: string,
  payload: CommunityPostUpdateRequest,
  token: string,
  idempotencyKey: string,
): Promise<CommunityPostDetail> {
  return apiRequest<CommunityPostDetail>(
    `/community/posts/${encodeURIComponent(postId)}`,
    {
      method: "PATCH",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function deleteCommunityPost(
  postId: string,
  expectedVersion: number,
  token: string,
  idempotencyKey: string,
): Promise<CommunityPostDetail> {
  return apiRequest<CommunityPostDetail>(
    `/community/posts/${encodeURIComponent(postId)}?expected_version=${expectedVersion}`,
    { method: "DELETE", headers: { "Idempotency-Key": idempotencyKey } },
    token,
  );
}

export function createCommunityComment(
  postId: string,
  payload: CommunityCommentCreateRequest,
  token: string,
  idempotencyKey: string,
): Promise<CommunityPostDetail> {
  return apiRequest<CommunityPostDetail>(
    `/community/posts/${encodeURIComponent(postId)}/comments`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function updateCommunityComment(
  commentId: string,
  payload: CommunityCommentUpdateRequest,
  token: string,
  idempotencyKey: string,
): Promise<CommunityPostDetail> {
  return apiRequest<CommunityPostDetail>(
    `/community/comments/${encodeURIComponent(commentId)}`,
    {
      method: "PATCH",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function deleteCommunityComment(
  commentId: string,
  expectedVersion: number,
  token: string,
  idempotencyKey: string,
): Promise<CommunityPostDetail> {
  return apiRequest<CommunityPostDetail>(
    `/community/comments/${encodeURIComponent(commentId)}?expected_version=${expectedVersion}`,
    { method: "DELETE", headers: { "Idempotency-Key": idempotencyKey } },
    token,
  );
}

export function createCommunityReport(
  payload: CommunityReportCreateRequest,
  token: string,
  idempotencyKey: string,
): Promise<CommunityReportResponse> {
  return apiRequest<CommunityReportResponse>(
    "/community/reports",
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}


export function listCommunityNotifications(
  token: string,
  options: { cursor?: string; limit?: number; unreadOnly?: boolean } = {},
): Promise<CommunityNotificationListResponse> {
  const params = new URLSearchParams({ limit: String(options.limit ?? 20) });
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.unreadOnly) params.set("unread_only", "true");
  return apiRequest<CommunityNotificationListResponse>(
    `/community/notifications?${params.toString()}`,
    {},
    token,
  );
}

export function markCommunityNotificationRead(
  notificationId: string,
  token: string,
  idempotencyKey: string,
): Promise<CommunityNotificationReadResponse> {
  return apiRequest<CommunityNotificationReadResponse>(
    `/community/notifications/${encodeURIComponent(notificationId)}/read`,
    { method: "POST", headers: { "Idempotency-Key": idempotencyKey } },
    token,
  );
}

export function markAllCommunityNotificationsRead(
  token: string,
  idempotencyKey: string,
): Promise<CommunityNotificationReadResponse> {
  return apiRequest<CommunityNotificationReadResponse>(
    "/community/notifications/read-all",
    { method: "POST", headers: { "Idempotency-Key": idempotencyKey } },
    token,
  );
}

export function setCommunityPostLike(
  postId: string,
  liked: boolean,
  token: string,
  idempotencyKey: string,
): Promise<CommunityPostInteractionResponse> {
  return apiRequest<CommunityPostInteractionResponse>(
    `/community/posts/${encodeURIComponent(postId)}/like`,
    {
      method: liked ? "PUT" : "DELETE",
      headers: { "Idempotency-Key": idempotencyKey },
    },
    token,
  );
}

export function setCommunityCommentLike(
  commentId: string,
  liked: boolean,
  token: string,
  idempotencyKey: string,
): Promise<CommunityCommentLikeResponse> {
  return apiRequest<CommunityCommentLikeResponse>(
    `/community/comments/${encodeURIComponent(commentId)}/like`,
    {
      method: liked ? "PUT" : "DELETE",
      headers: { "Idempotency-Key": idempotencyKey },
    },
    token,
  );
}

export function setCommunityPostBookmark(
  postId: string,
  bookmarked: boolean,
  token: string,
  idempotencyKey: string,
): Promise<CommunityPostInteractionResponse> {
  return apiRequest<CommunityPostInteractionResponse>(
    `/community/posts/${encodeURIComponent(postId)}/bookmark`,
    {
      method: bookmarked ? "PUT" : "DELETE",
      headers: { "Idempotency-Key": idempotencyKey },
    },
    token,
  );
}

export function listCommunityBookmarks(
  token: string,
  options: { cursor?: string; limit?: number } = {},
): Promise<CommunityBookmarkListResponse> {
  const params = new URLSearchParams({ limit: String(options.limit ?? 20) });
  if (options.cursor) params.set("cursor", options.cursor);
  return apiRequest<CommunityBookmarkListResponse>(
    `/community/bookmarks?${params.toString()}`,
    {},
    token,
  );
}
