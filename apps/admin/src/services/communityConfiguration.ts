import { createClientId } from "@/lib/clientId";
import type {
  AdminCommunityBoardCreateRequest,
  AdminCommunityBoardListResponse,
  AdminCommunityBoardMutationResponse,
  AdminCommunityBoardUpdateRequest,
  AdminCommunityImageUploadConfigResponse,
  AdminCommunityPostImageListResponse,
  CommunityImageUploadConfig,
  CommunityImageStatus,
  CommunityPostImage,
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

export function getCommunityImageUploadConfig(
  token: string,
): Promise<AdminCommunityImageUploadConfigResponse> {
  return apiRequest<AdminCommunityImageUploadConfigResponse>(
    "/admin/community/image-upload-config",
    {},
    token,
  );
}

export function saveCommunityImageUploadConfig(
  config: CommunityImageUploadConfig,
  token: string,
): Promise<AdminCommunityImageUploadConfigResponse> {
  return apiRequest<AdminCommunityImageUploadConfigResponse>(
    "/admin/community/image-upload-config",
    { method: "PUT", body: JSON.stringify(config) },
    token,
  );
}

export function listCommunityImages(
  status: CommunityImageStatus | "",
  token: string,
): Promise<AdminCommunityPostImageListResponse> {
  const params = new URLSearchParams({ page: "1", page_size: "50" });
  if (status) params.set("status", status);
  return apiRequest<AdminCommunityPostImageListResponse>(
    `/admin/community/images?${params.toString()}`,
    {},
    token,
  );
}

export function removeCommunityImage(
  imageId: string,
  token: string,
): Promise<CommunityPostImage> {
  return apiRequest<CommunityPostImage>(
    `/admin/community/images/${encodeURIComponent(imageId)}/remove`,
    { method: "POST" },
    token,
  );
}
