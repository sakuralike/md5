import type {
  DesktopPluginCapability,
  DesktopPluginReport,
  DesktopPluginReportListResponse,
  DesktopPluginReviewDetail,
  DesktopPluginReviewQueueResponse,
} from "@password-detective/api-contract";
import { createClientId } from "@/lib/clientId";
import { apiRequest } from "./api";

function mutationHeaders(): HeadersInit {
  return { "Idempotency-Key": `plugin-review-${createClientId()}` };
}

export function listPluginReviews(token: string): Promise<DesktopPluginReviewQueueResponse> {
  return apiRequest("/admin/plugin-reviews/queue?page=1&page_size=100", {}, token);
}

export function getPluginReview(token: string, versionId: string): Promise<DesktopPluginReviewDetail> {
  return apiRequest(`/admin/plugin-reviews/versions/${encodeURIComponent(versionId)}`, {}, token);
}

function mutateVersion(
  token: string,
  versionId: string,
  action: string,
  payload: Record<string, unknown>,
): Promise<DesktopPluginReviewDetail> {
  return apiRequest(
    `/admin/plugin-reviews/versions/${encodeURIComponent(versionId)}/${action}`,
    { method: "POST", headers: mutationHeaders(), body: JSON.stringify(payload) },
    token,
  );
}

export function approvePluginVersion(
  token: string,
  detail: DesktopPluginReviewDetail,
  approvedCapabilities: DesktopPluginCapability[],
  reviewNote: string,
): Promise<DesktopPluginReviewDetail> {
  return mutateVersion(token, detail.version_id, "approve", {
    version: detail.version,
    approved_capabilities: approvedCapabilities,
    review_note: reviewNote,
  });
}

export function rejectPluginVersion(token: string, detail: DesktopPluginReviewDetail, reviewNote: string) {
  return mutateVersion(token, detail.version_id, "reject", { version: detail.version, review_note: reviewNote });
}

export function publishPluginVersion(token: string, detail: DesktopPluginReviewDetail) {
  return mutateVersion(token, detail.version_id, "publish", { version: detail.version, channel: "stable" });
}

export function yankPluginVersion(token: string, detail: DesktopPluginReviewDetail, reason: string) {
  return mutateVersion(token, detail.version_id, "yank", { version: detail.version, reason });
}

export function revokePluginVersion(token: string, detail: DesktopPluginReviewDetail, reason: string) {
  return mutateVersion(token, detail.version_id, "revoke", {
    version: detail.version,
    reason_code: "manual_security_revoke",
    reason,
    affects_historical_versions: false,
  });
}

export function listPluginReports(token: string): Promise<DesktopPluginReportListResponse> {
  return apiRequest("/admin/plugin-reviews/reports?page=1&page_size=100", {}, token);
}

export function resolvePluginReport(token: string, report: DesktopPluginReport, note: string) {
  return apiRequest<DesktopPluginReport>(
    `/admin/plugin-reviews/reports/${encodeURIComponent(report.id)}/review`,
    {
      method: "POST",
      headers: mutationHeaders(),
      body: JSON.stringify({ status: "resolved", resolution_note: note }),
    },
    token,
  );
}
