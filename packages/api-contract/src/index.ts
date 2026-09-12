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
  priority_score: number;
  priority_reason: string | null;
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

export interface AdminHeatmapDay {
  day: string;
  weekday: number;
  activity_count_band: string;
  active_boards_count_band: string;
}

export interface AdminHeatmapBoard {
  board_code: string;
  board_name: string;
  activity_count_band: string;
}

export interface AdminCommunityHeatmapResponse {
  window_days: number;
  days: AdminHeatmapDay[];
  boards: AdminHeatmapBoard[];
  generated_at: string;
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

export type SeoTitleSeparator = "-" | "_" | "|" | "·";

export interface SeoSettings {
  enabled: boolean;
  indexing_enabled: boolean;
  home_title: string;
  keywords: string[];
  description: string;
  title_separator: SeoTitleSeparator;
  default_image_url: string;
  open_graph_enabled: boolean;
  sitemap_enabled: boolean;
}

export interface SeoSettingsResponse {
  settings: SeoSettings;
  updated_at: string | null;
  updated_by: string | null;
}

export interface PublicSeoConfig {
  enabled: boolean;
  indexing_enabled: boolean;
  home_title: string;
  keywords: string[];
  description: string;
  title_separator: SeoTitleSeparator;
  default_image_url: string;
  open_graph_enabled: boolean;
}

export type AdminUserProfileReasonCode =
  | "profile_correction"
  | "user_request"
  | "compliance_review";

export interface AdminUserProfileUpdateRequest {
  expected_updated_at: string;
  email?: string;
  email_verified?: boolean;
  reason_code: AdminUserProfileReasonCode;
  reauth_token: string;
}

export interface AdminUserProfileUpdateResponse {
  user_id: string;
  masked_email: string;
  email_verified: boolean;
  updated_at: string;
  audit_id: string;
  request_id: string | null;
}

export type RegistrationMode = "open" | "invite_only";
export type RegistrationInviteStatus = "active" | "exhausted" | "expired" | "revoked";

export interface RegistrationPolicy {
  mode: RegistrationMode;
}

export interface RegistrationInvite {
  id: string;
  label: string;
  max_uses: number;
  use_count: number;
  remaining_uses: number;
  status: RegistrationInviteStatus;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface RegistrationInviteCreated extends RegistrationInvite {
  code: string;
}

export interface RegistrationInviteListResponse {
  items: RegistrationInvite[];
  total: number;
}

export interface PublicLegalConfig {
  icp_record: string;
  public_security_record: string;
  copyright_text: string;
  public_contact_email: string;
}

export interface PublicMaintenanceConfig {
  active: boolean;
  message: string;
}

export interface PublicRegistrationConfig {
  mode: RegistrationMode;
}

export interface PublicSiteConfig {
  site_name: string;
  site_logo_url: string;
  navigation: SiteNavigationItem[];
  seo: PublicSeoConfig;
  legal: PublicLegalConfig;
  maintenance: PublicMaintenanceConfig;
  registration: PublicRegistrationConfig;
}

export interface HotHashSummary {
  algorithm: FingerprintAlgorithm;
  digest: string;
  like_count: number;
  comment_count: number;
  useful_vote_count: number;
  heat_score: number;
}

export interface UserRankingSummary {
  rank: number;
  uid: string;
  username: string;
  score: number;
}

export interface HomeDiscoveryResponse {
  hot_hashes: HotHashSummary[];
  contribution_leaders: UserRankingSummary[];
  points_leaders: UserRankingSummary[];
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
  icp_record: string;
  public_security_record: string;
  copyright_text: string;
  public_contact_email: string;
  maintenance_enabled: boolean;
  maintenance_message: string;
  maintenance_allowed_ip_cidrs: string[];
  max_active_sessions: number;
  session_overflow_policy: "deny_new" | "revoke_oldest";
  referral_reward_points: number;
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
  footer_html: string;
  content_format: "multipart";
  smtp_host: string;
  smtp_port: number;
  smtp_security: SmtpSecurityMode;
  smtp_username: string;
  smtp_auth_enabled: boolean;
  smtp_password_configured: boolean;
  smtp_timeout_seconds: number;
  configuration_source: "database" | "deployment_environment";
}

export interface EmailDeliverySettingsUpdate {
  enabled: boolean;
  sender_name: string;
  sender_email: string;
  subject_prefix: string;
  footer_text: string;
  footer_html: string;
  smtp_host: string;
  smtp_port: number;
  smtp_security: SmtpSecurityMode;
  smtp_username: string;
  smtp_auth_enabled: boolean;
  smtp_timeout_seconds: number;
  smtp_password?: string | null;
  clear_smtp_password: boolean;
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
export type CommunityDirectMessageReportStatus = "open" | "resolved" | "dismissed";
export type CommunityDirectMessageReportDecision = "dismiss" | "remove_message";
export type CommunityModerationAction = "lock" | "unlock" | "pin" | "unpin" | "remove" | "restore";
export type CommunityNotificationKind =
  | "mention"
  | "reply"
  | "follow"
  | "like_summary"
  | "group_application"
  | "group_decision"
  | "group_role_change"
  | "direct_message"
  | "plugin_review";
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

export interface CommunitySeoProjection {
  eligible: boolean;
  indexable: boolean;
  title: string | null;
  description: string | null;
  keywords: string[];
  canonical_path: string | null;
  og_image_url: string | null;
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
  seo_version: number;
  seo_title: string | null;
  seo_description: string | null;
  seo_keywords: string[] | null;
  seo_canonical_path: string | null;
  og_image_url: string | null;
  seo: CommunitySeoProjection;
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

export interface ReferralProfileResponse {
  code: string;
  referral_url: string;
  reward_points: number;
  referral_count: number;
  total_points_earned: number;
  created_at: string;
}

export type RewardCatalogKind = "virtual";
export type RewardCatalogStatus = "draft" | "active" | "inactive";
export type RewardStockStatus = "available" | "limited" | "out_of_stock";

export interface RewardCatalogItem {
  id: string;
  slug: string;
  name: string;
  description: string;
  kind: RewardCatalogKind;
  cost_points: number;
  per_user_limit: number;
  category: string;
  tags: string[];
  entitlement_key: string;
  entitlement_duration_days: number | null;
  redeem_start_at: string | null;
  redeem_end_at: string | null;
  stock_status: RewardStockStatus;
  redeem_status: "available" | "scheduled" | "ended" | "out_of_stock";
}

export interface RewardCatalogResponse {
  items: RewardCatalogItem[];
  available_points: number | null;
  categories: string[];
  tags: string[];
}

export interface AdminRewardCatalogItem extends RewardCatalogItem {
  stock: number;
  sort_weight: number;
  status: RewardCatalogStatus;
  version: number;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
}

export interface AdminRewardCatalogListResponse {
  items: AdminRewardCatalogItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface RewardCatalogCreateRequest {
  slug: string;
  name: string;
  description: string;
  kind: RewardCatalogKind;
  cost_points: number;
  stock: number;
  per_user_limit: number;
  category: string;
  tags: string[];
  sort_weight: number;
  entitlement_key: string;
  entitlement_duration_days: number | null;
  redeem_start_at: string | null;
  redeem_end_at: string | null;
  status: RewardCatalogStatus;
  reason_code: string;
}

export interface RewardCatalogUpdateRequest {
  name: string;
  description: string;
  kind: RewardCatalogKind;
  cost_points: number;
  per_user_limit: number;
  category: string;
  tags: string[];
  sort_weight: number;
  entitlement_key: string;
  entitlement_duration_days: number | null;
  redeem_start_at: string | null;
  redeem_end_at: string | null;
  status: RewardCatalogStatus;
  expected_version: number;
  reason_code: string;
}

export type RewardOrderStatus =
  | "pending_fulfillment"
  | "processing"
  | "fulfilled"
  | "failed"
  | "cancelled";
export type RewardFulfillmentStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "retryable"
  | "failed"
  | "cancelled";

export interface RewardFulfillmentSummary {
  status: RewardFulfillmentStatus;
  attempt_no: number;
  result_code: string | null;
  safe_message: string | null;
  completed_at: string | null;
}

export interface RewardOrderSummary {
  id: string;
  order_no: string;
  status: RewardOrderStatus;
  catalog_item_id: string;
  item_slug: string;
  item_name: string;
  quantity: number;
  unit_cost_points: number;
  total_cost_points: number;
  created_at: string;
  updated_at: string;
  fulfilled_at: string | null;
  cancelled_at: string | null;
  compensated_at: string | null;
  fulfillment: RewardFulfillmentSummary | null;
}

export interface RewardOrderListResponse {
  items: RewardOrderSummary[];
  page: number;
  page_size: number;
  total: number;
}

export interface RewardOrderTimelineEvent {
  id: string;
  from_status: RewardOrderStatus | null;
  to_status: RewardOrderStatus;
  event_type: string;
  reason_code: string;
  created_at: string;
}

export interface RewardEntitlementGrant {
  entitlement_key: string;
  status: string;
  starts_at: string;
  expires_at: string | null;
}

export interface RewardOrderDetail extends RewardOrderSummary {
  available_points: number;
  timeline: RewardOrderTimelineEvent[];
  entitlement: RewardEntitlementGrant | null;
}

export interface RewardOrderCreateRequest {
  catalog_item_id: string;
  quantity: number;
}

export interface RewardInventoryAdjustmentRequest {
  delta: number;
  reason_code: "initial_stock" | "restock" | "correction" | "campaign";
  expected_version: number;
  note?: string | null;
}

export interface RewardInventoryEvent {
  id: string;
  catalog_item_id: string;
  order_id: string | null;
  event_type: "redeemed" | "released" | "admin_adjusted";
  delta: number;
  stock_before: number;
  stock_after: number;
  actor_type: "user" | "admin" | "system";
  actor_id: string | null;
  reason_code: string;
  note: string | null;
  created_at: string;
}

export interface RewardInventoryEventListResponse {
  items: RewardInventoryEvent[];
  page: number;
  page_size: number;
  total: number;
}

export interface RewardAdminOrderActionRequest {
  expected_version: number;
  reason_code: string;
}

export interface RewardAdminFulfillment extends RewardFulfillmentSummary {
  id: string;
  attempt_no: number;
  delivery_kind: "internal_entitlement";
  retry_count: number;
  next_retry_at: string | null;
  started_at: string | null;
  created_at: string;
}

export interface RewardAdminOrder extends RewardOrderSummary {
  user_id: string;
  version: number;
  failure_code: string | null;
  points_ledger_entry_id: string;
  compensation_ledger_entry_id: string | null;
  fulfillments: RewardAdminFulfillment[];
  inventory_events: RewardInventoryEvent[];
  timeline: RewardOrderTimelineEvent[];
}

export interface RewardAdminOrderListResponse {
  items: RewardAdminOrder[];
  page: number;
  page_size: number;
  total: number;
}

export interface RewardOperationsStatsResponse {
  total_orders: number;
  pending_orders: number;
  fulfilled_orders: number;
  failed_orders: number;
  cancelled_orders: number;
  redeemed_points: number;
  compensated_points: number;
  fulfillment_success_rate: number;
  low_stock_items: number;
}

export interface AlgorithmDistributionItem {
  algorithm: FingerprintAlgorithm;
  count_band: string;
  percentage: number;
}

export interface AlgorithmDistributionResponse {
  total_count_band: string;
  items: AlgorithmDistributionItem[];
  generated_at: string;
}

export interface CommunityActivityTrendBucket {
  day: string;
  posts_count_band: string;
  comments_count_band: string;
  activity_count_band: string;
  active_boards_count_band: string;
}

export interface CommunityActivityTrendBoard {
  board_code: string;
  board_name: string;
  posts_count_band: string;
  comments_count_band: string;
  activity_count_band: string;
}

export interface CommunityActivityTrendResponse {
  window_days: number;
  buckets: CommunityActivityTrendBucket[];
  boards: CommunityActivityTrendBoard[];
  generated_at: string;
}

export interface CommunityGroupSeoUpdateRequest {
  seo_title?: string | null;
  seo_description?: string | null;
  seo_keywords?: string[] | null;
  seo_canonical_path?: string | null;
  og_image_url?: string | null;
  expected_seo_version: number;
}

export interface CommunityGroupMembershipResponse {
  group: CommunityGroupSummary;
  message: string;
}

export interface CommunityGroupMemberDecisionRequest {
  decision: "approve" | "reject" | "remove" | "invite";
  role?: CommunityGroupRole;
}

export interface CommunityPostSeoUpdateRequest {
  seo_title?: string | null;
  seo_description?: string | null;
  seo_keywords?: string[] | null;
  seo_canonical_path?: string | null;
  og_image_url?: string | null;
  expected_seo_version: number;
}

export interface CommunityPostCreateRequest {
  board_code: CommunityBoardCode;
  group_slug?: string | null;
  title: string;
  content: string;
  rules_accepted: boolean;
  attachment_ids?: string[];
}

export interface CommunityImageUploadConfig {
  enabled: boolean;
  max_bytes: number;
  max_pixels: number;
  max_per_post: number;
}

export type CommunityImageStatus = "uploaded" | "attached" | "removed";

export interface CommunityPostImage {
  id: string;
  url: string;
  content_type: string;
  size_bytes: number;
  width: number;
  height: number;
}

export interface AdminCommunityImageUploadConfigResponse {
  config: CommunityImageUploadConfig;
  audit_id: string | null;
  request_id: string | null;
}

export interface AdminCommunityPostImageSummary {
  id: string;
  owner_username: string;
  post_id: string | null;
  post_title: string | null;
  status: CommunityImageStatus;
  content_type: string;
  size_bytes: number;
  width: number;
  height: number;
  created_at: string;
  attached_at: string | null;
  removed_at: string | null;
}

export interface AdminCommunityPostImageListResponse {
  items: AdminCommunityPostImageSummary[];
  page: number;
  page_size: number;
  total: number;
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
  seo_version: number;
  seo_title: string | null;
  seo_description: string | null;
  seo_keywords: string[] | null;
  seo_canonical_path: string | null;
  og_image_url: string | null;
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
  seo_version: number;
  seo_title: string | null;
  seo_description: string | null;
  seo_keywords: string[] | null;
  seo_canonical_path: string | null;
  og_image_url: string | null;
  edited_at: string | null;
  last_activity_at: string;
  created_at: string;
  comments: CommunityCommentResponse[];
  seo: CommunitySeoProjection;
  attachments: CommunityPostImage[];
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
  supporter_badge: boolean;
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

export interface CommunityDirectMessageReportCreateRequest {
  reason: CommunityReportReason;
  details: string;
}

export interface CommunityDirectMessageReportResponse {
  id: string;
  message_id: string;
  reason: CommunityReportReason;
  status: CommunityDirectMessageReportStatus;
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

export interface AdminCommunityDirectMessageReportSummary {
  id: string;
  reporter_username: string;
  message_id: string | null;
  conversation_id: string | null;
  sender_username: string | null;
  reason: CommunityReportReason;
  details: string;
  status: CommunityDirectMessageReportStatus;
  decision: CommunityDirectMessageReportDecision | null;
  resolution_note: string | null;
  resolved_by_username: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface AdminCommunityDirectMessageReportListResponse {
  items: AdminCommunityDirectMessageReportSummary[];
  page: number;
  page_size: number;
  total: number;
}

export interface AdminCommunityDirectMessageReportDetail
  extends AdminCommunityDirectMessageReportSummary {
  message_body: string | null;
  message_sequence: number | null;
  message_created_at: string | null;
}

export interface AdminCommunityDirectMessageReportResolveRequest {
  decision: CommunityDirectMessageReportDecision;
  note: string;
}

export interface AdminCommunityDirectMessageReportMutationResponse {
  report: AdminCommunityDirectMessageReportSummary;
  message_removed: boolean;
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

export const DESKTOP_PLUGIN_ARCHITECTURES = [
  "windows-x64",
  "windows-arm64",
] as const;

export type DesktopPluginArchitecture =
  (typeof DESKTOP_PLUGIN_ARCHITECTURES)[number];

export const DESKTOP_PLUGIN_PROJECT_STATUSES = [
  "draft",
  "active",
  "suspended",
  "revoked",
] as const;

export type DesktopPluginProjectStatus =
  (typeof DESKTOP_PLUGIN_PROJECT_STATUSES)[number];

export const DESKTOP_PLUGIN_VERSION_STATUSES = [
  "draft",
  "uploading",
  "quarantined",
  "review_queued",
  "auto_review_running",
  "auto_review_failed",
  "manual_review_ready",
  "approved",
  "published",
  "yanked",
  "rejected",
  "withdrawn",
  "revoked",
] as const;

export type DesktopPluginVersionStatus =
  (typeof DESKTOP_PLUGIN_VERSION_STATUSES)[number];

export const DESKTOP_PLUGIN_CAPABILITIES = [
  "ui:command",
  "ui:theme",
  "storage:private",
  "file:read:selected",
  "api:profile:read",
  "api:hash:read",
  "api:verification:submit",
  "network:internet",
  "secret:candidate:ephemeral",
  "process:spawn",
  "system:persistence",
  "credential:read",
] as const;

export type DesktopPluginCapability =
  (typeof DESKTOP_PLUGIN_CAPABILITIES)[number];

export const DESKTOP_PLUGIN_PATHS = {
  catalog: "/desktop/plugins/catalog",
  detail: "/desktop/plugins/{plugin_slug}",
  version: "/desktop/plugins/{plugin_slug}/versions/{semver}",
  downloadTicket: "/desktop/plugins/{plugin_slug}/download-ticket",
  canaryCatalog: "/desktop/plugins/canary/catalog",
  canaryDetail: "/desktop/plugins/canary/{plugin_slug}",
  revocations: "/desktop/plugins/revocations",
  migrationRetries: "/desktop/plugins/migration-retries",
  brokerAuthorize: "/desktop/plugins/{plugin_slug}/broker/authorize",
  developerProjects: "/developer/plugins",
  developerSigningKeys: "/developer/plugins/signing-keys",
  developerVersions: "/developer/plugins/{plugin_id}/versions",
  uploadSession: "/developer/plugin-versions/{version_id}/upload-session",
  finalize: "/developer/plugin-versions/{version_id}/finalize",
  buildProof: "/developer/plugin-versions/{version_id}/build-proof",
  submit: "/developer/plugin-versions/{version_id}/submit",
  reviewReport: "/developer/plugin-versions/{version_id}/review-report",
  adminRunners: "/admin/plugin-review-runners",
  adminPluginReviewMetrics: "/admin/plugin-reviews/metrics",
  adminPluginReviewPolicy: "/admin/plugin-review-policy",
  adminPluginReviewLlmKey: "/admin/plugin-review-policy/llm-key",
  adminPluginReviewLlmTest: "/admin/plugin-review-policy/llm-test",
  adminPluginReviewSource: "/admin/plugin-reviews/versions/{version_id}/source",
  adminPluginInstallEvidence: "/admin/plugin-reviews/install-evidence",
  runnerHeartbeat: "/plugin-runner/heartbeat",
  runnerLease: "/plugin-runner/tasks/lease",
} as const;

export interface DesktopPluginArtifact {
  id: string;
  architecture: DesktopPluginArchitecture;
  status: "uploading" | "quarantined" | "public" | "yanked" | "revoked";
  zone: "quarantine" | "public" | "revoked";
  artifact_filename: string;
  size_bytes: number;
  expanded_size_bytes: number | null;
  sha256: string;
  created_at: string;
  updated_at: string;
}

export interface DesktopPluginVersion {
  id: string;
  plugin_id: string;
  semver: string;
  status: DesktopPluginVersionStatus;
  signing_key_id: string;
  signing_key_fingerprint: string;
  manifest_json: Record<string, unknown> | null;
  manifest_sha256: string | null;
  protocol_min: number;
  protocol_max: number;
  host_min: string;
  host_max: string;
  requested_capabilities: DesktopPluginCapability[];
  approved_capabilities: DesktopPluginCapability[];
  risk_tier: string;
  release_notes: string;
  source_review_mode: "source" | "reproducible" | "binary_only";
  review_policy_version: string | null;
  platform_key_id: string | null;
  platform_public_key_base64: string | null;
  platform_signature_base64: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  finalized_at: string | null;
  published_at: string | null;
  remediation_deadline_at: string | null;
  build_proof_sha256?: string | null;
  build_proof_git_commit?: string | null;
  build_proof_package_sha256?: string | null;
  build_proof_rebuild_sha256?: string | null;
  build_proof_verified_at?: string | null;
  artifacts: DesktopPluginArtifact[];
}

export interface DesktopPluginProject {
  id: string;
  slug: string;
  owner_user_id: string;
  linked_third_party_app_id: string | null;
  name: string;
  summary: string;
  description: string;
  category: string;
  tags: string[];
  website_url: string | null;
  privacy_policy_url: string | null;
  source_url: string | null;
  status: DesktopPluginProjectStatus;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface DesktopPluginProjectDetail extends DesktopPluginProject {
  versions: DesktopPluginVersion[];
}

export interface DesktopPluginCatalogItem {
  slug: string;
  name: string;
  developer_name: string;
  summary: string;
  category: string;
  tags: string[];
  latest_version: string;
  risk_tier: string;
  review_policy_version: string;
  published_at: string;
  architectures: DesktopPluginArchitecture[];
}

export interface DesktopPluginCatalogResponse {
  items: DesktopPluginCatalogItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface DesktopPluginPublicArtifact {
  architecture: DesktopPluginArchitecture;
  size_bytes: number;
  sha256: string;
  artifact_filename: string;
}

export interface DesktopPluginPublicVersion {
  version_id: string;
  plugin_slug: string;
  semver: string;
  status: "published";
  manifest_json: Record<string, unknown>;
  manifest_sha256: string;
  signing_key_fingerprint: string;
  protocol_min: number;
  protocol_max: number;
  host_min: string;
  host_max: string;
  approved_capabilities: DesktopPluginCapability[];
  risk_tier: string;
  release_notes: string;
  review_policy_version: string;
  platform_key_id: string;
  platform_public_key_base64: string;
  platform_signature_base64: string;
  platform_signature_payload: Record<string, unknown>;
  published_at: string;
  artifacts: DesktopPluginPublicArtifact[];
}

export interface DesktopPluginPublicDetail {
  slug: string;
  name: string;
  developer_name: string;
  summary: string;
  description: string;
  category: string;
  tags: string[];
  website_url: string | null;
  privacy_policy_url: string | null;
  source_url: string | null;
  versions: DesktopPluginPublicVersion[];
}

export interface DesktopPluginDownloadTicketResponse {
  download_url: string;
  expires_at: string;
  artifact_sha256: string;
  artifact_size_bytes: number;
}

export interface DesktopPluginInstallEventRequest {
  event_id: string;
  plugin_slug: string;
  semver: string;
  architecture: DesktopPluginArchitecture;
  source: "market_reviewed" | "local_unreviewed";
  kind: "installed" | "upgraded" | "rolled_back" | "enabled" | "disabled" | "uninstalled" | "download_failed";
  result: "success" | "failure";
  client_version: string | null;
  permission_evidence?: DesktopPluginPermissionEvidence | null;
  migration_evidence?: DesktopPluginMigrationEvidence | null;
  installation_id?: string | null;
  evidence_signature?: string | null;
}

export interface DesktopPluginPermissionEvidence {
  requested_capabilities: string[];
  approved_capabilities: string[];
  granted_capabilities: string[];
  publisher_key_fingerprint: string;
  risk_tier: "low" | "standard" | "medium" | "high" | "critical";
  consented_at: string;
}

export interface DesktopPluginMigrationEvidence {
  from_version: string;
  to_version: string;
  status: "completed" | "not_required" | "failed";
  started_at: string;
  completed_at: string | null;
  steps: DesktopPluginMigrationStepEvidence[];
  package_sha256?: string | null;
}

export interface DesktopPluginMigrationStepEvidence {
  step_id: string;
  status: "completed" | "skipped" | "failed";
  attempt_count: number;
}

export interface DesktopPluginBuildProvenanceRecord {
  path: string;
  size_bytes: number;
  sha256: string;
}

export interface DesktopPluginBuildProof {
  schema: "pd.plugin.build-proof/v1";
  git_commit: string;
  package_sha256: string;
  rebuild_sha256: string;
  content_reproducible: true;
  provenance: {
    schema: "pd.plugin.provenance/v1";
    source_commit: string;
    source_files: DesktopPluginBuildProvenanceRecord[];
    sbom: DesktopPluginBuildProvenanceRecord;
    binaries: DesktopPluginBuildProvenanceRecord[];
  };
  toolchain: Record<string, string>;
}

export interface DesktopPluginBuildProofRequest {
  version: number;
  architecture: DesktopPluginArchitecture;
  github_repository: string;
  github_run_id: number;
  github_artifact_id: number;
  proof: DesktopPluginBuildProof;
}

export interface DesktopPluginInstallEvidenceItem {
  event_id: string;
  plugin_slug: string;
  semver: string;
  architecture: DesktopPluginArchitecture;
  kind: string;
  result: string;
  client_version: string | null;
  user_id: string | null;
  installation_id: string | null;
  evidence_payload_hash: string | null;
  created_at: string;
  permission_evidence: DesktopPluginPermissionEvidence | null;
  migration_evidence: DesktopPluginMigrationEvidence | null;
}

export interface DesktopPluginInstallEvidenceListResponse {
  items: DesktopPluginInstallEvidenceItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface DesktopPluginInstallEventResponse {
  accepted: boolean;
  event_id: string;
}

export type DesktopPluginBrokerCapability =
  | "api:profile:read"
  | "api:hash:read"
  | "api:verification:submit";

export interface DesktopPluginBrokerAuthorizationRequest {
  semver: string;
  capability: DesktopPluginBrokerCapability;
}

export interface DesktopPluginBrokerAuthorizationResponse {
  allowed: true;
  plugin_slug: string;
  semver: string;
  capability: DesktopPluginBrokerCapability;
  scope: string;
  linked_application_id: string;
}

export interface DesktopPluginRevocation {
  id: string;
  scope: "plugin" | "version" | "signing_key";
  plugin_slug: string | null;
  semver: string | null;
  signing_key_fingerprint: string | null;
  reason_code: string;
  affects_historical_versions: boolean;
  effective_at: string;
  batch_id: string;
  platform_key_id: string;
  platform_public_key_base64: string;
  platform_signature_base64: string;
  platform_signature_payload: Record<string, unknown>;
}

export interface DesktopPluginRevocationListResponse {
  generated_at: string;
  policy_version: string;
  items: DesktopPluginRevocation[];
}

export interface DesktopPluginReviewEvent {
  id: string;
  kind: "submitted" | "withdrawn" | "approved" | "rejected" | "published" | "yanked" | "revoked";
  actor_user_id: string | null;
  note: string | null;
  requested_capabilities: DesktopPluginCapability[];
  approved_capabilities: DesktopPluginCapability[];
  version_number: number;
  created_at: string;
}

export interface DesktopPluginReviewQueueItem {
  version_id: string;
  plugin_id: string;
  plugin_slug: string;
  plugin_name: string;
  owner_user_id: string;
  semver: string;
  status: DesktopPluginVersionStatus;
  requested_capabilities: DesktopPluginCapability[];
  approved_capabilities: DesktopPluginCapability[];
  signing_key_fingerprint: string;
  manifest_sha256: string | null;
  risk_tier: string;
  submitted_at: string | null;
  updated_at: string;
  version: number;
}

export interface DesktopPluginStaticFinding {
  id: string;
  stage: "structure" | "signature" | "sbom" | "vulnerability" | "license" | "secret" | "static_behavior" | "pe_analysis";
  rule_id: string;
  severity: "info" | "low" | "medium" | "high" | "critical";
  title: string;
  detail: string;
  file_path: string | null;
  evidence: Record<string, unknown>;
  blocked: boolean;
  created_at: string;
}

export interface DesktopPluginStaticReviewRun {
  id: string;
  policy_version: string;
  status: "queued" | "running" | "passed" | "failed" | "infrastructure_failed" | "cancelled";
  attempt: number;
  summary: Record<string, unknown>;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  findings: DesktopPluginStaticFinding[];
  dynamic_tasks: DesktopPluginDynamicTask[];
}

export interface DesktopPluginDynamicTask {
  id: string;
  artifact_id: string;
  architecture: DesktopPluginArchitecture;
  status: "queued" | "leased" | "passed" | "blocked" | "infrastructure_failed" | "cancelled";
  runner_id: string | null;
  attempt: number;
  lease_expires_at: string | null;
  evidence_complete: boolean;
  fresh_environment: boolean;
  destruction_proof_sha256: string | null;
  error_code: string | null;
  error_message: string | null;
  result_summary: Record<string, unknown>;
  completed_at: string | null;
  created_at: string;
}

export interface DesktopPluginStaticReviewReport {
  version_id: string;
  version_status: DesktopPluginVersionStatus;
  runs: DesktopPluginStaticReviewRun[];
}

export interface DesktopPluginRunner {
  id: string;
  name: string;
  architecture: DesktopPluginArchitecture;
  certificate_fingerprint: string;
  status: "ready" | "busy" | "offline" | "revoked";
  policy_version: string | null;
  image_digest: string | null;
  probe_version: string | null;
  last_heartbeat_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface DesktopPluginRunnerRegistration extends DesktopPluginRunner {
  runner_secret: string | null;
}

export interface DesktopPluginRunnerListResponse {
  items: DesktopPluginRunner[];
}

export interface DesktopPluginReviewMetrics {
  generated_at: string;
  review_run_counts: Record<string, number>;
  version_status_counts: Record<string, number>;
  dynamic_task_counts: Record<string, number>;
  runner_status_counts: Record<string, number>;
  runner_capacity_by_architecture: Record<string, number>;
  runner_active_by_architecture: Record<string, number>;
  queue_depth_by_architecture: Record<string, number>;
  oldest_queued_seconds: number | null;
  average_review_seconds: number | null;
  p95_review_seconds: number | null;
  completed_last_24_hours: number;
  install_events_last_24_hours: number;
}

export interface DesktopPluginReviewPolicy {
  version: number;
  policy_version: string;
  static_engine_version: string;
  dynamic_engine_version: string;
  static_lease_seconds: number;
  dynamic_lease_seconds: number;
  task_token_seconds: number;
  maximum_static_attempts: number;
  maximum_dynamic_attempts: number;
  runner_offline_seconds: number;
  revocation_refresh_hours: number;
  revocation_max_stale_hours: number;
  dynamic_review_enabled: boolean;
  llm_review_enabled: boolean;
  llm_provider: "disabled" | "openai_compatible" | "anthropic_compatible";
  llm_base_url: string;
  llm_model: string;
  llm_timeout_seconds: number;
  llm_api_key_configured: boolean;
  updated_at: string | null;
  updated_by: string | null;
}

export interface DesktopPluginReviewDetail extends DesktopPluginReviewQueueItem {
  manifest_json: Record<string, unknown> | null;
  release_notes: string;
  source_review_mode: string;
  review_policy_version: string | null;
  platform_key_id: string | null;
  platform_public_key_base64: string | null;
  platform_signature_base64: string | null;
  platform_signature_payload: Record<string, unknown> | null;
  artifacts: DesktopPluginArtifact[];
  events: DesktopPluginReviewEvent[];
  review_runs: DesktopPluginStaticReviewRun[];
  remediation_deadline_at: string | null;
  publication_channels: string[];
}

export interface DesktopPluginMigrationRetry {
  event_id: string;
  plugin_slug: string;
  semver: string;
  architecture: DesktopPluginArchitecture;
  from_version: string;
  package_sha256: string;
  attempt: number;
  available_at: string;
}

export interface DesktopPluginMigrationRetryListResponse {
  items: DesktopPluginMigrationRetry[];
}

export interface DesktopPluginReviewQueueResponse {
  items: DesktopPluginReviewQueueItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface DesktopPluginReport {
  id: string;
  plugin_id: string;
  version_id: string | null;
  reporter_user_id: string;
  category: string;
  description: string;
  status: "open" | "acknowledged" | "resolved" | "dismissed";
  reviewer_user_id: string | null;
  resolution_note: string | null;
  created_at: string;
  updated_at: string;
}

export interface DesktopPluginReportListResponse {
  items: DesktopPluginReport[];
  page: number;
  page_size: number;
  total: number;
}
