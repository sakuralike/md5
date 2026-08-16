from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractContextManager
from typing import Protocol

from fastapi import Request
from pydantic import BaseModel
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from password_detective.db.models.community import (
    CommunityDirectEvent,
    CommunityDirectEventType,
)
from password_detective.modules.community.direct_message_events import (
    DirectEventBatch,
    DirectStreamCursor,
    list_direct_events,
    resolve_direct_stream_cursor,
)
from password_detective.modules.community.direct_message_realtime import (
    DirectStreamWakeSubscription,
)
from password_detective.modules.community.schemas import (
    CommunityDirectConversationReadEvent,
    CommunityDirectMessageCreatedEvent,
    CommunityDirectStreamReady,
    CommunityDirectUnreadChangedEvent,
)

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractContextManager[Session]]


class DirectWakeSubscription(Protocol):
    async def wait(self, timeout_seconds: float) -> bool: ...

    async def close(self) -> None: ...


SubscriptionFactory = Callable[..., Awaitable[DirectWakeSubscription]]


def load_cursor_snapshot(
    session_factory: SessionFactory,
    *,
    recipient_id: str,
    raw_last_event_id: str | None,
) -> DirectStreamCursor:
    with session_factory() as db:
        return resolve_direct_stream_cursor(
            db,
            recipient_id=recipient_id,
            raw_cursor=raw_last_event_id,
        )


def load_event_batch(
    session_factory: SessionFactory,
    *,
    recipient_id: str,
    after_sequence: int,
    limit: int = 50,
) -> DirectEventBatch:
    with session_factory() as db:
        return list_direct_events(
            db,
            recipient_id=recipient_id,
            after_sequence=after_sequence,
            limit=limit,
        )


def direct_event_payload(event: CommunityDirectEvent) -> BaseModel:
    common: dict[str, object] = {
        "event_id": str(event.sequence),
        "conversation_id": event.conversation_id,
        **event.payload,
    }
    if event.event_type == CommunityDirectEventType.MESSAGE_CREATED:
        common["message_id"] = event.message_id
        return CommunityDirectMessageCreatedEvent.model_validate(common)
    if event.event_type == CommunityDirectEventType.CONVERSATION_READ:
        return CommunityDirectConversationReadEvent.model_validate(common)
    if event.event_type == CommunityDirectEventType.UNREAD_CHANGED:
        return CommunityDirectUnreadChangedEvent.model_validate(common)
    raise ValueError(f"Unsupported direct stream event type: {event.event_type}")


def encode_sse(
    event: str,
    event_id: int,
    data: BaseModel | Mapping[str, object],
) -> str:
    payload = data.model_dump(mode="json") if isinstance(data, BaseModel) else dict(data)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event_id}\nevent: {event}\ndata: {encoded}\n\n"


async def direct_message_event_stream(
    request: Request,
    *,
    recipient_id: str,
    raw_last_event_id: str | None,
    session_factory: SessionFactory,
    redis_url: str,
    subscription_factory: SubscriptionFactory | None = None,
    poll_interval_seconds: float = 1.0,
    heartbeat_seconds: float = 15.0,
) -> AsyncIterator[str]:
    cursor = load_cursor_snapshot(
        session_factory,
        recipient_id=recipient_id,
        raw_last_event_id=raw_last_event_id,
    )
    after_sequence = cursor.after_sequence
    yield encode_sse(
        "ready",
        after_sequence,
        CommunityDirectStreamReady(
            event_id=str(after_sequence),
            total_unread_count=cursor.total_unread_count,
            reset_required=cursor.reset_required,
        ),
    )

    subscription: DirectWakeSubscription | None = None
    factory = subscription_factory or DirectStreamWakeSubscription.connect
    try:
        try:
            subscription = await factory(redis_url, user_id=recipient_id)
        except (OSError, RedisError, TimeoutError):
            logger.warning(
                "Direct message Redis subscription unavailable; using database polling",
                exc_info=True,
            )

        elapsed_without_event = 0.0
        while not await request.is_disconnected():
            batch = load_event_batch(
                session_factory,
                recipient_id=recipient_id,
                after_sequence=after_sequence,
                limit=50,
            )
            if batch.items:
                for item in batch.items:
                    after_sequence = item.sequence
                    yield encode_sse(
                        item.event_type.value,
                        item.sequence,
                        direct_event_payload(item),
                    )
                elapsed_without_event = 0.0
                continue

            if subscription is None:
                wait_seconds = max(0.0, poll_interval_seconds)
                await asyncio.sleep(wait_seconds)
                elapsed_without_event += wait_seconds
            else:
                wait_seconds = max(0.0, heartbeat_seconds)
                woke = await subscription.wait(wait_seconds)
                if woke:
                    elapsed_without_event = 0.0
                    continue
                elapsed_without_event += wait_seconds

            if heartbeat_seconds <= 0 or elapsed_without_event >= heartbeat_seconds:
                yield ": heartbeat\n\n"
                elapsed_without_event = 0.0
    finally:
        if subscription is not None:
            await subscription.close()
