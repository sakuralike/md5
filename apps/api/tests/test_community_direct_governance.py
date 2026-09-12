from __future__ import annotations

from sqlalchemy import select

from password_detective.core.time import utc_now
from password_detective.db.models.community import (
    CommunityDirectMessageReport,
    CommunityDirectMessageReportStatus,
    CommunityInteractionPolicy,
    CommunityPublicProfile,
)
from password_detective.db.models.user import User, UserRole


def _register_and_login(client, *, username: str, email: str) -> dict:
    password = "SyntheticPass123!"
    assert client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": password},
    ).status_code == 201
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        user.email_verified_at = utc_now()
        db.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"login": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()


def _headers(tokens: dict, key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        "Idempotency-Key": key,
    }


def _create_message(client) -> tuple[dict, dict, dict]:
    sender = _register_and_login(
        client,
        username="direct_report_sender",
        email="direct-report-sender@example.com",
    )
    recipient = _register_and_login(
        client,
        username="direct_report_recipient",
        email="direct-report-recipient@example.com",
    )
    with client.app.state.database.session_factory() as db:
        recipient_user = db.scalar(select(User).where(User.username == "direct_report_recipient"))
        assert recipient_user is not None
        profile = db.get(CommunityPublicProfile, recipient_user.id)
        if profile is None:
            profile = CommunityPublicProfile(
                user_id=recipient_user.id,
                display_name=recipient_user.username,
                avatar_seed=recipient_user.id.replace("-", "")[:24].ljust(24, "0"),
            )
            db.add(profile)
        profile.message_policy = CommunityInteractionPolicy.EVERYONE
        db.commit()
    conversation = client.post(
        "/api/v1/community/direct-conversations",
        json={"recipient_username": "direct_report_recipient"},
        headers=_headers(sender, "direct-report-conversation-001"),
    )
    assert conversation.status_code == 201
    conversation_id = conversation.json()["conversation"]["id"]
    message = client.post(
        f"/api/v1/community/direct-conversations/{conversation_id}/messages",
        json={"body": "合成的骚扰消息内容", "client_message_id": "direct-report-message-001"},
        headers=_headers(sender, "direct-report-message-001"),
    )
    assert message.status_code == 201
    return sender, recipient, message.json()


def _admin_login(client) -> dict[str, str]:
    tokens = _register_and_login(
        client,
        username="direct_report_admin",
        email="direct-report-admin@example.com",
    )
    with client.app.state.database.session_factory() as db:
        admin = db.scalar(select(User).where(User.username == "direct_report_admin"))
        assert admin is not None
        admin.role = UserRole.ADMIN
        db.commit()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_member_can_report_specific_direct_message_once(client):
    _, recipient, message = _create_message(client)
    payload = {
        "reason": "harassment",
        "details": "该合成消息用于验证私信举报的最小披露治理流程。",
    }
    created = client.post(
        f"/api/v1/community/messages/{message['id']}/reports",
        json=payload,
        headers=_headers(recipient, "direct-report-create-001"),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["message_id"] == message["id"]
    assert body["reason"] == "harassment"
    assert body["status"] == "open"
    assert "body" not in body
    assert "ciphertext" not in body

    replay = client.post(
        f"/api/v1/community/messages/{message['id']}/reports",
        json=payload,
        headers=_headers(recipient, "direct-report-create-001"),
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == body["id"]

    duplicate = client.post(
        f"/api/v1/community/messages/{message['id']}/reports",
        json=payload,
        headers=_headers(recipient, "direct-report-create-002"),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "community.direct_message_report_already_open"

    with client.app.state.database.session_factory() as db:
        report = db.scalar(
            select(CommunityDirectMessageReport).where(
                CommunityDirectMessageReport.id == body["id"]
            )
        )
        assert report is not None
        assert report.status == CommunityDirectMessageReportStatus.OPEN


def test_admin_can_read_reported_message_in_case_context_and_remove_it(client):
    _, recipient, message = _create_message(client)
    report = client.post(
        f"/api/v1/community/messages/{message['id']}/reports",
        json={"reason": "harassment", "details": "合成消息举报详情用于验证管理员最小披露。"},
        headers=_headers(recipient, "direct-report-admin-case-001"),
    )
    assert report.status_code == 201
    admin = _admin_login(client)
    queue = client.get("/api/v1/admin/community/message-reports?status=open", headers=admin)
    assert queue.status_code == 200
    assert queue.json()["total"] == 1
    assert "message_body" not in queue.json()["items"][0]

    detail = client.get(
        f"/api/v1/admin/community/message-reports/{report.json()['id']}", headers=admin
    )
    assert detail.status_code == 200
    assert detail.json()["message_body"] == "合成的骚扰消息内容"

    resolved = client.post(
        f"/api/v1/admin/community/message-reports/{report.json()['id']}/resolve",
        json={"decision": "remove_message", "note": "确认消息违规，移除消息并保留案件审计。"},
        headers={**admin, "Idempotency-Key": "direct-report-admin-resolve-001"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["message_removed"] is True
    assert resolved.json()["report"]["status"] == "resolved"

    after = client.get(
        f"/api/v1/admin/community/message-reports/{report.json()['id']}", headers=admin
    )
    assert after.status_code == 200
    assert after.json()["message_body"] is None
    messages = client.get(
        f"/api/v1/community/direct-conversations/{message['conversation_id']}/messages",
        headers={"Authorization": f"Bearer {recipient['access_token']}"},
    )
    assert messages.status_code == 200
    assert all(item["id"] != message["id"] for item in messages.json()["items"])


def test_sender_enters_cooldown_after_burst_of_direct_messages(client):
    sender, _, message = _create_message(client)
    conversation_id = message["conversation_id"]
    for index in range(2, 6):
        sent = client.post(
            f"/api/v1/community/direct-conversations/{conversation_id}/messages",
            json={"body": f"合成批量消息 {index}", "client_message_id": f"direct-burst-{index}"},
            headers=_headers(sender, f"direct-burst-key-{index:03d}"),
        )
        assert sent.status_code == 201

    blocked = client.post(
        f"/api/v1/community/direct-conversations/{conversation_id}/messages",
        json={"body": "合成批量消息 6", "client_message_id": "direct-burst-6"},
        headers=_headers(sender, "direct-burst-key-006"),
    )
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "community.direct_message_cooldown"
    assert blocked.json()["details"]["retry_after_seconds"] > 0


def test_non_member_cannot_report_a_direct_message(client):
    _, _, message = _create_message(client)
    outsider = _register_and_login(
        client,
        username="direct_report_outsider",
        email="direct-report-outsider@example.com",
    )
    denied = client.post(
        f"/api/v1/community/messages/{message['id']}/reports",
        json={"reason": "spam", "details": "合成非成员举报失败路径说明。"},
        headers=_headers(outsider, "direct-report-outsider-001"),
    )
    assert denied.status_code == 404
    assert denied.json()["code"] == "DIRECT_MESSAGE_NOT_PARTICIPANT"
