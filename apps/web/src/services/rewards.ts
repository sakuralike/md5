import type {
  RewardCatalogResponse,
  RewardOrderCreateRequest,
  RewardOrderDetail,
  RewardOrderListResponse,
} from "@password-detective/api-contract";
import { createClientId } from "@/lib/clientId";
import { apiRequest } from "./api";

export function getRewardCatalog(token?: string): Promise<RewardCatalogResponse> {
  return apiRequest<RewardCatalogResponse>("/rewards/catalog", {}, token);
}

export function createRewardOrderKey(): string {
  return `reward-order-${createClientId()}`;
}

export function createRewardOrder(
  payload: RewardOrderCreateRequest,
  token: string,
  idempotencyKey: string,
): Promise<RewardOrderDetail> {
  return apiRequest<RewardOrderDetail>(
    "/rewards/orders",
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function listRewardOrders(token: string): Promise<RewardOrderListResponse> {
  return apiRequest<RewardOrderListResponse>("/rewards/orders?page_size=50", {}, token);
}

export function cancelRewardOrder(
  orderId: string,
  token: string,
  idempotencyKey: string,
): Promise<RewardOrderDetail> {
  return apiRequest<RewardOrderDetail>(
    `/rewards/orders/${orderId}/cancel`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
    },
    token,
  );
}
