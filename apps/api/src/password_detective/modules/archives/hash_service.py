from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.models.archive_fingerprint import (
    ArchiveFingerprint,
    FingerprintAlgorithm,
)
from password_detective.db.models.hash_detail import (
    HashComment,
    HashCommentLike,
    HashLike,
    HashVote,
    HashVoteOutcome,
)
from password_detective.db.models.user import User
from password_detective.modules.archives.hash_schemas import (
    HashCommentCreateRequest,
    HashCommentListResponse,
    HashCommentResponse,
    HashDetailResponse,
    HashInteractionResponse,
    HashVoteRequest,
)
from password_detective.modules.archives.service import normalize_fingerprint, search_archive
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.community.schemas import CommunityAuthor


def _get_fingerprint(
    db: Session, *, algorithm: FingerprintAlgorithm | str, digest: str
) -> ArchiveFingerprint:
    query = normalize_fingerprint(digest, algorithm)
    fingerprint = db.scalar(
        select(ArchiveFingerprint).where(
            ArchiveFingerprint.algorithm == query.algorithm,
            ArchiveFingerprint.digest == query.digest,
        )
    )
    if fingerprint is None:
        raise AppError("hash.not_found", "该哈希值尚未建立详情档案", status_code=404)
    return fingerprint


def _vote_counts(db: Session, fingerprint_id: str) -> dict[str, int]:
    rows = db.execute(
        select(HashVote.outcome, func.count(HashVote.id))
        .where(HashVote.fingerprint_id == fingerprint_id)
        .group_by(HashVote.outcome)
    ).all()
    return {outcome.value: count for outcome, count in rows}


def _viewer_vote(
    db: Session, fingerprint_id: str, principal: Principal | None
) -> HashVoteOutcome | None:
    if principal is None:
        return None
    vote = db.scalar(
        select(HashVote).where(
            HashVote.fingerprint_id == fingerprint_id,
            HashVote.user_id == principal.user.id,
        )
    )
    return vote.outcome if vote else None


def _comment_response(
    db: Session, comment: HashComment, *, principal: Principal | None
) -> HashCommentResponse:
    user = db.get(User, comment.author_id)
    if user is None:
        raise AppError("hash.comment_author_unavailable", "评论作者不可用", status_code=500)
    viewer_has_liked = False
    if principal is not None:
        viewer_has_liked = (
            db.scalar(
                select(HashCommentLike.id).where(
                    HashCommentLike.comment_id == comment.id,
                    HashCommentLike.user_id == principal.user.id,
                )
            )
            is not None
        )
    return HashCommentResponse(
        id=comment.id,
        parent_id=comment.parent_id,
        content=comment.content,
        author=CommunityAuthor(user_id=user.id, username=user.username, role=user.role),
        like_count=comment.like_count,
        viewer_has_liked=viewer_has_liked,
        created_at=comment.created_at,
    )


def _encode_comment_cursor(created_at: datetime, comment_id: str) -> str:
    payload = {"created_at": created_at.isoformat(), "id": comment_id}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_comment_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        comment_id = str(payload["id"])
        if not comment_id:
            raise ValueError
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return created_at, comment_id
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError("hash.invalid_cursor", "评论分页游标无效", status_code=422) from exc


