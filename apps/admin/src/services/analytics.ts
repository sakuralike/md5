import type { AdminCommunityHeatmapResponse } from "@password-detective/api-contract";
import { apiRequest } from "./api";

export function getCommunityHeatmap(
  token: string,
  days = 30,
): Promise<AdminCommunityHeatmapResponse> {
  const params = new URLSearchParams({ days: String(days) });
  return apiRequest<AdminCommunityHeatmapResponse>(
    `/admin/analytics/community-heatmap?${params.toString()}`,
    {},
    token,
  );
}
