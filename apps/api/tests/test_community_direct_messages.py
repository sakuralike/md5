from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.models.community import (
    CommunityDirectConversation,
    CommunityDirectConversationMember,
    CommunityDirectMessage,
    CommunityInteractionPolicy,
    CommunityNotification,
    CommunityNotificationOutbox,
    CommunityPublicProfile,
    CommunityUserBlock,
    CommunityUserFollow,
)
from password_detective.db.models.user import User, UserStatus
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.community.direct_message_service import (
    _get_member_conversation,
    create_direct_conversation,
    list_direct_conversations,
    list_direct_messages,
    send_direct_message,
    update_direct_member_state,
    update_direct_read_state,
)
from password_detective.modules.community.schemas import (
    CommunityDirectConversationCreateRequest,
    CommunityDirectConversationCreateResponse,
    CommunityDirectConversationResponse,
    CommunityDirectMemberStateUpdateRequest,
    CommunityDirectMessageCreateRequest,
    CommunityDirectMessageResponse,
    CommunityDirectReadStateUpdateRequest,
)


def _register_login(client, username: str) -> dict[str, str]:
    password = "SyntheticPass123!"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
        },
    )
    assert response.status_code == 201
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        user.email_verified_at = utc_now()
        db.commit()
    login = client.post("/api/v1/auth/login", json={"login": username, "password": password})
    assert login.status_code == 200
    profile = client.get(
        "/api/v1/community/me/profile",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert profile.status_code == 200
    return login.json()


def _principal(db, username: str) -> Principal:
    user = db.scalar(select(User).where(User.username == username))
    assert user is not None
    return Principal(user=user, session_family_id="synthetic-session", mfa_verified=True)


def _set_message_policy(
    db, *, username: str, policy: CommunityInteractionPolicy
) -> None:
    user = db.scalar(select(User).where(User.username == username))
    assert user is not None
    profile = db.get(CommunityPublicProfile, user.id)
    if profile is None:
        profile = CommunityPublicProfile(
            user_id=user.id,
            display_name=user.username,
            avatar_seed=user.id.replace("-", "")[:24].ljust(24, "0"),
        )
        db.add(profile)
    profile.message_policy = policy
    db.flush()


def _assert_error_code(expected: str, callback) -> None:
    with pytest.raises(AppError) as captured:
        callback()
    assert captured.value.code == expected


def test_direct_message_request_schema_normalizes_and_rejects_blank_body() -> None:
    request = CommunityDirectMessageCreateRequest(
        body="  仅用于 schema 测试的合成内容  ", client_message_id="c-1"
    )

    assert request.body == "仅用于 schema 测试的合成内容"
    with pytest.raises(ValidationError):
        CommunityDirectMessageCreateRequest(body=" \n ", client_message_id="c-1")


def test_direct_conversation_schema_uses_public_username_not_internal_user_id() -> None:
    request = CommunityDirectConversationCreateRequest(recipient_username="  synthetic_receiver  ")

    assert request.recipient_username == "synthetic_receiver"
    assert "recipient_user_id" not in request.model_fields


def test_direct_message_responses_exclude_encryption_storage_fields() -> None:
    message = CommunityDirectMessageResponse(
        id="message-1",
        conversation_id="conversation-1",
        sender_username="synthetic_sender",
        body="仅用于契约测试的合成正文",
        sequence=1,
        created_at="2026-08-16T00:00:00Z",
    )
    conversation = CommunityDirectConversationResponse(
        id="conversation-1",
        counterpart_username="synthetic_receiver",
        counterpart_display_name="Synthetic Receiver",
        counterpart_avatar_seed="synthetic-seed",
        counterpart_avatar_url=None,
        last_message_at="2026-08-16T00:00:00Z",
        unread_count=1,
        last_read_sequence=0,
        archived_at=None,
        muted_until=None,
        created_at="2026-08-16T00:00:00Z",
        updated_at="2026-08-16T00:00:00Z",
    )
    created = CommunityDirectConversationCreateResponse(conversation=conversation, created=True)

    assert message.sequence == 1
    assert created.created is True
    assert {"ciphertext", "nonce", "key_version"}.isdisjoint(
        CommunityDirectMessageResponse.model_fields
    )


def test_direct_message_state_request_schemas_are_bounded() -> None:
    assert CommunityDirectReadStateUpdateRequest(last_read_sequence=0).last_read_sequence == 0
    assert CommunityDirectMemberStateUpdateRequest(archived=True).archived is True
    with pytest.raises(ValidationError):
        CommunityDirectReadStateUpdateRequest(last_read_sequence=-1)


def test_create_direct_conversation_rejects_self_blocked_disabled_and_policy(client) -> None:
    _register_login(client, "dm_guard_alice")
    _register_login(client, "dm_guard_bob")
    with client.app.state.database.session_factory() as db:
        alice = _principal(db, "dm_guard_alice")
        bob = db.scalar(select(User).where(User.username == "dm_guard_bob"))
        assert bob is not None
        payload = CommunityDirectConversationCreateRequest(recipient_username="dm_guard_bob")

        _assert_error_code(
            "DIRECT_MESSAGE_SELF_FORBIDDEN",
            lambda: create_direct_conversation(
                db,
                principal=alice,
                payload=CommunityDirectConversationCreateRequest(
                    recipient_username="dm_guard_alice"
                ),
            ),
        )
        bob.status = UserStatus.DISABLED
        db.flush()
        _assert_error_code(
            "DIRECT_MESSAGE_ACCOUNT_UNAVAILABLE",
            lambda: create_direct_conversation(db, principal=alice, payload=payload),
        )
        bob.status = UserStatus.ACTIVE
        db.add(CommunityUserBlock(blocker_id=alice.user.id, blocked_id=bob.id))
        db.flush()
        _assert_error_code(
            "DIRECT_MESSAGE_UNAVAILABLE",
            lambda: create_direct_conversation(db, principal=alice, payload=payload),
        )
        db.execute(CommunityUserBlock.__table__.delete())
        db.add(CommunityUserBlock(blocker_id=bob.id, blocked_id=alice.user.id))
        db.flush()
        _assert_error_code(
            "DIRECT_MESSAGE_UNAVAILABLE",
            lambda: create_direct_conversation(db, principal=alice, payload=payload),
        )
        db.execute(CommunityUserBlock.__table__.delete())
        _set_message_policy(db, username="dm_guard_bob", policy=CommunityInteractionPolicy.NOBODY)
        _assert_error_code(
            "DIRECT_MESSAGE_UNAVAILABLE",
            lambda: create_direct_conversation(db, principal=alice, payload=payload),
        )
        assert db.scalars(select(CommunityDirectConversation)).all() == []

        _set_message_policy(
            db,
            username="dm_guard_bob",
            policy=CommunityInteractionPolicy.FOLLOWING,
        )
        _assert_error_code(
            "DIRECT_MESSAGE_UNAVAILABLE",
            lambda: create_direct_conversation(db, principal=alice, payload=payload),
        )
        db.add(CommunityUserFollow(follower_id=bob.id, followed_id=alice.user.id))
        db.flush()
        assert create_direct_conversation(db, principal=alice, payload=payload).created is True


def test_create_direct_conversation_is_a_canonical_pair_and_hides_nonmembers(client) -> None:
    _register_login(client, "dm_pair_alice")
    _register_login(client, "dm_pair_bob")
    _register_login(client, "dm_pair_carol")
    with client.app.state.database.session_factory() as db:
        alice = _principal(db, "dm_pair_alice")
        bob = _principal(db, "dm_pair_bob")
        carol = _principal(db, "dm_pair_carol")
        _set_message_policy(
            db,
            username="dm_pair_alice",
            policy=CommunityInteractionPolicy.EVERYONE,
        )
        _set_message_policy(db, username="dm_pair_bob", policy=CommunityInteractionPolicy.EVERYONE)

        first = create_direct_conversation(
            db,
            principal=alice,
            payload=CommunityDirectConversationCreateRequest(recipient_username="dm_pair_bob"),
        )
        second = create_direct_conversation(
            db,
            principal=bob,
            payload=CommunityDirectConversationCreateRequest(recipient_username="dm_pair_alice"),
        )

        assert first.created is True
        assert second.created is False
        assert first.conversation.id == second.conversation.id
        assert len(db.scalars(select(CommunityDirectConversation)).all()) == 1
        assert len(db.scalars(select(CommunityDirectConversationMember)).all()) == 2
        _assert_error_code(
            "DIRECT_MESSAGE_NOT_PARTICIPANT",
            lambda: _get_member_conversation(
                db, conversation_id=first.conversation.id, user_id=carol.user.id
            ),
        )


def test_list_direct_conversations_excludes_archived_and_keeps_equal_timestamp_pages(
    client,
) -> None:
    _register_login(client, "dm_page_alice")
    _register_login(client, "dm_page_bob")
    _register_login(client, "dm_page_carol")
    _register_login(client, "dm_page_dave")
    with client.app.state.database.session_factory() as db:
        alice = _principal(db, "dm_page_alice")
        for username in ("dm_page_bob", "dm_page_carol", "dm_page_dave"):
            _set_message_policy(db, username=username, policy=CommunityInteractionPolicy.EVERYONE)
        created = [
            create_direct_conversation(
                db,
                principal=alice,
                payload=CommunityDirectConversationCreateRequest(recipient_username=username),
            )
            for username in ("dm_page_bob", "dm_page_carol", "dm_page_dave")
        ]
        timestamp = datetime(2026, 8, 16, 0, 0, tzinfo=UTC)
        for conversation in db.scalars(select(CommunityDirectConversation)).all():
            conversation.updated_at = timestamp
        archived_member = db.scalar(
            select(CommunityDirectConversationMember).where(
                CommunityDirectConversationMember.conversation_id == created[0].conversation.id,
                CommunityDirectConversationMember.user_id == alice.user.id,
            )
        )
        assert archived_member is not None
        archived_member.archived_at = timestamp
        db.commit()

        first_page = list_direct_conversations(
            db, principal=alice, cursor=None, include_archived=False, limit=1
        )
        assert first_page.has_more is True
        assert first_page.next_cursor is not None
        second_page = list_direct_conversations(
            db,
            principal=alice,
            cursor=first_page.next_cursor,
            include_archived=False,
            limit=1,
        )
        visible_usernames = {
            item.counterpart_username for item in [*first_page.items, *second_page.items]
        }
        assert visible_usernames == {"dm_page_carol", "dm_page_dave"}

        including_archived = list_direct_conversations(
            db, principal=alice, cursor=None, include_archived=True, limit=10
        )
        assert {item.counterpart_username for item in including_archived.items} == {
            "dm_page_bob",
            "dm_page_carol",
            "dm_page_dave",
        }


def test_send_direct_message_encrypts_storage_replays_and_hides_plaintext(client) -> None:
    _register_login(client, "dm_send_alice")
    _register_login(client, "dm_send_bob")
    with client.app.state.database.session_factory() as db:
        alice = _principal(db, "dm_send_alice")
        _set_message_policy(
            db,
            username="dm_send_bob",
            policy=CommunityInteractionPolicy.EVERYONE,
        )
        conversation = create_direct_conversation(
            db,
            principal=alice,
            payload=CommunityDirectConversationCreateRequest(recipient_username="dm_send_bob"),
        ).conversation
        sent = send_direct_message(
            db,
            principal=alice,
            conversation_id=conversation.id,
            payload=CommunityDirectMessageCreateRequest(
                body="只用于测试的合成私信",
                client_message_id="synthetic-client-1",
            ),
            idempotency_key="synthetic-http-key-1",
            settings=client.app.state.settings,
        )
        replayed = send_direct_message(
            db,
            principal=alice,
            conversation_id=conversation.id,
            payload=CommunityDirectMessageCreateRequest(
                body="只用于测试的合成私信",
                client_message_id="synthetic-client-1",
            ),
            idempotency_key="synthetic-http-key-1",
            settings=client.app.state.settings,
        )
        _assert_error_code(
            "DIRECT_MESSAGE_IDEMPOTENCY_CONFLICT",
            lambda: send_direct_message(
                db,
                principal=alice,
                conversation_id=conversation.id,
                payload=CommunityDirectMessageCreateRequest(
                    body="不同的合成私信正文",
                    client_message_id="synthetic-client-1",
                ),
                idempotency_key="synthetic-http-key-1",
                settings=client.app.state.settings,
            ),
        )
        db.commit()

        stored = db.scalar(select(CommunityDirectMessage))
        notification = db.scalar(select(CommunityNotification))
        outbox = db.scalar(select(CommunityNotificationOutbox))
        assert stored is not None
        assert notification is not None
        assert outbox is not None
        assert stored.ciphertext != "只用于测试的合成私信"
        assert stored.nonce
        assert sent.id == replayed.id
        assert notification.preview == "你收到一条新私信"
        assert "合成私信" not in notification.preview


def test_direct_message_access_read_state_and_member_state_are_private(client) -> None:
    _register_login(client, "dm_state_alice")
    _register_login(client, "dm_state_bob")
    with client.app.state.database.session_factory() as db:
        alice = _principal(db, "dm_state_alice")
        bob = _principal(db, "dm_state_bob")
        _set_message_policy(
            db,
            username="dm_state_bob",
            policy=CommunityInteractionPolicy.EVERYONE,
        )
        conversation = create_direct_conversation(
            db,
            principal=alice,
            payload=CommunityDirectConversationCreateRequest(recipient_username="dm_state_bob"),
        ).conversation
        send_direct_message(
            db,
            principal=alice,
            conversation_id=conversation.id,
            payload=CommunityDirectMessageCreateRequest(
                body="第一条合成私信",
                client_message_id="synthetic-state-1",
            ),
            idempotency_key="synthetic-state-http-1",
            settings=client.app.state.settings,
        )
        read = update_direct_read_state(
            db,
            principal=bob,
            conversation_id=conversation.id,
            payload=CommunityDirectReadStateUpdateRequest(last_read_sequence=1),
        )
        unchanged = update_direct_read_state(
            db,
            principal=bob,
            conversation_id=conversation.id,
            payload=CommunityDirectReadStateUpdateRequest(last_read_sequence=0),
        )
        assert read.last_read_sequence == unchanged.last_read_sequence == 1

        update_direct_member_state(
            db,
            principal=bob,
            conversation_id=conversation.id,
            payload=CommunityDirectMemberStateUpdateRequest(archived=True),
        )
        muted = update_direct_member_state(
            db,
            principal=alice,
            conversation_id=conversation.id,
            payload=CommunityDirectMemberStateUpdateRequest(
                muted_until=utc_now() + timedelta(days=7)
            ),
        )
        assert muted.muted_until is not None
        alice_state = update_direct_member_state(
            db,
            principal=alice,
            conversation_id=conversation.id,
            payload=CommunityDirectMemberStateUpdateRequest(muted_until=None),
        )
        assert alice_state.archived_at is None
        assert alice_state.muted_until is None

        db.add(CommunityUserBlock(blocker_id=bob.user.id, blocked_id=alice.user.id))
        db.flush()
        _assert_error_code(
            "DIRECT_MESSAGE_UNAVAILABLE",
            lambda: list_direct_messages(
                db,
                principal=alice,
                conversation_id=conversation.id,
                cursor=None,
                limit=20,
                settings=client.app.state.settings,
            ),
        )
        _assert_error_code(
            "DIRECT_MESSAGE_UNAVAILABLE",
            lambda: send_direct_message(
                db,
                principal=alice,
                conversation_id=conversation.id,
                payload=CommunityDirectMessageCreateRequest(
                    body="拉黑后不可发送",
                    client_message_id="synthetic-state-2",
                ),
                idempotency_key="synthetic-state-http-2",
                settings=client.app.state.settings,
            ),
        )

def test_direct_message_router_requires_auth_idempotency_and_enforces_membership(client) -> None:
    assert client.get("/api/v1/community/direct-conversations").status_code == 401
    alice = _register_login(client, "dm_router_alice")
    bob = _register_login(client, "dm_router_bob")
    missing_key = client.post(
        "/api/v1/community/direct-conversations",
        json={"recipient_username": "dm_router_bob"},
        headers={"Authorization": f"Bearer {alice['access_token']}"},
    )
    assert missing_key.status_code == 400
    assert missing_key.json()["code"] == "request.invalid_idempotency_key"
    with client.app.state.database.session_factory() as db:
        _set_message_policy(
            db,
            username="dm_router_bob",
            policy=CommunityInteractionPolicy.EVERYONE,
        )
        db.commit()
    created = client.post(
        "/api/v1/community/direct-conversations",
        json={"recipient_username": "dm_router_bob"},
        headers={
            "Authorization": f"Bearer {alice['access_token']}",
            "Idempotency-Key": "dm-router-conversation-1",
        },
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["conversation"]["id"]
    sent = client.post(
        f"/api/v1/community/direct-conversations/{conversation_id}/messages",
        json={"body": "仅用于路由测试的合成正文", "client_message_id": "dm-router-message-1"},
        headers={
            "Authorization": f"Bearer {alice['access_token']}",
            "Idempotency-Key": "dm-router-message-http-1",
        },
    )
    assert sent.status_code == 201, sent.text
    assert sent.json()["body"] == "仅用于路由测试的合成正文"
    listed = client.get(
        f"/api/v1/community/direct-conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {bob['access_token']}"},
    )
    assert listed.status_code == 200
    assert listed.json()["items"][0]["body"] == "仅用于路由测试的合成正文"