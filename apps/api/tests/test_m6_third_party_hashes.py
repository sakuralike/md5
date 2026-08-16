from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from sqlalchemy import select

FINGERPRINT = "7" * 64
SYNTHETIC_PASSWORD = "Synthetic-Third-Party-Hash-Read!"


def _register_and_login(client, suffix: str) -> dict[str, str]:
    username = f"tph_{suffix}_{uuid4().hex[:8]}"[:32]
    payload = {
        "username": username,
        "email": f"{username}@synthetic.example.com",
        "password": "SyntheticThirdPartyHash123!",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": payload["username"], "password": payload["password"]},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _admin_headers(client) -> dict[str, str]:
    headers = _register_and_login(client, "admin")
    from password_detective.db.models.user import User, UserRole

    with client.app.state.database.session_factory() as db:
        token = headers["Authorization"].removeprefix("Bearer ")
        del token
        user = db.scalar(select(User).where(User.username.like("tph_admin_%")))
        assert user is not None
        user.role = UserRole.ADMIN
        db.commit()
    return headers


def _pkce(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )


def _approved_app(
    client,
    admin_headers: dict[str, str],
    *,
    suffix: str,
    scopes: list[str],
) -> dict[str, object]:
    created = client.post(
        "/api/v1/admin/third-party-apps",
        headers=admin_headers,
        json={
            "name": f"Synthetic Hash Reader {suffix}",
            "developer_name": "Synthetic Developer",
            "redirect_uris": [f"http://127.0.0.1:{49500 + len(suffix)}/callback"],
            "scopes": scopes,
        },
    )
    assert created.status_code == 201
    approved = client.post(
        f"/api/v1/admin/third-party-apps/{created.json()['id']}/approve",
        headers=admin_headers,
    )
    assert approved.status_code == 200
    return approved.json()


def _token(
    client,
    app: dict[str, object],
    user_headers: dict[str, str],
    *,
    scopes: str,
) -> dict[str, str]:
    verifier = f"synthetic-hash-reader-{uuid4().hex}-abcdefghijklmnopqrstuvwxyz"
    redirect_uri = str(app["redirect_uris"][0])
    authorized = client.get(
        "/api/v1/third-party/oauth/authorize",
        headers=user_headers,
        params={
            "response_type": "code",
            "client_id": app["client_id"],
            "redirect_uri": redirect_uri,
            "code_challenge": _pkce(verifier),
            "code_challenge_method": "S256",
            "scope": scopes,
            "state": f"synthetic-state-{uuid4().hex}",
        },
        follow_redirects=False,
    )
    assert authorized.status_code == 302
    code = parse_qs(urlparse(authorized.headers["location"]).query)["code"][0]
    exchanged = client.post(
        "/api/v1/third-party/oauth/token",
        json={
            "grant_type": "authorization_code",
            "client_id": app["client_id"],
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
    )
    assert exchanged.status_code == 200
    return {"Authorization": f"Bearer {exchanged.json()['access_token']}"}


def _seed_hash_detail(client, user_headers: dict[str, str]) -> str:
    submitted = client.post(
        "/api/v1/archives/submissions",
        headers={**user_headers, "Idempotency-Key": f"tph-submit-{uuid4()}"},
        json={
            "fingerprints": [{"algorithm": "sha256", "digest": FINGERPRINT}],
            "password": SYNTHETIC_PASSWORD,
            "authorization_confirmed": True,
            "authorization_version": "synthetic-v1",
            "optional_size": 4096,
            "optional_format": "zip",
        },
    )
    assert submitted.status_code == 201
    detail_url = f"/api/v1/hashes/sha256/{FINGERPRINT}"
    comment = client.post(
        f"{detail_url}/comments",
        headers={**user_headers, "Idempotency-Key": f"tph-comment-{uuid4()}"},
        json={"content": "Synthetic third-party read comment", "rules_accepted": True},
    )
    assert comment.status_code == 201
    liked = client.put(
        f"{detail_url}/like",
        headers={**user_headers, "Idempotency-Key": f"tph-like-{uuid4()}"},
    )
    assert liked.status_code == 200
    voted = client.put(
        f"{detail_url}/vote",
        headers={**user_headers, "Idempotency-Key": f"tph-vote-{uuid4()}"},
        json={"outcome": "useful"},
    )
    assert voted.status_code == 200
    return comment.json()["comments"][0]["id"]


def test_third_party_hash_read_returns_private_projection_and_viewer_state(client) -> None:
    admin_headers = _admin_headers(client)
    user_headers = _register_and_login(client, "reader")
    app = _approved_app(client, admin_headers, suffix="detail", scopes=["hash:read"])
    access = _token(client, app, user_headers, scopes="hash:read")
    comment_id = _seed_hash_detail(client, user_headers)

    response = client.get(
        f"/api/v1/third-party/hashes/sha256/{FINGERPRINT}",
        headers=access,
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    body = response.json()
    assert body["matched"] is True
    assert body["viewer_has_liked"] is True
    assert body["viewer_vote"] == "useful"
    assert body["comment_count"] == 1
    assert body["comments"][0]["id"] == comment_id
    assert body["archive"]["candidates"][0]["masked_secret"] == "••••••••"
    assert SYNTHETIC_PASSWORD not in response.text
    assert "secret_ciphertext" not in response.text
    assert "secret_nonce" not in response.text


def test_third_party_hash_comments_support_cursor_and_require_hash_scope(client) -> None:
    admin_headers = _admin_headers(client)
    user_headers = _register_and_login(client, "comments")
    app = _approved_app(
        client,
        admin_headers,
        suffix="comments",
        scopes=["profile:read", "hash:read"],
    )
    access = _token(client, app, user_headers, scopes="hash:read")
    _seed_hash_detail(client, user_headers)
    for index in range(2):
        created = client.post(
            f"/api/v1/hashes/sha256/{FINGERPRINT}/comments",
            headers={**user_headers, "Idempotency-Key": f"tph-extra-comment-{index}-{uuid4()}"},
            json={
                "content": f"Synthetic paged third-party comment {index}",
                "rules_accepted": True,
            },
        )
        assert created.status_code == 201

    first = client.get(
        f"/api/v1/third-party/hashes/sha256/{FINGERPRINT}/comments",
        headers=access,
        params={"limit": 2},
    )
    assert first.status_code == 200
    assert first.headers["cache-control"] == "private, no-store"
    assert len(first.json()["items"]) == 2
    assert first.json()["has_more"] is True
    assert first.json()["next_cursor"]

    second = client.get(
        f"/api/v1/third-party/hashes/sha256/{FINGERPRINT}/comments",
        headers=access,
        params={"limit": 2, "cursor": first.json()["next_cursor"]},
    )
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1
    assert second.json()["has_more"] is False

    profile_only = _token(client, app, user_headers, scopes="profile:read")
    blocked = client.get(
        f"/api/v1/third-party/hashes/sha256/{FINGERPRINT}",
        headers=profile_only,
    )
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "third_party_oauth.insufficient_scope"


def test_third_party_hash_read_requires_oauth_token_and_preserves_not_found_semantics(
    client,
) -> None:
    missing = client.get(f"/api/v1/third-party/hashes/sha256/{FINGERPRINT}")
    assert missing.status_code == 401
    assert missing.json()["code"] == "third_party_oauth.authentication_required"

    admin_headers = _admin_headers(client)
    user_headers = _register_and_login(client, "unmatched")
    app = _approved_app(client, admin_headers, suffix="unmatched", scopes=["hash:read"])
    access = _token(client, app, user_headers, scopes="hash:read")
    unmatched = client.get(
        f"/api/v1/third-party/hashes/sha256/{'8' * 64}",
        headers=access,
    )
    assert unmatched.status_code == 200
    assert unmatched.json()["matched"] is False
    assert unmatched.json()["archive"] is None
