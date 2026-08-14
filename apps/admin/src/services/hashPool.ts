import type {
  FingerprintAlgorithm,
  HashPoolListResponse,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

export interface HashPoolFilters {
  query?: string;
  algorithm?: FingerprintAlgorithm | "";
  page?: number;
  pageSize?: number;
}

export function listHashPool(
  filters: HashPoolFilters,
  token: string,
): Promise<HashPoolListResponse> {
  const params = new URLSearchParams();
  const query = filters.query?.trim();
  if (query) params.set("query", query);
  if (filters.algorithm) params.set("algorithm", filters.algorithm);
  params.set("page", String(filters.page ?? 1));
  params.set("page_size", String(filters.pageSize ?? 20));
  return apiRequest<HashPoolListResponse>(
    `/admin/hash-pool?${params.toString()}`,
    {},
    token,
  );
}
