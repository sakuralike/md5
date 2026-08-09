from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from password_detective.core.candidate_secrets import CandidateSecretVault
from password_detective.core.config import Settings
from password_detective.core.ids import new_id
from password_detective.core.security import (
    encrypt_secret,
    hash_account_password,
    hash_opaque_token,
    hash_refresh_token,
)
from password_detective.core.time import utc_now
from password_detective.db.database import Database
from password_detective.db.models.account_action_token import (
    AccountActionToken,
    AccountTokenKind,
)
from password_detective.db.models.archive import Archive
from password_detective.db.models.archive_fingerprint import (
    ArchiveFingerprint,
    FingerprintAlgorithm,
)
from password_detective.db.models.password_candidate import (
    CandidateStatus,
    PasswordCandidate,
)
from password_detective.db.models.risk_alert import (
    RiskAlert,
    RiskAlertEvent,
    RiskAlertKind,
    RiskAlertSeverity,
    RiskAlertStatus,
)
from password_detective.db.models.trust_case import (
    TrustCase,
    TrustCaseKind,
    TrustCaseStatus,
    TrustCaseSubjectType,
)
from password_detective.db.models.user import User, UserRole, UserStatus
from password_detective.db.models.user_session import UserSession
from password_detective.db.models.verification import (
    CandidateFeedback,
    FeedbackOutcome,
    VerificationEvidenceEvent,
    VerificationSource,
)


def ensure_user(
    db: Session,
    *,
    username: str,
    email: str,
    password: str,
    user_id: str | None = None,
    role: UserRole = UserRole.USER,
    totp_secret: str | None = None,
    app_secret_key: str | None = None,
    email_verified: bool = True,
) -> User:
    existing = db.scalar(select(User).where(User.username == username))
    if existing is not None:
        return existing

    user = User(
        username=username,
        email=email,
        email_verified_at=utc_now() if email_verified else None,
        account_password_hash=hash_account_password(password),
        role=role,
        status=UserStatus.ACTIVE,
    )
    if user_id is not None:
        user.id = user_id
    if totp_secret is not None:
        if app_secret_key is None:
            raise ValueError("TOTP seed requires app_secret_key")
        user.totp_secret_ciphertext = encrypt_secret(totp_secret, app_secret_key)
        user.totp_enabled_at = utc_now()
    db.add(user)
    return user


def ensure_email_verification_token(
    db: Session,
    *,
    token_id: str,
    user_id: str,
    raw_token: str,
) -> AccountActionToken:
    existing = db.get(AccountActionToken, token_id)
    if existing is not None:
        return existing

    token = AccountActionToken(
        id=token_id,
        user_id=user_id,
        kind=AccountTokenKind.EMAIL_VERIFICATION,
        token_hash=hash_opaque_token(raw_token),
        expires_at=utc_now() + timedelta(hours=1),
    )
    db.add(token)
    return token


def ensure_refresh_session(
    db: Session,
    *,
    user_id: str,
    family_id: str,
    raw_token: str,
    user_agent: str,
    expires_in: timedelta = timedelta(days=7),
    mfa_verified: bool = False,
) -> UserSession:
    existing_sessions = list(
        db.scalars(select(UserSession).where(UserSession.family_id == family_id)).all()
    )
    if existing_sessions:
        for existing in existing_sessions:
            existing.rotated_from_id = None
        db.flush()
        for existing in existing_sessions:
            db.delete(existing)
        db.flush()

    now = utc_now()
    session = UserSession(
        user_id=user_id,
        family_id=family_id,
        refresh_token_hash=hash_refresh_token(raw_token),
        user_agent=user_agent,
        ip_prefix="127.0.0.0/24",
        expires_at=now + expires_in,
        created_at=now,
        last_used_at=now,
        mfa_verified_at=now if mfa_verified else None,
    )
    db.add(session)
    return session


def ensure_candidate(
    db: Session,
    *,
    vault: CandidateSecretVault,
    owner_id: str,
    candidate_id: str,
    sha256: str,
    password: str,
    status: CandidateStatus,
    md5: str | None = None,
) -> PasswordCandidate:
    existing = db.get(PasswordCandidate, candidate_id)
    if existing is not None:
        return existing

    archive = Archive(
        id=new_id(),
        created_by=owner_id,
        optional_size=4096,
        optional_format="zip",
    )
    encrypted = vault.encrypt(password)
    candidate = PasswordCandidate(
        id=candidate_id,
        archive_id=archive.id,
        secret_ciphertext=encrypted.ciphertext,
        secret_nonce=encrypted.nonce,
        secret_key_version=encrypted.key_version,
        secret_dedup_tag=encrypted.dedup_tag,
        status=status,
        confidence_score=0.95 if status == CandidateStatus.VERIFIED else 0.25,
        last_verified_at=utc_now() if status == CandidateStatus.VERIFIED else None,
    )
    fingerprints = [
        ArchiveFingerprint(
            archive_id=archive.id,
            algorithm=FingerprintAlgorithm.SHA256,
            digest=sha256,
        )
    ]
    if md5:
        fingerprints.append(
            ArchiveFingerprint(
                archive_id=archive.id,
                algorithm=FingerprintAlgorithm.MD5,
                digest=md5,
            )
        )
    db.add(archive)
    db.add_all([*fingerprints, candidate])
    return candidate


