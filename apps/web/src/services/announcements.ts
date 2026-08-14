import type { WebAnnouncementListResponse } from "@password-detective/api-contract";
import { apiRequest } from "./api";

export function getPopupAnnouncements(limit = 5): Promise<WebAnnouncementListResponse> {
  const boundedLimit = Math.min(20, Math.max(1, Math.trunc(limit)));
  return apiRequest<WebAnnouncementListResponse>(
    `/web/announcements?limit=${boundedLimit}&refresh=${Date.now()}`,
    { cache: "no-store" },
  );
}
