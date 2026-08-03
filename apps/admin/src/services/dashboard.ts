import type { AdminDashboardSummary } from "@password-detective/api-contract";
import { apiRequest } from "./api";

export function getAdminDashboardSummary(
  token: string,
  windowHours = 24,
): Promise<AdminDashboardSummary> {
  const params = new URLSearchParams({ window_hours: String(windowHours) });
  return apiRequest<AdminDashboardSummary>(
    `/admin/dashboard/summary?${params.toString()}`,
    {},
    token,
  );
}
