from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from password_detective.core.time import utc_now
from password_detective.db.models.community import (
    CommunityBoard,
    CommunityBoardStatus,
    CommunityContentStatus,
    CommunityGroup,
    CommunityGroupStatus,
    CommunityGroupVisibility,
    CommunityPost,
    CommunityPublicProfile,
    CommunitySearchDocument,
    CommunitySearchOutbox,
    CommunitySearchOutboxStatus,
    CommunitySearchRebuildRun,
    CommunitySearchRebuildStatus,
    CommunitySearchSource,
)
from password_detective.db.models.user import User, UserStatus

SearchOperation = Literal["upsert", "delete"]
_RETRY_DELAY = timedelta(seconds=30)


@dataclass(frozen=True)
class SearchDispatchResult:
    delivered: int = 0
    failed: int = 0
    retried: int = 0

    def as_dict(self) -> dict[str, int]:
        return {"delivered": self.delivered, "failed": self.failed, "retried": self.retried}


@dataclass(frozen=True)
class SearchRebuildResult:
    operation: str
    scanned: int
    upserted: int
    deleted: int
    mismatch_count: int
    run_id: str | None = None
    resume_cursor: str | None = None

    def as_dict(self) -> dict[str, int | str | None]:
        return {
            "operation": self.operation,
            "scanned": self.scanned,
            "upserted": self.upserted,
            "deleted": self.deleted,
            "mismatch_count": self.mismatch_count,
            "run_id": self.run_id,
            "resume_cursor": self.resume_cursor,
        }


@dataclass(frozen=True)
class _DocumentPayload:
    title: str
    body: str
    username: str | None
    board_code: str | None
    group_slug: str | None
    author_id: str | None
    source_updated_at: object


def enqueue_search_event(
    db: Session,
    *,
    source_type: CommunitySearchSource,
    source_id: str,
    document_version: int,
    operation: SearchOperation = "upsert",
) -> CommunitySearchOutbox:
    dedupe_key = f"community-search:{source_type.value}:{source_id}:v{document_version}:{operation}"
    existing = db.scalar(
        select(CommunitySearchOutbox).where(CommunitySearchOutbox.dedupe_key == dedupe_key)
    )
    if existing is not None:
        return existing
    event = CommunitySearchOutbox(
        event_type=operation,
        source_type=source_type,
        source_id=source_id,
        document_version=document_version,
        dedupe_key=dedupe_key,
        status=CommunitySearchOutboxStatus.PENDING,
        attempts=0,
        available_at=utc_now(),
    )
    db.add(event)
    return event


