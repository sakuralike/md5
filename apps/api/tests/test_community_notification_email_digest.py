from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from password_detective.core.notifications import MemoryNotificationGateway
from password_detective.core.time import utc_now
from password_detective.db.models.community import (
    CommunityNotificationEmailDigest,
    CommunityNotificationEmailDigestStatus,
    CommunityNotificationKind,
    CommunityNotificationOutbox,
    CommunityNotificationPreference,
    CommunityNotificationSource,
)
from password_detective.db.models.user import User
from password_detective.modules.community.notification_service import (
    create_notification,
    dispatch_pending_email_digests,
    notification_channels,
)

PASSWORD = "SyntheticEmailDigest123!"


def _register_user(client, suffix: str) -> str:
    payload = {
        "username": f"digest_{suffix}",
        "email": f"digest-{suffix}@synthetic.example.com",
        "password": PASSWORD,
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == payload["username"]))
        assert user is not None
        return user.id


def test_email_only_preference_creates_durable_digest_and_not_in_app_event(client) -> None:
    actor_id = _register_user(client, "actor")
    recipient_id = _register_user(client, "recipient")
    with client.app.state.database.session_factory() as db:
        db.add(
            CommunityNotificationPreference(
                user_id=recipient_id,
                kind=CommunityNotificationKind.REPLY,
                in_app_enabled=False,
                email_digest_enabled=True,
            )
        )
        db.flush()
        assert notification_channels(db, recipient_id, CommunityNotificationKind.REPLY) == (
            False,
            True,
        )
        notification = create_notification(
            db,
            recipient_id=recipient_id,
            actor_id=actor_id,
            kind=CommunityNotificationKind.REPLY,
            source_type=CommunityNotificationSource.COMMENT,
            source_id="synthetic-comment-001",
            post_id=None,
            comment_id=None,
            preview="合成回复通知",
        )
        assert notification is not None
        db.commit()
        event = db.scalar(
            select(CommunityNotificationOutbox).where(
                CommunityNotificationOutbox.notification_id == notification.id
            )
        )
        assert event is None, (event.notification_id, notification.id) if event else None
        digest = db.scalar(
            select(CommunityNotificationEmailDigest).where(
                CommunityNotificationEmailDigest.recipient_id == recipient_id
            )
        )
        assert digest is not None
        assert digest.status == CommunityNotificationEmailDigestStatus.PENDING
        digest.window_ends_at = utc_now() - timedelta(seconds=1)
        digest.available_at = utc_now() - timedelta(seconds=1)
        db.commit()

    gateway = MemoryNotificationGateway()
    with client.app.state.database.session_factory() as db:
        result = dispatch_pending_email_digests(db, gateway)
        digest = db.scalar(
            select(CommunityNotificationEmailDigest).where(
                CommunityNotificationEmailDigest.recipient_id == recipient_id
            )
        )
        assert result == {"processed": 1, "sent": 1, "retried": 0, "failed": 0, "suppressed": 0}
        assert digest is not None
        assert digest.status == CommunityNotificationEmailDigestStatus.SENT
    assert gateway.community_digest_messages[0].item_count == 1


def _login_headers(client, user_id: str, suffix: str) -> dict[str, str]:
    with client.app.state.database.session_factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        user.email_verified_at = utc_now()
        db.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"login": f"digest_{suffix}", "password": PASSWORD},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_email_only_preference_hides_existing_in_app_notification_paths(client) -> None:
    actor_id = _register_user(client, "vis_actor")
    recipient_id = _register_user(client, "vis_recipient")
    with client.app.state.database.session_factory() as db:
        notification = create_notification(
            db,
            recipient_id=recipient_id,
            actor_id=actor_id,
            kind=CommunityNotificationKind.REPLY,
            source_type=CommunityNotificationSource.COMMENT,
            source_id="synthetic-comment-visibility-001",
            post_id=None,
            comment_id=None,
            preview="合成历史回复通知",
        )
        assert notification is not None
        notification_id = notification.id
        preference = CommunityNotificationPreference(
            user_id=recipient_id,
            kind=CommunityNotificationKind.REPLY,
            in_app_enabled=False,
            email_digest_enabled=True,
        )
        db.add(preference)
        db.commit()

    headers = _login_headers(client, recipient_id, "vis_recipient")
    listing = client.get("/api/v1/community/notifications", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["items"] == []
    assert listing.json()["unread_count"] == 0

    read = client.post(
        f"/api/v1/community/notifications/{notification_id}/read",
        headers={**headers, "Idempotency-Key": "synthetic-email-only-read"},
    )
    assert read.status_code == 404
