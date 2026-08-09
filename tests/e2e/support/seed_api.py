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
from password_detective.core.security import encrypt_secret, hash_account_password
from password_detective.core.time import utc_now
from password_detective.db.database import Database
from password_detective.db.models.archive import Archive
from password_detective.db.models.archive_fingerprint import (
    ArchiveFingerprint,
    FingerprintAlgorithm,
)
from password_detective.db.models.password_candidate import (
    CandidateStatus,
    PasswordCandidate,
)
from password_detective.db.models.trust_case import (
    TrustCase,
    TrustCaseKind,
    TrustCaseStatus,
    TrustCaseSubjectType,
)
from password_detective.db.models.user import User, UserRole, UserStatus
from password_detective.db.models.user_session import UserSession


def ensure_user(
    db: Session,
    *,
    username: str,
    email: str,
    password: str,
) -> User:
    existing = db.scalar(select(User).where(User.username == username))
    if existing is not None:
        return existing

    user = User(
        username=username,
        email=email,
        email_verified_at=utc_now(),
        account_password_hash=hash_account_password(password),
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    return user


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
    verified_sha256 = os.environ["E2E_VERIFIED_SHA256"]
    verified_md5 = os.environ["E2E_VERIFIED_MD5"]
    verified_password = os.environ["E2E_VERIFIED_PASSWORD"]
    verified_candidate_id = os.environ["E2E_VERIFIED_CANDIDATE_ID"]
    pending_candidate_id = os.environ["E2E_ADMIN_PENDING_CANDIDATE_ID"]
    pending_sha256 = os.environ["E2E_ADMIN_PENDING_SHA256"]
    case_candidate_id = os.environ["E2E_ADMIN_CASE_CANDIDATE_ID"]
    case_sha256 = os.environ["E2E_ADMIN_CASE_SHA256"]
    case_id = os.environ["E2E_ADMIN_CASE_ID"]
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
        ensure_user(
            db,
            username=privacy_username,
            email=privacy_email,
            password=privacy_password,
        )
        db.flush()
        for family_id, refresh_hash, user_agent in (
            (security_session_id, "1" * 64, "Synthetic security device A"),
            (security_second_session_id, "2" * 64, "Synthetic security device B"),
        ):
            if db.scalar(select(UserSession).where(UserSession.family_id == family_id)) is None:
                now = utc_now()
                db.add(
                    UserSession(
                        user_id=security_user.id,
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
