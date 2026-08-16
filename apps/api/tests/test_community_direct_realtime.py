from __future__ import annotations

import asyncio

from redis.exceptions import RedisError
from sqlalchemy import select

from password_detective.core.time import utc_now
from password_detective.db.models.community import (
    CommunityDirectConversation,
    CommunityDirectConversationMember,
    CommunityDirectEvent,
    CommunityDirectEventType,
    CommunityDirectMessage,
    CommunityInteractionPolicy,
    CommunityPublicProfile,
)
from password_detective.db.models.user import User
from password_detective.modules.community import router as community_router
from password_detective.modules.community.direct_message_events import (
    DirectEventDraft,
    append_direct_events,
    conversation_unread_count,
    latest_direct_event_sequence,
    list_direct_events,
    resolve_direct_stream_cursor,
    total_direct_unread_count,
)
from password_detective.modules.community.direct_message_realtime import (
    DirectStreamWakeSubscription,
    direct_stream_channel,
    publish_direct_message_wakeups,
)


def _seed_users_and_conversation(db):
    alice = User(
        username="direct_realtime_alice",
        email="direct-realtime-alice@example.com",
        account_password_hash="synthetic-hash",
    )
    bob = User(
        username="direct_realtime_bob",
        email="direct-realtime-bob@example.com",
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
    db.flush()
    return alice, bob, conversation


def test_append_events_allocates_independent_monotonic_recipient_sequences(client) -> None:
    with client.app.state.database.session_factory() as db:
        alice, bob, conversation = _seed_users_and_conversation(db)

        first = append_direct_events(
            db,
            drafts=[
                DirectEventDraft(
                    recipient_id=alice.id,
                    event_type=CommunityDirectEventType.MESSAGE_CREATED,
                    conversation_id=conversation.id,
                    actor_id=alice.id,
                    message_id=None,
                    payload={"message_sequence": 1},
                ),
                DirectEventDraft(
                    recipient_id=bob.id,
                    event_type=CommunityDirectEventType.MESSAGE_CREATED,
                    conversation_id=conversation.id,
                    actor_id=alice.id,
                    message_id=None,
                    payload={"message_sequence": 1},
                ),
            ],
        )
        second = append_direct_events(
            db,
            drafts=[
                DirectEventDraft(
                    recipient_id=alice.id,
                    event_type=CommunityDirectEventType.CONVERSATION_READ,
                    conversation_id=conversation.id,
                    actor_id=bob.id,
                    message_id=None,
                    payload={"last_read_sequence": 1},
                )
            ],
        )

        assert [event.sequence for event in first] == [1, 1]
        assert [event.sequence for event in second] == [2]
        assert latest_direct_event_sequence(db, recipient_id=alice.id) == 2
        assert latest_direct_event_sequence(db, recipient_id=bob.id) == 1
        assert all(
            "body" not in event.payload and "ciphertext" not in event.payload
            for event in [*first, *second]
        )


def test_event_payload_rejects_sensitive_message_material(client) -> None:
    with client.app.state.database.session_factory() as db:
        alice, _, conversation = _seed_users_and_conversation(db)

        try:
            append_direct_events(
                db,
                drafts=[
                    DirectEventDraft(
                        recipient_id=alice.id,
                        event_type=CommunityDirectEventType.MESSAGE_CREATED,
                        conversation_id=conversation.id,
                        actor_id=alice.id,
                        message_id=None,
                        payload={"body": "synthetic forbidden content"},
                    )
                ],
            )
        except ValueError as error:
            assert "body" in str(error)
        else:
            raise AssertionError("Sensitive direct event payload was accepted")

def test_event_listing_and_cursor_resolution_are_recipient_scoped(client) -> None:
    with client.app.state.database.session_factory() as db:
        alice, bob, conversation = _seed_users_and_conversation(db)
        append_direct_events(
            db,
            drafts=[
                DirectEventDraft(
                    recipient_id=alice.id,
                    event_type=CommunityDirectEventType.UNREAD_CHANGED,
                    conversation_id=conversation.id,
                    actor_id=bob.id,
                    message_id=None,
                    payload={"conversation_unread_count": 1, "total_unread_count": 1},
                ),
                DirectEventDraft(
                    recipient_id=bob.id,
                    event_type=CommunityDirectEventType.MESSAGE_CREATED,
                    conversation_id=conversation.id,
                    actor_id=bob.id,
                    message_id=None,
                    payload={"message_sequence": 1},
                ),
            ],
        )

        alice_batch = list_direct_events(db, recipient_id=alice.id, after_sequence=0)
        assert [(item.recipient_id, item.sequence) for item in alice_batch.items] == [
            (alice.id, 1)
        ]
        assert db.scalars(
            select(CommunityDirectEvent).where(CommunityDirectEvent.recipient_id == bob.id)
        ).all()

        first_connection = resolve_direct_stream_cursor(
            db, recipient_id=alice.id, raw_cursor=None
        )
        valid = resolve_direct_stream_cursor(db, recipient_id=alice.id, raw_cursor="0")
        invalid = resolve_direct_stream_cursor(db, recipient_id=alice.id, raw_cursor="invalid")
        future = resolve_direct_stream_cursor(db, recipient_id=alice.id, raw_cursor="99")

        assert first_connection.after_sequence == 1
        assert first_connection.reset_required is False
        assert valid.after_sequence == 0
        assert valid.reset_required is False
        assert invalid.after_sequence == 1
        assert invalid.reset_required is True
        assert future.after_sequence == 1
        assert future.reset_required is True


def test_unread_counts_exclude_messages_sent_by_the_reader(client) -> None:
    with client.app.state.database.session_factory() as db:
        alice, bob, conversation = _seed_users_and_conversation(db)
        db.add_all(
            [
                CommunityDirectMessage(
                    conversation_id=conversation.id,
                    sender_id=alice.id,
                    sequence=1,
                    ciphertext="synthetic-ciphertext-1",
                    nonce="synthetic-nonce-1",
                    key_version="v1",
                    client_message_id="synthetic-message-1",
                ),
                CommunityDirectMessage(
                    conversation_id=conversation.id,
                    sender_id=alice.id,
                    sequence=2,
                    ciphertext="synthetic-ciphertext-2",
                    nonce="synthetic-nonce-2",
                    key_version="v1",
                    client_message_id="synthetic-message-2",
                ),
            ]
        )
        bob_member = db.scalar(
            select(CommunityDirectConversationMember).where(
                CommunityDirectConversationMember.conversation_id == conversation.id,
                CommunityDirectConversationMember.user_id == bob.id,
            )
        )
        assert bob_member is not None
        bob_member.last_read_sequence = 1
        db.flush()

        assert conversation_unread_count(
            db, user_id=bob.id, conversation_id=conversation.id
        ) == 1
        assert total_direct_unread_count(db, user_id=bob.id) == 1
        assert conversation_unread_count(
            db, user_id=alice.id, conversation_id=conversation.id
        ) == 0
        assert total_direct_unread_count(db, user_id=alice.id) == 0

class _FakePublishClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []
        self.closed = False

    def publish(self, channel: str, payload: str) -> None:
        self.published.append((channel, payload))

    def close(self) -> None:
        self.closed = True


class _FakeAsyncPubSub:
    def __init__(self) -> None:
        self.messages = [None, {"type": "message", "data": '{"max_sequence":12}'}]
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        self.subscribed.append(channel)

    async def get_message(self, **_kwargs):
        return self.messages.pop(0)

    async def unsubscribe(self, channel: str) -> None:
        self.unsubscribed.append(channel)

    async def aclose(self) -> None:
        self.closed = True


class _FakeAsyncClient:
    def __init__(self, pubsub: _FakeAsyncPubSub) -> None:
        self._pubsub = pubsub
        self.closed = False

    def pubsub(self) -> _FakeAsyncPubSub:
        return self._pubsub

    async def aclose(self) -> None:
        self.closed = True


def _register_verified_login(client, username: str) -> dict[str, str]:
    password = "SyntheticPass123!"
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
        },
    )
    assert registered.status_code == 201
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        user.email_verified_at = utc_now()
        db.commit()
    login = client.post(
        "/api/v1/auth/login",
        json={"login": username, "password": password},
    )
    assert login.status_code == 200
    return login.json()


