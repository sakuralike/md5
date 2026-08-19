from __future__ import annotations

import pyotp
from sqlalchemy import select

from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.community import (
    CommunityBoard,
    CommunityComment,
    CommunityContentStatus,
    CommunityPost,
)
from password_detective.db.models.password_candidate import (
    CandidateStatus,
    PasswordCandidate,
)
from password_detective.db.models.user import User, UserRole

PASSWORD = "SyntheticDashboardPass123!"


def _register_and_login(client, suffix: str) -> tuple[dict[str, str], dict[str, str]]:
    registration = {
        "username": f"dashboard_{suffix}",
        "email": f"dashboard-{suffix}@synthetic.example.com",
        "password": PASSWORD,
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": PASSWORD},
    )
    assert login.status_code == 200
    return registration, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _admin_headers(client) -> dict[str, str]:
    registration, initial_headers = _register_and_login(client, "admin")
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user.role = UserRole.ADMIN
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
            "login": registration["username"],
            "password": PASSWORD,
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert authenticated.status_code == 200
    return {"Authorization": f"Bearer {authenticated.json()['access_token']}"}


def _create_candidate(client, headers: dict[str, str], digit: str) -> str:
    response = client.post(
        "/api/v1/archives/submissions",
        headers={**headers, "Idempotency-Key": f"dashboard-submission-{digit}"},
        json={
            "fingerprints": [{"algorithm": "sha256", "digest": digit * 64}],
            "password": f"Synthetic-Dashboard-Candidate-{digit}!",
            "authorization_confirmed": True,
            "authorization_version": "2026-08-03",
        },
    )
    assert response.status_code == 201
    return response.json()["candidate_id"]


def test_dashboard_summary_uses_real_metrics_and_search_telemetry(client):
    _, contributor_headers = _register_and_login(client, "contributor")
    pending_id = _create_candidate(client, contributor_headers, "1")
    verified_id = _create_candidate(client, contributor_headers, "2")
    quarantined_id = _create_candidate(client, contributor_headers, "3")

    with client.app.state.database.session_factory() as db:
        verified = db.get(PasswordCandidate, verified_id)
        quarantined = db.get(PasswordCandidate, quarantined_id)
        assert verified is not None and quarantined is not None
        verified.status = CandidateStatus.VERIFIED
        quarantined.status = CandidateStatus.QUARANTINED
        db.add(
            AuditLog(
                action="synthetic.failed_operation",
                target_type="synthetic",
                result="failure",
                details={"reason": "synthetic-test-only"},
            )
        )
        db.commit()

    hit = client.get("/api/v1/archives/search", params={"fingerprint": "1" * 64})
    miss = client.get("/api/v1/archives/search", params={"fingerprint": "4" * 64})
    assert hit.status_code == 200 and hit.json()["matched"] is True
    hit_archive_id = hit.json()["archive"]["id"]
    assert miss.status_code == 200 and miss.json()["matched"] is False

    forbidden = client.get("/api/v1/admin/dashboard/summary", headers=contributor_headers)
    assert forbidden.status_code == 403

    summary_response = client.get(
        "/api/v1/admin/dashboard/summary",
        headers=_admin_headers(client),
        params={"window_hours": 24},
    )
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["window_hours"] == 24
    assert summary["search_count"] == 2
    assert summary["search_hit_count"] == 1
    assert summary["search_hit_rate"] == 0.5
    assert summary["contribution_count"] == 3
    assert summary["candidate_count"] == 3
    assert summary["verified_candidate_count"] == 1
    assert summary["candidate_verification_rate"] == 0.3333
    assert summary["quarantined_candidate_count"] == 1
    assert summary["audited_operation_count"] >= 6
    assert summary["audited_error_count"] >= 1
    assert summary["audited_error_rate"] > 0
    assert summary["queue_backlog"]["pending_candidates"] == 1
    assert summary["queue_backlog"]["total"] >= 1

    with client.app.state.database.session_factory() as db:
        search_events = list(
            db.scalars(
                select(AuditLog)
                .where(AuditLog.action == "archive.search")
                .order_by(AuditLog.created_at)
            )
        )
        assert len(search_events) == 2
        assert pending_id
        assert search_events[0].target_id == hit_archive_id
        assert search_events[1].target_id is None
        serialized = str([event.details for event in search_events])
        assert "1" * 64 not in serialized
        assert "4" * 64 not in serialized
        assert [event.details["matched"] for event in search_events] == [True, False]


def test_dashboard_summary_validates_window(client):
    response = client.get(
        "/api/v1/admin/dashboard/summary",
        headers=_admin_headers(client),
        params={"window_hours": 0},
    )
    assert response.status_code == 422


def test_admin_community_heatmap_is_privacy_bounded_and_mfa_protected(client):
    registration, contributor_headers = _register_and_login(client, "heatmap")
    client.get("/api/v1/community/boards")
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        board = db.scalar(select(CommunityBoard).where(CommunityBoard.code == "general"))
        assert user is not None and board is not None
        post = CommunityPost(
            board_id=board.id,
            board_code=board.code,
            author_id=user.id,
            title="合成热度主题",
            content="这是用于验证管理端聚合热度矩阵的合成社区主题内容。",
            status=CommunityContentStatus.PUBLISHED,
        )
        db.add(post)
        db.flush()
        db.add(
            CommunityComment(
                post_id=post.id,
                author_id=user.id,
                content="这是用于验证日期活动桶的合成回复。",
                status=CommunityContentStatus.PUBLISHED,
            )
        )
        db.commit()

    forbidden = client.get(
        "/api/v1/admin/analytics/community-heatmap",
        headers=contributor_headers,
    )
    assert forbidden.status_code == 403

    response = client.get(
        "/api/v1/admin/analytics/community-heatmap",
        headers=_admin_headers(client),
        params={"days": 7},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["window_days"] == 7
    assert len(body["days"]) == 7
    assert any(item["activity_count_band"] == "少于 10" for item in body["days"])
    assert any(item["board_code"] == "general" for item in body["boards"])
    assert "合成热度主题" not in response.text
    assert "合成热度主题" not in str(body)
    assert "username" not in response.text


def test_admin_community_heatmap_validates_window(client):
    response = client.get(
        "/api/v1/admin/analytics/community-heatmap",
        headers=_admin_headers(client),
        params={"days": 180},
    )
    assert response.status_code == 422
