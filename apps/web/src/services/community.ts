import type {
  CommunityBoardListResponse,
  CommunityBoardCode,
  CommunityCommentCreateRequest,
  CommunityCommentListResponse,
  CommunityCommentUpdateRequest,
  CommunityPostCreateRequest,
  CommunityPostUpdateRequest,
  CommunityPostDetail,
  CommunityPostListResponse,
  CommunityReportCreateRequest,
  CommunityReportResponse,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export function createCommunityIdempotencyKey(
  kind: "post" | "post-update" | "post-delete" | "comment" | "comment-update" | "comment-delete" | "report",
): string {
  return `web-community-${kind}-${crypto.randomUUID()}`;
}

export function listCommunityBoards(): Promise<CommunityBoardListResponse> {
  return apiRequest<CommunityBoardListResponse>("/community/boards");
}

export function listCommunityPosts(
  boardCode?: CommunityBoardCode,
): Promise<CommunityPostListResponse> {
  const params = new URLSearchParams({ page: "1", page_size: "50" });
  if (boardCode) params.set("board_code", boardCode);
  return apiRequest<CommunityPostListResponse>(`/community/posts?${params.toString()}`);
}

export function getCommunityPost(postId: string): Promise<CommunityPostDetail> {
  return apiRequest<CommunityPostDetail>(`/community/posts/${postId}`);
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
): Promise<CommunityCommentListResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  return apiRequest<CommunityCommentListResponse>(
    `/community/posts/${postId}/comments?${params.toString()}`,
  );
}

export function updateCommunityPost(
  postId: string,
  payload: CommunityPostUpdateRequest,
  token: string,
  idempotencyKey: string,
): Promise<CommunityPostDetail> {
  return apiRequest<CommunityPostDetail>(
    `/community/posts/${postId}`,
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
    `/community/posts/${postId}?expected_version=${expectedVersion}`,
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
    `/community/posts/${postId}/comments`,
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
    `/community/comments/${commentId}`,
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
    `/community/comments/${commentId}?expected_version=${expectedVersion}`,
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