def test_publish_uses_user_channel_without_sensitive_payload() -> None:
    fake = _FakePublishClient()

    publish_direct_message_wakeups(
        "redis://synthetic",
        {"user-b": 7, "user-a": 12},
        client_factory=lambda *_args, **_kwargs: fake,
    )

    assert direct_stream_channel("user-a") == "community:direct-stream:user:user-a"
    assert fake.published == [
        ("community:direct-stream:user:user-a", '{"max_sequence":12}'),
        ("community:direct-stream:user:user-b", '{"max_sequence":7}'),
    ]
    assert all("body" not in payload for _, payload in fake.published)
    assert fake.closed is True


def test_wake_subscription_connects_to_user_channel_and_closes_client() -> None:
    pubsub = _FakeAsyncPubSub()
    client = _FakeAsyncClient(pubsub)
    subscription = asyncio.run(
        DirectStreamWakeSubscription.connect(
            "redis://synthetic",
            user_id="user-a",
            client_factory=lambda *_args, **_kwargs: client,
        )
    )

    assert pubsub.subscribed == ["community:direct-stream:user:user-a"]
    asyncio.run(subscription.close())
    assert client.closed is True


def test_wake_subscription_waits_and_closes_user_channel() -> None:
    pubsub = _FakeAsyncPubSub()
    subscription = DirectStreamWakeSubscription(user_id="user-a", pubsub=pubsub)

    assert asyncio.run(subscription.wait(0.01)) is False
    assert asyncio.run(subscription.wait(0.01)) is True
    asyncio.run(subscription.close())

    assert pubsub.unsubscribed == ["community:direct-stream:user:user-a"]
    assert pubsub.closed is True


