from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager

from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from password_detective.core.time import utc_now
from password_detective.db.models.community import (
    CommunityDirectConversation,
    CommunityDirectConversationMember,
    CommunityDirectEventType,
    CommunityDirectMessage,
)
from password_detective.db.models.user import User
from password_detective.modules.community import router as community_router
from password_detective.modules.community.direct_message_events import (
    DirectEventDraft,
    append_direct_events,
)
from password_detective.modules.community.direct_message_stream import (
    direct_message_event_stream,
)


class _OpenRequest:
    async def is_disconnected(self) -> bool:
        return False


class _WakeSubscription:
    def __init__(self, *, on_wait=None) -> None:
        self.closed = False
        self.on_wait = on_wait

    async def wait(self, _timeout_seconds: float) -> bool:
        if self.on_wait is not None:
            self.on_wait()
        return False

    async def close(self) -> None:
        self.closed = True


def _parse_sse(message: str) -> tuple[str, str | None, dict[str, object]]:
    event = ""
    event_id = None
    data = "{}"
    for line in message.strip().splitlines():
        if line.startswith("event: "):
            event = line.removeprefix("event: ")
        elif line.startswith("id: "):
            event_id = line.removeprefix("id: ")
        elif line.startswith("data: "):
            data = line.removeprefix("data: ")
    return event, event_id, json.loads(data)


def _seed_direct_event(client) -> tuple[str, int]:
    with client.app.state.database.session_factory() as db:
        alice = User(
            username="direct_stream_alice",
            email="direct-stream-alice@example.com",
            account_password_hash="synthetic-hash",
        )
        bob = User(
            username="direct_stream_bob",
            email="direct-stream-bob@example.com",
            account_password_hash="synthetic-hash",
        )
        db.add_all([alice, bob])
        db.flush()
        low_id, high_id = sorted((alice.id, bob.id))
        conversation = CommunityDirectConversation(
            participant_low_id=low_id,
            participant_high_id=high_id,
        )
        db.add(conversation)
        db.flush()
        db.add_all(
            [
                CommunityDirectConversationMember(
                    conversation_id=conversation.id,
                    user_id=alice.id,
                    last_read_sequence=0,
                ),
                CommunityDirectConversationMember(
                    conversation_id=conversation.id,
                    user_id=bob.id,
                    last_read_sequence=0,
                ),
            ]
        )
        message = CommunityDirectMessage(
            conversation_id=conversation.id,
            sender_id=alice.id,
            sequence=1,
            ciphertext="synthetic-ciphertext",
            nonce="synthetic-nonce",
            key_version="v1",
            client_message_id="synthetic-client-message",
        )
        db.add(message)
        db.flush()
        event = append_direct_events(
            db,
            drafts=[
                DirectEventDraft(
                    recipient_id=bob.id,
                    event_type=CommunityDirectEventType.MESSAGE_CREATED,
                    conversation_id=conversation.id,
                    actor_id=alice.id,
                    message_id=message.id,
                    payload={
                        "message_sequence": 1,
                        "sender_id": alice.id,
                        "created_at": message.created_at.isoformat(),
                    },
                )
            ],
        )[0]
        db.commit()
        return bob.id, event.sequence


def test_first_connection_starts_from_snapshot_without_history(client) -> None:
    recipient_id, latest_sequence = _seed_direct_event(client)
    subscription = _WakeSubscription()

    async def scenario() -> None:
        stream = direct_message_event_stream(
            _OpenRequest(),
            recipient_id=recipient_id,
            raw_last_event_id=None,
            session_factory=client.app.state.database.session_factory,
            redis_url="redis://synthetic",
            subscription_factory=lambda *_args, **_kwargs: asyncio.sleep(0, result=subscription),
            heartbeat_seconds=0,
        )
        ready = _parse_sse(await anext(stream))
        heartbeat = await anext(stream)
        await stream.aclose()

        assert ready == (
            "ready",
            str(latest_sequence),
            {
                "event_id": str(latest_sequence),
                "total_unread_count": 1,
                "reset_required": False,
            },
        )
        assert heartbeat == ": heartbeat\n\n"
        assert subscription.closed is True

    asyncio.run(scenario())


def test_valid_cursor_replays_domain_events_in_sequence_order(client) -> None:
    recipient_id, latest_sequence = _seed_direct_event(client)
    subscription = _WakeSubscription()

    async def scenario() -> None:
        stream = direct_message_event_stream(
            _OpenRequest(),
            recipient_id=recipient_id,
            raw_last_event_id="0",
            session_factory=client.app.state.database.session_factory,
            redis_url="redis://synthetic",
            subscription_factory=lambda *_args, **_kwargs: asyncio.sleep(0, result=subscription),
        )
        ready = _parse_sse(await anext(stream))
        event = _parse_sse(await anext(stream))
        await stream.aclose()

        assert ready[0:2] == ("ready", "0")
        assert ready[2]["reset_required"] is False
        assert event[0:2] == ("message.created", str(latest_sequence))
        assert event[2]["event_id"] == str(latest_sequence)
        assert event[2]["message_sequence"] == 1
        assert "body" not in event[2]
        assert "ciphertext" not in event[2]

    asyncio.run(scenario())


