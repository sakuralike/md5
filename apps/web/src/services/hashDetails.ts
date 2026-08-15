import type {
  HashCommentCreateRequest,
  HashCommentListResponse,
  HashDetailResponse,
  HashInteractionResponse,
  HashVoteOutcome,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

function hashPath(algorithm: string, digest: string, suffix = ""): string {
  return `/hashes/${encodeURIComponent(algorithm)}/${encodeURIComponent(digest)}${suffix}`;
}

export function getHashDetail(
  algorithm: string,
  digest: string,
  token?: string,
): Promise<HashDetailResponse> {
  return apiRequest<HashDetailResponse>(hashPath(algorithm, digest), {}, token);
}

export function getHashComments(
  algorithm: string,
  digest: string,
  cursor: string | null = null,
  limit = 20,
  token?: string,
): Promise<HashCommentListResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  return apiRequest<HashCommentListResponse>(
    hashPath(algorithm, digest, `/comments?${params.toString()}`),
    {},
    token,
  );
}

export function setHashLike(
  algorithm: string,
  digest: string,
  liked: boolean,
  token: string,
  idempotencyKey: string,
): Promise<HashInteractionResponse> {
  return apiRequest<HashInteractionResponse>(hashPath(algorithm, digest, "/like"), {
    method: liked ? "PUT" : "DELETE",
    headers: { "Idempotency-Key": idempotencyKey },
  }, token);
}

export function voteHash(
  algorithm: string,
  digest: string,
  outcome: HashVoteOutcome,
  token: string,
  idempotencyKey: string,
): Promise<HashInteractionResponse> {
  return apiRequest<HashInteractionResponse>(hashPath(algorithm, digest, "/vote"), {
    method: "PUT",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ outcome }),
  }, token);
}

export function createHashComment(
  algorithm: string,
  digest: string,
  payload: HashCommentCreateRequest,
  token: string,
  idempotencyKey: string,
): Promise<HashDetailResponse> {
  return apiRequest<HashDetailResponse>(hashPath(algorithm, digest, "/comments"), {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(payload),
  }, token);
}

export function setHashCommentLike(
  algorithm: string,
  digest: string,
  commentId: string,
  liked: boolean,
  token: string,
  idempotencyKey: string,
): Promise<HashDetailResponse> {
  return apiRequest<HashDetailResponse>(
    hashPath(algorithm, digest, `/comments/${encodeURIComponent(commentId)}/like`),
    {
      method: liked ? "PUT" : "DELETE",
      headers: { "Idempotency-Key": idempotencyKey },
    },
    token,
  );
}
