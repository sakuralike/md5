import { createClientId } from "@/lib/clientId";
import type {
  AdminCommunityBoardCreateRequest,
  AdminCommunityBoardListResponse,
  AdminCommunityBoardMutationResponse,
  AdminCommunityBoardUpdateRequest,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export function createCommunityConfigurationKey(kind: "create" | "update"): string {
  return `admin-community-board-${kind}-${createClientId()}`;
}

export function listCommunityBoards(token: string): Promise<AdminCommunityBoardListResponse> {
  return apiRequest<AdminCommunityBoardListResponse>("/admin/community/boards", {}, token);
}

export function createCommunityBoard(
  payload: AdminCommunityBoardCreateRequest,
  token: string,
  idempotencyKey: string,
): Promise<AdminCommunityBoardMutationResponse> {
  return apiRequest<AdminCommunityBoardMutationResponse>(
    "/admin/community/boards",
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function updateCommunityBoard(
  boardCode: string,
  payload: AdminCommunityBoardUpdateRequest,
  token: string,
  idempotencyKey: string,
): Promise<AdminCommunityBoardMutationResponse> {
  return apiRequest<AdminCommunityBoardMutationResponse>(
    `/admin/community/boards/${encodeURIComponent(boardCode)}`,
    {
      method: "PATCH",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}
