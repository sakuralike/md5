from __future__ import annotations

from sqlalchemy import select
from test_m4_trust_cases import _admin_headers, _create_candidate, _register_and_login

from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.trust_case import TrustCase, TrustCaseEvent
from password_detective.db.models.user import User


def test_case_assignment_reopen_and_version_conflicts_are_idempotent(client):
    _, owner_headers = _register_and_login(client, "wp2_assignment_owner")
    candidate_id = _create_candidate(client, owner_headers, "6")
    created = client.post(
        "/api/v1/trust/reports",
        headers={**owner_headers, "Idempotency-Key": "wp2-assignment-report-0001"},
        json={
            "candidate_id": candidate_id,
            "reason_code": "report.policy_violation",
            "description": "合成指派测试案件。",
        },
    )
    assert created.status_code == 201
    case_id = created.json()["id"]
    assert created.json()["version"] == 1

    admin_headers = _admin_headers(client, "wp2_assignment_admin")
    target_headers = _admin_headers(client, "wp2_assignment_target")
    with client.app.state.database.session_factory() as db:
        target = db.scalar(select(User).where(User.username == "trust_wp2_assignment_target"))
        assert target is not None
        target_id = target.id

    assign_headers = {
        **admin_headers,
        "Idempotency-Key": "wp2-case-assign-0001",
        "X-Request-ID": "synthetic-wp2-assign",
    }
    assign_payload = {
        "expected_version": 1,
        "assignee_id": target_id,
        "reason_code": "admin.assigned",
        "note": "合成指派说明，不进入审计摘要。",
    }
    assigned = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/assign",
        headers=assign_headers,
        json=assign_payload,
    )
    repeated = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/assign",
        headers=assign_headers,
        json=assign_payload,
    )
    assert assigned.status_code == repeated.status_code == 200
    assert assigned.json() == repeated.json()
    assert assigned.json()["version"] == 2
    assert assigned.json()["current_assignee_id"] == target_id

    stale_assign = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/assign",
        headers={**admin_headers, "Idempotency-Key": "wp2-case-assign-stale-0001"},
        json={
            **assign_payload,
            "expected_version": 1,
            "assignee_id": admin_headers["Authorization"].split("Bearer ", 1)[1][:36],
            "reason_code": "admin.reassigned",
        },
    )
    assert stale_assign.status_code == 409
    assert stale_assign.json()["code"] == "trust.case_version_conflict"
    assert stale_assign.json()["details"]["current_version"] == 2

    review = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/transition",
        headers={**admin_headers, "Idempotency-Key": "wp2-case-review-0001"},
        json={
            "expected_version": 2,
            "target_status": "in_review",
            "resolution_code": "admin.review_started",
            "resolution_note": "合成开始复核。",
        },
    )
    assert review.status_code == 200
    assert review.json()["version"] == 3
    assert review.json()["current_assignee_id"] == target_id

    closed = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/transition",
        headers={**admin_headers, "Idempotency-Key": "wp2-case-dismiss-0001"},
        json={
            "expected_version": 3,
            "target_status": "dismissed",
            "resolution_code": "admin.no_violation",
            "resolution_note": "合成关闭说明。",
        },
    )
    assert closed.status_code == 200
    assert closed.json()["version"] == 4

    reopen_headers = {
        **admin_headers,
        "Idempotency-Key": "wp2-case-reopen-0001",
        "X-Request-ID": "synthetic-wp2-reopen",
    }
    reopen_payload = {
        "expected_version": 4,
        "reason_code": "admin.reopened",
        "note": "合成重开说明，不进入审计摘要。",
    }
    reopened = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/reopen",
        headers=reopen_headers,
        json=reopen_payload,
    )
    repeated_reopen = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/reopen",
        headers=reopen_headers,
        json=reopen_payload,
    )
    assert reopened.status_code == repeated_reopen.status_code == 200
    assert reopened.json() == repeated_reopen.json()
    assert reopened.json()["current_status"] == "open"
    assert reopened.json()["current_assignee_id"] is None
    assert reopened.json()["version"] == 5

    stale_reopen = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/reopen",
        headers={**admin_headers, "Idempotency-Key": "wp2-case-reopen-stale-0001"},
        json=reopen_payload,
    )
    assert stale_reopen.status_code == 409
    assert stale_reopen.json()["code"] == "trust.case_version_conflict"

    detail = client.get(f"/api/v1/admin/trust-cases/{case_id}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["version"] == 5
    assert detail.json()["events"][1]["previous_assignee_id"] is None
    assert detail.json()["events"][1]["next_assignee_id"] == target_id
    assert detail.json()["events"][-1]["action"] == "case.reopened"

    with client.app.state.database.session_factory() as db:
        events = list(db.scalars(select(TrustCaseEvent).where(TrustCaseEvent.case_id == case_id)))
        assert len(events) == 5
        audits = list(
            db.scalars(
                select(AuditLog).where(AuditLog.target_id == case_id).order_by(AuditLog.created_at)
            )
        )
        assignment_audit = next(item for item in audits if item.action == "trust_case.assign")
        reopen_audit = next(item for item in audits if item.action == "trust_case.reopen")
        assert "note" not in assignment_audit.details
        assert "note" not in reopen_audit.details
        stored = db.get(TrustCase, case_id)
        assert stored is not None and stored.version == 5 and stored.assigned_to_id is None

    assert target_headers["Authorization"]


def test_case_assignment_requires_active_moderator_or_admin(client):
    _, owner_headers = _register_and_login(client, "wp2_bad_owner")
    candidate_id = _create_candidate(client, owner_headers, "7")
    created = client.post(
        "/api/v1/trust/reports",
        headers={**owner_headers, "Idempotency-Key": "wp2-invalid-assignment-report-0001"},
        json={"candidate_id": candidate_id, "reason_code": "report.other"},
    )
    assert created.status_code == 201
    admin_headers = _admin_headers(client, "wp2_bad_admin")
    _, normal_headers = _register_and_login(client, "wp2_bad_user")
    with client.app.state.database.session_factory() as db:
        normal = db.scalar(select(User).where(User.username == "trust_wp2_bad_user"))
        assert normal is not None
        normal_id = normal.id
    response = client.post(
        f"/api/v1/admin/trust-cases/{created.json()['id']}/assign",
        headers={**admin_headers, "Idempotency-Key": "wp2-invalid-assignment-0001"},
        json={
            "expected_version": 1,
            "assignee_id": normal_id,
            "reason_code": "admin.assigned",
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "trust.invalid_assignee"
    assert normal_headers["Authorization"]