def list_hash_comments(
    db: Session,
    *,
    algorithm: FingerprintAlgorithm | str,
    digest: str,
    principal: Principal | None,
    cursor: str | None,
    limit: int,
) -> HashCommentListResponse:
    query = normalize_fingerprint(digest, algorithm)
    fingerprint = db.scalar(
        select(ArchiveFingerprint).where(
            ArchiveFingerprint.algorithm == query.algorithm,
            ArchiveFingerprint.digest == query.digest,
        )
    )
    if fingerprint is None:
        return HashCommentListResponse()

    conditions = [HashComment.fingerprint_id == fingerprint.id]
    if cursor is not None:
        created_at, comment_id = _decode_comment_cursor(cursor)
        conditions.append(
            or_(
                HashComment.created_at < created_at,
                (HashComment.created_at == created_at) & (HashComment.id < comment_id),
            )
        )
    comments = db.scalars(
        select(HashComment)
        .where(*conditions)
        .order_by(HashComment.created_at.desc(), HashComment.id.desc())
        .limit(limit + 1)
    ).all()
    has_more = len(comments) > limit
    items = comments[:limit]
    next_cursor = (
        _encode_comment_cursor(items[-1].created_at, items[-1].id)
        if has_more and items
        else None
    )
    return HashCommentListResponse(
        items=[_comment_response(db, item, principal=principal) for item in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )


def get_hash_detail(
    db: Session,
    *,
    algorithm: FingerprintAlgorithm | str,
    digest: str,
    principal: Principal | None,
    context: ClientContext,
) -> HashDetailResponse:
    query = normalize_fingerprint(digest, algorithm)
    archive_response = search_archive(
        db, digest=query.digest, algorithm=query.algorithm, principal=principal, context=context
    )
    fingerprint = db.scalar(
        select(ArchiveFingerprint).where(
            ArchiveFingerprint.algorithm == query.algorithm,
            ArchiveFingerprint.digest == query.digest,
        )
    )
    if fingerprint is None:
        return HashDetailResponse(
            algorithm=query.algorithm,
            digest=query.digest,
            matched=archive_response.matched,
            archive=archive_response.archive,
            like_count=0,
            viewer_has_liked=False,
            vote_counts={},
            viewer_vote=None,
            comment_count=0,
            comments=[],
            comments_next_cursor=None,
        )
    like_count = (
        db.scalar(select(func.count(HashLike.id)).where(HashLike.fingerprint_id == fingerprint.id))
        or 0
    )
    viewer_has_liked = (
        principal is not None
        and db.scalar(
            select(HashLike.id).where(
                HashLike.fingerprint_id == fingerprint.id,
                HashLike.user_id == principal.user.id,
            )
        )
        is not None
    )
    comment_page = list_hash_comments(
        db,
        algorithm=query.algorithm,
        digest=query.digest,
        principal=principal,
        cursor=None,
        limit=20,
    )
    comment_count = (
        db.scalar(
            select(func.count(HashComment.id)).where(
                HashComment.fingerprint_id == fingerprint.id
            )
        )
        or 0
    )
    return HashDetailResponse(
        algorithm=query.algorithm,
        digest=query.digest,
        matched=archive_response.matched,
        archive=archive_response.archive,
        like_count=like_count,
        viewer_has_liked=viewer_has_liked,
        vote_counts=_vote_counts(db, fingerprint.id),
        viewer_vote=_viewer_vote(db, fingerprint.id, principal),
        comment_count=comment_count,
        comments=comment_page.items,
        comments_next_cursor=comment_page.next_cursor,
    )


def set_hash_like(
    db: Session,
    *,
    algorithm: FingerprintAlgorithm | str,
    digest: str,
    principal: Principal,
    liked: bool,
) -> HashInteractionResponse:
    fingerprint = _get_fingerprint(db, algorithm=algorithm, digest=digest)
    existing = db.scalar(
        select(HashLike).where(
            HashLike.fingerprint_id == fingerprint.id,
            HashLike.user_id == principal.user.id,
        )
    )
    if liked and existing is None:
        db.add(HashLike(fingerprint_id=fingerprint.id, user_id=principal.user.id))
    elif not liked and existing is not None:
        db.delete(existing)
    db.commit()
    return _interaction_response(db, fingerprint, principal)


def set_hash_vote(
    db: Session,
    *,
    algorithm: FingerprintAlgorithm | str,
    digest: str,
    payload: HashVoteRequest,
    principal: Principal,
) -> HashInteractionResponse:
    fingerprint = _get_fingerprint(db, algorithm=algorithm, digest=digest)
    existing = db.scalar(
        select(HashVote).where(
            HashVote.fingerprint_id == fingerprint.id,
            HashVote.user_id == principal.user.id,
        )
    )
    if existing is None:
        db.add(
            HashVote(
                fingerprint_id=fingerprint.id, user_id=principal.user.id, outcome=payload.outcome
            )
        )
    else:
        existing.outcome = payload.outcome
        existing.updated_at = utc_now()
    db.commit()
    return _interaction_response(db, fingerprint, principal)


def create_hash_comment(
    db: Session,
    *,
    algorithm: FingerprintAlgorithm | str,
    digest: str,
    payload: HashCommentCreateRequest,
    principal: Principal,
    context: ClientContext,
) -> HashDetailResponse:
    if not payload.rules_accepted:
        raise AppError("community.rules_required", "请先确认遵守社区规则", status_code=422)
    fingerprint = _get_fingerprint(db, algorithm=algorithm, digest=digest)
    parent = None
    if payload.parent_id:
        parent = db.scalar(
            select(HashComment).where(
                HashComment.id == payload.parent_id,
                HashComment.fingerprint_id == fingerprint.id,
            )
        )
        if parent is None:
            raise AppError("hash.comment_parent_not_found", "被回复的评论不存在", status_code=404)
    db.add(
        HashComment(
            fingerprint_id=fingerprint.id,
            author_id=principal.user.id,
            parent_id=parent.id if parent else None,
            content=payload.content,
        )
    )
    db.commit()
    return get_hash_detail(
        db,
        algorithm=algorithm,
        digest=digest,
        principal=principal,
        context=context,
    )


def _interaction_response(
    db: Session, fingerprint: ArchiveFingerprint, principal: Principal
) -> HashInteractionResponse:
    like_count = (
        db.scalar(select(func.count(HashLike.id)).where(HashLike.fingerprint_id == fingerprint.id))
        or 0
    )
    return HashInteractionResponse(
        algorithm=fingerprint.algorithm,
        digest=fingerprint.digest,
        like_count=like_count,
        viewer_has_liked=db.scalar(
            select(HashLike.id).where(
                HashLike.fingerprint_id == fingerprint.id,
                HashLike.user_id == principal.user.id,
            )
        )
        is not None,
        vote_counts=_vote_counts(db, fingerprint.id),
        viewer_vote=_viewer_vote(db, fingerprint.id, principal),
    )


def set_hash_comment_like(
    db: Session,
    *,
    algorithm: FingerprintAlgorithm | str,
    digest: str,
    comment_id: str,
    principal: Principal,
    liked: bool,
) -> HashDetailResponse:
    fingerprint = _get_fingerprint(db, algorithm=algorithm, digest=digest)
    comment = db.scalar(
        select(HashComment).where(
            HashComment.id == comment_id,
            HashComment.fingerprint_id == fingerprint.id,
        )
    )
    if comment is None:
        raise AppError("hash.comment_not_found", "评论不存在", status_code=404)
    existing = db.scalar(
        select(HashCommentLike).where(
            HashCommentLike.comment_id == comment.id,
            HashCommentLike.user_id == principal.user.id,
        )
    )
    if liked and existing is None:
        db.add(HashCommentLike(comment_id=comment.id, user_id=principal.user.id))
        comment.like_count += 1
    elif not liked and existing is not None:
        db.delete(existing)
        comment.like_count = max(0, comment.like_count - 1)
    db.commit()
    return get_hash_detail(
        db,
        algorithm=algorithm,
        digest=digest,
        principal=principal,
        context=ClientContext(request_id=None, ip_prefix=None, user_agent=None),
    )
