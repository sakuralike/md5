from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from password_detective.core.ids import new_id
from password_detective.core.time import utc_now
from password_detective.db.models.community import (
    CommunityDirectConversationMember,
    CommunityDirectEvent,
    CommunityDirectEventType,
    CommunityDirectMessage,
    CommunityDirectStreamPosition,
)

_SENSITIVE_EVENT_KEYS = frozenset(
    {"body", "ciphertext", "nonce", "key_version", "access_token", "refresh_token"}
)

@dataclass(frozen=True)
class DirectEventDraft:
    recipient_id: str
    event_type: CommunityDirectEventType
    conversation_id: str
    actor_id: str
    message_id: str | None
    payload: Mapping[str, object]


@dataclass(frozen=True)
class DirectEventBatch:
    items: list[CommunityDirectEvent]
    last_sequence: int


@dataclass(frozen=True)
class DirectStreamCursor:
    after_sequence: int
    latest_sequence: int
    total_unread_count: int
    reset_required: bool


def append_direct_events(
    db: Session,
    *,
    drafts: Sequence[DirectEventDraft],
) -> list[CommunityDirectEvent]:
    if not drafts:
        return []
    for draft in drafts:
        _validate_event_payload(draft.payload)

    recipient_ids = sorted({draft.recipient_id for draft in drafts})
    for recipient_id in recipient_ids:
        _ensure_stream_position(db, recipient_id)

    positions = {
        position.user_id: position
        for position in db.scalars(
            select(CommunityDirectStreamPosition)
            .where(CommunityDirectStreamPosition.user_id.in_(recipient_ids))
            .order_by(CommunityDirectStreamPosition.user_id)
            .with_for_update()
        )
    }
    now = utc_now()
    created: list[CommunityDirectEvent] = []
    for draft in drafts:
        position = positions[draft.recipient_id]
        position.last_sequence += 1
        position.updated_at = now
        event = CommunityDirectEvent(
            id=new_id(),
            recipient_id=draft.recipient_id,
            sequence=position.last_sequence,
            event_type=draft.event_type,
            conversation_id=draft.conversation_id,
            actor_id=draft.actor_id,
            message_id=draft.message_id,
            payload=dict(draft.payload),
            created_at=now,
        )
        db.add(event)
        created.append(event)
    db.flush()
    return created


def latest_direct_event_sequence(db: Session, *, recipient_id: str) -> int:
    value = db.scalar(
        select(CommunityDirectStreamPosition.last_sequence).where(
            CommunityDirectStreamPosition.user_id == recipient_id
        )
    )
    return int(value or 0)


def list_direct_events(
    db: Session,
    *,
    recipient_id: str,
    after_sequence: int,
    limit: int = 100,
) -> DirectEventBatch:
    items = list(
        db.scalars(
            select(CommunityDirectEvent)
            .where(
                CommunityDirectEvent.recipient_id == recipient_id,
                CommunityDirectEvent.sequence > after_sequence,
            )
            .order_by(CommunityDirectEvent.sequence)
            .limit(limit)
        )
    )
    last_sequence = items[-1].sequence if items else after_sequence
    return DirectEventBatch(items=items, last_sequence=last_sequence)


def resolve_direct_stream_cursor(
    db: Session,
    *,
    recipient_id: str,
    raw_cursor: str | None,
) -> DirectStreamCursor:
    latest_sequence = latest_direct_event_sequence(db, recipient_id=recipient_id)
    total_unread = total_direct_unread_count(db, user_id=recipient_id)
    if raw_cursor is None:
        return DirectStreamCursor(
            after_sequence=latest_sequence,
            latest_sequence=latest_sequence,
            total_unread_count=total_unread,
            reset_required=False,
        )
    try:
        parsed = int(raw_cursor)
    except (TypeError, ValueError):
        return DirectStreamCursor(
            after_sequence=latest_sequence,
            latest_sequence=latest_sequence,
            total_unread_count=total_unread,
            reset_required=True,
        )
    minimum_sequence = db.scalar(
        select(func.min(CommunityDirectEvent.sequence)).where(
            CommunityDirectEvent.recipient_id == recipient_id
        )
    )
    expired = minimum_sequence is not None and parsed < int(minimum_sequence) - 1
    invalid = parsed < 0 or parsed > latest_sequence or expired
    return DirectStreamCursor(
        after_sequence=latest_sequence if invalid else parsed,
        latest_sequence=latest_sequence,
        total_unread_count=total_unread,
        reset_required=invalid,
    )


def conversation_unread_count(
    db: Session,
    *,
    user_id: str,
    conversation_id: str,
) -> int:
    last_read_sequence = db.scalar(
        select(CommunityDirectConversationMember.last_read_sequence).where(
            CommunityDirectConversationMember.user_id == user_id,
            CommunityDirectConversationMember.conversation_id == conversation_id,
        )
    )
    if last_read_sequence is None:
        return 0
    value = db.scalar(
        select(func.count(CommunityDirectMessage.id)).where(
            CommunityDirectMessage.conversation_id == conversation_id,
            CommunityDirectMessage.removed_at.is_(None),
            CommunityDirectMessage.sequence > last_read_sequence,
            CommunityDirectMessage.sender_id != user_id,
        )
    )
    return int(value or 0)


def total_direct_unread_count(db: Session, *, user_id: str) -> int:
    value = db.scalar(
        select(func.count(CommunityDirectMessage.id))
        .select_from(CommunityDirectMessage)
        .join(
            CommunityDirectConversationMember,
            CommunityDirectConversationMember.conversation_id
            == CommunityDirectMessage.conversation_id,
        )
        .where(
            CommunityDirectConversationMember.user_id == user_id,
            CommunityDirectMessage.removed_at.is_(None),
            CommunityDirectMessage.sequence
            > CommunityDirectConversationMember.last_read_sequence,
            CommunityDirectMessage.sender_id != user_id,
        )
    )
    return int(value or 0)


def _ensure_stream_position(db: Session, user_id: str) -> None:
    table = CommunityDirectStreamPosition.__table__
    now = utc_now()
    values = {
        "user_id": user_id,
        "last_sequence": 0,
        "created_at": now,
        "updated_at": now,
    }
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "mysql":
        statement = mysql_insert(table).values(**values)
        db.execute(
            statement.on_duplicate_key_update(
                last_sequence=table.c.last_sequence,
                updated_at=table.c.updated_at,
            )
        )
        return
    if dialect_name == "sqlite":
        db.execute(
            sqlite_insert(table)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["user_id"])
        )
        return
    if db.get(CommunityDirectStreamPosition, user_id) is None:
        db.add(CommunityDirectStreamPosition(**values))
        db.flush()

def _validate_event_payload(payload: Mapping[str, object]) -> None:
    pending: list[Mapping[str, object]] = [payload]
    while pending:
        current = pending.pop()
        forbidden = _SENSITIVE_EVENT_KEYS.intersection(current)
        if forbidden:
            names = ", ".join(sorted(forbidden))
            raise ValueError(f"Sensitive direct event payload keys are forbidden: {names}")
        for value in current.values():
            if isinstance(value, Mapping):
                pending.append(value)
