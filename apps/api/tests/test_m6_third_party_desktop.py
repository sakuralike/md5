from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select

from password_detective.db.models.desktop_verification import (
    ClientInstallation,
    VerificationChallenge,
    VerificationReceipt,
)
from password_detective.db.models.password_candidate import CandidateStatus
from password_detective.modules.third_party_desktop.schemas import ThirdPartyReceiptRequest
from password_detective.modules.third_party_desktop.service import build_canonical_receipt_payload

PASSWORD = "Synthetic-Third-Party-Desktop!"
PASSWORD_DIGEST = hashlib.sha256(PASSWORD.encode()).hexdigest()
CLIENT_VERSION = "0.1.0"


def _admin_headers(client) -> dict[str, str]:
    registration = {
        "username": "third_party_desktop_admin",
        "email": "third-party-desktop-admin@synthetic.example.com",
        "password": "SyntheticThirdPartyAdmin123!",
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": registration["password"]},
    )
    assert login.status_code == 200
    from password_detective.db.models.user import User, UserRole

    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.username == registration["username"]))
        assert user is not None
        user.role = UserRole.ADMIN
        db.commit()
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _user_headers(client, suffix: str = "user") -> dict[str, str]:
    username_suffix = suffix.replace("-", "_")
    registration = {
        "username": f"tpd_{username_suffix}"[:32],
        "email": f"third-party-desktop-{suffix}@synthetic.example.com",
        "password": "SyntheticThirdPartyUser123!",
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": registration["username"], "password": registration["password"]},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _app(client, admin_headers: dict[str, str], suffix: str, *, trusted: bool = False) -> dict:
    created = client.post(
        "/api/v1/admin/third-party-apps",
        headers=admin_headers,
        json={
            "name": f"Synthetic Third Party Desktop {suffix}",
            "developer_name": "Synthetic Developer",
            "redirect_uris": [f"http://127.0.0.1:{49200 + len(suffix)}/callback"],
            "scopes": ["desktop:installations", "desktop:verification"],
        },
    )
    assert created.status_code == 201
    app = created.json()
    approved = client.post(
        f"/api/v1/admin/third-party-apps/{app['id']}/approve",
        headers=admin_headers,
        json={"trusted_verification_enabled": trusted},
    )
    assert approved.status_code == 200
    return approved.json()


def _token(
    client,
    app: dict,
    user_headers: dict[str, str],
    *,
    trusted: bool = False,
    scopes: str = "desktop:installations desktop:verification",
) -> dict[str, str]:
    verifier = f"synthetic-third-party-verifier-{uuid4().hex}-abcdefghijklmnopqrstuvwxyz"
    requested_scope = scopes
    if trusted:
        requested_scope += " desktop:verification:trusted"
    issued = client.get(
        "/api/v1/third-party/oauth/authorize",
        headers=user_headers,
        params={
            "response_type": "code",
            "client_id": app["client_id"],
            "redirect_uri": app["redirect_uris"][0],
            "code_challenge": _pkce(verifier),
            "code_challenge_method": "S256",
            "scope": requested_scope,
            "state": "synthetic-third-party-state",
        },
        follow_redirects=False,
    )
    assert issued.status_code == 302
    code = parse_qs(urlparse(issued.headers["location"]).query)["code"][0]
    exchanged = client.post(
        "/api/v1/third-party/oauth/token",
        json={
            "grant_type": "authorization_code",
            "client_id": app["client_id"],
            "code": code,
            "redirect_uri": app["redirect_uris"][0],
            "code_verifier": verifier,
        },
    )
    assert exchanged.status_code == 200
    return {"Authorization": f"Bearer {exchanged.json()['access_token']}"}


def _pkce(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )


def _candidate(client, owner_headers: dict[str, str], suffix: str) -> tuple[str, str]:
    fingerprint = hashlib.sha256(f"third-party-archive-{suffix}".encode()).hexdigest()
    md5 = hashlib.md5(f"third-party-archive-{suffix}".encode(), usedforsecurity=False).hexdigest()
    response = client.post(
        "/api/v1/archives/submissions",
        headers={**owner_headers, "Idempotency-Key": f"third-party-submission-{suffix}-0001"},
        json={
            "fingerprints": [
                {"algorithm": "sha256", "digest": fingerprint},
                {"algorithm": "md5", "digest": md5},
            ],
            "password": PASSWORD,
            "authorization_confirmed": True,
            "authorization_version": "2026-08-01",
            "optional_size": 4096,
            "optional_format": "zip",
        },
    )
    assert response.status_code == 201
    return response.json()["candidate_id"], fingerprint


def _identity() -> tuple[str, ec.EllipticCurvePrivateKey, str]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return str(uuid4()), private_key, base64.b64encode(public_key).decode()


def _challenge(
    client, token: dict[str, str], installation_id: str, candidate_id: str, fingerprint: str
):
    return client.post(
        "/api/v1/third-party/challenges",
        headers=token,
        json={
            "installation_id": installation_id,
            "candidate_id": candidate_id,
            "fingerprint_algorithm": "sha256",
            "fingerprint_digest": fingerprint,
            "client_version": CLIENT_VERSION,
        },
    )


def _receipt(
    challenge: dict, app: dict, installation_id: str, key: ec.EllipticCurvePrivateKey
) -> dict:
    payload = {
        "challenge_id": challenge["challenge_id"],
        "challenge_nonce": challenge["challenge_nonce"],
        "installation_id": installation_id,
        "client_id": app["client_id"],
        "account_id": challenge["account_id"],
        "candidate_id": challenge["candidate_id"],
        "fingerprint_algorithm": challenge["fingerprint_algorithm"],
        "fingerprint_digest": challenge["fingerprint_digest"],
        "candidate_digest": PASSWORD_DIGEST,
        "outcome": "success",
        "archive_format": "zip",
        "client_version": CLIENT_VERSION,
        "verified_at": datetime.now(UTC).isoformat(),
        "signature": "placeholder-signature-value-that-is-long-enough-for-schema-validation",
    }
    model = ThirdPartyReceiptRequest.model_validate(payload)
    payload["signature"] = base64.b64encode(
        key.sign(build_canonical_receipt_payload(model), ec.ECDSA(hashes.SHA256()))
    ).decode()
    return payload


def test_third_party_verification_requires_installation_and_verification_scopes(client) -> None:
    admin = _admin_headers(client)
    app = _app(client, admin, "scope")
    user = _user_headers(client, "scope")
    token = _token(client, app, user)
    installation_id, _, public_key = _identity()
    missing = client.post(
        "/api/v1/third-party/installations",
        headers={"Authorization": token["Authorization"] + "invalid"},
        json={
            "installation_id": installation_id,
            "public_key": public_key,
            "client_version": CLIENT_VERSION,
        },
    )
    assert missing.status_code == 401

    app_no_verification = client.post(
        "/api/v1/admin/third-party-apps",
        headers=admin,
        json={
            "name": "Synthetic Install Only",
            "developer_name": "Synthetic Developer",
            "redirect_uris": ["http://127.0.0.1:49301/callback"],
            "scopes": ["desktop:installations"],
        },
    ).json()
    client.post(
        f"/api/v1/admin/third-party-apps/{app_no_verification['id']}/approve", headers=admin
    )
    token_no_verification = _token(
        client,
        app_no_verification,
        user,
        scopes="desktop:installations",
    )
    blocked = client.post(
        "/api/v1/third-party/challenges",
        headers=token_no_verification,
        json={
            "installation_id": installation_id,
            "candidate_id": str(uuid4()),
            "fingerprint_algorithm": "sha256",
            "fingerprint_digest": "a" * 64,
            "client_version": CLIENT_VERSION,
        },
    )
    assert blocked.status_code in {403, 404}
    if blocked.status_code == 403:
        assert blocked.json()["code"] == "third_party_oauth.insufficient_scope"


def test_ordinary_third_party_receipt_stays_pending_and_binds_app(client) -> None:
    admin = _admin_headers(client)
    app = _app(client, admin, "ordinary")
    owner = _user_headers(client, "ordinary-owner")
    verifier = _user_headers(client, "ordinary-verifier")
    candidate_id, fingerprint = _candidate(client, owner, "ordinary")
    token = _token(client, app, verifier)
    installation_id, key, public_key = _identity()
    registered = client.post(
        "/api/v1/third-party/installations",
        headers=token,
        json={
            "installation_id": installation_id,
            "public_key": public_key,
            "client_version": CLIENT_VERSION,
        },
    )
    assert registered.status_code == 200
    challenge = _challenge(client, token, installation_id, candidate_id, fingerprint)
    assert challenge.status_code == 200
    assert challenge.json()["canonical_payload_version"] == "third-party-desktop-receipt-v1"
    accepted = client.post(
        "/api/v1/third-party/verification-receipts",
        headers=token,
        json=_receipt(challenge.json(), app, installation_id, key),
    )
    assert accepted.status_code == 200
    assert accepted.json()["candidate_status"] == CandidateStatus.PENDING.value
    with client.app.state.database.session_factory() as db:
        receipt = db.get(VerificationReceipt, accepted.json()["receipt_id"])
        assert receipt is not None
        assert receipt.third_party_app_id == app["id"]
        assert receipt.trust_channel == "third_party_pending"
        installation = db.get(ClientInstallation, installation_id)
        challenge_row = db.get(VerificationChallenge, challenge.json()["challenge_id"])
        assert installation is not None and installation.third_party_app_id == app["id"]
        assert challenge_row is not None and challenge_row.third_party_app_id == app["id"]


def test_trusted_third_party_receipt_enters_verified_pool(client) -> None:
    admin = _admin_headers(client)
    app = _app(client, admin, "trusted", trusted=True)
    owner = _user_headers(client, "trusted-owner")
    verifier = _user_headers(client, "trusted-verifier")
    candidate_id, fingerprint = _candidate(client, owner, "trusted")
    token = _token(client, app, verifier, trusted=True)
    installation_id, key, public_key = _identity()
    assert (
        client.post(
            "/api/v1/third-party/installations",
            headers=token,
            json={
                "installation_id": installation_id,
                "public_key": public_key,
                "client_version": CLIENT_VERSION,
            },
        ).status_code
        == 200
    )
    challenge = _challenge(client, token, installation_id, candidate_id, fingerprint).json()
    accepted = client.post(
        "/api/v1/third-party/verification-receipts",
        headers=token,
        json=_receipt(challenge, app, installation_id, key),
    )
    assert accepted.status_code == 200
    assert accepted.json()["candidate_status"] == CandidateStatus.VERIFIED.value
    with client.app.state.database.session_factory() as db:
        receipt = db.get(VerificationReceipt, accepted.json()["receipt_id"])
        assert receipt is not None and receipt.trust_channel == "third_party_trusted"


def test_third_party_installation_and_challenge_cannot_cross_apps(client) -> None:
    admin = _admin_headers(client)
    app_a = _app(client, admin, "cross-a")
    app_b = _app(client, admin, "cross-b")
    user = _user_headers(client, "cross")
    token_a = _token(client, app_a, user)
    token_b = _token(client, app_b, user)
    installation_id, _, public_key = _identity()
    assert (
        client.post(
            "/api/v1/third-party/installations",
            headers=token_a,
            json={
                "installation_id": installation_id,
                "public_key": public_key,
                "client_version": CLIENT_VERSION,
            },
        ).status_code
        == 200
    )
    reused = client.post(
        "/api/v1/third-party/installations",
        headers=token_b,
        json={
            "installation_id": installation_id,
            "public_key": public_key,
            "client_version": CLIENT_VERSION,
        },
    )
    assert reused.status_code == 409
    assert reused.json()["code"] == "third_party_desktop.installation_app_mismatch"
    challenge = _challenge(client, token_a, installation_id, str(uuid4()), "b" * 64)
    assert challenge.status_code == 404
