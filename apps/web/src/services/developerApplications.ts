import { apiRequest } from "./api";

export type DeveloperApplicationStatus = "draft" | "pending_review" | "rejected" | "approved";

export interface DeveloperApplicationForm {
  name: string;
  developer_name: string;
  description: string;
  website_url: string;
  privacy_policy_url: string;
  redirect_uris: string[];
  scopes: string[];
  windows_release_info: string;
  use_case: string;
}

export interface DeveloperApplicationEvent {
  id: string;
  kind: "created" | "submitted" | "resubmitted" | "rejected" | "approved";
  note: string | null;
  version: number;
  created_at: string;
}

export interface DeveloperApplication {
  id: string;
  name: string;
  developer_name: string;
  description: string;
  website_url: string;
  privacy_policy_url: string;
  redirect_uris: string[];
  requested_scopes: string[];
  windows_release_info: string;
  use_case: string;
  status: DeveloperApplicationStatus;
  resubmission_count: number;
  current_version: number;
  review_note: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
  approved_application: {
    id: string;
    client_id: string;
    name: string;
    status: "approved" | "suspended" | "revoked" | "pending_review" | "draft";
    approved_scopes: string[];
    redirect_uris: string[];
    trusted_verification_enabled: boolean;
  } | null;
  events: DeveloperApplicationEvent[];
}

interface DeveloperApplicationListResponse {
  items: DeveloperApplication[];
  page: number;
  page_size: number;
  total: number;
}

export function listDeveloperApplications(token: string): Promise<DeveloperApplicationListResponse> {
  return apiRequest<DeveloperApplicationListResponse>("/me/third-party-applications", {}, token);
}

export function createDeveloperApplication(
  payload: DeveloperApplicationForm,
  token: string,
): Promise<DeveloperApplication> {
  return apiRequest<DeveloperApplication>(
    "/me/third-party-applications",
    { method: "POST", body: JSON.stringify(payload) },
    token,
  );
}

export function updateDeveloperApplication(
  id: string,
  payload: Partial<DeveloperApplicationForm>,
  token: string,
): Promise<DeveloperApplication> {
  return apiRequest<DeveloperApplication>(
    `/me/third-party-applications/${encodeURIComponent(id)}`,
    { method: "PATCH", body: JSON.stringify(payload) },
    token,
  );
}

export function submitDeveloperApplication(id: string, token: string): Promise<DeveloperApplication> {
  return apiRequest<DeveloperApplication>(
    `/me/third-party-applications/${encodeURIComponent(id)}/submit`,
    { method: "POST" },
    token,
  );
}
