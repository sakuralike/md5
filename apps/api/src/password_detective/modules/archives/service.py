from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from password_detective.core.candidate_secrets import CandidateSecretVault
from password_detective.core.config import Settings
from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.archive import Archive
from password_detective.db.models.archive_fingerprint import (
    ArchiveFingerprint,
    FingerprintAlgorithm,
)
from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.password_candidate import CandidateStatus, PasswordCandidate
from password_detective.db.models.points_ledger import PointsLedger, PointsLedgerStatus
from password_detective.db.models.submission import Submission, SubmissionSource
from password_detective.modules.archives.schemas import (
    ArchiveSearchResponse,
    ArchiveSearchResult,
    CandidateSummary,
    FingerprintInput,
    MySubmissionItem,
    MySubmissionsResponse,
    NormalizedFingerprint,
    RevealResponse,
    SubmissionRequest,
    SubmissionResponse,
)
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.verification.service import (
    has_ever_been_verified,
    summarize_feedbacks,
)

_HEX_PATTERN = re.compile(r"^[0-9a-f]+$")
_LENGTH_TO_ALGORITHM = {
    32: FingerprintAlgorithm.MD5,
    40: FingerprintAlgorithm.SHA1,
    64: FingerprintAlgorithm.SHA256,
    128: FingerprintAlgorithm.SHA512,
}
_VISIBLE_STATUSES = {CandidateStatus.PENDING, CandidateStatus.VERIFIED}



def _sortable_timestamp(value: datetime | None) -> float:
    if value is None:
        return float("-inf")
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def normalize_fingerprint(
    digest: str,
    algorithm: FingerprintAlgorithm | str | None = None,
) -> NormalizedFingerprint:
    normalized = digest.strip().lower()
    if not _HEX_PATTERN.fullmatch(normalized):
        raise AppError(
            "archive.invalid_fingerprint",
            "文件指纹必须是完整的十六进制字符串",
            status_code=422,
        )
    detected = _LENGTH_TO_ALGORITHM.get(len(normalized))
    if detected is None:
        raise AppError(
            "archive.invalid_fingerprint_length",
            "文件指纹长度不符合 MD5、SHA-1、SHA-256 或 SHA-512",
            status_code=422,
        )
    if algorithm is not None:
        try:
            supplied = FingerprintAlgorithm(algorithm)
        except ValueError as exc:
            raise AppError(
                "archive.unsupported_fingerprint_algorithm",
                "不支持该文件指纹算法",
                status_code=422,
            ) from exc
        if supplied != detected:
            raise AppError(
                "archive.fingerprint_algorithm_mismatch",
                "文件指纹长度与算法不匹配",
                status_code=422,
            )
    return NormalizedFingerprint(algorithm=detected, digest=normalized)


def normalize_fingerprints(items: list[FingerprintInput]) -> list[NormalizedFingerprint]:
    normalized: list[NormalizedFingerprint] = []
    seen: set[tuple[FingerprintAlgorithm, str]] = set()
    for item in items:
        value = normalize_fingerprint(item.digest, item.algorithm)
        key = (value.algorithm, value.digest)
        if key not in seen:
            normalized.append(value)
            seen.add(key)
    return normalized


def _candidate_summary(candidate: PasswordCandidate, principal: Principal) -> CandidateSummary:
    totals = summarize_feedbacks(list(candidate.feedbacks))
    return CandidateSummary(
        id=candidate.id,
        status=candidate.status,
        confidence_score=candidate.confidence_score,
        submission_count=len(candidate.submissions),
        success_evidence_count=totals.independent_success_count,
        failure_evidence_count=totals.independent_failure_count,
        my_feedback=next(
            (
                feedback.outcome
                for feedback in candidate.feedbacks
                if feedback.user_id == principal.user.id
            ),
            None,
        ),
        last_verified_at=candidate.last_verified_at,
    )


