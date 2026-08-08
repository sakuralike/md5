from __future__ import annotations

from sqlalchemy import select
from test_m4_trust_cases import _admin_headers, _create_candidate, _register_and_login

from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.trust_case import TrustCase, TrustCaseEvent, TrustCaseStatus
from password_detective.db.models.user import User


def test_atomic_case_resolution_is_idempotent_versioned_and_audited(client):
    _, owner_headers = _register_and_login(client, "wp2_resolve_owner")
    candidate_id = _create_candidate(client, owner_headers, "7")
    created = client.post(
        "/api/v1/trust/reports",
        headers={**owner_headers, "Idempotency-Key": "wp2-resolution-report-0001"},
        json={
            "candidate_id": candidate_id,
            "reason_code": "report.policy_violation",
            "description": "合成原子处置测试案件。",
        },
    )
    assert created.status_code == 201
    case_id = created.json()["id"]
    admin_headers = _admin_headers(client, "wp2_resolution_admin")

    request_headers = {
        **admin_headers,
        "Idempotency-Key": "wp2-case-resolution-0001",
        "X-Request-ID": "synthetic-wp2-resolution",
    }
    payload = {
        "expected_version": 1,
        "resolution_code": "admin.action_taken",
        "resolution_note": "合成处置说明：确认需要采取治理动作。",
    }
    resolved = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/resolve",
        headers=request_headers,
        json=payload,
    )
    repeated = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/resolve",
        headers=request_headers,
        json=payload,
    )
    assert resolved.status_code == repeated.status_code == 200
    assert resolved.json() == repeated.json()
    assert resolved.json()["current_status"] == "resolved"
    assert resolved.json()["version"] == 2
    assert resolved.json()["request_id"] == "synthetic-wp2-resolution"

    stale = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/resolve",
        headers={**admin_headers, "Idempotency-Key": "wp2-case-resolution-stale-0001"},
        json={**payload, "resolution_code": "admin.no_violation"},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "trust.case_version_conflict"

    with client.app.state.database.session_factory() as db:
        case = db.get(TrustCase, case_id)
        assert case is not None
        assert case.status == TrustCaseStatus.RESOLVED
        assert case.version == 2
        assert case.resolved_by_id == case.assigned_to_id
        events = list(
            db.scalars(select(TrustCaseEvent).where(TrustCaseEvent.case_id == case_id))
        )
        assert len(events) == 2
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.target_id == case_id,
                AuditLog.action == "trust_case.resolve",
            )
        )
        assert audit is not None
        assert audit.details["resolution_code"] == "admin.action_taken"
        assert "resolution_note" not in audit.details


def test_case_resolution_enforces_kind_and_assignee(client):
    _, owner_headers = _register_and_login(client, "wp2_resolution_kind_owner")
    candidate_id = _create_candidate(client, owner_headers, "8")
    created = client.post(
        "/api/v1/trust/reports",
        headers={**owner_headers, "Idempotency-Key": "wp2-resolution-kind-report-0001"},
        json={
            "candidate_id": candidate_id,
            "reason_code": "report.other",
            "description": "合成结果码和负责人约束测试。",
        },
    )
    case_id = created.json()["id"]
    assigner_headers = _admin_headers(client, "wp2_resolution_assigner")
    assignee_headers = _admin_headers(client, "wp2_resolution_assignee")
    with client.app.state.database.session_factory() as db:
        assignee = db.scalar(select(User).where(User.username == "trust_wp2_resolution_assignee"))
        assert assignee is not None
        assignee_id = assignee.id

    assigned = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/assign",
        headers={**assigner_headers, "Idempotency-Key": "wp2-resolution-assign-0001"},
        json={
            "expected_version": 1,
            "assignee_id": assignee_id,
            "reason_code": "admin.assigned",
        },
    )
    assert assigned.status_code == 200

    wrong_actor = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/resolve",
        headers={**assigner_headers, "Idempotency-Key": "wp2-resolution-wrong-actor-0001"},
        json={
            "expected_version": 2,
            "resolution_code": "admin.action_taken",
            "resolution_note": "合成错误负责人尝试。",
        },
    )
    assert wrong_actor.status_code == 409
    assert wrong_actor.json()["code"] == "trust.case_assignee_mismatch"

    wrong_kind = client.post(
        f"/api/v1/admin/trust-cases/{case_id}/resolve",
        headers={**assignee_headers, "Idempotency-Key": "wp2-resolution-wrong-kind-0001"},
        json={
            "expected_version": 2,
            "resolution_code": "admin.account_restored",
            "resolution_note": "合成错误案件类型结果码。",
        },
    )
    assert wrong_kind.status_code == 422
    assert wrong_kind.json()["code"] == "trust.resolution_not_allowed"
