from __future__ import annotations

from sqlalchemy import select

from password_detective.db.models.community import (
    CommunityDirectConversation,
    CommunityDirectConversationMember,
    CommunityDirectEvent,
    CommunityDirectEventType,
    CommunityDirectMessage,
)
from password_detective.db.models.user import User
from password_detective.modules.community.direct_message_events import (
    DirectEventDraft,
    append_direct_events,
    conversation_unread_count,
    latest_direct_event_sequence,
    list_direct_events,
    resolve_direct_stream_cursor,
    total_direct_unread_count,
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
