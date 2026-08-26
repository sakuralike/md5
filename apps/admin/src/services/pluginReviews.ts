import type {
  DesktopPluginCapability,
  DesktopPluginReport,
  DesktopPluginReportListResponse,
  DesktopPluginReviewDetail,
  DesktopPluginReviewQueueResponse,
  DesktopPluginRunner,
  DesktopPluginRunnerListResponse,
  DesktopPluginRunnerRegistration,
  DesktopPluginReviewMetrics,
  DesktopPluginReviewPolicy,
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

export function rerunPluginStaticReview(
  token: string,
  detail: DesktopPluginReviewDetail,
): Promise<DesktopPluginReviewDetail> {
  return mutateVersion(token, detail.version_id, "rerun", {});
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

export function listPluginRunners(token: string): Promise<DesktopPluginRunnerListResponse> {
  return apiRequest("/admin/plugin-review-runners", {}, token);
}

export function getPluginReviewMetrics(token: string): Promise<DesktopPluginReviewMetrics> {
  return apiRequest("/admin/plugin-reviews/metrics", {}, token);
}

export function getPluginReviewPolicy(token: string): Promise<DesktopPluginReviewPolicy> {
  return apiRequest("/admin/plugin-review-policy", {}, token);
}

export function savePluginReviewPolicy(
  token: string,
  policy: DesktopPluginReviewPolicy,
): Promise<DesktopPluginReviewPolicy> {
  return apiRequest(
    "/admin/plugin-review-policy",
    {
      method: "PUT",
      headers: mutationHeaders(),
      body: JSON.stringify({
        version: policy.version,
        static_lease_seconds: policy.static_lease_seconds,
        dynamic_lease_seconds: policy.dynamic_lease_seconds,
        task_token_seconds: policy.task_token_seconds,
        maximum_static_attempts: policy.maximum_static_attempts,
        maximum_dynamic_attempts: policy.maximum_dynamic_attempts,
        runner_offline_seconds: policy.runner_offline_seconds,
        revocation_refresh_hours: policy.revocation_refresh_hours,
        revocation_max_stale_hours: policy.revocation_max_stale_hours,
        dynamic_review_enabled: policy.dynamic_review_enabled,
        llm_review_enabled: policy.llm_review_enabled,
        llm_provider: policy.llm_provider,
        llm_base_url: policy.llm_base_url,
        llm_model: policy.llm_model,
        llm_timeout_seconds: policy.llm_timeout_seconds,
      }),
    },
    token,
  );
}

export function getPluginReviewSource(token: string, versionId: string): Promise<{ files: Array<{ path: string; content: string; truncated: boolean }> }> {
  return apiRequest(`/admin/plugin-reviews/versions/${encodeURIComponent(versionId)}/source`, {}, token);
}

export function savePluginReviewLlmKey(token: string, apiKey: string): Promise<void> {
  return apiRequest(
    "/admin/plugin-review-policy/llm-key",
    { method: "PUT", headers: mutationHeaders(), body: JSON.stringify({ api_key: apiKey }) },
    token,
  );
}

export function testPluginReviewLlm(token: string): Promise<{ connected: true; provider: string; model: string }> {
  return apiRequest("/admin/plugin-review-policy/llm-test", { method: "POST" }, token);
}

export function createPluginRunner(
  token: string,
  payload: {
    name: string;
    architecture: "windows-x64" | "windows-arm64";
    certificate_fingerprint: string;
  },
): Promise<DesktopPluginRunnerRegistration> {
  return apiRequest(
    "/admin/plugin-review-runners",
    { method: "POST", headers: mutationHeaders(), body: JSON.stringify(payload) },
    token,
  );
}

export function revokePluginRunner(
  token: string,
  runner: DesktopPluginRunner,
): Promise<DesktopPluginRunner> {
  return apiRequest(
    `/admin/plugin-review-runners/${encodeURIComponent(runner.id)}/revoke`,
    { method: "POST", headers: mutationHeaders() },
    token,
  );
}
