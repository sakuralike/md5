import type { RewardCatalogResponse } from "@password-detective/api-contract";
import { apiRequest } from "./api";

export function getRewardCatalog(token?: string): Promise<RewardCatalogResponse> {
  return apiRequest<RewardCatalogResponse>("/rewards/catalog", {}, token);
}