def dispatch_pending_search_events(db: Session, *, limit: int = 100) -> SearchDispatchResult:
    now = utc_now()
    events = db.scalars(
        select(CommunitySearchOutbox)
        .where(
            CommunitySearchOutbox.available_at <= now,
            CommunitySearchOutbox.status.in_(
                (CommunitySearchOutboxStatus.PENDING, CommunitySearchOutboxStatus.FAILED)
            ),
        )
        .order_by(
            CommunitySearchOutbox.available_at,
            CommunitySearchOutbox.created_at,
            CommunitySearchOutbox.id,
        )
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    delivered = 0
    failed = 0
    retried = 0
    for event in events:
        event.attempts += 1
        was_retry = event.status is CommunitySearchOutboxStatus.FAILED
        try:
            _apply_search_event(db, event)
        except Exception as exc:  # noqa: BLE001 - persisted events must survive individual failures.
            event.status = CommunitySearchOutboxStatus.FAILED
            event.failed_at = now
            event.available_at = now + _RETRY_DELAY
            event.last_error_code = type(exc).__name__[:128]
            failed += 1
            continue
        event.status = CommunitySearchOutboxStatus.DELIVERED
        event.delivered_at = now
        event.failed_at = None
        event.last_error_code = None
        delivered += 1
        if was_retry:
            retried += 1
    db.commit()
    return SearchDispatchResult(delivered=delivered, failed=failed, retried=retried)


def rebuild_search_index(
    db: Session,
    *,
    apply: bool,
    batch_size: int = 200,
    resume_run_id: str | None = None,
    max_batches: int | None = None,
) -> SearchRebuildResult:
    if batch_size < 1 or batch_size > 1_000:
        raise ValueError("batch_size must be between 1 and 1000")
    if max_batches is not None and max_batches < 1:
        raise ValueError("max_batches must be positive when provided")

    operation = "apply" if apply else "dry-run"
    run = _load_rebuild_run(db, operation=operation, resume_run_id=resume_run_id)
    source_keys = _all_source_keys(db)
    resume_after = _parse_rebuild_cursor(run.cursor)
    pending_keys = [
        key for key in source_keys if resume_after is None or _source_key_value(key) > resume_after
    ]
    scanned = 0
    upserted = 0
    processed_batches = 0

    try:
        for offset in range(0, len(pending_keys), batch_size):
            if max_batches is not None and processed_batches >= max_batches:
                break
            batch = pending_keys[offset : offset + batch_size]
            for source_type, source_id in batch:
                scanned += 1
                payload = _build_document_payload(
                    db,
                    source_type=source_type,
                    source_id=source_id,
                )
                if payload is None:
                    continue
                upserted += 1
                if apply:
                    _upsert_document(
                        db,
                        source_type=source_type,
                        source_id=source_id,
                        document_version=_source_version(db, source_type, source_id),
                        payload=payload,
                    )
            run.cursor = _serialize_rebuild_cursor(batch[-1])
            run.status = CommunitySearchRebuildStatus.RUNNING
            run.error_summary = None
            db.flush()
            processed_batches += 1

        completed = processed_batches * batch_size >= len(pending_keys)
        if not completed:
            db.commit()
            return SearchRebuildResult(
                operation=operation,
                scanned=scanned,
                upserted=upserted,
                deleted=0,
                mismatch_count=0,
                run_id=run.id,
                resume_cursor=run.cursor,
            )

        expected = _expected_documents(db)
        missing_count, extra_documents, stale_count, indexed_count = _projection_drift(
            db,
            expected,
        )
        deleted = 0
        if apply:
            for document in extra_documents:
                db.delete(document)
            deleted = len(extra_documents)
            db.flush()
            missing_count, _remaining_extra, stale_count, indexed_count = _projection_drift(
                db,
                expected,
            )

        extra_count = len(extra_documents if not apply else _remaining_extra)
        mismatch_count = missing_count + extra_count + stale_count
        run.expected_count = len(expected)
        run.indexed_count = indexed_count
        run.missing_count = missing_count
        run.extra_count = extra_count
        run.cursor = None
        run.status = CommunitySearchRebuildStatus.COMPLETED
        run.error_summary = None
        run.finished_at = utc_now()
        db.commit()
        return SearchRebuildResult(
            operation=operation,
            scanned=scanned,
            upserted=upserted,
            deleted=deleted,
            mismatch_count=mismatch_count,
            run_id=run.id,
        )
    except Exception as exc:
        run.status = CommunitySearchRebuildStatus.FAILED
        run.error_summary = type(exc).__name__[:256]
        run.finished_at = utc_now()
        db.commit()
        raise


def _load_rebuild_run(
    db: Session,
    *,
    operation: str,
    resume_run_id: str | None,
) -> CommunitySearchRebuildRun:
    if resume_run_id is not None:
        run = db.get(CommunitySearchRebuildRun, resume_run_id)
        if run is None:
            raise ValueError("search rebuild run was not found")
        if run.status is not CommunitySearchRebuildStatus.RUNNING:
            raise ValueError("search rebuild run is not resumable")
        if run.scope != operation:
            raise ValueError("search rebuild operation does not match resumable run")
        return run

    run = CommunitySearchRebuildRun(
        scope=operation,
        status=CommunitySearchRebuildStatus.RUNNING,
        started_at=utc_now(),
    )
    db.add(run)
    db.flush()
    return run


def _all_source_keys(db: Session) -> list[tuple[CommunitySearchSource, str]]:
    keys = [
        (source_type, source_id)
        for source_type, source_ids in _all_source_ids(db)
        for source_id in source_ids
    ]
    return sorted(keys, key=_source_key_value)


def _source_key_value(key: tuple[CommunitySearchSource, str]) -> tuple[str, str]:
    return key[0].value, key[1]


def _serialize_rebuild_cursor(key: tuple[CommunitySearchSource, str]) -> str:
    source_type, source_id = key
    return json.dumps(
        {"source_type": source_type.value, "source_id": source_id},
        separators=(",", ":"),
        sort_keys=True,
    )


def _parse_rebuild_cursor(cursor: str | None) -> tuple[str, str] | None:
    if cursor is None:
        return None
    try:
        payload = json.loads(cursor)
        source_type = CommunitySearchSource(payload["source_type"])
        source_id = payload["source_id"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("search rebuild cursor is invalid") from exc
    if not isinstance(source_id, str):
        raise ValueError("search rebuild cursor is invalid")
    return source_type.value, source_id


def _expected_documents(
    db: Session,
) -> dict[tuple[CommunitySearchSource, str], tuple[int, _DocumentPayload]]:
    expected: dict[tuple[CommunitySearchSource, str], tuple[int, _DocumentPayload]] = {}
    for source_type, source_id in _all_source_keys(db):
        payload = _build_document_payload(db, source_type=source_type, source_id=source_id)
        if payload is not None:
            expected[(source_type, source_id)] = (
                _source_version(db, source_type, source_id),
                payload,
            )
    return expected


def _projection_drift(
    db: Session,
    expected: dict[tuple[CommunitySearchSource, str], tuple[int, _DocumentPayload]],
) -> tuple[int, list[CommunitySearchDocument], int, int]:
    documents = db.scalars(select(CommunitySearchDocument)).all()
    by_key = {(document.source_type, document.source_id): document for document in documents}
    expected_keys = set(expected)
    document_keys = set(by_key)
    missing_count = len(expected_keys - document_keys)
    extra_documents = [document for key, document in by_key.items() if key not in expected_keys]
    stale_count = sum(
        1
        for key in expected_keys & document_keys
        if not _document_matches(
            by_key[key],
            document_version=expected[key][0],
            payload=expected[key][1],
        )
    )
    indexed_count = len(expected_keys & document_keys)
    return missing_count, extra_documents, stale_count, indexed_count


def _document_matches(
    document: CommunitySearchDocument,
    *,
    document_version: int,
    payload: _DocumentPayload,
) -> bool:
    return (
        document.document_version == document_version
        and document.title == payload.title
        and document.body == payload.body
        and document.username == payload.username
        and document.board_code == payload.board_code
        and document.group_slug == payload.group_slug
        and document.author_id == payload.author_id
        and document.is_public is True
        and document.source_updated_at == payload.source_updated_at
    )

def _apply_search_event(db: Session, event: CommunitySearchOutbox) -> None:
    if event.event_type == "delete":
        db.execute(
            delete(CommunitySearchDocument).where(
                CommunitySearchDocument.source_type == event.source_type,
                CommunitySearchDocument.source_id == event.source_id,
            )
        )
        return
    payload = _build_document_payload(db, source_type=event.source_type, source_id=event.source_id)
    if payload is None:
        db.execute(
            delete(CommunitySearchDocument).where(
                CommunitySearchDocument.source_type == event.source_type,
                CommunitySearchDocument.source_id == event.source_id,
            )
        )
        return
    _upsert_document(
        db,
        source_type=event.source_type,
        source_id=event.source_id,
        document_version=event.document_version,
        payload=payload,
    )


def _upsert_document(
    db: Session,
    *,
    source_type: CommunitySearchSource,
    source_id: str,
    document_version: int,
    payload: _DocumentPayload,
) -> None:
    document = db.scalar(
        select(CommunitySearchDocument).where(
            CommunitySearchDocument.source_type == source_type,
            CommunitySearchDocument.source_id == source_id,
        )
    )
    if document is not None and document.document_version > document_version:
        return
    if document is None:
        document = CommunitySearchDocument(
            source_type=source_type,
            source_id=source_id,
            document_version=document_version,
            title=payload.title,
            body=payload.body,
            username=payload.username,
            board_code=payload.board_code,
            group_slug=payload.group_slug,
            author_id=payload.author_id,
            is_public=True,
            source_updated_at=payload.source_updated_at,
        )
        db.add(document)
        return
    document.document_version = document_version
    document.title = payload.title
    document.body = payload.body
    document.username = payload.username
    document.board_code = payload.board_code
    document.group_slug = payload.group_slug
    document.author_id = payload.author_id
    document.is_public = True
    document.source_updated_at = payload.source_updated_at


def _build_document_payload(
    db: Session,
    *,
    source_type: CommunitySearchSource,
    source_id: str,
) -> _DocumentPayload | None:
    if source_type is CommunitySearchSource.POST:
        post = db.get(CommunityPost, source_id)
        if (
            post is None
            or post.status is not CommunityContentStatus.PUBLISHED
            or post.deleted_by_author_at
        ):
            return None
        board = db.get(CommunityBoard, post.board_id)
        group = db.get(CommunityGroup, post.group_id) if post.group_id else None
        author = db.get(User, post.author_id)
        if (
            board is None
            or board.status is not CommunityBoardStatus.ACTIVE
            or author is None
            or author.status is not UserStatus.ACTIVE
            or (
                group is not None
                and (
                    group.status is not CommunityGroupStatus.ACTIVE
                    or group.visibility is not CommunityGroupVisibility.PUBLIC
                )
            )
        ):
            return None
        return _DocumentPayload(
            title=post.title,
            body=post.content,
            username=author.username,
            board_code=post.board_code,
            group_slug=group.slug if group is not None else None,
            author_id=post.author_id,
            source_updated_at=post.updated_at,
        )
    if source_type is CommunitySearchSource.USER:
        user = db.get(User, source_id)
        profile = db.get(CommunityPublicProfile, source_id)
        if user is None or profile is None or user.status is not UserStatus.ACTIVE:
            return None
        return _DocumentPayload(
            title=profile.display_name,
            body="",
            username=user.username,
            board_code=None,
            group_slug=None,
            author_id=user.id,
            source_updated_at=profile.updated_at,
        )
    if source_type is CommunitySearchSource.BOARD:
        board = db.get(CommunityBoard, source_id)
        if board is None or board.status is not CommunityBoardStatus.ACTIVE:
            return None
        return _DocumentPayload(
            title=board.name,
            body=board.description,
            username=None,
            board_code=board.code,
            group_slug=None,
            author_id=None,
            source_updated_at=board.updated_at,
        )
    group = db.get(CommunityGroup, source_id)
    if (
        group is None
        or group.status is not CommunityGroupStatus.ACTIVE
        or group.visibility is not CommunityGroupVisibility.PUBLIC
    ):
        return None
    return _DocumentPayload(
        title=group.name,
        body=group.description,
        username=None,
        board_code=None,
        group_slug=group.slug,
        author_id=group.owner_id,
        source_updated_at=group.updated_at,
    )


def source_document_version(source: object) -> int:
    version = getattr(source, "version", None)
    if isinstance(version, int):
        return version
    updated_at = getattr(source, "updated_at", None)
    if updated_at is None:
        return int(utc_now().timestamp() * 1_000_000)
    return int(updated_at.timestamp() * 1_000_000)


def _source_version(db: Session, source_type: CommunitySearchSource, source_id: str) -> int:
    if source_type is CommunitySearchSource.POST:
        source = db.get(CommunityPost, source_id)
        return source.version if source is not None else 0
    if source_type is CommunitySearchSource.USER:
        source = db.get(CommunityPublicProfile, source_id)
    elif source_type is CommunitySearchSource.BOARD:
        source = db.get(CommunityBoard, source_id)
    else:
        source = db.get(CommunityGroup, source_id)
    if source is None:
        return 0
    return int(source.updated_at.timestamp() * 1_000_000)


def _all_source_ids(db: Session):
    return (
        (CommunitySearchSource.POST, list(db.scalars(select(CommunityPost.id)))),
        (CommunitySearchSource.USER, list(db.scalars(select(CommunityPublicProfile.user_id)))),
        (CommunitySearchSource.BOARD, list(db.scalars(select(CommunityBoard.id)))),
        (CommunitySearchSource.GROUP, list(db.scalars(select(CommunityGroup.id)))),
    )
