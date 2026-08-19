import type {
  AdminRewardCatalogItem,
  AdminRewardCatalogListResponse,
  RewardCatalogCreateRequest,
  RewardCatalogStatus,
  RewardCatalogUpdateRequest,
  RewardInventoryAdjustmentRequest,
  RewardAdminOrder,
  RewardAdminOrderActionRequest,
  RewardAdminOrderListResponse,
  RewardOperationsStatsResponse,
  RewardOrderStatus,
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

export function adjustAdminRewardInventory(
  itemId: string,
  payload: RewardInventoryAdjustmentRequest,
  token: string,
  idempotencyKey: string,
): Promise<AdminRewardCatalogItem> {
  return apiRequest<AdminRewardCatalogItem>(
    `/admin/rewards/catalog/${itemId}/inventory-adjustments`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function listAdminRewardOrders(
  status: RewardOrderStatus | "",
  token: string,
): Promise<RewardAdminOrderListResponse> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiRequest<RewardAdminOrderListResponse>(`/admin/rewards/orders${query}`, {}, token);
}

export function getAdminRewardOrder(orderId: string, token: string): Promise<RewardAdminOrder> {
  return apiRequest<RewardAdminOrder>(`/admin/rewards/orders/${orderId}`, {}, token);
}

export function getRewardOperationsStats(token: string): Promise<RewardOperationsStatsResponse> {
  return apiRequest<RewardOperationsStatsResponse>("/admin/rewards/operations/stats", {}, token);
}

export function retryAdminRewardOrder(
  orderId: string,
  payload: RewardAdminOrderActionRequest,
  token: string,
  idempotencyKey: string,
): Promise<RewardAdminOrder> {
  return apiRequest<RewardAdminOrder>(
    `/admin/rewards/orders/${orderId}/retry`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function compensateAdminRewardOrder(
  orderId: string,
  payload: RewardAdminOrderActionRequest,
  token: string,
  idempotencyKey: string,
): Promise<RewardAdminOrder> {
  return apiRequest<RewardAdminOrder>(
    `/admin/rewards/orders/${orderId}/compensate`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}
