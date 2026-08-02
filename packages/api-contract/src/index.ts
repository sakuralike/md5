export type UserRole = "user" | "trusted_contributor" | "moderator" | "admin" | "service";
export type UserStatus = "active" | "locked" | "disabled";

export interface User {
  id: string;
  username: string;
  email: string;
  email_verified: boolean;
  status: UserStatus;
  role: UserRole;
  reputation_score: number;
  totp_enabled: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
  mfa_verified: boolean;
  user: User;
}

export interface BrowserTokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  mfa_verified: boolean;
  user: User;
}

export interface Session {
  id: string;
  created_at: string;
  last_used_at: string;
  expires_at: string;
  user_agent: string | null;
  ip_prefix: string | null;
  current: boolean;
  mfa_verified: boolean;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details: Record<string, unknown>;
  request_id: string | null;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: ApiErrorBody,
  ) {
    super(body.message);
  }
}

export function isPrivilegedRole(role: UserRole): boolean {
  return role === "moderator" || role === "admin";
}

export type FingerprintAlgorithm = "md5" | "sha1" | "sha256" | "sha512";
export type CandidateStatus = "pending" | "verified" | "rejected" | "quarantined";
export type FeedbackOutcome = "success" | "failure";
export type VerificationSource = "web_feedback" | "desktop_receipt";

export interface ArchiveFingerprint {
  algorithm: FingerprintAlgorithm;
  digest: string;
}

export interface CandidateSummary {
  id: string;
  status: CandidateStatus;
  confidence_score: number;
  masked_secret: string;
  submission_count: number;
  success_evidence_count: number;
  failure_evidence_count: number;
  my_feedback: FeedbackOutcome | null;
  last_verified_at: string | null;
}

export interface ArchiveSearchResult {
  id: string;
  optional_size: number | null;
  optional_format: string | null;
  fingerprints: ArchiveFingerprint[];
  candidate_count: number;
  status_counts: Record<string, number>;
  candidates: CandidateSummary[];
}

export interface ArchiveSearchResponse {
  matched: boolean;
  query: ArchiveFingerprint;
  authenticated: boolean;
  archive: ArchiveSearchResult | null;
}

export interface ArchiveSubmissionRequest {
  fingerprints: ArchiveFingerprint[];
  password: string;
  authorization_confirmed: boolean;
  authorization_version: string;
  optional_size?: number;
  optional_format?: string;
}

export interface ArchiveSubmissionResponse {
  submission_id: string;
  archive_id: string;
  candidate_id: string;
  candidate_status: CandidateStatus;
  archive_created: boolean;
  candidate_created: boolean;
  evidence_merged: boolean;
  pending_points: number;
  created_at: string;
}

export interface ArchiveRevealResponse {
  archive_id: string;
  candidate_id: string;
  password: string;
  candidate_status: CandidateStatus;
  remaining_daily_quota: number;
}

export interface MySubmission {
  id: string;
  archive_id: string;
  candidate_id: string;
  candidate_status: CandidateStatus;
  fingerprints: ArchiveFingerprint[];
  source: string;
  authorization_version: string;
  created_at: string;
}

export interface MySubmissionsResponse {
  items: MySubmission[];
  page: number;
  page_size: number;
  total: number;
}

export interface CandidateFeedbackRequest {
  outcome: FeedbackOutcome;
}

export interface VerificationSnapshot {
  rule_version: string;
  independent_success_count: number;
  independent_failure_count: number;
  success_weight: number;
  failure_weight: number;
  needs_more_independent_success: number;
}

export interface CandidateFeedbackResponse {
  feedback_id: string;
  evidence_event_id: string | null;
  candidate_id: string;
  outcome: FeedbackOutcome;
  source: VerificationSource;
  revision: number;
  created: boolean;
  changed: boolean;
  candidate_status: CandidateStatus;
  snapshot: VerificationSnapshot;
  updated_at: string;
}

export interface MyFeedbackHistoryItem {
  evidence_event_id: string;
  feedback_id: string;
  candidate_id: string;
  previous_outcome: FeedbackOutcome | null;
  outcome: FeedbackOutcome;
  source: VerificationSource;
  revision: number;
  rule_version: string;
  candidate_status: CandidateStatus;
  created_at: string;
}