def ensure_risk_alert(
    db: Session,
    *,
    owner_id: str,
    candidate_id: str,
    feedback_id: str,
    evidence_id: str,
    alert_id: str,
) -> None:
    if db.get(RiskAlert, alert_id) is not None:
        return

    now = utc_now()
    if db.get(CandidateFeedback, feedback_id) is None:
        db.add(
            CandidateFeedback(
                id=feedback_id,
                candidate_id=candidate_id,
                user_id=owner_id,
                outcome=FeedbackOutcome.FAILURE,
                source=VerificationSource.WEB_FEEDBACK,
                weight=3.0,
                rule_version="risk-alert-v1",
                revision=1,
                created_at=now,
                updated_at=now,
            )
        )
    if db.get(VerificationEvidenceEvent, evidence_id) is None:
        db.add(
            VerificationEvidenceEvent(
                id=evidence_id,
                feedback_id=feedback_id,
                candidate_id=candidate_id,
                user_id=owner_id,
                previous_outcome=None,
                outcome=FeedbackOutcome.FAILURE,
                source=VerificationSource.WEB_FEEDBACK,
                weight=3.0,
                rule_version="risk-alert-v1",
                revision=1,
                created_at=now,
            )
        )
    db.add(
        RiskAlert(
            id=alert_id,
            candidate_id=candidate_id,
            trigger_evidence_id=evidence_id,
            kind=RiskAlertKind.FAILURE_SURGE,
            severity=RiskAlertSeverity.HIGH,
            status=RiskAlertStatus.OPEN,
            rule_version="risk-alert-v1",
            sla_rule_version="risk-alert-sla-v1",
            window_started_at=now - timedelta(minutes=10),
            window_ended_at=now,
            acknowledge_due_at=now + timedelta(minutes=15),
            resolve_due_at=now + timedelta(hours=2),
            independent_failure_count=3,
            failure_weight=3.0,
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        RiskAlertEvent(
            alert_id=alert_id,
            actor_id=None,
            previous_status=None,
            next_status=RiskAlertStatus.OPEN,
            previous_assignee_id=None,
            next_assignee_id=None,
            action="risk_alert.detected",
            reason_code="detection.failure_surge",
            note=None,
            request_id=None,
            created_at=now,
        )
    )


def main() -> None:
    settings = Settings()
    database = Database(settings)
    database.create_tables()
    admin_username = os.environ["E2E_ADMIN_USERNAME"]
    admin_password = os.environ["E2E_ADMIN_PASSWORD"]
    admin_email = os.environ["E2E_ADMIN_EMAIL"]
    workflow_admin_id = os.environ["E2E_ADMIN_WORKFLOW_ID"]
    workflow_admin_username = os.environ["E2E_ADMIN_WORKFLOW_USERNAME"]
    workflow_admin_password = os.environ["E2E_ADMIN_WORKFLOW_PASSWORD"]
    workflow_admin_email = os.environ["E2E_ADMIN_WORKFLOW_EMAIL"]
    workflow_admin_totp_secret = os.environ["E2E_ADMIN_WORKFLOW_TOTP_SECRET"]
    reviewer_id = os.environ["E2E_ADMIN_REVIEWER_ID"]
    reviewer_username = os.environ["E2E_ADMIN_REVIEWER_USERNAME"]
    reviewer_password = os.environ["E2E_ADMIN_REVIEWER_PASSWORD"]
    reviewer_email = os.environ["E2E_ADMIN_REVIEWER_EMAIL"]
    reviewer_totp_secret = os.environ["E2E_ADMIN_REVIEWER_TOTP_SECRET"]
    governance_user_id = os.environ["E2E_ADMIN_GOVERNANCE_USER_ID"]
    governance_username = os.environ["E2E_ADMIN_GOVERNANCE_USERNAME"]
    governance_email = os.environ["E2E_ADMIN_GOVERNANCE_EMAIL"]
    governance_password = os.environ["E2E_ADMIN_GOVERNANCE_PASSWORD"]
    governance_session_id = os.environ["E2E_ADMIN_GOVERNANCE_SESSION_ID"]
    role_target_id = os.environ["E2E_ADMIN_ROLE_TARGET_ID"]
    role_target_username = os.environ["E2E_ADMIN_ROLE_TARGET_USERNAME"]
    role_target_email = os.environ["E2E_ADMIN_ROLE_TARGET_EMAIL"]
    role_target_password = os.environ["E2E_ADMIN_ROLE_TARGET_PASSWORD"]
    role_target_session_id = os.environ["E2E_ADMIN_ROLE_TARGET_SESSION_ID"]
    web_username = os.environ["E2E_WEB_USERNAME"]
    web_password = os.environ["E2E_WEB_PASSWORD"]
    web_email = os.environ["E2E_WEB_EMAIL"]
    security_username = os.environ["E2E_WEB_SECURITY_USERNAME"]
    security_email = os.environ["E2E_WEB_SECURITY_EMAIL"]
    security_password = os.environ["E2E_WEB_SECURITY_PASSWORD"]
    security_session_id = os.environ["E2E_WEB_SECURITY_SESSION_ID"]
    security_second_session_id = os.environ["E2E_WEB_SECURITY_SECOND_SESSION_ID"]
    totp_username = os.environ["E2E_WEB_TOTP_USERNAME"]
    totp_email = os.environ["E2E_WEB_TOTP_EMAIL"]
    totp_password = os.environ["E2E_WEB_TOTP_PASSWORD"]
    privacy_username = os.environ["E2E_WEB_PRIVACY_USERNAME"]
    privacy_email = os.environ["E2E_WEB_PRIVACY_EMAIL"]
    privacy_password = os.environ["E2E_WEB_PRIVACY_PASSWORD"]
    accessibility_security_username = os.environ["E2E_WEB_ACCESSIBILITY_SECURITY_USERNAME"]
    accessibility_security_email = os.environ["E2E_WEB_ACCESSIBILITY_SECURITY_EMAIL"]
    accessibility_security_password = os.environ["E2E_WEB_ACCESSIBILITY_SECURITY_PASSWORD"]
    accessibility_privacy_username = os.environ["E2E_WEB_ACCESSIBILITY_PRIVACY_USERNAME"]
    accessibility_privacy_email = os.environ["E2E_WEB_ACCESSIBILITY_PRIVACY_EMAIL"]
    accessibility_privacy_password = os.environ["E2E_WEB_ACCESSIBILITY_PRIVACY_PASSWORD"]
    email_verify_user_id = os.environ["E2E_WEB_EMAIL_VERIFY_USER_ID"]
    email_verify_username = os.environ["E2E_WEB_EMAIL_VERIFY_USERNAME"]
    email_verify_email = os.environ["E2E_WEB_EMAIL_VERIFY_EMAIL"]
    email_verify_password = os.environ["E2E_WEB_EMAIL_VERIFY_PASSWORD"]
    email_verify_token_id = os.environ["E2E_WEB_EMAIL_VERIFY_TOKEN_ID"]
    email_verify_token = os.environ["E2E_WEB_EMAIL_VERIFY_TOKEN"]
    email_verify_refresh_family_id = os.environ["E2E_WEB_EMAIL_VERIFY_REFRESH_FAMILY_ID"]
    email_verify_refresh_token = os.environ["E2E_WEB_EMAIL_VERIFY_REFRESH_TOKEN"]
    web_refresh_family_id = os.environ["E2E_WEB_REFRESH_FAMILY_ID"]
    web_refresh_token = os.environ["E2E_WEB_REFRESH_TOKEN"]
    web_expired_refresh_family_id = os.environ["E2E_WEB_EXPIRED_REFRESH_FAMILY_ID"]
    web_expired_refresh_token = os.environ["E2E_WEB_EXPIRED_REFRESH_TOKEN"]
    web_concurrent_refresh_family_id = os.environ["E2E_WEB_CONCURRENT_REFRESH_FAMILY_ID"]
    web_concurrent_refresh_token = os.environ["E2E_WEB_CONCURRENT_REFRESH_TOKEN"]
    web_accessibility_security_refresh_family_id = os.environ[
        "E2E_WEB_ACCESSIBILITY_SECURITY_REFRESH_FAMILY_ID"
    ]
    web_accessibility_security_refresh_token = os.environ[
        "E2E_WEB_ACCESSIBILITY_SECURITY_REFRESH_TOKEN"
    ]
    web_accessibility_privacy_refresh_family_id = os.environ[
        "E2E_WEB_ACCESSIBILITY_PRIVACY_REFRESH_FAMILY_ID"
    ]
    web_accessibility_privacy_refresh_token = os.environ[
        "E2E_WEB_ACCESSIBILITY_PRIVACY_REFRESH_TOKEN"
    ]
    admin_accessibility_refresh_family_id = os.environ[
        "E2E_ADMIN_ACCESSIBILITY_REFRESH_FAMILY_ID"
    ]
    admin_accessibility_refresh_token = os.environ[
        "E2E_ADMIN_ACCESSIBILITY_REFRESH_TOKEN"
    ]
    verified_sha256 = os.environ["E2E_VERIFIED_SHA256"]
    verified_md5 = os.environ["E2E_VERIFIED_MD5"]
    verified_password = os.environ["E2E_VERIFIED_PASSWORD"]
    verified_candidate_id = os.environ["E2E_VERIFIED_CANDIDATE_ID"]
    pending_candidate_id = os.environ["E2E_ADMIN_PENDING_CANDIDATE_ID"]
    pending_sha256 = os.environ["E2E_ADMIN_PENDING_SHA256"]
    case_candidate_id = os.environ["E2E_ADMIN_CASE_CANDIDATE_ID"]
    case_sha256 = os.environ["E2E_ADMIN_CASE_SHA256"]
    case_id = os.environ["E2E_ADMIN_CASE_ID"]
    risk_candidate_id = os.environ["E2E_ADMIN_RISK_CANDIDATE_ID"]
    risk_sha256 = os.environ["E2E_ADMIN_RISK_SHA256"]
    risk_feedback_id = os.environ["E2E_ADMIN_RISK_FEEDBACK_ID"]
    risk_evidence_id = os.environ["E2E_ADMIN_RISK_EVIDENCE_ID"]
    risk_alert_id = os.environ["E2E_ADMIN_RISK_ALERT_ID"]
    vault = CandidateSecretVault(settings.app_secret_key)

    with database.session_factory() as db:
        admin = db.scalar(select(User).where(User.username == admin_username))
        if admin is None:
            admin = User(
                username=admin_username,
                email=admin_email,
                email_verified_at=utc_now(),
                account_password_hash=hash_account_password(admin_password),
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
            )
            db.add(admin)

        workflow_admin = db.get(User, workflow_admin_id)
        if workflow_admin is None:
            workflow_admin = User(
                id=workflow_admin_id,
                username=workflow_admin_username,
                email=workflow_admin_email,
                email_verified_at=utc_now(),
                account_password_hash=hash_account_password(workflow_admin_password),
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
                totp_secret_ciphertext=encrypt_secret(
                    workflow_admin_totp_secret,
                    settings.app_secret_key,
                ),
                totp_enabled_at=utc_now(),
            )
            db.add(workflow_admin)

        web_user = ensure_user(
            db,
            username=web_username,
            email=web_email,
            password=web_password,
        )
        ensure_user(
            db,
            user_id=reviewer_id,
            username=reviewer_username,
            email=reviewer_email,
            password=reviewer_password,
            role=UserRole.ADMIN,
            totp_secret=reviewer_totp_secret,
            app_secret_key=settings.app_secret_key,
        )
        governance_user = ensure_user(
            db,
            user_id=governance_user_id,
            username=governance_username,
            email=governance_email,
            password=governance_password,
        )
        role_target = ensure_user(
            db,
            user_id=role_target_id,
            username=role_target_username,
            email=role_target_email,
            password=role_target_password,
        )
        security_user = ensure_user(
            db,
            username=security_username,
            email=security_email,
            password=security_password,
        )
        ensure_user(
            db,
            username=totp_username,
            email=totp_email,
            password=totp_password,
        )
        privacy_user = ensure_user(
            db,
            username=privacy_username,
            email=privacy_email,
            password=privacy_password,
        )
        accessibility_security_user = ensure_user(
            db,
            username=accessibility_security_username,
            email=accessibility_security_email,
            password=accessibility_security_password,
        )
        accessibility_privacy_user = ensure_user(
            db,
            username=accessibility_privacy_username,
            email=accessibility_privacy_email,
            password=accessibility_privacy_password,
        )
        email_verify_user = ensure_user(
            db,
            user_id=email_verify_user_id,
            username=email_verify_username,
            email=email_verify_email,
            password=email_verify_password,
            email_verified=False,
        )
        db.flush()
        ensure_email_verification_token(
            db,
            token_id=email_verify_token_id,
            user_id=email_verify_user.id,
            raw_token=email_verify_token,
        )
        ensure_refresh_session(
            db,
            user_id=email_verify_user.id,
            family_id=email_verify_refresh_family_id,
            raw_token=email_verify_refresh_token,
            user_agent="Synthetic email verification browser",
        )
        ensure_refresh_session(
            db,
            user_id=web_user.id,
            family_id=web_refresh_family_id,
            raw_token=web_refresh_token,
            user_agent="Synthetic refresh replay browser",
        )
        ensure_refresh_session(
            db,
            user_id=web_user.id,
            family_id=web_expired_refresh_family_id,
            raw_token=web_expired_refresh_token,
            user_agent="Synthetic expired refresh browser",
            expires_in=timedelta(minutes=-5),
        )
        ensure_refresh_session(
            db,
            user_id=web_user.id,
            family_id=web_concurrent_refresh_family_id,
            raw_token=web_concurrent_refresh_token,
            user_agent="Synthetic concurrent refresh browser",
        )
        ensure_refresh_session(
            db,
            user_id=accessibility_security_user.id,
            family_id=web_accessibility_security_refresh_family_id,
            raw_token=web_accessibility_security_refresh_token,
            user_agent="Synthetic security accessibility browser",
        )
        ensure_refresh_session(
            db,
            user_id=accessibility_privacy_user.id,
            family_id=web_accessibility_privacy_refresh_family_id,
            raw_token=web_accessibility_privacy_refresh_token,
            user_agent="Synthetic privacy accessibility browser",
        )
        ensure_refresh_session(
            db,
            user_id=workflow_admin.id,
            family_id=admin_accessibility_refresh_family_id,
            raw_token=admin_accessibility_refresh_token,
            user_agent="Synthetic admin accessibility browser",
            mfa_verified=True,
        )
        db.flush()
        for user, family_id, refresh_hash, user_agent in (
            (security_user, security_session_id, "1" * 64, "Synthetic security device A"),
            (security_user, security_second_session_id, "2" * 64, "Synthetic security device B"),
            (governance_user, governance_session_id, "3" * 64, "Synthetic governance device"),
            (role_target, role_target_session_id, "4" * 64, "Synthetic role target device"),
        ):
            if db.scalar(select(UserSession).where(UserSession.family_id == family_id)) is None:
                now = utc_now()
                db.add(
                    UserSession(
                        user_id=user.id,
                        family_id=family_id,
                        refresh_token_hash=refresh_hash,
                        user_agent=user_agent,
                        ip_prefix="127.0.0.0/24",
                        expires_at=now + timedelta(days=7),
                        created_at=now,
                        last_used_at=now,
                    )
                )

        ensure_candidate(
            db,
            vault=vault,
            owner_id=web_user.id,
            candidate_id=verified_candidate_id,
            sha256=verified_sha256,
            md5=verified_md5,
            password=verified_password,
            status=CandidateStatus.VERIFIED,
        )
        ensure_candidate(
            db,
            vault=vault,
            owner_id=web_user.id,
            candidate_id=pending_candidate_id,
            sha256=pending_sha256,
            password="Synthetic-Pending-Candidate-2026!",
            status=CandidateStatus.PENDING,
        )
        case_candidate = ensure_candidate(
            db,
            vault=vault,
            owner_id=web_user.id,
            candidate_id=case_candidate_id,
            sha256=case_sha256,
            password="Synthetic-Reported-Candidate-2026!",
            status=CandidateStatus.VERIFIED,
        )
        risk_candidate = ensure_candidate(
            db,
            vault=vault,
            owner_id=web_user.id,
            candidate_id=risk_candidate_id,
            sha256=risk_sha256,
            password="Synthetic-Risk-Candidate-2026!",
            status=CandidateStatus.QUARANTINED,
        )
        ensure_risk_alert(
            db,
            owner_id=web_user.id,
            candidate_id=risk_candidate.id,
            feedback_id=risk_feedback_id,
            evidence_id=risk_evidence_id,
            alert_id=risk_alert_id,
        )
        if db.get(TrustCase, case_id) is None:
            db.add(
                TrustCase(
                    id=case_id,
                    kind=TrustCaseKind.REPORT,
                    subject_type=TrustCaseSubjectType.CANDIDATE,
                    status=TrustCaseStatus.OPEN,
                    reporter_id=web_user.id,
                    candidate_id=case_candidate.id,
                    reason_code="report.policy_violation",
                    requested_action="candidate.review",
                    description="合成测试：候选内容需要管理员复核。",
                    evidence_summary="合成测试证据摘要，不包含密码、令牌或个人信息。",
                    sla_due_at=utc_now() + timedelta(hours=24),
                )
            )
        db.commit()
    database.dispose()


if __name__ == "__main__":
    main()
