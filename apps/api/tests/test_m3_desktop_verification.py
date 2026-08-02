from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select

from password_detective.db.models.desktop_verification import (
    ClientInstallation,
    InstallationStatus,
    VerificationChallenge,
    VerificationReceipt,
)
from password_detective.db.models.password_candidate import CandidateStatus, PasswordCandidate
from password_detective.db.models.verification import CandidateFeedback, VerificationSource
from password_detective.modules.desktop_verification.schemas import ReceiptRequest
from password_detective.modules.desktop_verification.service import build_canonical_receipt_payload

PASSWORD = "Synthetic-Desktop-Verification!"
PASSWORD_DIGEST = hashlib.sha256(PASSWORD.encode()).hexdigest()
CLIENT_VERSION = "0.1.0"


def _register_and_login(client, suffix: str) -> tuple[dict[str, str], str]:
    payload = {
        "username": f"desktop_{suffix}",
        "email": f"desktop-{suffix}@synthetic.example.com",
        "password": "SyntheticDesktopPass123!",
    }
    registered = client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": payload["username"], "password": payload["password"]},
    )
    assert login.status_code == 200
    body = login.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


def _create_candidate(client, headers: dict[str, str], suffix: str) -> tuple[dict, str]:
    sha256 = hashlib.sha256(f"desktop-archive-{suffix}".encode()).hexdigest()
    md5 = hashlib.md5(f"desktop-archive-{suffix}".encode(), usedforsecurity=False).hexdigest()
    response = client.post(
        "/api/v1/archives/submissions",
        headers={**headers, "Idempotency-Key": f"desktop-submission-{suffix}-0001"},
        json={
            "fingerprints": [
                {"algorithm": "sha256", "digest": sha256},
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
    return response.json(), sha256


def _new_identity() -> tuple[str, ec.EllipticCurvePrivateKey, str]:
    installation_id = str(uuid4())
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return installation_id, private_key, base64.b64encode(public_key).decode()


def _register_installation(
    client,
    headers: dict[str, str],
    installation_id: str,
    public_key: str,
    *,
    client_version: str = CLIENT_VERSION,
):
    return client.post(
        "/api/v1/desktop/installations",
        headers=headers,
        json={
            "installation_id": installation_id,
            "public_key": public_key,
            "key_algorithm": "ecdsa-p256-sha256",
            "client_version": client_version,
        },
    )


def _challenge(
    client,
    headers: dict[str, str],
    installation_id: str,
    candidate_id: str,
    fingerprint: str,
):
    return client.post(
        "/api/v1/desktop/challenges",
        headers=headers,
        json={
            "installation_id": installation_id,
            "candidate_id": candidate_id,
            "fingerprint_algorithm": "sha256",
            "fingerprint_digest": fingerprint,
            "client_version": CLIENT_VERSION,
        },
    )


def _receipt_payload(
    challenge: dict,
    private_key: ec.EllipticCurvePrivateKey,
    *,
    outcome: str = "success",
    verified_at: datetime | None = None,
) -> dict:
    payload = {
        "challenge_id": challenge["challenge_id"],
        "challenge_nonce": challenge["challenge_nonce"],
        "installation_id": challenge["installation_id"],
        "account_id": challenge["account_id"],
        "candidate_id": challenge["candidate_id"],
        "fingerprint_algorithm": challenge["fingerprint_algorithm"],
        "fingerprint_digest": challenge["fingerprint_digest"],
        "candidate_digest": PASSWORD_DIGEST,
        "outcome": outcome,
        "archive_format": "zip",
        "client_version": challenge["client_version"],
        "verified_at": (verified_at or datetime.now(UTC)).isoformat(),
        "signature": "placeholder-signature-value-that-is-long-enough-for-schema-validation",
    }
    model = ReceiptRequest.model_validate(payload)
    signature = private_key.sign(
        build_canonical_receipt_payload(model),
        ec.ECDSA(hashes.SHA256()),
    )
    payload["signature"] = base64.b64encode(signature).decode()
    return payload


def test_unsupported_client_version_returns_machine_readable_upgrade_details(client):
    verifier, _ = _register_and_login(client, "upgrade_verifier")
    installation_id, _, public_key = _new_identity()

    response = _register_installation(
        client,
        verifier,
        installation_id,
        public_key,
        client_version="0.0.1",
    )

    assert response.status_code == 426
    assert response.json()["code"] == "desktop.client_version_unsupported"
    assert response.json()["details"] == {
        "minimum_client_version": CLIENT_VERSION,
        "current_client_version": "0.0.1",
    }


def test_signed_receipt_is_accepted_once_and_becomes_desktop_evidence(client):
    owner, _ = _register_and_login(client, "owner")
    verifier, verifier_id = _register_and_login(client, "verifier")
    created, fingerprint = _create_candidate(client, owner, "accepted")
    installation_id, private_key, public_key = _new_identity()

    registered = _register_installation(client, verifier, installation_id, public_key)
    assert registered.status_code == 200
    assert registered.json()["status"] == "active"

    challenge = _challenge(
        client,
        verifier,
        installation_id,
        created["candidate_id"],
        fingerprint,
    )
    assert challenge.status_code == 200
    assert challenge.json()["canonical_payload_version"] == "desktop-receipt-v1"

    payload = _receipt_payload(challenge.json(), private_key)
    accepted = client.post("/api/v1/desktop/receipts", headers=verifier, json=payload)
    assert accepted.status_code == 200
    assert accepted.json()["candidate_status"] == "pending"
    assert accepted.json()["snapshot"]["independent_success_count"] == 1

    replay = client.post("/api/v1/desktop/receipts", headers=verifier, json=payload)
    assert replay.status_code == 409
    assert replay.json()["code"] == "desktop.challenge_replayed"

    with client.app.state.database.session_factory() as db:
        receipt = db.scalar(select(VerificationReceipt))
        assert receipt is not None
        assert receipt.user_id == verifier_id
        assert receipt.candidate_digest_hash != PASSWORD_DIGEST
        challenge_row = db.get(VerificationChallenge, challenge.json()["challenge_id"])
        assert challenge_row is not None and challenge_row.used_at is not None
        installation = db.get(ClientInstallation, installation_id)
        assert installation is not None and installation.receipt_count == 1
        feedback = db.scalar(select(CandidateFeedback))
        assert feedback is not None
        assert feedback.source == VerificationSource.DESKTOP_RECEIPT
        assert feedback.installation_id_hash is not None


def test_tampered_receipt_is_rejected_without_consuming_challenge(client):
    owner, _ = _register_and_login(client, "tamper_owner")
    verifier, _ = _register_and_login(client, "tamper_verifier")
    created, fingerprint = _create_candidate(client, owner, "tamper")
    installation_id, private_key, public_key = _new_identity()
    assert _register_installation(client, verifier, installation_id, public_key).status_code == 200
    challenge = _challenge(
        client,
        verifier,
        installation_id,
        created["candidate_id"],
        fingerprint,
    ).json()
    valid_payload = _receipt_payload(challenge, private_key)
    tampered = {**valid_payload, "outcome": "failure"}

    rejected = client.post("/api/v1/desktop/receipts", headers=verifier, json=tampered)
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "desktop.signature_invalid"

    accepted = client.post("/api/v1/desktop/receipts", headers=verifier, json=valid_payload)
    assert accepted.status_code == 200


def test_expired_challenge_clock_skew_and_revoked_installation_are_rejected(client):
    owner, _ = _register_and_login(client, "gate_owner")
    verifier, _ = _register_and_login(client, "gate_verifier")
    created, fingerprint = _create_candidate(client, owner, "gates")
    installation_id, private_key, public_key = _new_identity()
    assert _register_installation(client, verifier, installation_id, public_key).status_code == 200

    expired = _challenge(
        client,
        verifier,
        installation_id,
        created["candidate_id"],
        fingerprint,
    ).json()
    with client.app.state.database.session_factory() as db:
        row = db.get(VerificationChallenge, expired["challenge_id"])
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    expired_response = client.post(
        "/api/v1/desktop/receipts",
        headers=verifier,
        json=_receipt_payload(expired, private_key),
    )
    assert expired_response.status_code == 409
    assert expired_response.json()["code"] == "desktop.challenge_expired"

    current = _challenge(
        client,
        verifier,
        installation_id,
        created["candidate_id"],
        fingerprint,
    ).json()
    skewed = _receipt_payload(
        current,
        private_key,
        verified_at=datetime.now(UTC) - timedelta(hours=1),
    )
    skewed_response = client.post(
        "/api/v1/desktop/receipts", headers=verifier, json=skewed
    )
    assert skewed_response.status_code == 409
    assert skewed_response.json()["code"] == "desktop.receipt_clock_skew"

    revoked = client.post(
        f"/api/v1/desktop/installations/{installation_id}/revoke",
        headers=verifier,
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    blocked = _challenge(
        client,
        verifier,
        installation_id,
        created["candidate_id"],
        fingerprint,
    )
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "desktop.installation_revoked"


def test_installation_cannot_switch_accounts_or_replace_public_key(client):
    first, _ = _register_and_login(client, "account_one")
    second, _ = _register_and_login(client, "account_two")
    installation_id, _, public_key = _new_identity()
    assert _register_installation(client, first, installation_id, public_key).status_code == 200

    switched = _register_installation(client, second, installation_id, public_key)
    assert switched.status_code == 409
    assert switched.json()["code"] == "desktop.installation_account_mismatch"

    _, _, replacement_public_key = _new_identity()
    replaced = _register_installation(client, first, installation_id, replacement_public_key)
    assert replaced.status_code == 409
    assert replaced.json()["code"] == "desktop.installation_key_mismatch"


def test_two_independent_signed_receipts_can_verify_candidate(client):
    owner, _ = _register_and_login(client, "state_owner")
    first, _ = _register_and_login(client, "state_first")
    second, _ = _register_and_login(client, "state_second")
    created, fingerprint = _create_candidate(client, owner, "state")

    for headers in (first, second):
        installation_id, private_key, public_key = _new_identity()
        assert _register_installation(
            client, headers, installation_id, public_key
        ).status_code == 200
        challenge = _challenge(
            client,
            headers,
            installation_id,
            created["candidate_id"],
            fingerprint,
        ).json()
        accepted = client.post(
            "/api/v1/desktop/receipts",
            headers=headers,
            json=_receipt_payload(challenge, private_key),
        )
        assert accepted.status_code == 200

    assert accepted.json()["candidate_status"] == "verified"
    assert accepted.json()["snapshot"]["independent_success_count"] == 2
    with client.app.state.database.session_factory() as db:
        candidate = db.get(PasswordCandidate, created["candidate_id"])
        assert candidate is not None and candidate.status == CandidateStatus.VERIFIED
        installations = list(db.scalars(select(ClientInstallation)))
        assert len(installations) == 2
        assert all(item.status == InstallationStatus.ACTIVE for item in installations)