def test_future_cursor_requires_snapshot_reset_without_replay(client) -> None:
    recipient_id, latest_sequence = _seed_direct_event(client)

    async def scenario() -> None:
        stream = direct_message_event_stream(
            _OpenRequest(),
            recipient_id=recipient_id,
            raw_last_event_id="999",
            session_factory=client.app.state.database.session_factory,
            redis_url="redis://synthetic",
            subscription_factory=lambda *_args, **_kwargs: asyncio.sleep(
                0, result=_WakeSubscription()
            ),
            heartbeat_seconds=0,
        )
        ready = _parse_sse(await anext(stream))
        heartbeat = await anext(stream)
        await stream.aclose()

        assert ready[1] == str(latest_sequence)
        assert ready[2]["reset_required"] is True
        assert heartbeat == ": heartbeat\n\n"

    asyncio.run(scenario())


def test_stream_closes_database_session_before_waiting(client) -> None:
    recipient_id, _ = _seed_direct_event(client)
    original_factory = client.app.state.database.session_factory
    state = {"active_sessions": 0, "observed_wait": False}

    @contextmanager
    def tracked_factory() -> Iterator[Session]:
        state["active_sessions"] += 1
        try:
            with original_factory() as db:
                yield db
        finally:
            state["active_sessions"] -= 1

    def assert_no_open_session() -> None:
        assert state["active_sessions"] == 0
        state["observed_wait"] = True

    async def scenario() -> None:
        stream = direct_message_event_stream(
            _OpenRequest(),
            recipient_id=recipient_id,
            raw_last_event_id=None,
            session_factory=tracked_factory,
            redis_url="redis://synthetic",
            subscription_factory=lambda *_args, **_kwargs: asyncio.sleep(
                0, result=_WakeSubscription(on_wait=assert_no_open_session)
            ),
            heartbeat_seconds=0,
        )
        await anext(stream)
        await anext(stream)
        await stream.aclose()

    asyncio.run(scenario())
    assert state == {"active_sessions": 0, "observed_wait": True}


def _register_and_login(client) -> dict[str, object]:
    payload = {
        "username": "direct_stream_route_user",
        "email": "direct-stream-route-user@example.com",
        "password": "SyntheticPass123!",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == payload["username"]))
        assert user is not None
        user.email_verified_at = utc_now()
        db.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"login": payload["username"], "password": payload["password"]},
    )
    assert response.status_code == 200
    return response.json()


def test_direct_stream_releases_auth_session_before_streaming(client, monkeypatch) -> None:
    tokens = _register_and_login(client)
    database = client.app.state.database
    original_session = database.session
    state = {"active_request_sessions": 0}

    def tracked_session() -> Iterator[Session]:
        state["active_request_sessions"] += 1
        try:
            yield from original_session()
        finally:
            state["active_request_sessions"] -= 1

    async def finite_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
        del args, kwargs
        yield f"data: active={state['active_request_sessions']}\n\n"

    monkeypatch.setattr(database, "session", tracked_session)
    monkeypatch.setattr(community_router, "_direct_message_event_stream", finite_stream)

    response = client.get(
        "/api/v1/community/direct-messages/stream",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"
    assert "data: active=0" in response.text
    assert state["active_request_sessions"] == 0


def test_redis_subscription_failure_falls_back_to_database_polling(client) -> None:
    recipient_id, latest_sequence = _seed_direct_event(client)

    async def unavailable_subscription(*_args, **_kwargs):
        raise RedisError("synthetic Redis outage")

    async def scenario() -> None:
        stream = direct_message_event_stream(
            _OpenRequest(),
            recipient_id=recipient_id,
            raw_last_event_id=str(latest_sequence),
            session_factory=client.app.state.database.session_factory,
            redis_url="redis://synthetic",
            subscription_factory=unavailable_subscription,
            poll_interval_seconds=0,
            heartbeat_seconds=0,
        )
        await anext(stream)
        heartbeat = await anext(stream)
        await stream.aclose()
        assert heartbeat == ": heartbeat\n\n"

    asyncio.run(scenario())


def test_direct_stream_requires_authentication(client) -> None:
    response = client.get("/api/v1/community/direct-messages/stream")
    assert response.status_code == 401