export interface MyFeedbackHistoryResponse {
  items: MyFeedbackHistoryItem[];
  page: number;
  page_size: number;
  total: number;
}

export type DesktopInstallationStatus = "active" | "revoked";
export type DesktopKeyAlgorithm = "ecdsa-p256-sha256";
export type DesktopArchiveFormat = "zip" | "7z";

export interface DesktopInstallationRegistrationRequest {
  installation_id: string;
  public_key: string;
  key_algorithm: DesktopKeyAlgorithm;
  client_version: string;
}

export interface DesktopInstallation {
  installation_id: string;
  status: DesktopInstallationStatus;
  key_algorithm: DesktopKeyAlgorithm;
  public_key_fingerprint: string;
  client_version: string;
  receipt_count: number;
  created_at: string;
  last_seen_at: string;
  revoked_at: string | null;
}

export interface DesktopInstallationListResponse {
  items: DesktopInstallation[];
}

export interface DesktopChallengeRequest {
  installation_id: string;
  candidate_id: string;
  fingerprint_algorithm: FingerprintAlgorithm;
  fingerprint_digest: string;
  client_version: string;
}

export interface DesktopChallengeResponse {
  challenge_id: string;
  challenge_nonce: string;
  installation_id: string;
  account_id: string;
  candidate_id: string;
  fingerprint_algorithm: FingerprintAlgorithm;
  fingerprint_digest: string;
  client_version: string;
  canonical_payload_version: "desktop-receipt-v1";
  expires_at: string;
}

export interface DesktopReceiptRequest {
  challenge_id: string;
  challenge_nonce: string;
  installation_id: string;
  account_id: string;
  candidate_id: string;
  fingerprint_algorithm: FingerprintAlgorithm;
  fingerprint_digest: string;
  candidate_digest: string;
  outcome: FeedbackOutcome;
  archive_format: DesktopArchiveFormat;
  client_version: string;
  verified_at: string;
  signature: string;
}

export interface DesktopReceiptResponse {
  receipt_id: string;
  evidence_event_id: string | null;
  candidate_id: string;
  outcome: FeedbackOutcome;
  candidate_status: CandidateStatus;
  snapshot: VerificationSnapshot;
  accepted_at: string;
}

export type DesktopReleaseChannel = "stable" | "beta";
export type DesktopArchitecture = "x64" | "arm64";
export type DesktopReleaseStatus = "draft" | "published" | "withdrawn";
export type DesktopCodeSignatureStatus = "unsigned" | "test_signed" | "verified";

export interface DesktopReleaseCreateRequest {
  channel: DesktopReleaseChannel;
  platform: "windows";
  architecture: DesktopArchitecture;
  version: string;
  minimum_supported_version: string;
  mandatory: boolean;
  release_notes: string;
  artifact_filename: string;
  artifact_sha256: string;
  artifact_size_bytes: number;
  content_type: string;
  code_signature_status: DesktopCodeSignatureStatus;
  signer_subject: string | null;
  signer_thumbprint: string | null;
}

export interface DesktopRelease {
  id: string;
  channel: DesktopReleaseChannel;
  platform: string;
  architecture: DesktopArchitecture;
  version: string;
  minimum_supported_version: string;
  status: DesktopReleaseStatus;
  mandatory: boolean;
  release_notes: string;
  artifact_filename: string;
  artifact_sha256: string;
  artifact_size_bytes: number;
  content_type: string;
  artifact_uploaded: boolean;
  code_signature_status: DesktopCodeSignatureStatus;
  signer_subject: string | null;
  signer_thumbprint: string | null;
  download_count: number;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  withdrawn_at: string | null;
}

export interface DesktopReleaseListResponse {
  items: DesktopRelease[];
}

export type StateTransitionSource = "automatic" | "manual";
export type ManualTransitionReason =
  | "manual.evidence_conflict"
  | "manual.security_hold"
  | "manual.invalid_candidate"
  | "manual.policy_violation"
  | "manual.review_reopened"
  | "manual.verified_by_review"
  | "manual.quarantine_cleared";

