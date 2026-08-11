import type {
  CommunityBoardListResponse,
  CommunityBoardCode,
  CommunityCommentCreateRequest,
  CommunityPostCreateRequest,
  CommunityPostDetail,
  CommunityPostListResponse,
  CommunityReportCreateRequest,
  CommunityReportResponse,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export function createCommunityIdempotencyKey(kind: "post" | "comment" | "report"): string {
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
