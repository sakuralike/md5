from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from test_m4_trust_cases import _admin_headers, _create_candidate, _register_and_login

from password_detective.core.notifications import MemoryNotificationGateway
from password_detective.core.time import utc_now
from password_detective.db.models.trust_case import (
    TrustCaseNotification,
    TrustCaseNotificationStatus,
)
from password_detective.modules.trust_cases.notifications import (
    dispatch_pending_case_notifications,
)


class _FailingGateway:
    provider_name = "synthetic-failure"

    def send_trust_case_result(self, **kwargs: str) -> str | None:
        del kwargs
        raise RuntimeError("synthetic delivery failure")


def _create_resolved_case(client):
    _, owner_headers = _register_and_login(client, "wp2_notification_owner")
    candidate_id = _create_candidate(client, owner_headers, "9")
    created = client.post(
        "/api/v1/trust/reports",
        headers={**owner_headers, "Idempotency-Key": "wp2-notification-report-0001"},
        json={
            "candidate_id": candidate_id,
            "reason_code": "report.other",
            "description": "合成案件结果通知测试。",
        },
    )
    admin_headers = _admin_headers(client, "wp2_notification_admin")
    resolved = client.post(
        f"/api/v1/admin/trust-cases/{created.json()['id']}/resolve",
        headers={**admin_headers, "Idempotency-Key": "wp2-notification-resolve-0001"},
        json={
            "expected_version": 1,
            "resolution_code": "admin.no_violation",
            "resolution_note": "合成处置说明：未发现违规。",
        },
    )
    assert resolved.status_code == 200
    return created.json()["id"], owner_headers, admin_headers


def test_resolution_outbox_dispatches_minimum_disclosure_and_is_visible(client):
    case_id, owner_headers, admin_headers = _create_resolved_case(client)
    gateway = MemoryNotificationGateway()
    with client.app.state.database.session_factory() as db:
        notification = db.scalar(
            select(TrustCaseNotification).where(TrustCaseNotification.case_id == case_id)
        )
        assert notification is not None
        assert notification.status == TrustCaseNotificationStatus.PENDING
        result = dispatch_pending_case_notifications(db, gateway)
    assert result == {"processed": 1, "sent": 1, "failed": 0}
    assert len(gateway.trust_case_messages) == 1
    delivered = gateway.trust_case_messages[0]
    assert delivered.case_id == case_id
    assert delivered.case_kind == "report"
    assert delivered.case_status == "dismissed"
    assert delivered.resolution_code == "admin.no_violation"

    detail = client.get(f"/api/v1/trust/cases/{case_id}", headers=owner_headers)
    assert detail.status_code == 200
    assert detail.json()["notifications"][0]["status"] == "sent"
    listing = client.get(
        "/api/v1/admin/trust-cases/notifications",
        headers=admin_headers,
        params={"status": "sent"},
    )
    assert listing.status_code == 200
    assert listing.json()["items"][0]["case_id"] == case_id


def test_notification_retry_fails_closed_and_admin_replay_is_idempotent(client):
    case_id, _, admin_headers = _create_resolved_case(client)
    now = utc_now()
    gateway = _FailingGateway()
    with client.app.state.database.session_factory() as db:
        for offset in (0, 10, 30):
            dispatch_pending_case_notifications(
                db, gateway, now=now + timedelta(minutes=offset)
            )
        notification = db.scalar(
            select(TrustCaseNotification).where(TrustCaseNotification.case_id == case_id)
        )
        assert notification is not None
        assert notification.status == TrustCaseNotificationStatus.FAILED
        assert notification.attempts == 3
        notification_id = notification.id

    headers = {
        **admin_headers,
        "Idempotency-Key": "wp2-notification-replay-0001",
        "X-Request-ID": "synthetic-notification-replay",
    }
    payload = {
        "reason_code": "admin.delivery_retry",
        "note": "合成重放说明。",
    }
    replayed = client.post(
        f"/api/v1/admin/trust-cases/notifications/{notification_id}/replay",
        headers=headers,
        json=payload,
    )
    repeated = client.post(
        f"/api/v1/admin/trust-cases/notifications/{notification_id}/replay",
        headers=headers,
        json=payload,
    )
    assert replayed.status_code == repeated.status_code == 200
    assert replayed.json() == repeated.json()
    assert replayed.json()["status"] == "pending"
    assert replayed.json()["attempts"] == 0
    assert replayed.json()["replay_count"] == 1
