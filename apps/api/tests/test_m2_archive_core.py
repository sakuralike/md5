from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from password_detective.db.models.archive import Archive
from password_detective.db.models.archive_fingerprint import ArchiveFingerprint
from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.password_candidate import CandidateStatus, PasswordCandidate
from password_detective.db.models.points_ledger import PointsLedger, PointsLedgerStatus
from password_detective.db.models.submission import Submission
from password_detective.modules.admin.setting_schemas import default_user_levels

REGISTER_PAYLOAD = {
    "username": "archive_detective",
    "email": "archive-detective@example.com",
    "password": "SyntheticArchivePass123!",
}
SHA256 = "a" * 64
MD5 = "b" * 32


def _register_and_login(client) -> dict[str, str]:
    response = client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": REGISTER_PAYLOAD["username"], "password": REGISTER_PAYLOAD["password"]},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _submission_payload(password: str = "Synthetic-ZIP-Password!") -> dict:
    return {
        "fingerprints": [
            {"algorithm": "sha256", "digest": SHA256.upper()},
            {"digest": MD5},
        ],
        "password": password,
        "authorization_confirmed": True,
        "authorization_version": "2026-08-01",
        "optional_size": 4096,
        "optional_format": "ZIP",
    }


def test_submission_encrypts_secret_and_creates_pending_evidence(client):
    headers = _register_and_login(client)
    headers["Idempotency-Key"] = "archive-submission-0001"
    response = client.post(
        "/api/v1/archives/submissions", json=_submission_payload(), headers=headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["archive_created"] is True
    assert body["candidate_created"] is True
    assert body["candidate_status"] == "pending"
    assert body["pending_points"] == 1
    assert body["submitter_kind"] == "authenticated"
    assert body["pool_status"] == "pending_verification"
    assert body["required_success_confirmations"] == 4

    with client.app.state.database.session_factory() as db:
        archive = db.get(Archive, body["archive_id"])
        candidate = db.get(PasswordCandidate, body["candidate_id"])
        assert archive is not None and archive.optional_format == "zip"
        assert candidate is not None
        assert candidate.secret_ciphertext != _submission_payload()["password"]
        assert _submission_payload()["password"] not in candidate.secret_ciphertext
        assert len(candidate.secret_dedup_tag) == 64
        assert db.query(ArchiveFingerprint).count() == 2
        assert db.query(Submission).count() == 1
        ledger = db.scalar(select(PointsLedger))
        assert ledger is not None and ledger.status == PointsLedgerStatus.PENDING
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "archive.submission_created"))
        assert audit is not None
        assert _submission_payload()["password"] not in str(audit.details)


def test_guest_web_submission_enters_pending_pool_without_points(client):
    headers = {
        "Idempotency-Key": "guest-archive-submission-0001",
        "User-Agent": "SyntheticGuestBrowser/1.0",
    }
    first = client.post(
        "/api/v1/archives/submissions", json=_submission_payload(), headers=headers
    )
    retry = client.post(
        "/api/v1/archives/submissions", json=_submission_payload(), headers=headers
    )

    assert first.status_code == retry.status_code == 201
    assert first.json() == retry.json()
    body = first.json()
    assert body["candidate_status"] == "pending"
    assert body["submitter_kind"] == "guest"
    assert body["pool_status"] == "pending_verification"
    assert body["required_success_confirmations"] == 4
    assert body["pending_points"] == 0

    with client.app.state.database.session_factory() as db:
        archive = db.get(Archive, body["archive_id"])
        submission = db.get(Submission, body["submission_id"])
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "archive.submission_created"))
        assert archive is not None and archive.created_by is None
        assert submission is not None and submission.user_id is None
        assert db.query(Submission).count() == 1
        assert db.query(PointsLedger).count() == 0
        assert audit is not None and audit.actor_id is None
        assert audit.details["authenticated"] is False
        assert audit.details["pool_status"] == "pending_verification"


def test_idempotent_retry_does_not_duplicate_submission(client):
    headers = _register_and_login(client)
    headers["Idempotency-Key"] = "archive-submission-0002"
    first = client.post("/api/v1/archives/submissions", json=_submission_payload(), headers=headers)
    second = client.post(
        "/api/v1/archives/submissions", json=_submission_payload(), headers=headers
    )
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    with client.app.state.database.session_factory() as db:
        assert db.query(Archive).count() == 1
        assert db.query(PasswordCandidate).count() == 1
        assert db.query(Submission).count() == 1
        assert db.query(PointsLedger).count() == 1


def test_duplicate_candidate_merges_new_submission_evidence(client):
    headers = _register_and_login(client)
    first_headers = {**headers, "Idempotency-Key": "archive-submission-0003"}
    second_headers = {**headers, "Idempotency-Key": "archive-submission-0004"}
    first = client.post(
        "/api/v1/archives/submissions", json=_submission_payload(), headers=first_headers
    )
    second = client.post(
        "/api/v1/archives/submissions", json=_submission_payload(), headers=second_headers
    )
    assert first.status_code == second.status_code == 201
    assert second.json()["archive_created"] is False
    assert second.json()["candidate_created"] is False
    assert second.json()["evidence_merged"] is True
    assert first.json()["candidate_id"] == second.json()["candidate_id"]
    with client.app.state.database.session_factory() as db:
        assert db.query(PasswordCandidate).count() == 1
        assert db.query(Submission).count() == 2


