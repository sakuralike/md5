export type UserRole = "user" | "trusted_contributor" | "moderator" | "admin" | "service";
export type UserStatus = "active" | "locked" | "disabled";

export interface User {
  id: string;
  uid?: string;
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

export interface ProfileUpdateRequest {
  username: string;
}

export type ReauthenticationPurpose =
  | "password_change"
  | "totp_disable"
  | "account_deletion";

export interface ReauthenticationRequest {
  purpose: ReauthenticationPurpose;
  current_password: string;
  totp_code?: string | null;
}

export interface ReauthenticationResponse {
  reauth_token: string;
  purpose: ReauthenticationPurpose;
  expires_at: string;
}

export interface PasswordChangeRequest {
  reauth_token: string;
  new_password: string;
}

export interface TotpCodeRequest {
  code: string;
}

export interface TotpDisableRequest {
  reauth_token: string;
}

export interface TotpSetupResponse {
  secret: string;
  provisioning_uri: string;
  message: string;
}

export interface MessageResponse {
  message: string;
}

export interface BrowserLoginRequest {
  login: string;
  password: string;
  totp_code?: string;
}

export interface EmailTokenRequest {
  token: string;
}

export interface PasswordForgotRequest {
  email: string;
}

export interface PasswordResetRequest {
  token: string;
  new_password: string;
}

export type AuthorizationSource = "web" | "desktop" | "api";
export type PrivacyExportStatus =
  | "pending"
  | "processing"
  | "ready"
  | "failed"
  | "expired"
  | "downloaded";
export type PrivacyDeletionStatus = "pending" | "cancelled" | "processing" | "completed";

export interface RevealHistoryItem {
  audit_id: string;
  archive_id: string | null;
  fingerprint_summary: string[];
  result: string;
  revealed_at: string;
}

export interface RevealHistoryResponse {
  items: RevealHistoryItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface AuthorizationDeclarationCreateRequest {
  purpose: string;
  source: AuthorizationSource;
  accepted: true;
}

export interface AuthorizationDeclaration {
  id: string;
  declaration_version: string;
  purpose: string;
  source: AuthorizationSource;
  confirmed_at: string;
  withdrawn_at: string | null;
  active: boolean;
}

export interface AuthorizationDeclarationListResponse {
  items: AuthorizationDeclaration[];
  page: number;
  page_size: number;
  total: number;
}

export interface PrivacyExport {
  id: string;
  status: PrivacyExportStatus;
  requested_at: string;
  completed_at: string | null;
  expires_at: string | null;
  downloaded_at: string | null;
  download_available: boolean;
  download_token: string | null;
  artifact_sha256: string | null;
  failure_code: string | null;
}

export interface PrivacyDeletionCreateRequest {
  reauth_token: string;
}

export interface PrivacyDeletionRequest {
  id: string;
  status: PrivacyDeletionStatus;
  requested_at: string;
  cancel_before: string;
  cancelled_at: string | null;
  processing_started_at: string | null;
  completed_at: string | null;
  can_cancel: boolean;
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

export type HashVoteOutcome = "useful" | "not_useful";

export interface HashCommentResponse {
  id: string;
  parent_id: string | null;
  content: string;
  author: CommunityAuthor;
  like_count: number;
  viewer_has_liked: boolean;
  created_at: string;
}

export interface HashCommentListResponse {
  items: HashCommentResponse[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface HashInteractionResponse {
  algorithm: FingerprintAlgorithm;
  digest: string;
  like_count: number;
  viewer_has_liked: boolean;
  vote_counts: Record<string, number>;
  viewer_vote: HashVoteOutcome | null;
}

export interface HashDetailResponse extends HashInteractionResponse {
  matched: boolean;
  archive: ArchiveSearchResult | null;
  comment_count: number;
  comments: HashCommentResponse[];
  comments_next_cursor: string | null;
}

export interface HashCommentCreateRequest {
  content: string;
  parent_id?: string | null;
  rules_accepted: boolean;
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
  submitter_kind: "guest" | "authenticated";
  pool_status: "pending_verification" | "global";
  required_success_confirmations: number;
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

export type PointsLedgerStatus = "pending" | "posted" | "reversed";

export interface PointsSummary {
  available: number;
  pending: number;
  reversed: number;
}

export interface FeedbackSummary {
  effective_success: number;
  effective_failure: number;
  history_events: number;
}

export interface ContributionSummary {
  total: number;
  verified: number;
}

export interface UserLevelEntitlements {
  daily_reveal_quota: number;
  can_submit: boolean;
}

export interface UserLevelSummary {
  code: string;
  name: string;
  description: string;
  min_growth_points: number;
  entitlements: UserLevelEntitlements;
}

export interface UserLevelProfileResponse {
  growth_points: number;
  current: UserLevelSummary;
  next: UserLevelSummary | null;
  progress_percent: number;
  points_to_next_level: number;
  rule_hash: string;
}

export interface UserLevelCatalogResponse {
  items: UserLevelSummary[];
  rule_hash: string;
}

export interface GrowthEventItem {
  id: string;
  amount: number;
  event_type: string;
  reference_id: string;
  reason_code: string;
  rule_version: string;
  created_at: string;
}

export interface GrowthEventsResponse {
  items: GrowthEventItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface TrustProfileResponse {
  reputation_score: number;
  reputation_min: number;
  reputation_max: number;
  points: PointsSummary;
  feedback: FeedbackSummary;
  contributions: ContributionSummary;
  level: UserLevelProfileResponse;
}

export interface PointsLedgerItem {
  id: string;
  amount: number;
  event_type: string;
  reference_id: string;
  status: PointsLedgerStatus;
  created_at: string;
  settled_at: string | null;
}

export interface PointsLedgerResponse {
  items: PointsLedgerItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface ReputationEventItem {
  id: string;
  amount: number;
  event_type: string;
  reference_id: string;
  reason_code: string;
  rule_version: string;
  previous_score: number;
  next_score: number;
  created_at: string;
}

export interface ReputationEventsResponse {
  items: ReputationEventItem[];
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
  distribution_authorized: boolean;
  legal_declaration: string;
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
  distribution_authorized: boolean;
  legal_declaration: string;
  download_count: number;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  withdrawn_at: string | null;
}

export interface DesktopReleaseListResponse {
  items: DesktopRelease[];
}

export type DesktopAnnouncementStatus = "draft" | "published" | "archived";
export type DesktopAnnouncementContentType = "text" | "html";

export interface DesktopAnnouncementWriteRequest {
  title: string;
  content: string;
  content_type: DesktopAnnouncementContentType;
  image_urls: string[];
  action_label: string | null;
  action_url: string | null;
  sort_order: number;
  starts_at: string | null;
  ends_at: string | null;
}

export interface DesktopAnnouncement extends DesktopAnnouncementWriteRequest {
  id: string;
  status: DesktopAnnouncementStatus;
  revision: number;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  archived_at: string | null;
}

export interface DesktopAnnouncementListResponse {
  items: DesktopAnnouncement[];
}

export interface DesktopAnnouncementImageUploadResponse {
  url: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
}

export type WebAnnouncementStatus = "draft" | "published" | "archived";
export type WebAnnouncementContentType = "text" | "html";

export interface WebAnnouncementWriteRequest {
  title: string;
  content: string;
  content_type: WebAnnouncementContentType;
  image_urls: string[];
  action_label: string | null;
  action_url: string | null;
  sort_order: number;
  auto_close_seconds: number | null;
  starts_at: string | null;
  ends_at: string | null;
}

export interface WebAnnouncement extends WebAnnouncementWriteRequest {
  id: string;
  status: WebAnnouncementStatus;
  revision: number;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  archived_at: string | null;
}

export interface WebAnnouncementListResponse {
  items: WebAnnouncement[];
}

export interface WebAnnouncementImageUploadResponse {
  url: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
}

export type StateTransitionSource = "automatic" | "manual";
export type RewardAdjustmentDirection = "invalidate" | "restore";
export type RewardKind = "contribution" | "verification";
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

export interface HashPoolOverview {
  verified_candidates: number;
  unique_archives: number;
  unique_fingerprints: number;
  pending_candidates: number;
  quarantined_candidates: number;
}

export interface HashPoolItem {
  candidate_id: string;
  archive_id: string;
  fingerprints: ArchiveFingerprint[];
  confidence_score: number;
  submission_count: number;
  feedback_count: number;
  last_verified_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface HashPoolListResponse {
  overview: HashPoolOverview;
  items: HashPoolItem[];
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

export interface CorrelationSnapshot {
  rule_version: string;
  feedback_count: number;
  independent_group_count: number;
  correlated_group_count: number;
  downweighted_feedback_count: number;
  raw_success_weight: number;
  effective_success_weight: number;
  raw_failure_weight: number;
  effective_failure_weight: number;
}

export type CorrelationSignal = "installation" | "ip_prefix";

export interface CorrelationGroup {
  group_id: string;
  feedback_ids: string[];
  user_ids: string[];
  shared_signals: CorrelationSignal[];
  member_count: number;
  success_count: number;
  failure_count: number;
  raw_success_weight: number;
  effective_success_weight: number;
  raw_failure_weight: number;
  effective_failure_weight: number;
}

export interface CorrelationAssessment extends CorrelationSnapshot {
  id: string;
  trigger_evidence_id: string;
  created_at: string;
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

export interface RewardAdjustmentSummary {
  rule_version: string;
  direction: RewardAdjustmentDirection | null;
  affected_users: number;
  points_entries: number;
  reputation_events: number;
  points_amount: number;
  reputation_amount: number;
}

export interface RewardAdjustmentEvent {
  id: string;
  state_event_id: string;
  user_id: string;
  reward_kind: RewardKind;
  source_reference_id: string;
  direction: RewardAdjustmentDirection;
  points_amount: number;
  reputation_amount: number;
  reason_code: string;
  rule_version: string;
  created_at: string;
}

export interface CandidateModerationDetail extends CandidateModerationSummary {
  evidence_snapshot: ModerationEvidenceSnapshot;
  correlation_snapshot: CorrelationSnapshot;
  correlation_groups: CorrelationGroup[];
  correlation_assessments: CorrelationAssessment[];
  evidence_events: ModerationEvidenceEvent[];
  state_events: CandidateStateEvent[];
  reward_adjustments: RewardAdjustmentEvent[];
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
  reward_adjustment: RewardAdjustmentSummary;
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

export type AccountAppealReason =
  | "account_appeal.restriction_incorrect"
  | "account_appeal.account_recovered"
  | "account_appeal.context_missing"
  | "account_appeal.other";
export type AccountAppealRequestedAction = "restore_access" | "review_restriction";

export interface AccountAppealCreateRequest {
  requested_action: AccountAppealRequestedAction;
  reason_code: AccountAppealReason;
  description: string;
  evidence_summary?: string | null;
}

export type TrustCaseKind = "report" | "appeal" | "account_appeal";
export type TrustCaseSubjectType = "candidate" | "account" | "risk_alert";
export type TrustCaseStatus = "open" | "in_review" | "resolved" | "dismissed";
export type TrustCaseResolutionCode =
  | "admin.review_started"
  | "admin.action_taken"
  | "admin.no_violation"
  | "admin.insufficient_evidence"
  | "admin.appeal_upheld"
  | "admin.appeal_denied"
  | "admin.account_restored"
  | "admin.account_restriction_upheld"
  | "admin.reopened";
export type TrustCaseAssignmentReason = "admin.assigned" | "admin.reassigned";
export type TrustCaseReopenReason = "admin.reopened";

export interface TrustCaseSummary {
  id: string;
  version: number;
  kind: TrustCaseKind;
  subject_type: TrustCaseSubjectType;
  status: TrustCaseStatus;
  reporter_id: string;
  reporter_username: string;
  candidate_id: string | null;
  target_user_id: string | null;
  risk_alert_id: string | null;
  related_case_id: string | null;
  reason_code: string;
  requested_action: string | null;
  description: string | null;
  evidence_summary: string | null;
  assigned_to_id: string | null;
  resolved_by_id: string | null;
  resolution_code: string | null;
  resolution_note: string | null;
  resolved_at: string | null;
  sla_due_at: string | null;
  escalated_at: string | null;
  escalation_count: number;
  last_escalation_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface TrustCaseEvent {
  id: string;
  actor_id: string | null;
  previous_status: TrustCaseStatus | null;
  previous_assignee_id: string | null;
  next_status: TrustCaseStatus;
  next_assignee_id: string | null;
  action: string;
  reason_code: string;
  note: string | null;
  request_id: string | null;
  created_at: string;
}

export type TrustCaseNotificationStatus = "pending" | "sent" | "failed";

export interface TrustCaseNotification {
  id: string;
  case_id: string;
  recipient_user_id: string;
  kind: "resolution";
  status: TrustCaseNotificationStatus;
  attempts: number;
  provider: string | null;
  provider_message_id: string | null;
  available_at: string;
  sent_at: string | null;
  failed_at: string | null;
  last_error_code: string | null;
  replay_count: number;
  last_replayed_at: string | null;
  last_replayed_by_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface TrustCaseDetail extends TrustCaseSummary {
  events: TrustCaseEvent[];
  notifications: TrustCaseNotification[];
}

export interface TrustCaseListResponse {
  items: TrustCaseSummary[];
  page: number;
  page_size: number;
  total: number;
}

export interface TrustCaseTransitionRequest {
  expected_version: number;
  target_status: TrustCaseStatus;
  resolution_code: TrustCaseResolutionCode;
  resolution_note?: string | null;
}

export interface TrustCaseTransitionResponse {
  case_id: string;
  previous_status: TrustCaseStatus;
  current_status: TrustCaseStatus;
  previous_assignee_id: string | null;
  current_assignee_id: string | null;
  version: number;
  event_id: string;
  resolution_code: TrustCaseResolutionCode;
  request_id: string | null;
}

export type TrustCaseCandidateTargetStatus = "verified" | "rejected" | "quarantined";

export interface TrustCaseResolveRequest {
  expected_version: number;
  resolution_code: TrustCaseResolutionCode;
  resolution_note: string;
  candidate_target_status?: TrustCaseCandidateTargetStatus | null;
}

export interface TrustCaseRewardAdjustment {
  affected_users: number;
  points_entries: number;
  reputation_events: number;
  points_amount: number;
  reputation_amount: number;
}

export interface TrustCaseSideEffect {
  effect_type: string;
  target_type: string;
  target_id: string;
  previous_value: string | null;
  next_value: string | null;
  reference_id: string | null;
  reward_adjustment: TrustCaseRewardAdjustment | null;
}

export interface TrustCaseResolveResponse {
  case_id: string;
  previous_status: TrustCaseStatus;
  current_status: TrustCaseStatus;
  current_assignee_id: string;
  resolved_by_id: string;
  version: number;
  event_id: string;
  resolution_code: TrustCaseResolutionCode;
  side_effects: TrustCaseSideEffect[];
  request_id: string | null;
}

export interface TrustCaseNotificationListResponse {
  items: TrustCaseNotification[];
  page: number;
  page_size: number;
  total: number;
}

export interface TrustCaseNotificationReplayRequest {
  reason_code: string;
  note?: string | null;
}

export interface TrustCaseAssignRequest {
  expected_version: number;
  assignee_id: string;
  reason_code: TrustCaseAssignmentReason;
  note?: string | null;
}

export interface TrustCaseAssignResponse {
  case_id: string;
  previous_status: TrustCaseStatus;
  current_status: TrustCaseStatus;
  previous_assignee_id: string | null;
  current_assignee_id: string;
  version: number;
  event_id: string;
  reason_code: TrustCaseAssignmentReason;
  request_id: string | null;
}

export interface TrustCaseReopenRequest {
  expected_version: number;
  reason_code?: TrustCaseReopenReason;
  note?: string | null;
}

export interface TrustCaseReopenResponse {
  case_id: string;
  previous_status: TrustCaseStatus;
  current_status: TrustCaseStatus;
  previous_assignee_id: string | null;
  current_assignee_id: string | null;
  version: number;
  event_id: string;
  reason_code: TrustCaseReopenReason;
  request_id: string | null;
}


export type RiskAlertKind = "failure_surge";
export type RiskAlertSeverity = "high";
export type RiskAlertStatus = "open" | "acknowledged" | "resolved";
export type RiskAlertSlaState =
  | "within_sla"
  | "acknowledgement_overdue"
  | "resolution_overdue"
  | "met"
  | "breached";
export type RiskAlertNotificationKind =
  | "detected"
  | "assigned"
  | "acknowledgement_overdue"
  | "resolution_overdue"
  | "resolved"
  | "reopened";
export type RiskAlertNotificationStatus = "pending" | "sent" | "failed";
export type RiskAlertResolutionCode =
  | "admin.investigation_started"
  | "admin.mitigated"
  | "admin.false_positive"
  | "admin.reopened";

export interface RiskAlertSummary {
  id: string;
  candidate_id: string;
  trigger_evidence_id: string;
  kind: RiskAlertKind;
  severity: RiskAlertSeverity;
  status: RiskAlertStatus;
  rule_version: string;
  sla_rule_version: string;
  sla_state: RiskAlertSlaState;
  window_started_at: string;
  window_ended_at: string;
  acknowledge_due_at: string;
  resolve_due_at: string;
  acknowledged_at: string | null;
  independent_failure_count: number;
  failure_weight: number;
  assigned_to_id: string | null;
  assigned_to_username: string | null;
  resolved_by_id: string | null;
  resolution_code: string | null;
  resolution_note: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RiskAlertEvent {
  id: string;
  actor_id: string | null;
  previous_status: RiskAlertStatus | null;
  next_status: RiskAlertStatus;
  previous_assignee_id: string | null;
  next_assignee_id: string | null;
  action: string;
  reason_code: string;
  note: string | null;
  request_id: string | null;
  created_at: string;
}

export interface RiskAlertNotification {
  id: string;
  alert_id: string;
  event_id: string | null;
  recipient_user_id: string;
  recipient_username: string;
  kind: RiskAlertNotificationKind;
  status: RiskAlertNotificationStatus;
  attempts: number;
  provider: string | null;
  provider_message_id: string | null;
  available_at: string;
  sent_at: string | null;
  failed_at: string | null;
  last_error_code: string | null;
  replay_count: number;
  last_replayed_at: string | null;
  last_replayed_by_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface RiskAlertNotificationProviderMetrics {
  provider: string;
  pending_count: number;
  sent_count: number;
  failed_count: number;
}

export interface RiskAlertNotificationMetricsResponse {
  generated_at: string;
  pending_count: number;
  sent_count: number;
  failed_count: number;
  failed_last_24_hours: number;
  oldest_pending_seconds: number | null;
  providers: RiskAlertNotificationProviderMetrics[];
}

export interface RiskAlertNotificationListResponse {
  items: RiskAlertNotification[];
  page: number;
  page_size: number;
  total: number;
}

export interface RiskAlertNotificationReplayRequest {
  reason: string;
}

export interface RiskAlertNotificationReplayResponse {
  notification_id: string;
  status: RiskAlertNotificationStatus;
  replay_count: number;
  request_id: string | null;
}

export interface RiskAlertDetail extends RiskAlertSummary {
  events: RiskAlertEvent[];
  notifications: RiskAlertNotification[];
}

export interface RiskAlertListResponse {
  items: RiskAlertSummary[];
  page: number;
  page_size: number;
  total: number;
}

export interface RiskAlertTransitionRequest {
  target_status: RiskAlertStatus;
  resolution_code: RiskAlertResolutionCode;
  resolution_note?: string | null;
}

export interface RiskAlertTransitionResponse {
  alert_id: string;
  previous_status: RiskAlertStatus;
  current_status: RiskAlertStatus;
  event_id: string;
  resolution_code: RiskAlertResolutionCode;
  request_id: string | null;
}

export interface RiskAlertOperator {
  id: string;
  username: string;
  role: UserRole;
}

export interface RiskAlertAssignmentRequest {
  assignee_id: string;
  assignment_note?: string | null;
}

export interface RiskAlertAssignmentResponse {
  alert_id: string;
  previous_assignee_id: string | null;
  current_assignee_id: string;
  event_id: string;
  request_id: string | null;
}

export interface AdminQueueBacklog {
  pending_candidates: number;
  active_trust_cases: number;
  active_risk_alerts: number;
  pending_privacy_exports: number;
  pending_deletion_requests: number;
  total: number;
}

export interface AdminDashboardSummary {
  window_hours: number;
  window_started_at: string;
  generated_at: string;
  search_count: number;
  search_hit_count: number;
  search_hit_rate: number;
  contribution_count: number;
  candidate_count: number;
  verified_candidate_count: number;
  candidate_verification_rate: number;
  quarantined_candidate_count: number;
  audited_operation_count: number;
  audited_error_count: number;
  audited_error_rate: number;
  queue_backlog: AdminQueueBacklog;
}

export type AuditDetailValue =
  | string
  | number
  | boolean
  | null
  | AuditDetailValue[]
  | { [key: string]: AuditDetailValue };

export interface AdminAuditLogEntry {
  id: string;
  actor_id: string | null;
  actor_username: string | null;
  actor_role: UserRole | null;
  action: string;
  target_type: string;
  target_id: string | null;
  result: string;
  ip_prefix: string | null;
  request_id: string | null;
  details: Record<string, AuditDetailValue>;
  created_at: string;
}

export interface AdminAuditLogListResponse {
  items: AdminAuditLogEntry[];
  page: number;
  page_size: number;
  total: number;
}


export interface AdminUserCreateRequest {
  username: string;
  email: string;
  password: string;
  role: "user" | "trusted_contributor" | "moderator";
  status: "active" | "disabled";
  email_verified: boolean;
}

export interface AdminUserListItem {
  id: string;
  uid?: string;
  username: string;
  masked_email: string;
  email_verified: boolean;
  status: UserStatus;
  role: UserRole;
  reputation_score: number;
  totp_enabled: boolean;
  active_session_count: number;
  last_active_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminUserListResponse {
  items: AdminUserListItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface AdminUserDetail extends AdminUserListItem {
  level: UserLevelProfileResponse;
  total_session_count: number;
  submission_count: number;
  trust_case_count: number;
  points_balance: number;
  reputation_event_count: number;
  pending_privacy_export_count: number;
  pending_deletion_request_count: number;
}

export type AdminUserStatusReasonCode =
  | "security_risk"
  | "abuse_confirmed"
  | "policy_violation"
  | "appeal_approved"
  | "manual_review";

export type AdminSessionRevocationReasonCode =
  | "security_risk"
  | "user_request"
  | "incident_response"
  | "manual_review";

export interface AdminReauthenticationResponse {
  reauth_token: string;
  purpose:
    | "admin_user_governance"
    | "admin_settings_governance"
    | "admin_community_notification_ops";
  expires_at: string;
}

export interface AdminUserStatusChangeResponse {
  user_id: string;
  previous_status: UserStatus;
  current_status: UserStatus;
  revoked_session_count: number;
  audit_id: string;
  request_id: string | null;
}

export interface AdminUserSessionRevocationResponse {
  user_id: string;
  revoked_session_count: number;
  audit_id: string;
  request_id: string | null;
}


export type RoleChangeRequestStatus = "pending" | "approved" | "rejected";
export type RoleChangeReasonCode =
  | "trust_promotion"
  | "role_alignment"
  | "duty_assignment"
  | "duty_removal"
  | "security_response";
export type RoleChangeReviewReasonCode =
  | "verified"
  | "insufficient_evidence"
  | "policy_conflict"
  | "security_response";

export interface RoleChangeRequest {
  id: string;
  target_user_id: string;
  expected_role: UserRole;
  requested_role: UserRole;
  status: RoleChangeRequestStatus;
  requested_by: string;
  reviewed_by: string | null;
  reason_code: string;
  review_reason_code: string | null;
  created_at: string;
  reviewed_at: string | null;
}

export interface RoleChangeRequestListResponse {
  items: RoleChangeRequest[];
  page: number;
  page_size: number;
  total: number;
}

export interface RoleChangeMutationResponse {
  request: RoleChangeRequest;
  revoked_session_count: number;
  audit_id: string;
  request_id: string | null;
}

export interface SiteNavigationItem {
  label: string;
  path: string;
  enabled: boolean;
  requires_auth: boolean;
}

export interface UserLevelDefinition {
  code: string;
  name: string;
  description: string;
  min_growth_points: number;
  daily_reveal_quota: number;
  can_submit: boolean;
}

export interface OperationalSettingsSnapshot {
  site_name: string;
  site_logo_url: string;
  site_navigation: SiteNavigationItem[];
  daily_reveal_quota: number;
  reauthentication_ttl_minutes: number;
  privacy_deletion_grace_hours: number;
  desktop_min_client_version: string;
  desktop_update_download_cache_seconds: number;
  user_levels: UserLevelDefinition[];
}

export type NotificationBackend = "memory" | "log" | "webhook" | "smtp";
export type SmtpSecurityMode = "starttls" | "ssl" | "none";

export interface EmailDeliverySettings {
  backend: NotificationBackend;
  enabled: boolean;
  smtp_configured: boolean;
  sender_name: string;
  sender_email: string;
  subject_prefix: string;
  footer_text: string;
  content_format: "plain_text";
  smtp_host: string;
  smtp_port: number;
  smtp_security: SmtpSecurityMode;
  smtp_username: string;
  smtp_auth_enabled: boolean;
  smtp_password_configured: boolean;
  smtp_timeout_seconds: number;
  configuration_source: "deployment_environment";
}

export interface EmailDeliveryTestResponse {
  message: string;
  provider_message_id: string;
}
export interface OperationalSettingsResponse {
  settings: OperationalSettingsSnapshot;
  updated_at: string | null;
  updated_by: string | null;
}

export interface SiteLogoUploadResponse {
  url: string;
  content_type: "image/png" | "image/jpeg" | "image/webp";
  size_bytes: number;
  sha256: string;
}


export type CommunityBoardCode = string;
export type CommunityContentStatus = "published" | "removed";
export type CommunityReportReason = "spam" | "harassment" | "privacy" | "unsafe" | "other";
export type CommunityReportStatus = "open" | "resolved" | "dismissed";
export type CommunityReportDecision = "dismiss" | "remove_content" | "remove_and_lock";
export type CommunityModerationAction = "lock" | "unlock" | "pin" | "unpin" | "remove" | "restore";
export type CommunityNotificationKind =
  | "mention"
  | "reply"
  | "follow"
  | "like_summary"
  | "group_application"
  | "group_decision"
  | "group_role_change"
  | "direct_message";
export type CommunityNotificationSource =
  | "post"
  | "comment"
  | "user"
  | "group"
  | "direct_message";
export type CommunityNotificationOutboxStatus = "pending" | "delivered" | "failed";
export type CommunityActivityFeed = "latest" | "following" | "groups";
export type CommunityActivityKind =
  | "post_published"
  | "comment_published"
  | "group_joined"
  | "user_followed";
export type CommunityActivitySource =
  | "post"
  | "comment"
  | "group_membership"
  | "user_follow";

export type CommunityBoardStatus = "active" | "inactive";
export type CommunityGroupVisibility = "public" | "approval" | "private";
export type CommunityGroupStatus = "active" | "inactive";
export type CommunityGroupRole = "owner" | "moderator" | "member";
export type CommunityGroupMembershipStatus = "pending" | "active" | "rejected" | "removed";

export interface CommunityBoard {
  code: CommunityBoardCode;
  name: string;
  description: string;
  sort_order: number;
  minimum_role: UserRole;
  status: CommunityBoardStatus;
  is_read_only: boolean;
  post_count: number;
}

export interface CommunityBoardListResponse {
  items: CommunityBoard[];
}

export interface CommunityAuthor {
  user_id: string;
  username: string;
  role: UserRole;
}

export interface CommunityGroupSummary {
  slug: string;
  name: string;
  description: string;
  visibility: CommunityGroupVisibility;
  status: CommunityGroupStatus;
  member_count: number;
  post_count: number;
  viewer_role: CommunityGroupRole | null;
  viewer_membership_status: CommunityGroupMembershipStatus | null;
}

export interface CommunityGroupMember {
  username: string;
  role: CommunityGroupRole;
  status: CommunityGroupMembershipStatus;
}

export interface CommunityGroupListResponse {
  items: CommunityGroupSummary[];
}

export interface CommunityGroupDetail extends CommunityGroupSummary {
  owner_username: string;
  members: CommunityGroupMember[];
}

export interface CommunityGroupCreateRequest {
  slug: string;
  name: string;
  description: string;
  visibility: CommunityGroupVisibility;
}

export interface CommunityGroupUpdateRequest {
  name: string;
  description: string;
  visibility: CommunityGroupVisibility;
  status: CommunityGroupStatus;
}

export interface CommunityGroupMembershipResponse {
  group: CommunityGroupSummary;
  message: string;
}

export interface CommunityGroupMemberDecisionRequest {
  decision: "approve" | "reject" | "remove" | "invite";
  role?: CommunityGroupRole;
}

export interface CommunityPostCreateRequest {
  board_code: CommunityBoardCode;
  group_slug?: string | null;
  title: string;
  content: string;
  rules_accepted: boolean;
}

export interface CommunityPostUpdateRequest {
  title: string;
  content: string;
  rules_accepted: boolean;
  expected_version: number;
}

export interface CommunityCommentCreateRequest {
  content: string;
  parent_id?: string | null;
  rules_accepted: boolean;
}

export interface CommunityCommentUpdateRequest {
  content: string;
  rules_accepted: boolean;
  expected_version: number;
}

export interface CommunityPostSummary {
  id: string;
  board_code: CommunityBoardCode;
  group_slug: string | null;
  title: string;
  content_preview: string;
  author: CommunityAuthor;
  is_pinned: boolean;
  is_locked: boolean;
  reply_count: number;
  like_count: number;
  version: number;
  edited_at: string | null;
  last_activity_at: string;
  created_at: string;
}

export interface CommunityPostListResponse {
  items: CommunityPostSummary[];
  page: number;
  page_size: number;
  total: number;
  next_cursor?: string | null;
  has_more?: boolean;
}

export interface CommunityCommentResponse {
  id: string;
  parent_id: string | null;
  root_id: string | null;
  reply_to_user_id: string | null;
  content: string;
  author: CommunityAuthor;
  like_count: number;
  viewer_has_liked: boolean;
  version: number;
  edited_at: string | null;
  created_at: string;
}

export interface CommunityCommentListResponse {
  items: CommunityCommentResponse[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface CommunityPostDetail {
  id: string;
  board_code: CommunityBoardCode;
  group_slug: string | null;
  title: string;
  content: string;
  author: CommunityAuthor;
  is_pinned: boolean;
  is_locked: boolean;
  reply_count: number;
  like_count: number;
  viewer_has_liked: boolean;
  viewer_has_bookmarked: boolean;
  version: number;
  edited_at: string | null;
  last_activity_at: string;
  created_at: string;
  comments: CommunityCommentResponse[];
}

export interface CommunityHomeResponse {
  boards: CommunityBoard[];
  posts: CommunityPostListResponse;
}


export const COMMUNITY_SEARCH_RESULT_TYPES = [
  "post",
  "user",
  "board",
  "group",
] as const;

export type CommunitySearchResultType =
  (typeof COMMUNITY_SEARCH_RESULT_TYPES)[number];

export const COMMUNITY_SEARCH_MODES = [
  "ngram",
  "prefix_fallback",
  "test",
] as const;

export type CommunitySearchMode = (typeof COMMUNITY_SEARCH_MODES)[number];

export interface CommunitySearchResultItem {
  type: CommunitySearchResultType;
  source_id: string;
  title: string;
  preview: string;
  username: string | null;
  board_code: CommunityBoardCode | null;
  group_slug: string | null;
  updated_at: string;
}

export interface CommunitySearchProviderState {
  mode: CommunitySearchMode;
  degraded: boolean;
}

export interface CommunitySearchResponse {
  query: string;
  items: CommunitySearchResultItem[];
  page: number;
  page_size: number;
  total: number;
  provider: CommunitySearchProviderState;
}

export type CommunitySearchRebuildStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed";

export interface CommunitySearchRebuildSummary {
  status: CommunitySearchRebuildStatus;
  expected_count: number;
  indexed_count: number;
  missing_count: number;
  extra_count: number;
  started_at: string | null;
  finished_at: string | null;
}

export interface CommunitySearchHealthResponse {
  generated_at: string;
  provider: CommunitySearchProviderState;
  pending_count: number;
  delivered_count: number;
  failed_count: number;
  retry_due_count: number;
  oldest_pending_seconds: number | null;
  last_delivered_at: string | null;
  delivery_latency_buckets: Record<string, number>;
  last_rebuild: CommunitySearchRebuildSummary | null;
}
export interface CommunityPostInteractionResponse {
  post_id: string;
  like_count: number;
  viewer_has_liked: boolean;
  viewer_has_bookmarked: boolean;
}

export interface CommunityCommentLikeResponse {
  comment_id: string;
  like_count: number;
  viewer_has_liked: boolean;
}

export interface CommunityBookmarkItem {
  post_id: string;
  bookmarked_at: string;
  post: CommunityPostSummary | null;
}

export interface CommunityBookmarkListResponse {
  items: CommunityBookmarkItem[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface CommunityDirectConversationCreateRequest {
  recipient_username: string;
}

export interface CommunityDirectMessageCreateRequest {
  body: string;
  client_message_id: string;
}

export interface CommunityDirectReadStateUpdateRequest {
  last_read_sequence: number;
}

export interface CommunityDirectMemberStateUpdateRequest {
  archived?: boolean | null;
  muted_until?: string | null;
}

export interface CommunityDirectConversationResponse {
  id: string;
  counterpart_username: string;
  counterpart_display_name: string;
  counterpart_avatar_seed: string;
  counterpart_avatar_url: string | null;
  last_message_at: string | null;
  unread_count: number;
  last_read_sequence: number;
  archived_at: string | null;
  muted_until: string | null;
  created_at: string;
  updated_at: string;
}

export interface CommunityDirectConversationCreateResponse {
  conversation: CommunityDirectConversationResponse;
  created: boolean;
}

export interface CommunityDirectConversationListResponse {
  items: CommunityDirectConversationResponse[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface CommunityDirectMessageResponse {
  id: string;
  conversation_id: string;
  sender_username: string;
  body: string;
  sequence: number;
  created_at: string;
}

export interface CommunityDirectMessageListResponse {
  items: CommunityDirectMessageResponse[];
  next_cursor: string | null;
  has_more: boolean;
  last_read_sequence: number;
  counterpart_last_read_sequence: number;
  unread_count: number;
}

export type CommunityDirectStreamStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "offline";

export interface CommunityDirectStreamReadyEvent {
  type: "ready";
  eventId: number;
  totalUnreadCount: number;
  resetRequired: boolean;
}

export interface CommunityDirectMessageCreatedEvent {
  type: "message.created";
  eventId: number;
  conversationId: string;
  messageId: string;
  messageSequence: number;
  senderId: string;
  createdAt: string;
}

export interface CommunityDirectConversationReadEvent {
  type: "conversation.read";
  eventId: number;
  conversationId: string;
  readerId: string;
  lastReadSequence: number;
  readAt: string;
}

export interface CommunityDirectUnreadChangedEvent {
  type: "unread.changed";
  eventId: number;
  conversationId: string;
  conversationUnreadCount: number;
  totalUnreadCount: number;
  changedAt: string;
}

export type CommunityDirectStreamEvent =
  | CommunityDirectStreamReadyEvent
  | CommunityDirectMessageCreatedEvent
  | CommunityDirectConversationReadEvent
  | CommunityDirectUnreadChangedEvent;

export interface CommunityDirectReadStateResponse {
  conversation_id: string;
  last_read_sequence: number;
  unread_count: number;
}

export interface CommunityDirectMemberStateResponse {
  conversation_id: string;
  archived_at: string | null;
  muted_until: string | null;
}

export interface CommunityNotificationResponse {
  id: string;
  kind: CommunityNotificationKind;
  source_type: CommunityNotificationSource;
  source_id: string;
  post_id: string | null;
  comment_id: string | null;
  preview: string;
  actor: CommunityAuthor;
  read_at: string | null;
  created_at: string;
}

export interface CommunityNotificationListResponse {
  items: CommunityNotificationResponse[];
  unread_count: number;
  next_cursor: string | null;
  has_more: boolean;
}

export interface CommunityNotificationStreamReady {
  event_id: string | null;
  unread_count: number;
}

export interface CommunityNotificationStreamEvent {
  event_id: string;
  notification: CommunityNotificationResponse;
  unread_count: number;
}

export type CommunityNotificationStreamStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "offline";

export interface CommunityNotificationReadResponse {
  message: string;
  unread_count: number;
}

export interface CommunityNotificationPreferenceItem {
  kind: CommunityNotificationKind;
  in_app_enabled: boolean;
  email_digest_enabled: boolean;
}

export interface CommunityNotificationPreferencesResponse {
  items: CommunityNotificationPreferenceItem[];
}

export interface CommunityNotificationPreferencesUpdateRequest {
  items: CommunityNotificationPreferenceItem[];
}

export interface CommunityActivityPreferenceResponse {
  share_group_joins: boolean;
  share_follows: boolean;
}

export interface CommunityActivityPreferenceUpdateRequest {
  share_group_joins: boolean;
  share_follows: boolean;
}

export interface CommunityActivityItem {
  id: string;
  kind: CommunityActivityKind;
  source_type: CommunityActivitySource;
  source_id: string;
  actor: CommunityAuthor;
  preview: string;
  post_id: string | null;
  post_title: string | null;
  comment_id: string | null;
  group_slug: string | null;
  group_name: string | null;
  target_username: string | null;
  created_at: string;
}

export interface CommunityActivityListResponse {
  feed: CommunityActivityFeed;
  items: CommunityActivityItem[];
  next_cursor: string | null;
  has_more: boolean;
}

export type CommunityRelationVisibility = "public" | "private";
export type CommunityInteractionPolicy = "everyone" | "following" | "nobody";

export interface CommunityPublicLevel {
  code: string;
  name: string;
}

export interface CommunityProfileStats {
  post_count: number;
  comment_count: number;
  follower_count: number;
  following_count: number;
}

export interface CommunityRelationshipState {
  viewer_is_self: boolean;
  viewer_is_following: boolean;
  follows_viewer: boolean;
  viewer_is_blocking: boolean;
  viewer_is_blocked: boolean;
  viewer_is_muting: boolean;
}

export interface CommunityPublicCommentSummary {
  id: string;
  post_id: string;
  post_title: string;
  content_preview: string;
  like_count: number;
  created_at: string;
}

export type CommunityAvatarKind = "generated" | "upload" | "gravatar";

export interface CommunityPublicProfileResponse {
  username: string;
  display_name: string;
  bio: string;
  avatar_seed: string;
  avatar_kind: CommunityAvatarKind;
  avatar_url: string | null;
  role: UserRole;
  level: CommunityPublicLevel;
  registered_month: string;
  stats: CommunityProfileStats;
  relationship: CommunityRelationshipState;
  recent_posts: CommunityPostSummary[];
  recent_comments: CommunityPublicCommentSummary[];
}

export interface CommunityOwnProfileResponse extends CommunityPublicProfileResponse {
  follower_visibility: CommunityRelationVisibility;
  following_visibility: CommunityRelationVisibility;
  message_policy: CommunityInteractionPolicy;
  mention_policy: CommunityInteractionPolicy;
  gravatar_enabled: boolean;
}

export interface CommunityProfileUpdateRequest {
  display_name: string;
  bio: string;
  regenerate_avatar: boolean;
  avatar_kind: CommunityAvatarKind;
  gravatar_enabled: boolean;
}

export interface CommunityPrivacyUpdateRequest {
  follower_visibility: CommunityRelationVisibility;
  following_visibility: CommunityRelationVisibility;
  message_policy: CommunityInteractionPolicy;
  mention_policy: CommunityInteractionPolicy;
}

export interface CommunityMuteRequest {
  expires_at: string | null;
}

export interface CommunityRelationshipMutationResponse {
  username: string;
  relationship: CommunityRelationshipState;
  message: string;
}

export interface CommunityRelationUser {
  username: string;
  display_name: string;
  avatar_seed: string;
  role: UserRole;
  level: CommunityPublicLevel;
}

export interface CommunityRelationListResponse {
  items: CommunityRelationUser[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface CommunityReportCreateRequest {
  post_id: string;
  comment_id?: string | null;
  reason: CommunityReportReason;
  details: string;
}

export interface CommunityReportResponse {
  id: string;
  post_id: string;
  comment_id: string | null;
  reason: CommunityReportReason;
  status: CommunityReportStatus;
  created_at: string;
}

export interface AdminCommunityReportSummary {
  id: string;
  reporter_username: string;
  post_id: string;
  post_title: string;
  comment_id: string | null;
  target_type: "post" | "comment";
  target_excerpt: string;
  reason: CommunityReportReason;
  details: string;
  status: CommunityReportStatus;
  decision: CommunityReportDecision | null;
  resolution_note: string | null;
  resolved_by_username: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface AdminCommunityReportListResponse {
  items: AdminCommunityReportSummary[];
  page: number;
  page_size: number;
  total: number;
}

export interface AdminCommunityReportResolveRequest {
  decision: CommunityReportDecision;
  note: string;
}

export interface AdminCommunityPostModerateRequest {
  action: CommunityModerationAction;
  note: string;
}

export interface AdminCommunityPostState {
  id: string;
  board_code: CommunityBoardCode;
  title: string;
  status: CommunityContentStatus;
  is_pinned: boolean;
  is_locked: boolean;
  reply_count: number;
  updated_at: string;
}

export interface AdminCommunityReportMutationResponse {
  report: AdminCommunityReportSummary;
  post: AdminCommunityPostState;
  audit_id: string;
  request_id: string | null;
}

export interface AdminCommunityPostMutationResponse {
  post: AdminCommunityPostState;
  audit_id: string;
  request_id: string | null;
}


export interface AdminCommunityBoardCreateRequest {
  code: string;
  name: string;
  description: string;
  sort_order: number;
  minimum_role: UserRole;
  is_read_only: boolean;
  status: CommunityBoardStatus;
}

export type AdminCommunityBoardUpdateRequest = Omit<AdminCommunityBoardCreateRequest, "code">;

export interface AdminCommunityBoardResponse extends CommunityBoard {
  created_at: string;
  updated_at: string;
}

export interface AdminCommunityBoardListResponse {
  items: AdminCommunityBoardResponse[];
}

export interface AdminCommunityBoardMutationResponse {
  board: AdminCommunityBoardResponse;
  audit_id: string;
  request_id: string | null;
}

export interface AdminCommunityNotificationOutboxItem {
  id: string;
  notification_id: string;
  recipient_username: string;
  actor_username: string;
  kind: CommunityNotificationKind;
  source_type: CommunityNotificationSource;
  status: CommunityNotificationOutboxStatus;
  attempts: number;
  available_at: string;
  delivered_at: string | null;
  failed_at: string | null;
  last_error_code: string | null;
  replay_count: number;
  last_replayed_at: string | null;
  last_replayed_by_username: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminCommunityNotificationOutboxListResponse {
  items: AdminCommunityNotificationOutboxItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface AdminCommunityNotificationOutboxMetrics {
  generated_at: string;
  pending_count: number;
  delivered_count: number;
  failed_count: number;
  failed_last_24_hours: number;
  retry_due_count: number;
  oldest_pending_seconds: number | null;
  email_digest_pending_count: number;
  email_digest_sent_count: number;
  email_digest_failed_count: number;
  email_digest_suppressed_count: number;
  email_digest_last_sent_at: string | null;
}

export interface AdminCommunityNotificationReplayResponse {
  event: AdminCommunityNotificationOutboxItem;
  audit_id: string;
  request_id: string | null;
}

export type ThirdPartyAppStatus =
  | "draft"
  | "pending_review"
  | "approved"
  | "suspended"
  | "revoked";
export type ThirdPartyAppSource = "admin" | "developer_self_service";

export const THIRD_PARTY_API_V1_SCOPES = [
  "profile:read",
  "hash:read",
  "announcements:read",
  "updates:read",
  "desktop:installations",
  "desktop:verification",
  "desktop:verification:trusted",
] as const;

export type ThirdPartyScope = (typeof THIRD_PARTY_API_V1_SCOPES)[number];

export const THIRD_PARTY_REQUESTABLE_SCOPE_OPTIONS = [
  {
    value: "profile:read",
    label: "读取已授权用户的公开资料",
    description: "仅用于显示当前已授权用户的基础资料。",
  },
  {
    value: "hash:read",
    label: "读取已公开的哈希资料",
    description: "查询公开哈希条目及其公开评论。",
  },
  {
    value: "announcements:read",
    label: "读取桌面端公告",
    description: "获取面向桌面端的公告内容与图片链接。",
  },
  {
    value: "updates:read",
    label: "检查桌面端版本更新",
    description: "检查当前桌面程序是否有可用更新。",
  },
  {
    value: "desktop:installations",
    label: "登记与管理本机安装实例",
    description: "登记当前设备安装实例以完成桌面端可信调用。",
  },
  {
    value: "desktop:verification",
    label: "验证压缩包密码并提交回执",
    description: "提交本地验证结果；默认进入待验证池。",
  },
] as const satisfies ReadonlyArray<{
  value: Exclude<ThirdPartyScope, "desktop:verification:trusted">;
  label: string;
  description: string;
}>;

export type ThirdPartyRequestableScope =
  (typeof THIRD_PARTY_REQUESTABLE_SCOPE_OPTIONS)[number]["value"];

export const THIRD_PARTY_OAUTH_GRANT_TYPES = [
  "authorization_code",
  "refresh_token",
] as const;

export type ThirdPartyOAuthGrantType =
  (typeof THIRD_PARTY_OAUTH_GRANT_TYPES)[number];

export const THIRD_PARTY_API_V1_PATHS = {
  oauthAuthorize: "/third-party/oauth/authorize",
  oauthConsent: "/third-party/oauth/consent",
  authorizedApplications: "/third-party/oauth/authorized-applications",
  oauthToken: "/third-party/oauth/token",
  oauthRevoke: "/third-party/oauth/revoke",
  oauthMe: "/third-party/oauth/me",
  hashDetail: "/third-party/hashes/{algorithm}/{digest}",
  hashComments: "/third-party/hashes/{algorithm}/{digest}/comments",
  announcements: "/third-party/announcements",
  updatesCheck: "/third-party/updates/check",
  installations: "/third-party/installations",
  challenges: "/third-party/challenges",
  verificationReceipts: "/third-party/verification-receipts",
} as const;

export interface ThirdPartyAnnouncementItem {
  id: string;
  title: string;
  content: string;
  content_type: DesktopAnnouncementContentType;
  image_urls: string[];
  action_label: string | null;
  action_url: string | null;
  sort_order: number;
  starts_at: string | null;
  ends_at: string | null;
}

export interface ThirdPartyAnnouncementListResponse {
  items: ThirdPartyAnnouncementItem[];
}

export interface ThirdPartyUpdateCheckResponse {
  update_available: boolean;
  mandatory: boolean;
  current_version: string;
  latest_version: string | null;
  minimum_supported_version: string | null;
  channel: DesktopReleaseChannel;
  platform: string;
  architecture: DesktopArchitecture;
  release_id: string | null;
  release_notes: string;
  published_at: string | null;
  download_url: string | null;
  artifact_filename: string | null;
  artifact_sha256: string | null;
  artifact_size_bytes: number | null;
  artifact_integrity: "sha256-verified" | null;
}

export type ThirdPartyHashDetailResponse = HashDetailResponse;
export type ThirdPartyHashCommentListResponse = HashCommentListResponse;
export const THIRD_PARTY_RECEIPT_CANONICAL_PAYLOAD_VERSION =
  "desktop-receipt-v1" as const;

export const THIRD_PARTY_RECEIPT_CANONICAL_FIELDS = [
  "version",
  "client_id",
  "challenge_id",
  "challenge_nonce",
  "installation_id",
  "account_id",
  "candidate_id",
  "fingerprint_algorithm",
  "fingerprint_digest",
  "candidate_digest",
  "outcome",
  "archive_format",
  "client_version",
  "verified_at",
] as const;

export type ThirdPartyReceiptCanonicalField =
  (typeof THIRD_PARTY_RECEIPT_CANONICAL_FIELDS)[number];

export interface ThirdPartyAuthorizationRequest {
  response_type: "code";
  client_id: string;
  redirect_uri: string;
  code_challenge: string;
  state: string;
  code_challenge_method: "S256";
  scope?: string;
}

export interface ThirdPartyAuthorizationDetails {
  client_id: string;
  app_name: string;
  developer_name: string;
  description: string;
  redirect_uri: string;
  requested_scopes: string[];
  approved_scopes: string[];
  previously_authorized: boolean;
}

export interface ThirdPartyAuthorizationDecisionRequest
  extends ThirdPartyAuthorizationRequest {
  decision: "approve" | "deny";
}

export interface ThirdPartyAuthorizationDecisionResponse {
  redirect_url: string;
}

export interface ThirdPartyOAuthTokenRequest {
  grant_type: ThirdPartyOAuthGrantType;
  client_id: string;
  code?: string | null;
  redirect_uri?: string | null;
  code_verifier?: string | null;
  refresh_token?: string | null;
}

export interface ThirdPartyOAuthTokenResponse {
  access_token: string;
  token_type: "Bearer";
  expires_in: number;
  refresh_token: string;
  scope: string;
}

export interface ThirdPartyOAuthRevokeRequest {
  client_id: string;
  token: string;
  token_type_hint?: "access_token" | "refresh_token" | null;
}

export interface ThirdPartyPrincipalResponse {
  user_id: string;
  client_id: string;
  app_id: string;
  scopes: ThirdPartyScope[];
}

export type ThirdPartyOperatingSystem =
  | "windows"
  | "linux"
  | "macos"
  | "other";
export type ThirdPartyArchitecture = "x86" | "x64" | "arm64" | "other";

export interface ThirdPartyInstallationRegistrationRequest
  extends DesktopInstallationRegistrationRequest {
  operating_system?: ThirdPartyOperatingSystem | null;
  architecture?: ThirdPartyArchitecture | null;
}

export interface ThirdPartyInstallation extends DesktopInstallation {
  client_id: string;
  receipt_protocol: typeof THIRD_PARTY_RECEIPT_CANONICAL_PAYLOAD_VERSION;
  operating_system: ThirdPartyOperatingSystem | null;
  architecture: ThirdPartyArchitecture | null;
}

export interface ThirdPartyInstallationListResponse {
  items: ThirdPartyInstallation[];
}

export type ThirdPartyChallengeRequest = DesktopChallengeRequest;

export interface ThirdPartyChallengeResponse extends DesktopChallengeResponse {
  client_id: string;
}

export interface ThirdPartyReceiptRequest extends DesktopReceiptRequest {
  client_id: string;
}

export interface ThirdPartyReceiptResponse extends DesktopReceiptResponse {
  trust_channel: "third_party_pending" | "third_party_trusted";
}

export interface AuthorizedApplication {
  app_id: string;
  client_id: string;
  app_name: string;
  developer_name: string;
  scopes: string[];
  authorized_at: string;
  last_used_at: string | null;
}

export interface AuthorizedApplicationListResponse {
  items: AuthorizedApplication[];
}

export interface ThirdPartyApp {
  id: string;
  client_id: string;
  name: string;
  developer_name: string;
  description: string;
  status: ThirdPartyAppStatus;
  application_source: ThirdPartyAppSource;
  requested_scopes: string[];
  approved_scopes: string[];
  redirect_uris: string[];
  trusted_verification_enabled: boolean;
  request_count: number;
  last_used_at: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
  revoked_at: string | null;
  management_secret: string | null;
}

export interface ThirdPartyAppListResponse {
  items: ThirdPartyApp[];
  page: number;
  page_size: number;
  total: number;
}

export interface ThirdPartyAppCreateRequest {
  name: string;
  developer_name: string;
  description: string;
  redirect_uris: string[];
  scopes: string[];
}

export interface ThirdPartyAppReviewRequest {
  review_note?: string | null;
  trusted_verification_enabled: boolean;
}
