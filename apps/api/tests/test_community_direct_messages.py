from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.models.community import (
    CommunityDirectConversation,
    CommunityDirectConversationMember,
    CommunityInteractionPolicy,
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
