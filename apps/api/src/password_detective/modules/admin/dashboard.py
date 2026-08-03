from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from password_detective.core.time import utc_now
from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.password_candidate import CandidateStatus, PasswordCandidate
from password_detective.db.models.privacy_request import (
    PrivacyDeletionRequest,
    PrivacyDeletionStatus,
    PrivacyExport,
    PrivacyExportStatus,
)
from password_detective.db.models.risk_alert import RiskAlert, RiskAlertStatus
from password_detective.db.models.submission import Submission
from password_detective.db.models.trust_case import TrustCase, TrustCaseStatus
from password_detective.modules.admin.dashboard_schemas import (
    AdminDashboardSummary,
    AdminQueueBacklog,
)


def _count(db: Session, model: type[object], *conditions: object) -> int:
    statement = select(func.count()).select_from(model)
    if conditions:
        statement = statement.where(*conditions)
    return int(db.scalar(statement) or 0)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def get_dashboard_summary(db: Session, *, window_hours: int) -> AdminDashboardSummary:
    generated_at = utc_now()
    window_started_at = generated_at - timedelta(hours=window_hours)

    search_count = _count(
        db,
        AuditLog,
        AuditLog.action == "archive.search",
        AuditLog.created_at >= window_started_at,
    )
    search_hit_count = _count(
        db,
        AuditLog,
        AuditLog.action == "archive.search",
        AuditLog.target_id.is_not(None),
        AuditLog.created_at >= window_started_at,
    )
    contribution_count = _count(db, Submission, Submission.created_at >= window_started_at)

    candidate_count = _count(db, PasswordCandidate)
    verified_candidate_count = _count(
        db,
        PasswordCandidate,
        PasswordCandidate.status == CandidateStatus.VERIFIED,
    )
    quarantined_candidate_count = _count(
        db,
        PasswordCandidate,
        PasswordCandidate.status == CandidateStatus.QUARANTINED,
    )

    audited_operation_count = _count(
        db,
        AuditLog,
        AuditLog.created_at >= window_started_at,
    )
    audited_error_count = _count(
        db,
        AuditLog,
        AuditLog.created_at >= window_started_at,
        AuditLog.result != "success",
    )

    pending_candidates = _count(
        db,
        PasswordCandidate,
        PasswordCandidate.status == CandidateStatus.PENDING,
    )
    active_trust_cases = _count(
        db,
        TrustCase,
        TrustCase.status.in_([TrustCaseStatus.OPEN, TrustCaseStatus.IN_REVIEW]),
    )
    active_risk_alerts = _count(
        db,
        RiskAlert,
        RiskAlert.status.in_([RiskAlertStatus.OPEN, RiskAlertStatus.ACKNOWLEDGED]),
    )
    pending_privacy_exports = _count(
        db,
        PrivacyExport,
        PrivacyExport.status.in_([PrivacyExportStatus.PENDING, PrivacyExportStatus.PROCESSING]),
    )
    pending_deletion_requests = _count(
        db,
        PrivacyDeletionRequest,
        PrivacyDeletionRequest.status.in_(
            [PrivacyDeletionStatus.PENDING, PrivacyDeletionStatus.PROCESSING]
        ),
    )
    queue_total = (
        pending_candidates
        + active_trust_cases
        + active_risk_alerts
        + pending_privacy_exports
        + pending_deletion_requests
    )

    return AdminDashboardSummary(
        window_hours=window_hours,
        window_started_at=window_started_at,
        generated_at=generated_at,
        search_count=search_count,
        search_hit_count=search_hit_count,
        search_hit_rate=_ratio(search_hit_count, search_count),
        contribution_count=contribution_count,
        candidate_count=candidate_count,
        verified_candidate_count=verified_candidate_count,
        candidate_verification_rate=_ratio(verified_candidate_count, candidate_count),
        quarantined_candidate_count=quarantined_candidate_count,
        audited_operation_count=audited_operation_count,
        audited_error_count=audited_error_count,
        audited_error_rate=_ratio(audited_error_count, audited_operation_count),
        queue_backlog=AdminQueueBacklog(
            pending_candidates=pending_candidates,
            active_trust_cases=active_trust_cases,
            active_risk_alerts=active_risk_alerts,
            pending_privacy_exports=pending_privacy_exports,
            pending_deletion_requests=pending_deletion_requests,
            total=queue_total,
        ),
    )
