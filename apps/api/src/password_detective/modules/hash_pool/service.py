from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from password_detective.db.models.archive import Archive
from password_detective.db.models.archive_fingerprint import (
    ArchiveFingerprint,
    FingerprintAlgorithm,
)
from password_detective.db.models.password_candidate import CandidateStatus, PasswordCandidate
from password_detective.db.models.submission import Submission
from password_detective.db.models.verification import CandidateFeedback
from password_detective.modules.hash_pool.schemas import (
    HashPoolFingerprint,
    HashPoolItem,
    HashPoolListResponse,
    HashPoolOverview,
)


def list_hash_pool(
    db: Session,
    *,
    query: str | None,
    algorithm: FingerprintAlgorithm | None,
    page: int,
    page_size: int,
) -> HashPoolListResponse:
    filters = [PasswordCandidate.status == CandidateStatus.VERIFIED]
    normalized_query = query.strip().lower() if query else None
    if normalized_query:
        pattern = f"%{normalized_query}%"
        matching_archive_ids = select(ArchiveFingerprint.archive_id).where(
            func.lower(ArchiveFingerprint.digest).like(pattern)
        )
        filters.append(
            or_(
                func.lower(PasswordCandidate.id).like(pattern),
                func.lower(PasswordCandidate.archive_id).like(pattern),
                PasswordCandidate.archive_id.in_(matching_archive_ids),
            )
        )
    if algorithm is not None:
        matching_archive_ids = select(ArchiveFingerprint.archive_id).where(
            ArchiveFingerprint.algorithm == algorithm
        )
        filters.append(PasswordCandidate.archive_id.in_(matching_archive_ids))

    total = int(db.scalar(select(func.count(PasswordCandidate.id)).where(*filters)) or 0)
    candidates = list(
        db.scalars(
            select(PasswordCandidate)
            .options(
                selectinload(PasswordCandidate.archive),
                selectinload(PasswordCandidate.archive).selectinload(Archive.fingerprints),
            )
            .where(*filters)
            .order_by(
                PasswordCandidate.last_verified_at.desc(),
                PasswordCandidate.updated_at.desc(),
                PasswordCandidate.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    candidate_ids = [candidate.id for candidate in candidates]
    submission_counts = _counts(db, Submission, candidate_ids)
    feedback_counts = _counts(db, CandidateFeedback, candidate_ids)

    return HashPoolListResponse(
        overview=_overview(db),
        items=[
            HashPoolItem(
                candidate_id=candidate.id,
                archive_id=candidate.archive_id,
                fingerprints=[
                    HashPoolFingerprint(algorithm=item.algorithm, digest=item.digest)
                    for item in sorted(
                        candidate.archive.fingerprints,
                        key=lambda fingerprint: (fingerprint.algorithm.value, fingerprint.digest),
                    )
                ],
                confidence_score=round(candidate.confidence_score, 3),
                submission_count=submission_counts.get(candidate.id, 0),
                feedback_count=feedback_counts.get(candidate.id, 0),
                last_verified_at=candidate.last_verified_at,
                created_at=candidate.created_at,
                updated_at=candidate.updated_at,
            )
            for candidate in candidates
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


def _overview(db: Session) -> HashPoolOverview:
    verified_archive_ids = select(PasswordCandidate.archive_id).where(
        PasswordCandidate.status == CandidateStatus.VERIFIED
    )
    return HashPoolOverview(
        verified_candidates=_candidate_status_count(db, CandidateStatus.VERIFIED),
        unique_archives=int(
            db.scalar(
                select(func.count(func.distinct(PasswordCandidate.archive_id))).where(
                    PasswordCandidate.status == CandidateStatus.VERIFIED
                )
            )
            or 0
        ),
        unique_fingerprints=int(
            db.scalar(
                select(func.count(ArchiveFingerprint.id)).where(
                    ArchiveFingerprint.archive_id.in_(verified_archive_ids)
                )
            )
            or 0
        ),
        pending_candidates=_candidate_status_count(db, CandidateStatus.PENDING),
        quarantined_candidates=_candidate_status_count(db, CandidateStatus.QUARANTINED),
    )


def _candidate_status_count(db: Session, status: CandidateStatus) -> int:
    return int(
        db.scalar(
            select(func.count(PasswordCandidate.id)).where(PasswordCandidate.status == status)
        )
        or 0
    )


def _counts(
    db: Session,
    model: type[Submission] | type[CandidateFeedback],
    candidate_ids: list[str],
) -> dict[str, int]:
    if not candidate_ids:
        return {}
    return {
        candidate_id: int(count)
        for candidate_id, count in db.execute(
            select(model.candidate_id, func.count(model.id))
            .where(model.candidate_id.in_(candidate_ids))
            .group_by(model.candidate_id)
        ).all()
    }
