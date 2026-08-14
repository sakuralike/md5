from __future__ import annotations

import pyotp
from sqlalchemy import select

from password_detective.core.time import utc_now
from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.community import (
    CommunityNotification,
    CommunityNotificationKind,
    CommunityNotificationOutbox,
    CommunityNotificationOutboxStatus,
    CommunityNotificationSource,
)
from password_detective.db.models.user import User, UserRole
from password_detective.modules.community.notification_service import (
    dispatch_pending_notification_events,
)

PASSWORD = "SyntheticCommunityOutbox123!"


def _register_user(client, suffix: str) -> str:
    payload = {
        "username": f"outbox_user_{suffix}",
        "email": f"outbox-user-{suffix}@synthetic.example.com",
        "password": PASSWORD,
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == payload["username"]))
        assert user is not None
        return user.id


def _privileged_session(client, suffix: str, role: UserRole) -> tuple[dict[str, str], str]:
    user_id = _register_user(client, suffix)
    login = client.post(
        "/api/v1/auth/login",
        json={"login": f"outbox_user_{suffix}", "password": PASSWORD},
    )
    assert login.status_code == 200
    initial_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    with client.app.state.database.session_factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        user.role = role
        db.commit()
    setup = client.post("/api/v1/admin/totp/setup", headers=initial_headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    confirm = client.post(
        "/api/v1/admin/totp/confirm",
        headers=initial_headers,
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert confirm.status_code == 200
    authenticated = client.post(
        "/api/v1/auth/login",
        json={
            "login": f"outbox_user_{suffix}",
            "password": PASSWORD,
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert authenticated.status_code == 200
    return {"Authorization": f"Bearer {authenticated.json()['access_token']}"}, secret


def _failed_event(client, suffix: str) -> str:
    actor_id = _register_user(client, f"actor_{suffix}")
    recipient_id = _register_user(client, f"recipient_{suffix}")
    now = utc_now()
    with client.app.state.database.session_factory() as db:
        notification = CommunityNotification(
            recipient_id=recipient_id,
            actor_id=actor_id,
            kind=CommunityNotificationKind.FOLLOW,
            source_type=CommunityNotificationSource.USER,
            source_id=actor_id,
            preview="合成关注通知",
        )
        db.add(notification)
        db.flush()
        event = CommunityNotificationOutbox(
            notification_id=notification.id,
            recipient_id=recipient_id,
            dedupe_key=f"synthetic:outbox:{suffix}",
            status=CommunityNotificationOutboxStatus.FAILED,
            attempts=5,
            available_at=now,
            failed_at=now,
            last_error_code="community.notification_dispatch_failed",
        )
        db.add(event)
        db.commit()
        return event.id


def test_notification_outbox_metrics_and_failure_query_are_admin_only(client):
    event_id = _failed_event(client, "query")
    moderator_headers, _ = _privileged_session(client, "moderator", UserRole.MODERATOR)
    forbidden = client.get(
        "/api/v1/admin/community/notification-outbox/metrics",
        headers=moderator_headers,
    )
    assert forbidden.status_code == 403

    admin_headers, _ = _privileged_session(client, "admin_query", UserRole.ADMIN)
    metrics = client.get(
        "/api/v1/admin/community/notification-outbox/metrics",
        headers=admin_headers,
    )
    assert metrics.status_code == 200
    assert metrics.json()["failed_count"] >= 1
    assert metrics.json()["failed_last_24_hours"] >= 1

    listed = client.get(
        "/api/v1/admin/community/notification-outbox",
        headers=admin_headers,
        params={
            "status": "failed",
            "kind": "follow",
            "error_code": "community.notification_dispatch_failed",
        },
    )
    assert listed.status_code == 200, listed.text
    item = next(item for item in listed.json()["items"] if item["id"] == event_id)
    assert item["attempts"] == 5
    assert item["replay_count"] == 0
    assert item["last_error_code"] == "community.notification_dispatch_failed"


def test_admin_replays_failed_notification_with_fresh_mfa_reauthentication(client):
    event_id = _failed_event(client, "replay")
    admin_headers, secret = _privileged_session(client, "admin_replay", UserRole.ADMIN)
    reauthenticated = client.post(
        "/api/v1/admin/auth/reauthenticate",
        headers=admin_headers,
        json={
            "purpose": "admin_community_notification_ops",
            "current_password": PASSWORD,
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert reauthenticated.status_code == 200, reauthenticated.text
    assert reauthenticated.json()["purpose"] == "admin_community_notification_ops"
    payload = {
        "reason": "合成故障已排除，允许重新进入投递队列",
        "reauth_token": reauthenticated.json()["reauth_token"],
    }
    headers = {
        **admin_headers,
        "Idempotency-Key": "community-outbox-replay-synthetic-0001",
    }
    replayed = client.post(
        f"/api/v1/admin/community/notification-outbox/{event_id}/replay",
        headers=headers,
        json=payload,
    )
    assert replayed.status_code == 200, replayed.text
    body = replayed.json()
    assert body["event"]["status"] == "pending"
    assert body["event"]["attempts"] == 0
    assert body["event"]["replay_count"] == 1
    assert body["event"]["last_error_code"] is None

    idempotent_replay = client.post(
        f"/api/v1/admin/community/notification-outbox/{event_id}/replay",
        headers=headers,
        json=payload,
    )
    assert idempotent_replay.status_code == 200
    assert idempotent_replay.json() == body

    with client.app.state.database.session_factory() as db:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "community.notification_outbox.replay",
                AuditLog.target_id == event_id,
            )
        )
        assert audit is not None
        assert audit.details["previous"]["attempts"] == 5
        result = dispatch_pending_notification_events(db)
        assert result["delivered"] >= 1
        event = db.get(CommunityNotificationOutbox, event_id)
        assert event is not None
        assert event.status == CommunityNotificationOutboxStatus.DELIVERED
        assert event.attempts == 1
