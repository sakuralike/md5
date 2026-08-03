from __future__ import annotations

from datetime import timedelta

import pyotp
from sqlalchemy import func, select

from password_detective.core.notifications import MemoryNotificationGateway
from password_detective.core.time import utc_now
from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.password_candidate import CandidateStatus, PasswordCandidate
from password_detective.db.models.risk_alert import (
    RiskAlert,
    RiskAlertEvent,
    RiskAlertNotification,
    RiskAlertNotificationKind,
    RiskAlertNotificationStatus,
    RiskAlertStatus,
)
from password_detective.db.models.user import User, UserRole
from password_detective.modules.risk_alerts.notifications import (
    dispatch_pending_notifications,
    queue_due_sla_notifications,
)


def _register_and_login(client, suffix: str) -> tuple[dict[str, str], dict[str, str]]:
    registration = {
        "username": f"risk_{suffix}",
        "email": f"risk-{suffix}@synthetic.example.com",
        "password": "SyntheticRiskAlertPass123!",
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": registration["password"]},
    )
    assert login.status_code == 200
    return registration, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _admin_headers(client, suffix: str) -> dict[str, str]:
    registration, initial_headers = _register_and_login(client, suffix)
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user.role = UserRole.ADMIN
        db.commit()

    setup = client.post("/api/v1/admin/totp/setup", headers=initial_headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert (
        client.post(
            "/api/v1/admin/totp/confirm",
            headers=initial_headers,
            json={"code": pyotp.TOTP(secret).now()},
        ).status_code
        == 200
    )
    login = client.post(
        "/api/v1/auth/login",
        json={
            "login": registration["username"],
            "password": registration["password"],
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _create_candidate(client, headers: dict[str, str], suffix: str) -> str:
    digit = str((sum(ord(char) for char in suffix) % 8) + 1)
    response = client.post(
        "/api/v1/archives/submissions",
        headers={**headers, "Idempotency-Key": f"risk-submission-{suffix}"},
        json={
            "fingerprints": [
                {"algorithm": "sha256", "digest": digit * 64},
                {"algorithm": "md5", "digest": digit * 32},
            ],
            "password": f"Synthetic-Risk-Candidate-{suffix}!",
            "authorization_confirmed": True,
            "authorization_version": "2026-08-01",
        },
    )
    assert response.status_code == 201
    return response.json()["candidate_id"]


def _feedback(
    client,
    headers: dict[str, str],
    candidate_id: str,
    suffix: str,
    outcome: str = "failure",
):
    return client.post(
        f"/api/v1/candidates/{candidate_id}/feedback",
        headers={**headers, "Idempotency-Key": f"risk-feedback-{suffix}"},
        json={"outcome": outcome},
    )


def _trigger_failure_surge(client, suffix: str) -> tuple[str, list[dict[str, str]]]:
    _, owner = _register_and_login(client, f"{suffix}_owner")
    voters = [_register_and_login(client, f"{suffix}_failure_{index}")[1] for index in range(1, 4)]
    candidate_id = _create_candidate(client, owner, suffix)
    for index, voter in enumerate(voters, start=1):
        response = _feedback(client, voter, candidate_id, f"{suffix}-{index}")
        assert response.status_code == 200
    return candidate_id, voters


def test_failure_surge_creates_one_aggregate_only_alert_and_requires_admin_mfa(client):
    candidate_id, voters = _trigger_failure_surge(client, "surge")

    with client.app.state.database.session_factory() as db:
        candidate = db.get(PasswordCandidate, candidate_id)
        assert candidate is not None and candidate.status == CandidateStatus.QUARANTINED
        alerts = list(db.scalars(select(RiskAlert)))
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.status == RiskAlertStatus.OPEN
        assert alert.independent_failure_count == 3
        assert alert.failure_weight == 3.0
        assert db.scalar(select(func.count(RiskAlertEvent.id))) == 1

    ordinary = client.get("/api/v1/admin/risk-alerts", headers=voters[0])
    assert ordinary.status_code == 403

    admin_headers = _admin_headers(client, "surge_admin")
    queue = client.get(
        "/api/v1/admin/risk-alerts",
        headers=admin_headers,
        params={"status": "open", "query": candidate_id},
    )
    assert queue.status_code == 200
    body = queue.json()
    assert body["total"] == 1
    summary = body["items"][0]
    assert summary["candidate_id"] == candidate_id
    assert summary["kind"] == "failure_surge"
    assert summary["severity"] == "high"
    assert summary["independent_failure_count"] == 3
    assert "installation_id_hash" not in summary
    assert "ip_prefix" not in summary

    detail = client.get(f"/api/v1/admin/risk-alerts/{summary['id']}", headers=admin_headers)
    assert detail.status_code == 200
    assert [event["action"] for event in detail.json()["events"]] == ["risk_alert.detected"]

    unchanged = _feedback(client, voters[-1], candidate_id, "surge-replay")
    assert unchanged.status_code == 200
    assert unchanged.json()["changed"] is False
    with client.app.state.database.session_factory() as db:
        assert db.scalar(select(func.count(RiskAlert.id))) == 1
        assert db.scalar(select(func.count(RiskAlertEvent.id))) == 1


def test_admin_can_acknowledge_resolve_and_replay_transition_idempotently(client):
    candidate_id, voters = _trigger_failure_surge(client, "handling")
    admin_headers = _admin_headers(client, "handling_admin")
    queue = client.get(
        "/api/v1/admin/risk-alerts", headers=admin_headers, params={"query": candidate_id}
    )
    alert_id = queue.json()["items"][0]["id"]

    acknowledge_headers = {
        **admin_headers,
        "Idempotency-Key": "risk-alert-acknowledge-0001",
        "X-Request-ID": "synthetic-risk-acknowledge-request",
    }
    acknowledge_payload = {
        "target_status": "acknowledged",
        "resolution_code": "admin.investigation_started",
        "resolution_note": "合成说明：开始核查短时间窗失败激增。",
    }
    first = client.post(
        f"/api/v1/admin/risk-alerts/{alert_id}/transition",
        headers=acknowledge_headers,
        json=acknowledge_payload,
    )
    repeated = client.post(
        f"/api/v1/admin/risk-alerts/{alert_id}/transition",
        headers=acknowledge_headers,
        json=acknowledge_payload,
    )
    assert first.status_code == repeated.status_code == 200
    assert first.json()["event_id"] == repeated.json()["event_id"]
    assert first.json()["current_status"] == "acknowledged"

    conflict = client.post(
        f"/api/v1/admin/risk-alerts/{alert_id}/transition",
        headers=acknowledge_headers,
        json={
            "target_status": "resolved",
            "resolution_code": "admin.false_positive",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "request.idempotency_conflict"

    resolved = client.post(
        f"/api/v1/admin/risk-alerts/{alert_id}/transition",
        headers={
            **admin_headers,
            "Idempotency-Key": "risk-alert-resolve-0001",
            "X-Request-ID": "synthetic-risk-resolve-request",
        },
        json={
            "target_status": "resolved",
            "resolution_code": "admin.mitigated",
            "resolution_note": "合成说明：风险已处置。",
        },
    )
    assert resolved.status_code == 200
    assert resolved.json()["current_status"] == "resolved"

    with client.app.state.database.session_factory() as db:
        alert = db.get(RiskAlert, alert_id)
        assert alert is not None
        assert alert.status == RiskAlertStatus.RESOLVED
        assert alert.resolved_by_id is not None
        assert db.scalar(select(func.count(RiskAlertEvent.id))) == 3
        audits = list(
            db.scalars(
                select(AuditLog)
                .where(AuditLog.target_type == "risk_alert", AuditLog.target_id == alert_id)
                .order_by(AuditLog.created_at)
            )
        )
        assert len(audits) == 2
        assert all("resolution_note" not in audit.details for audit in audits)
        assert all("installation_id_hash" not in audit.details for audit in audits)
        assert all("ip_prefix" not in audit.details for audit in audits)
        assert all(audit.ip_prefix is None for audit in audits)

    changed_to_success = _feedback(
        client, voters[-1], candidate_id, "handling-revision-success", outcome="success"
    )
    assert changed_to_success.status_code == 200
    changed_to_failure = _feedback(
        client, voters[-1], candidate_id, "handling-revision-failure", outcome="failure"
    )
    assert changed_to_failure.status_code == 200
    with client.app.state.database.session_factory() as db:
        alerts = list(
            db.scalars(
                select(RiskAlert)
                .where(RiskAlert.candidate_id == candidate_id)
                .order_by(RiskAlert.created_at)
            )
        )
        assert len(alerts) == 2
        assert alerts[0].status == RiskAlertStatus.RESOLVED
        assert alerts[1].status == RiskAlertStatus.OPEN
        assert db.scalar(select(func.count(RiskAlertEvent.id))) == 4


def test_alert_sla_assignment_and_notification_outbox_close_the_operator_loop(
    client, notifications: MemoryNotificationGateway
):
    admin_headers = _admin_headers(client, "sla_admin")
    candidate_id, voters = _trigger_failure_surge(client, "sla")

    operators = client.get("/api/v1/admin/risk-alerts/operators", headers=admin_headers)
    assert operators.status_code == 200
    assert len(operators.json()) == 1
    operator = operators.json()[0]

    queue = client.get(
        "/api/v1/admin/risk-alerts",
        headers=admin_headers,
        params={"query": candidate_id},
    )
    assert queue.status_code == 200
    summary = queue.json()["items"][0]
    alert_id = summary["id"]
    assert summary["sla_rule_version"] == "risk-alert-sla-v1"
    assert summary["sla_state"] == "within_sla"
    assert summary["assigned_to_id"] is None

    ordinary_registration = _register_and_login(client, "sla_ordinary")[0]
    with client.app.state.database.session_factory() as db:
        ordinary = db.scalar(select(User).where(User.username == ordinary_registration["username"]))
        assert ordinary is not None
        ordinary_id = ordinary.id
    invalid = client.post(
        f"/api/v1/admin/risk-alerts/{alert_id}/assign",
        headers={**admin_headers, "Idempotency-Key": "risk-invalid-assignee"},
        json={"assignee_id": ordinary_id},
    )
    assert invalid.status_code == 422

    assignment_headers = {**admin_headers, "Idempotency-Key": "risk-valid-assignee"}
    assignment = client.post(
        f"/api/v1/admin/risk-alerts/{alert_id}/assign",
        headers=assignment_headers,
        json={"assignee_id": operator["id"], "assignment_note": "合成值班指派"},
    )
    assert assignment.status_code == 200
    assert assignment.json()["current_assignee_id"] == operator["id"]
    replay = client.post(
        f"/api/v1/admin/risk-alerts/{alert_id}/assign",
        headers=assignment_headers,
        json={"assignee_id": operator["id"], "assignment_note": "合成值班指派"},
    )
    assert replay.status_code == 200
    assert replay.json() == assignment.json()

    assigned_queue = client.get(
        "/api/v1/admin/risk-alerts",
        headers=admin_headers,
        params={"assigned_to_id": operator["id"]},
    )
    assert assigned_queue.status_code == 200
    assert assigned_queue.json()["total"] == 1

    with client.app.state.database.session_factory() as db:
        alert = db.get(RiskAlert, alert_id)
        assert alert is not None
        assert alert.assigned_to_id == operator["id"]
        kinds = list(
            db.scalars(
                select(RiskAlertNotification.kind)
                .where(RiskAlertNotification.alert_id == alert_id)
                .order_by(RiskAlertNotification.created_at)
            )
        )
        assert kinds == [
            RiskAlertNotificationKind.DETECTED,
            RiskAlertNotificationKind.ASSIGNED,
        ]
        result = dispatch_pending_notifications(
            db,
            notifications,
            now=utc_now() + timedelta(seconds=1),
        )
        assert result == {"selected": 2, "sent": 2, "failed": 0}

    assert [message.kind for message in notifications.risk_alert_messages] == [
        "detected",
        "assigned",
    ]
    assert all(
        message.recipient.endswith("@synthetic.example.com")
        for message in notifications.risk_alert_messages
    )
    assert all(message.alert_id == alert_id for message in notifications.risk_alert_messages)
    assert all(message.severity == "high" for message in notifications.risk_alert_messages)

    detail = client.get(f"/api/v1/admin/risk-alerts/{alert_id}", headers=admin_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["assigned_to_username"] == operator["username"]
    assert [event["action"] for event in body["events"]] == [
        "risk_alert.detected",
        "risk_alert.assigned",
    ]
    assert all(item["status"] == "sent" for item in body["notifications"])
    assert all("recipient_email" not in item for item in body["notifications"])
    assert all("ip_prefix" not in item for item in body["notifications"])
    assert voters


def test_alert_sla_overdue_notifications_are_deduplicated_and_queryable(client):
    admin_headers = _admin_headers(client, "overdue_admin")
    candidate_id, _ = _trigger_failure_surge(client, "overdue")
    operator = client.get("/api/v1/admin/risk-alerts/operators", headers=admin_headers).json()[0]
    summary = client.get(
        "/api/v1/admin/risk-alerts",
        headers=admin_headers,
        params={"query": candidate_id},
    ).json()["items"][0]
    alert_id = summary["id"]
    assert (
        client.post(
            f"/api/v1/admin/risk-alerts/{alert_id}/assign",
            headers={**admin_headers, "Idempotency-Key": "risk-overdue-assign"},
            json={"assignee_id": operator["id"]},
        ).status_code
        == 200
    )

    observed_at = utc_now()
    with client.app.state.database.session_factory() as db:
        alert = db.get(RiskAlert, alert_id)
        assert alert is not None
        alert.acknowledge_due_at = observed_at - timedelta(minutes=1)
        db.commit()
        assert queue_due_sla_notifications(db, now=observed_at) == 1
        assert queue_due_sla_notifications(db, now=observed_at) == 0

    overdue_queue = client.get(
        "/api/v1/admin/risk-alerts",
        headers=admin_headers,
        params={"overdue": True, "query": candidate_id},
    )
    assert overdue_queue.status_code == 200
    assert overdue_queue.json()["total"] == 1
    assert overdue_queue.json()["items"][0]["sla_state"] == "acknowledgement_overdue"

    acknowledged = client.post(
        f"/api/v1/admin/risk-alerts/{alert_id}/transition",
        headers={**admin_headers, "Idempotency-Key": "risk-overdue-ack"},
        json={
            "target_status": "acknowledged",
            "resolution_code": "admin.investigation_started",
        },
    )
    assert acknowledged.status_code == 200

    with client.app.state.database.session_factory() as db:
        alert = db.get(RiskAlert, alert_id)
        assert alert is not None
        alert.resolve_due_at = observed_at - timedelta(minutes=1)
        db.commit()
        assert queue_due_sla_notifications(db, now=observed_at) == 1
        assert queue_due_sla_notifications(db, now=observed_at) == 0
        overdue_kinds = list(
            db.scalars(
                select(RiskAlertNotification.kind).where(
                    RiskAlertNotification.alert_id == alert_id,
                    RiskAlertNotification.kind.in_(
                        [
                            RiskAlertNotificationKind.ACKNOWLEDGEMENT_OVERDUE,
                            RiskAlertNotificationKind.RESOLUTION_OVERDUE,
                        ]
                    ),
                )
            )
        )
        assert set(overdue_kinds) == {
            RiskAlertNotificationKind.ACKNOWLEDGEMENT_OVERDUE,
            RiskAlertNotificationKind.RESOLUTION_OVERDUE,
        }
        assert (
            db.scalar(
                select(func.count(RiskAlertNotification.id)).where(
                    RiskAlertNotification.status == RiskAlertNotificationStatus.PENDING
                )
            )
            == 4
        )

    detail = client.get(f"/api/v1/admin/risk-alerts/{alert_id}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["sla_state"] == "resolution_overdue"
