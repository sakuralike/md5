import type { CommunitySearchHealthResponse } from "@password-detective/api-contract";
import { apiRequest } from "./api";

export function getCommunitySearchHealth(
  token: string,
): Promise<CommunitySearchHealthResponse> {
  return apiRequest<CommunitySearchHealthResponse>(
    "/admin/community/search/health",
    {},
    token,
  );
}