def test_search_sorts_mixed_sqlite_timestamps_without_timezone_error(client):
    headers = _register_and_login(client)
    first = client.post(
        "/api/v1/archives/submissions",
        json=_submission_payload("Synthetic-Candidate-One!"),
        headers={**headers, "Idempotency-Key": "archive-submission-sort-0001"},
    ).json()
    second = client.post(
        "/api/v1/archives/submissions",
        json=_submission_payload("Synthetic-Candidate-Two!"),
        headers={**headers, "Idempotency-Key": "archive-submission-sort-0002"},
    ).json()
    with client.app.state.database.session_factory() as db:
        first_candidate = db.get(PasswordCandidate, first["candidate_id"])
        second_candidate = db.get(PasswordCandidate, second["candidate_id"])
        assert first_candidate is not None and second_candidate is not None
        first_candidate.status = CandidateStatus.VERIFIED
        second_candidate.status = CandidateStatus.VERIFIED
        first_candidate.confidence_score = second_candidate.confidence_score = 0.8
        first_candidate.last_verified_at = datetime(2026, 8, 1, 12, 0, 0)
        db.commit()

    response = client.get(
        "/api/v1/archives/search", params={"fingerprint": SHA256}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["archive"]["candidates"][0]["id"] == first["candidate_id"]


def test_search_visibility_and_fingerprint_validation(client):
    missing = client.get("/api/v1/archives/search", params={"fingerprint": "c" * 64})
    assert missing.status_code == 200
    assert missing.json()["matched"] is False
    assert missing.json()["query"]["algorithm"] == "sha256"

    invalid = client.get("/api/v1/archives/search", params={"fingerprint": "x" * 64})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "archive.invalid_fingerprint"

    mismatch = client.get(
        "/api/v1/archives/search", params={"fingerprint": SHA256, "algorithm": "md5"}
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["code"] == "archive.fingerprint_algorithm_mismatch"

    headers = _register_and_login(client)
    submission_headers = {**headers, "Idempotency-Key": "archive-submission-0005"}
    assert (
        client.post(
            "/api/v1/archives/submissions",
            json=_submission_payload(),
            headers=submission_headers,
        ).status_code
        == 201
    )
    anonymous = client.get("/api/v1/archives/search", params={"fingerprint": SHA256})
    authenticated = client.get(
        "/api/v1/archives/search", params={"fingerprint": SHA256}, headers=headers
    )
    assert anonymous.json()["matched"] is True
    assert anonymous.json()["archive"]["candidate_count"] == 1
    assert anonymous.json()["archive"]["candidates"] == []
    assert authenticated.json()["archive"]["candidates"][0]["masked_secret"] == "••••••••"
    assert "Synthetic-ZIP-Password!" not in authenticated.text


def test_reveal_requires_verified_candidate_enforces_quota_and_audits(client):
    headers = _register_and_login(client)
    created = client.post(
        "/api/v1/archives/submissions",
        json=_submission_payload(),
        headers={**headers, "Idempotency-Key": "archive-submission-0006"},
    ).json()
    denied = client.post(f"/api/v1/archives/{created['archive_id']}/reveal", headers=headers)
    assert denied.status_code == 409
    assert denied.json()["code"] == "archive.no_revealable_candidate"

    with client.app.state.database.session_factory() as db:
        candidate = db.get(PasswordCandidate, created["candidate_id"])
        assert candidate is not None
        candidate.status = CandidateStatus.VERIFIED
        candidate.confidence_score = 0.8
        db.commit()

    default_level_quota = default_user_levels()[0].daily_reveal_quota
    with client.app.state.database.session_factory() as db:
        submission = db.get(Submission, created["submission_id"])
        assert submission is not None
        for index in range(default_level_quota - 1):
            db.add(
                AuditLog(
                    actor_id=submission.user_id,
                    action="archive.password_revealed",
                    target_type="password_candidate",
                    target_id=created["candidate_id"],
                    result="success",
                    request_id=f"synthetic-quota-{index}",
                    details={"archive_id": created["archive_id"]},
                )
            )
        db.commit()

    reveal = client.post(f"/api/v1/archives/{created['archive_id']}/reveal", headers=headers)
    assert reveal.status_code == 200
    assert reveal.json()["password"] == "Synthetic-ZIP-Password!"
    assert reveal.json()["remaining_daily_quota"] == 0
    assert reveal.headers["cache-control"] == "no-store"

    exceeded = client.post(f"/api/v1/archives/{created['archive_id']}/reveal", headers=headers)
    assert exceeded.status_code == 429
    assert exceeded.json()["code"] == "archive.daily_reveal_quota_exceeded"
    with client.app.state.database.session_factory() as db:
        audits = list(
            db.scalars(select(AuditLog).where(AuditLog.action == "archive.password_revealed"))
        )
        assert len(audits) == default_level_quota
        assert all("Synthetic-ZIP-Password!" not in str(item.details) for item in audits)


def test_my_submissions_returns_status_without_secret(client):
    headers = _register_and_login(client)
    client.post(
        "/api/v1/archives/submissions",
        json=_submission_payload(),
        headers={**headers, "Idempotency-Key": "archive-submission-0007"},
    )
    response = client.get("/api/v1/me/submissions", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["candidate_status"] == "pending"
    assert body["items"][0]["fingerprints"][0]["digest"] in {MD5, SHA256}
    assert "Synthetic-ZIP-Password!" not in response.text


def test_hash_detail_supports_like_vote_comment_and_comment_like(client):
    headers = _register_and_login(client)
    submission = client.post(
        "/api/v1/archives/submissions",
        json=_submission_payload(),
        headers={**headers, "Idempotency-Key": "hash-detail-submission-0001"},
    )
    assert submission.status_code == 201

    detail_url = f"/api/v1/hashes/sha256/{SHA256}"
    detail = client.get(detail_url, headers=headers)
    assert detail.status_code == 200
    assert detail.json()["digest"] == SHA256
    assert detail.json()["comments"] == []

    liked = client.put(
        f"{detail_url}/like",
        headers={**headers, "Idempotency-Key": "hash-detail-like-0001"},
    )
    assert liked.status_code == 200
    assert liked.json()["like_count"] == 1
    assert liked.json()["viewer_has_liked"] is True

    voted = client.put(
        f"{detail_url}/vote",
        json={"outcome": "useful"},
        headers={**headers, "Idempotency-Key": "hash-detail-vote-0001"},
    )
    assert voted.status_code == 200
    assert voted.json()["vote_counts"]["useful"] == 1
    assert voted.json()["viewer_vote"] == "useful"

    comment = client.post(
        f"{detail_url}/comments",
        json={"content": "Synthetic verification note", "rules_accepted": True},
        headers={**headers, "Idempotency-Key": "hash-detail-comment-0001"},
    )
    assert comment.status_code == 201
    comment_body = comment.json()
    assert len(comment_body["comments"]) == 1
    comment_id = comment_body["comments"][0]["id"]

    comment_like = client.put(
        f"{detail_url}/comments/{comment_id}/like",
        headers={**headers, "Idempotency-Key": "hash-detail-comment-like-0001"},
    )
    assert comment_like.status_code == 200
    assert comment_like.json()["comments"][0]["like_count"] == 1

    unliked = client.delete(
        f"{detail_url}/like",
        headers={**headers, "Idempotency-Key": "hash-detail-unlike-0001"},
    )
    assert unliked.status_code == 200
    assert unliked.json()["like_count"] == 0


def test_hash_detail_can_open_unmatched_hash(client):
    response = client.get(f"/api/v1/hashes/sha256/{'c' * 64}")
    assert response.status_code == 200
    assert response.json()["matched"] is False
    assert response.json()["archive"] is None
    assert response.json()["comments"] == []


def test_hash_comment_list_uses_stable_cursor_pagination(client):
    headers = _register_and_login(client)
    submission = client.post(
        "/api/v1/archives/submissions",
        json=_submission_payload(),
        headers={**headers, "Idempotency-Key": "hash-comment-page-submission-0001"},
    )
    assert submission.status_code == 201

    detail_url = f"/api/v1/hashes/sha256/{SHA256}"
    created_ids: list[str] = []
    for index in range(3):
        response = client.post(
            f"{detail_url}/comments",
            json={"content": f"Synthetic paged comment {index}", "rules_accepted": True},
            headers={
                **headers,
                "Idempotency-Key": f"hash-comment-page-create-{index:04d}",
            },
        )
        assert response.status_code == 201
        created_ids.append(response.json()["comments"][0]["id"])

    first_page = client.get(f"{detail_url}/comments?limit=2", headers=headers)
    assert first_page.status_code == 200
    first_body = first_page.json()
    assert [item["id"] for item in first_body["items"]] == list(reversed(created_ids[1:]))
    assert first_body["next_cursor"]
    assert first_body["has_more"] is True

    second_page = client.get(
        f"{detail_url}/comments",
        params={"limit": 2, "cursor": first_body["next_cursor"]},
        headers=headers,
    )
    assert second_page.status_code == 200
    second_body = second_page.json()
    assert [item["id"] for item in second_body["items"]] == created_ids[:1]
    assert second_body["next_cursor"] is None
    assert second_body["has_more"] is False

    invalid = client.get(
        f"{detail_url}/comments",
        params={"cursor": "not-a-valid-cursor"},
        headers=headers,
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "hash.invalid_cursor"

    detail = client.get(detail_url, headers=headers)
    assert detail.status_code == 200
    assert detail.json()["comment_count"] == 3
    assert detail.json()["comments_next_cursor"] is None
    assert [item["id"] for item in detail.json()["comments"]] == list(reversed(created_ids))
