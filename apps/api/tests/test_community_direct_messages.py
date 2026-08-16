from __future__ import annotations

import pytest
from pydantic import ValidationError

from password_detective.modules.community.schemas import (
    CommunityDirectConversationCreateRequest,
    CommunityDirectConversationCreateResponse,
    CommunityDirectConversationResponse,
    CommunityDirectMemberStateUpdateRequest,
    CommunityDirectMessageCreateRequest,
    CommunityDirectMessageResponse,
    CommunityDirectReadStateUpdateRequest,
)


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