def search_archive(
    db: Session,
    *,
    digest: str,
    algorithm: FingerprintAlgorithm | str | None,
    principal: Principal | None,
) -> ArchiveSearchResponse:
    query = normalize_fingerprint(digest, algorithm)
    fingerprint = db.scalar(
        select(ArchiveFingerprint)
        .where(
            ArchiveFingerprint.algorithm == query.algorithm,
            ArchiveFingerprint.digest == query.digest,
        )
        .options(selectinload(ArchiveFingerprint.archive))
    )
    if fingerprint is None:
        return ArchiveSearchResponse(
            matched=False,
            query=query,
            authenticated=principal is not None,
        )

    archive = db.scalar(
        select(Archive)
        .where(Archive.id == fingerprint.archive_id)
        .options(
            selectinload(Archive.fingerprints),
            selectinload(Archive.candidates).selectinload(PasswordCandidate.submissions),
            selectinload(Archive.candidates).selectinload(PasswordCandidate.feedbacks),
        )
    )
    if archive is None:
        raise AppError("archive.record_unavailable", "档案记录暂时不可用", status_code=500)

    visible = [
        candidate for candidate in archive.candidates if candidate.status in _VISIBLE_STATUSES
    ]
    visible.sort(
        key=lambda item: (
            item.status == CandidateStatus.VERIFIED,
            item.confidence_score,
            _sortable_timestamp(item.last_verified_at),
        ),
        reverse=True,
    )
    if not visible:
        return ArchiveSearchResponse(
            matched=False,
            query=query,
            authenticated=principal is not None,
        )
    counts = Counter(candidate.status.value for candidate in visible)
    candidates = (
        [
            _candidate_summary(candidate, principal)
            for candidate in visible
        ]
        if principal is not None
        else []
    )
    return ArchiveSearchResponse(
        matched=bool(visible),
        query=query,
        authenticated=principal is not None,
        archive=ArchiveSearchResult(
            id=archive.id,
            optional_size=archive.optional_size,
            optional_format=archive.optional_format,
            fingerprints=sorted(
                [
                    NormalizedFingerprint(algorithm=item.algorithm, digest=item.digest)
                    for item in archive.fingerprints
                ],
                key=lambda item: item.algorithm.value,
            ),
            candidate_count=len(visible),
            status_counts=dict(counts),
            candidates=candidates,
        ),
    )


def create_submission(
    db: Session,
    settings: Settings,
    *,
    payload: SubmissionRequest,
    principal: Principal,
    context: ClientContext,
    idempotency_key: str,
) -> SubmissionResponse:
    fingerprints = normalize_fingerprints(payload.fingerprints)
    predicates = [
        and_(
            ArchiveFingerprint.algorithm == item.algorithm,
            ArchiveFingerprint.digest == item.digest,
        )
        for item in fingerprints
    ]
    existing = list(db.scalars(select(ArchiveFingerprint).where(or_(*predicates))))
    archive_ids = {item.archive_id for item in existing}
    if len(archive_ids) > 1:
        raise AppError(
            "archive.fingerprint_conflict",
            "提交的多个指纹已属于不同档案，无法自动合并",
            status_code=409,
        )

    archive_created = not archive_ids
    if archive_created:
        archive = Archive(
            created_by=principal.user.id,
            optional_size=payload.optional_size,
            optional_format=payload.optional_format,
        )
        db.add(archive)
        db.flush()
    else:
        archive = db.get(Archive, next(iter(archive_ids)))
        if archive is None:
            raise AppError("archive.record_unavailable", "档案记录暂时不可用", status_code=500)
        if archive.optional_size is None and payload.optional_size is not None:
            archive.optional_size = payload.optional_size
        if archive.optional_format is None and payload.optional_format:
            archive.optional_format = payload.optional_format

    existing_keys = {(item.algorithm, item.digest) for item in existing}
    for item in fingerprints:
        if (item.algorithm, item.digest) not in existing_keys:
            db.add(
                ArchiveFingerprint(
                    archive_id=archive.id,
                    algorithm=item.algorithm,
                    digest=item.digest,
                )
            )

    vault = CandidateSecretVault(
        settings.app_secret_key,
        key_version=settings.candidate_secret_key_version,
    )
    dedup_tag = vault.dedup_tag(payload.password)
    candidate = db.scalar(
        select(PasswordCandidate).where(
            PasswordCandidate.archive_id == archive.id,
            PasswordCandidate.secret_dedup_tag == dedup_tag,
        )
    )
    candidate_created = candidate is None
    if candidate is None:
        protected = vault.encrypt(payload.password)
        candidate = PasswordCandidate(
            archive_id=archive.id,
            secret_ciphertext=protected.ciphertext,
            secret_nonce=protected.nonce,
            secret_key_version=protected.key_version,
            secret_dedup_tag=protected.dedup_tag,
            status=CandidateStatus.PENDING,
        )
        db.add(candidate)
        db.flush()

    submission = Submission(
        candidate_id=candidate.id,
        user_id=principal.user.id,
        source=SubmissionSource.WEB,
        authorization_version=payload.authorization_version,
        idempotency_key_hash=hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest(),
        ip_prefix=context.ip_prefix,
    )
    db.add(submission)
    db.flush()

    pending_points = settings.submission_pending_points
    if settings.submission_pending_points:
        already_verified = has_ever_been_verified(db, candidate.id)
        db.add(
            PointsLedger(
                user_id=principal.user.id,
                amount=settings.submission_pending_points,
                event_type="submission.pending",
                reference_id=submission.id,
                status=(
                    PointsLedgerStatus.REVERSED
                    if already_verified
                    else PointsLedgerStatus.PENDING
                ),
                settled_at=utc_now() if already_verified else None,
            )
        )
        if already_verified:
            pending_points = 0
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="archive.submission_created",
        target_type="password_candidate",
        target_id=candidate.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "archive_id": archive.id,
            "submission_id": submission.id,
            "fingerprint_algorithms": [item.algorithm.value for item in fingerprints],
            "candidate_created": candidate_created,
            "authorization_version": payload.authorization_version,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            "archive.concurrent_submission_conflict",
            "相同档案正在被并发更新，请重试原请求",
            status_code=409,
        ) from exc
    db.refresh(submission)
    return SubmissionResponse(
        submission_id=submission.id,
        archive_id=archive.id,
        candidate_id=candidate.id,
        candidate_status=candidate.status,
        archive_created=archive_created,
        candidate_created=candidate_created,
        evidence_merged=not candidate_created,
        pending_points=pending_points,
        created_at=submission.created_at,
    )


