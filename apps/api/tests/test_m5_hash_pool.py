from __future__ import annotations

import pyotp
from sqlalchemy import select

from password_detective.core.time import utc_now
from password_detective.db.models.password_candidate import CandidateStatus, PasswordCandidate
from password_detective.db.models.user import User, UserRole

SHA256 = "a" * 64
MD5 = "b" * 32


def _register_and_login(client, suffix: str) -> tuple[dict[str, str], dict[str, str]]:
    registration = {
        "username": f"hash_pool_{suffix}",
        "email": f"hash-pool-{suffix}@synthetic.example.com",
        "password": "SyntheticHashPoolPass123!",
    }
    response = client.post("/api/v1/auth/register", json=registration)
    assert response.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": registration["password"]},
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
            "password": registration["password"],
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert authenticated.status_code == 200
    return {"Authorization": f"Bearer {authenticated.json()['access_token']}"}


def _create_candidate(client, headers: dict[str, str], suffix: str, sha256: str, md5: str) -> str:
    response = client.post(
        "/api/v1/archives/submissions",
        headers={**headers, "Idempotency-Key": f"hash-pool-submission-{suffix}"},
        json={
            "fingerprints": [
                {"algorithm": "sha256", "digest": sha256},
                {"algorithm": "md5", "digest": md5},
            ],
            "password": f"Synthetic-Hash-Pool-Candidate-{suffix}!",
            "authorization_confirmed": True,
            "authorization_version": "2026-08-01",
        },
    )
    assert response.status_code == 201
    return response.json()["candidate_id"]


def test_hash_pool_only_lists_verified_candidates_and_never_exposes_secret(client):
    _, owner_headers = _register_and_login(client, "owner")
    verified_id = _create_candidate(client, owner_headers, "verified", SHA256, MD5)
    _create_candidate(client, owner_headers, "pending", "c" * 64, "d" * 32)
    with client.app.state.database.session_factory() as db:
        candidate = db.get(PasswordCandidate, verified_id)
        assert candidate is not None
        candidate.status = CandidateStatus.VERIFIED
        candidate.confidence_score = 0.96
        candidate.last_verified_at = utc_now()
        db.commit()

    forbidden = client.get("/api/v1/admin/hash-pool", headers=owner_headers)
    assert forbidden.status_code == 403

    response = client.get(
        "/api/v1/admin/hash-pool",
        headers=_admin_headers(client),
        params={"query": SHA256[:20], "algorithm": "sha256"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["overview"]["verified_candidates"] == 1
    assert body["overview"]["pending_candidates"] == 1
    assert body["overview"]["unique_archives"] == 1
    assert body["overview"]["unique_fingerprints"] == 2
    assert body["items"][0]["candidate_id"] == verified_id
    assert body["items"][0]["confidence_score"] == 0.96
    serialized = response.text.lower()
    for forbidden_field in ("password", "ciphertext", "nonce", "dedup", "secret"):
        assert forbidden_field not in serialized


def test_hash_pool_algorithm_filter_rejects_unknown_value(client):
    response = client.get(
        "/api/v1/admin/hash-pool",
        headers=_admin_headers(client),
        params={"algorithm": "crc32"},
    )
    assert response.status_code == 422