def test_redis_publish_failure_does_not_change_committed_message(client, monkeypatch) -> None:
    alice = _register_verified_login(client, "direct_redis_alice")
    bob = _register_verified_login(client, "direct_redis_bob")
    with client.app.state.database.session_factory() as db:
        bob_user = db.scalar(select(User).where(User.username == "direct_redis_bob"))
        assert bob_user is not None
        profile = db.get(CommunityPublicProfile, bob_user.id)
        if profile is None:
            profile = CommunityPublicProfile(
                user_id=bob_user.id,
                display_name=bob_user.username,
                avatar_seed=bob_user.id.replace("-", "")[:24].ljust(24, "0"),
            )
            db.add(profile)
        profile.message_policy = CommunityInteractionPolicy.EVERYONE
        db.commit()

    created = client.post(
        "/api/v1/community/direct-conversations",
        json={"recipient_username": "direct_redis_bob"},
        headers={
            "Authorization": f"Bearer {alice['access_token']}",
            "Idempotency-Key": "direct-redis-conversation-1",
        },
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["conversation"]["id"]

    def raise_redis_error(*_args, **_kwargs) -> None:
        raise RedisError("synthetic Redis outage")

    monkeypatch.setattr(community_router, "publish_direct_message_wakeups", raise_redis_error)
    sent = client.post(
        f"/api/v1/community/direct-conversations/{conversation_id}/messages",
        json={
            "body": "仅用于 Redis 故障隔离测试的合成私信",
            "client_message_id": "direct-redis-message-1",
        },
        headers={
            "Authorization": f"Bearer {alice['access_token']}",
            "Idempotency-Key": "direct-redis-message-http-1",
        },
    )
    assert sent.status_code == 201, sent.text

    listed = client.get(
        f"/api/v1/community/direct-conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {bob['access_token']}"},
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"][0]["body"] == "仅用于 Redis 故障隔离测试的合成私信"
