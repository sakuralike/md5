import type {
  AdminRewardCatalogItem,
  AdminRewardCatalogListResponse,
  RewardCatalogCreateRequest,
  RewardCatalogStatus,
  RewardCatalogUpdateRequest,
} from "@password-detective/api-contract";
import { createClientId } from "@/lib/clientId";
import { apiRequest } from "./api";

export function createRewardCatalogKey(action: string): string {
  return `reward-catalog-${action}-${createClientId()}`;
}

export function listAdminRewardCatalog(
  status: RewardCatalogStatus | "",
  token: string,
): Promise<AdminRewardCatalogListResponse> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiRequest<AdminRewardCatalogListResponse>(`/admin/rewards/catalog${query}`, {}, token);
}

export function createAdminRewardCatalog(
  payload: RewardCatalogCreateRequest,
  token: string,
  idempotencyKey: string,
): Promise<AdminRewardCatalogItem> {
  return apiRequest<AdminRewardCatalogItem>(
    "/admin/rewards/catalog",
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function updateAdminRewardCatalog(
  itemId: string,
  payload: RewardCatalogUpdateRequest,
  token: string,
  idempotencyKey: string,
): Promise<AdminRewardCatalogItem> {
  return apiRequest<AdminRewardCatalogItem>(
    `/admin/rewards/catalog/${itemId}`,
    {
      method: "PATCH",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}