export interface CandidateModerationSummary {
  id: string;
  archive_id: string;
  status: CandidateStatus;
  confidence_score: number;
  fingerprints: ArchiveFingerprint[];
  submission_count: number;
  feedback_count: number;
  created_at: string;
  updated_at: string;
}

export interface CandidateModerationListResponse {
  items: CandidateModerationSummary[];
  page: number;
  page_size: number;
  total: number;
}

export interface ModerationEvidenceSnapshot {
  rule_version: string;
  independent_success_count: number;
  independent_failure_count: number;
  success_weight: number;
  failure_weight: number;
}

export interface ModerationEvidenceEvent {
  id: string;
  user_id: string;
  previous_outcome: FeedbackOutcome | null;
  outcome: FeedbackOutcome;
  source: VerificationSource;
  weight: number;
  rule_version: string;
  revision: number;
  created_at: string;
}

export interface CandidateStateEvent {
  id: string;
  previous_status: CandidateStatus;
  next_status: CandidateStatus;
  reason_code: string;
  reason_note: string | null;
  rule_version: string;
  transition_source: StateTransitionSource;
  actor_id: string | null;
  request_id: string | null;
  independent_success_count: number;
  independent_failure_count: number;
  success_weight: number;
  failure_weight: number;
  created_at: string;
}

export interface CandidateModerationDetail extends CandidateModerationSummary {
  evidence_snapshot: ModerationEvidenceSnapshot;
  evidence_events: ModerationEvidenceEvent[];
  state_events: CandidateStateEvent[];
}

export interface CandidateTransitionRequest {
  target_status: CandidateStatus;
  reason_code: ManualTransitionReason;
  reason_note?: string | null;
}

export interface CandidateTransitionResponse {
  candidate_id: string;
  previous_status: CandidateStatus;
  current_status: CandidateStatus;
  state_event_id: string;
  reason_code: ManualTransitionReason;
  request_id: string | null;
}

export type ReportReason =
  | "report.invalid_candidate"
  | "report.policy_violation"
  | "report.misleading_metadata"
  | "report.other";
export type AppealReason =
  | "appeal.decision_incorrect"
  | "appeal.new_evidence"
  | "appeal.context_missing"
  | "appeal.other";

export interface ReportCreateRequest {
  candidate_id: string;
  reason_code: ReportReason;
  description?: string | null;
}

export interface AppealCreateRequest {
  candidate_id: string;
  related_case_id?: string | null;
  reason_code: AppealReason;
  description: string;
}

export type TrustCaseKind = "report" | "appeal";
export type TrustCaseStatus = "open" | "in_review" | "resolved" | "dismissed";
export type TrustCaseResolutionCode =
  | "admin.review_started"
  | "admin.action_taken"
  | "admin.no_violation"
  | "admin.insufficient_evidence"
  | "admin.appeal_upheld"
  | "admin.appeal_denied"
  | "admin.reopened";

export interface TrustCaseSummary {
  id: string;
  kind: TrustCaseKind;
  status: TrustCaseStatus;
  reporter_id: string;
  reporter_username: string;
  candidate_id: string;
  related_case_id: string | null;
  reason_code: string;
  description: string | null;
  assigned_to_id: string | null;
  resolved_by_id: string | null;
  resolution_code: string | null;
  resolution_note: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TrustCaseEvent {
  id: string;
  actor_id: string | null;
  previous_status: TrustCaseStatus | null;
  next_status: TrustCaseStatus;
  action: string;
  reason_code: string;
  note: string | null;
  request_id: string | null;
  created_at: string;
}

export interface TrustCaseDetail extends TrustCaseSummary {
  events: TrustCaseEvent[];
}

export interface TrustCaseListResponse {
  items: TrustCaseSummary[];
  page: number;
  page_size: number;
  total: number;
}

export interface TrustCaseTransitionRequest {
  target_status: TrustCaseStatus;
  resolution_code: TrustCaseResolutionCode;
  resolution_note?: string | null;
}

export interface TrustCaseTransitionResponse {
  case_id: string;
  previous_status: TrustCaseStatus;
  current_status: TrustCaseStatus;
  event_id: string;
  resolution_code: TrustCaseResolutionCode;
  request_id: string | null;
}