def reveal_best_candidate(
    db: Session,
    settings: Settings,
    *,
    archive_id: str,
    principal: Principal,
    context: ClientContext,
) -> RevealResponse:
    archive = db.get(Archive, archive_id)
    if archive is None:
        raise AppError("archive.not_found", "未找到档案记录", status_code=404)
    candidate = db.scalar(
        select(PasswordCandidate)
        .where(
            PasswordCandidate.archive_id == archive_id,
            PasswordCandidate.status == CandidateStatus.VERIFIED,
        )
        .order_by(
            desc(PasswordCandidate.confidence_score),
            desc(PasswordCandidate.last_verified_at),
            PasswordCandidate.created_at,
        )
    )
    if candidate is None:
        raise AppError(
            "archive.no_revealable_candidate",
            "当前没有可揭示的已验证候选",
            status_code=409,
        )

    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    used = db.scalar(
        select(func.count(AuditLog.id)).where(
            AuditLog.actor_id == principal.user.id,
            AuditLog.action == "archive.password_revealed",
            AuditLog.created_at >= day_start,
            AuditLog.result == "success",
        )
    ) or 0
    if used >= settings.daily_reveal_quota:
        raise AppError(
            "archive.daily_reveal_quota_exceeded",
            "今日密码揭示配额已用完",
            status_code=429,
            details={"daily_quota": settings.daily_reveal_quota},
        )

    vault = CandidateSecretVault(
        settings.app_secret_key,
        key_version=settings.candidate_secret_key_version,
    )
    password = vault.decrypt(
        ciphertext=candidate.secret_ciphertext,
        nonce=candidate.secret_nonce,
        key_version=candidate.secret_key_version,
    )
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="archive.password_revealed",
        target_type="password_candidate",
        target_id=candidate.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"archive_id": archive_id, "quota_position": used + 1},
    )
    db.commit()
    return RevealResponse(
        archive_id=archive_id,
        candidate_id=candidate.id,
        password=password,
        candidate_status=candidate.status,
        remaining_daily_quota=max(settings.daily_reveal_quota - used - 1, 0),
    )


def list_my_submissions(
    db: Session,
    *,
    principal: Principal,
    page: int,
    page_size: int,
) -> MySubmissionsResponse:
    total = db.scalar(
        select(func.count(Submission.id)).where(Submission.user_id == principal.user.id)
    ) or 0
    submissions = list(
        db.scalars(
            select(Submission)
            .where(Submission.user_id == principal.user.id)
            .options(
                selectinload(Submission.candidate)
                .selectinload(PasswordCandidate.archive)
                .selectinload(Archive.fingerprints)
            )
            .order_by(desc(Submission.created_at), desc(Submission.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return MySubmissionsResponse(
        items=[
            MySubmissionItem(
                id=item.id,
                archive_id=item.candidate.archive_id,
                candidate_id=item.candidate_id,
                candidate_status=item.candidate.status,
                fingerprints=[
                    NormalizedFingerprint(algorithm=fp.algorithm, digest=fp.digest)
                    for fp in sorted(
                        item.candidate.archive.fingerprints,
                        key=lambda fingerprint: fingerprint.algorithm.value,
                    )
                ],
                source=item.source.value,
                authorization_version=item.authorization_version,
                created_at=item.created_at,
            )
            for item in submissions
        ],
        page=page,
        page_size=page_size,
        total=total,
    )
