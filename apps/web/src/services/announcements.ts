import type { DesktopAnnouncementListResponse } from "@password-detective/api-contract";
import { apiRequest } from "./api";

export function getPopupAnnouncements(limit = 5): Promise<DesktopAnnouncementListResponse> {
  const boundedLimit = Math.min(20, Math.max(1, Math.trunc(limit)));
  return apiRequest<DesktopAnnouncementListResponse>(
    `/desktop/announcements?limit=${boundedLimit}&refresh=${Date.now()}`,
    { cache: "no-store" },
  );
}
