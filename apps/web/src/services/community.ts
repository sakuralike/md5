import type {
  CommunityActivityFeed,
  CommunityActivityListResponse,
  CommunityActivityPreferenceResponse,
  CommunityActivityPreferenceUpdateRequest,
  CommunityBoardListResponse,
  CommunityBookmarkListResponse,
  CommunityBoardCode,
  CommunityCommentCreateRequest,
  CommunityCommentLikeResponse,
  CommunityCommentListResponse,
  CommunityCommentUpdateRequest,
  CommunityGroupCreateRequest,
  CommunityGroupDetail,
  CommunityGroupListResponse,
  CommunityGroupMemberDecisionRequest,
  CommunityGroupMembershipResponse,
  CommunityGroupRole,
  CommunityGroupUpdateRequest,
  CommunityHomeResponse,
  CommunityNotificationKind,
  CommunityNotificationListResponse,
  CommunityNotificationPreferencesResponse,
  CommunityNotificationPreferencesUpdateRequest,
  CommunityNotificationReadResponse,
  CommunityMuteRequest,
  CommunityOwnProfileResponse,
  CommunityPrivacyUpdateRequest,
  CommunityProfileUpdateRequest,
  CommunityPublicProfileResponse,
  CommunityRelationListResponse,
  CommunityRelationshipMutationResponse,
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
    | "notifications-read-all"
    | "notification-preferences"
    | "activity-preferences"
    | "profile-update"
    | "privacy-update"
    | "follow"
    | "unfollow"
    | "block"
    | "unblock"
    | "mute"
    | "unmute"
    | "group-create"
    | "group-update"
    | "group-join"
    | "group-leave"
    | "group-member-decision"
    | "group-member-role",
): string {
  return `web-community-${kind}-${crypto.randomUUID()}`;
}

export function listCommunityBoards(): Promise<CommunityBoardListResponse> {
  return apiRequest<CommunityBoardListResponse>("/community/boards");
}

export function getCommunityHome(
  boardCode?: CommunityBoardCode,
  token?: string,
): Promise<CommunityHomeResponse> {
  const params = new URLSearchParams({ page_size: "50" });
  if (boardCode) params.set("board_code", boardCode);
  return apiRequest<CommunityHomeResponse>(`/community/home?${params.toString()}`, {}, token);
}

export function listCommunityPosts(
  boardCode?: CommunityBoardCode,
  token?: string,
  groupSlug?: string,
): Promise<CommunityPostListResponse> {
  const params = new URLSearchParams({ page: "1", page_size: "50" });
  if (boardCode) params.set("board_code", boardCode);
  if (groupSlug) params.set("group_slug", groupSlug);
  return apiRequest<CommunityPostListResponse>(`/community/posts?${params.toString()}`, {}, token);
}

export function listCommunityGroups(token?: string): Promise<CommunityGroupListResponse> {
  return apiRequest<CommunityGroupListResponse>("/community/groups", {}, token);
}

export function getCommunityGroup(slug: string, token?: string): Promise<CommunityGroupDetail> {
  return apiRequest<CommunityGroupDetail>(`/community/groups/${encodeURIComponent(slug)}`, {}, token);
}

export function createCommunityGroup(
  payload: CommunityGroupCreateRequest, token: string, idempotencyKey: string,
): Promise<CommunityGroupDetail> {
  return apiRequest<CommunityGroupDetail>("/community/groups", {
    method: "POST", headers: { "Idempotency-Key": idempotencyKey }, body: JSON.stringify(payload),
  }, token);
}

export function updateCommunityGroup(
  slug: string, payload: CommunityGroupUpdateRequest, token: string, idempotencyKey: string,
): Promise<CommunityGroupDetail> {
  return apiRequest<CommunityGroupDetail>(`/community/groups/${encodeURIComponent(slug)}`, {
    method: "PATCH", headers: { "Idempotency-Key": idempotencyKey }, body: JSON.stringify(payload),
  }, token);
}

export function setCommunityGroupMembership(
  slug: string, joined: boolean, token: string, idempotencyKey: string,
): Promise<CommunityGroupMembershipResponse> {
  return apiRequest<CommunityGroupMembershipResponse>(
    `/community/groups/${encodeURIComponent(slug)}/${joined ? "join" : "membership"}`,
    { method: joined ? "POST" : "DELETE", headers: { "Idempotency-Key": idempotencyKey } }, token,
  );
}

export function decideCommunityGroupMember(
  slug: string, username: string, payload: CommunityGroupMemberDecisionRequest,
  token: string, idempotencyKey: string,
): Promise<CommunityGroupMembershipResponse> {
  return apiRequest<CommunityGroupMembershipResponse>(
    `/community/groups/${encodeURIComponent(slug)}/members/${encodeURIComponent(username)}/decision`,
    { method: "POST", headers: { "Idempotency-Key": idempotencyKey }, body: JSON.stringify(payload) }, token,
  );
}

