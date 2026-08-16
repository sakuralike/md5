from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from password_detective.db import models  # noqa: F401
from password_detective.db.base import Base
from password_detective.db.models.community import (
    CommunityNotificationKind,
    CommunityNotificationSource,
)


def test_direct_messages_revision_remains_in_release_history() -> None:
    api_directory = Path(__file__).resolve().parents[1]
    config = Config(str(api_directory / "alembic.ini"))
    config.set_main_option("script_location", str(api_directory / "alembic"))

    script = ScriptDirectory.from_config(config)
    assert script.get_revision("20260816_0044") is not None
    assert script.get_revision("20260816_0045").down_revision == "20260816_0044"


def test_direct_message_tables_have_canonical_pair_constraints_and_indexes() -> None:
    conversation = Base.metadata.tables["community_direct_conversations"]
    member = Base.metadata.tables["community_direct_conversation_members"]
    message = Base.metadata.tables["community_direct_messages"]

    assert {item.name for item in conversation.constraints} >= {
        "uq_community_direct_conversation_pair"
    }
    assert {item.name for item in member.constraints} >= {"uq_community_direct_member"}
    assert {item.name for item in message.constraints} >= {
        "uq_community_direct_message_sequence",
        "uq_community_direct_sender_client_message",
    }
    assert {index.name for index in member.indexes} >= {
        "ix_community_direct_member_user_updated"
    }
    assert {index.name for index in message.indexes} >= {
        "ix_community_direct_message_conversation_sequence"
    }


def test_direct_message_models_store_only_encrypted_body_fields() -> None:
    message = Base.metadata.tables["community_direct_messages"]
    member = Base.metadata.tables["community_direct_conversation_members"]

    assert {"ciphertext", "nonce", "key_version", "client_message_id", "sequence"} <= set(
        message.columns.keys()
    )
    assert "body" not in message.columns
    assert {"last_read_sequence", "archived_at", "muted_until"} <= set(member.columns.keys())


def test_direct_message_notification_enums_are_available() -> None:
    assert CommunityNotificationKind.DIRECT_MESSAGE.value == "direct_message"
    assert CommunityNotificationSource.DIRECT_MESSAGE.value == "direct_message"