export function changeCommunityGroupMemberRole(
  slug: string, username: string, role: CommunityGroupRole, token: string, idempotencyKey: string,
): Promise<CommunityGroupMembershipResponse> {
  return apiRequest<CommunityGroupMembershipResponse>(
    `/community/groups/${encodeURIComponent(slug)}/members/${encodeURIComponent(username)}/role?role=${encodeURIComponent(role)}`,
    { method: "PATCH", headers: { "Idempotency-Key": idempotencyKey } }, token,
  );
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
  options: {
    cursor?: string;
    limit?: number;
    unreadOnly?: boolean;
    kind?: CommunityNotificationKind;
  } = {},
): Promise<CommunityNotificationListResponse> {
  const params = new URLSearchParams({ limit: String(options.limit ?? 20) });
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.unreadOnly) params.set("unread_only", "true");
  if (options.kind) params.set("kind", options.kind);
  return apiRequest<CommunityNotificationListResponse>(
    `/community/notifications?${params.toString()}`,
    {},
    token,
  );
}

export function getCommunityNotificationPreferences(
  token: string,
): Promise<CommunityNotificationPreferencesResponse> {
  return apiRequest<CommunityNotificationPreferencesResponse>(
    "/community/notifications/preferences",
    {},
    token,
  );
}

export function updateCommunityNotificationPreferences(
  payload: CommunityNotificationPreferencesUpdateRequest,
  token: string,
): Promise<CommunityNotificationPreferencesResponse> {
  return apiRequest<CommunityNotificationPreferencesResponse>(
    "/community/notifications/preferences",
    { method: "PUT", body: JSON.stringify(payload) },
    token,
  );
}

export function listCommunityActivity(
  feed: CommunityActivityFeed,
  token?: string,
  options: { cursor?: string; limit?: number } = {},
): Promise<CommunityActivityListResponse> {
  const params = new URLSearchParams({ feed, limit: String(options.limit ?? 20) });
  if (options.cursor) params.set("cursor", options.cursor);
  return apiRequest<CommunityActivityListResponse>(
    `/community/activity?${params.toString()}`,
    {},
    token,
  );
}

export function getCommunityActivityPreferences(
  token: string,
): Promise<CommunityActivityPreferenceResponse> {
  return apiRequest<CommunityActivityPreferenceResponse>(
    "/community/activity/preferences",
    {},
    token,
  );
}

export function updateCommunityActivityPreferences(
  payload: CommunityActivityPreferenceUpdateRequest,
  token: string,
): Promise<CommunityActivityPreferenceResponse> {
  return apiRequest<CommunityActivityPreferenceResponse>(
    "/community/activity/preferences",
    { method: "PUT", body: JSON.stringify(payload) },
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


export function getCommunityPublicProfile(
  username: string,
  token?: string,
): Promise<CommunityPublicProfileResponse> {
  return apiRequest<CommunityPublicProfileResponse>(
    `/community/users/${encodeURIComponent(username)}`,
    {},
    token,
  );
}

export function getCommunityOwnProfile(token: string): Promise<CommunityOwnProfileResponse> {
  return apiRequest<CommunityOwnProfileResponse>("/community/me/profile", {}, token);
}

export function updateCommunityOwnProfile(
  payload: CommunityProfileUpdateRequest,
  token: string,
  idempotencyKey: string,
): Promise<CommunityOwnProfileResponse> {
  return apiRequest<CommunityOwnProfileResponse>(
    "/community/me/profile",
    {
      method: "PATCH",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function updateCommunityPrivacy(
  payload: CommunityPrivacyUpdateRequest,
  token: string,
  idempotencyKey: string,
): Promise<CommunityOwnProfileResponse> {
  return apiRequest<CommunityOwnProfileResponse>(
    "/community/me/privacy",
    {
      method: "PATCH",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function listCommunityRelations(
  username: string,
  direction: "followers" | "following",
  token?: string,
  cursor?: string,
): Promise<CommunityRelationListResponse> {
  const params = new URLSearchParams({ limit: "20" });
  if (cursor) params.set("cursor", cursor);
  return apiRequest<CommunityRelationListResponse>(
    `/community/users/${encodeURIComponent(username)}/${direction}?${params.toString()}`,
    {},
    token,
  );
}

export function setCommunityUserRelation(
  username: string,
  relation: "follow" | "block" | "mute",
  enabled: boolean,
  token: string,
  idempotencyKey: string,
  mutePayload: CommunityMuteRequest = { expires_at: null },
): Promise<CommunityRelationshipMutationResponse> {
  return apiRequest<CommunityRelationshipMutationResponse>(
    `/community/users/${encodeURIComponent(username)}/${relation}`,
    {
      method: enabled ? "PUT" : "DELETE",
      headers: { "Idempotency-Key": idempotencyKey },
      ...(enabled && relation === "mute" ? { body: JSON.stringify(mutePayload) } : {}),
    },
    token,
  );
}
