from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.archive import Archive
from password_detective.db.models.archive_fingerprint import (
    ArchiveFingerprint,
    FingerprintAlgorithm,
)
from password_detective.db.models.authorization_declaration import AuthorizationDeclaration
from password_detective.db.models.community import (
    CommunityDirectConversation,
    CommunityDirectConversationMember,
    CommunityDirectMessage,
    CommunityInteractionPolicy,
    CommunityNotification,
    CommunityNotificationOutbox,
    CommunityPublicProfile,
)
from password_detective.db.models.privacy_request import (
    PrivacyDeletionRequest,
    PrivacyDeletionStatus,
    PrivacyExport,
)
from password_detective.db.models.user import User, UserStatus
from password_detective.modules.account_privacy.service import process_due_deletion_requests

PASSWORD = "SyntheticPrivacyPass123!"


def _register_and_login(client, suffix: str = "one") -> tuple[dict, dict[str, str]]:
    payload = {
        "username": f"privacy_{suffix}",
        "email": f"privacy-{suffix}@example.com",
        "password": PASSWORD,
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"login": payload["username"], "password": payload["password"]},
    )
    assert login.status_code == 200
    return login.json(), {"Authorization": f"Bearer {login.json()['access_token']}"}



def _conversation_with_two_users(client) -> tuple[dict, dict[str, str], str]:
    owner, owner_headers = _register_and_login(client, "dm_owner")
    _register_and_login(client, "dm_other")
    with client.app.state.database.session_factory() as db:
        other_user = db.scalar(select(User).where(User.username == "privacy_dm_other"))
        assert other_user is not None
        profile = db.get(CommunityPublicProfile, other_user.id)
        if profile is None:
            profile = CommunityPublicProfile(
                user_id=other_user.id,
                display_name=other_user.username,
                avatar_seed=other_user.id.replace("-", "")[:24].ljust(24, "0"),
            )
            db.add(profile)
            db.flush()
        profile.message_policy = CommunityInteractionPolicy.EVERYONE
        db.commit()
    response = client.post(
        "/api/v1/community/direct-conversations",
        json={"recipient_username": "privacy_dm_other"},
        headers={**owner_headers, "Idempotency-Key": "privacy-dm-conversation-0001"},
    )
    assert response.status_code == 201
    return owner, owner_headers, response.json()["conversation"]["id"]


def _send_direct_message(client, headers: dict[str, str], conversation_id: str) -> dict:
    response = client.post(
        f"/api/v1/community/direct-conversations/{conversation_id}/messages",
        json={"body": "导出用合成正文", "client_message_id": "privacy-export-message-0001"},
        headers={**headers, "Idempotency-Key": "privacy-export-message-request-0001"},
    )
    assert response.status_code == 201
    return response.json()


def _reauthenticate(
    client,
    headers: dict[str, str],
    *,
    purpose: str = "account_deletion",
    password: str = PASSWORD,
) -> str:
    response = client.post(
        "/api/v1/me/security/reauthenticate",
        json={"purpose": purpose, "current_password": password},
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["reauth_token"]



def test_privacy_export_contains_only_requesters_direct_message_records(client):
    owner, owner_headers, conversation_id = _conversation_with_two_users(client)
    _send_direct_message(client, owner_headers, conversation_id)
    export_response = client.post(
        "/api/v1/me/privacy/exports",
        headers={**owner_headers, "Idempotency-Key": "privacy-dm-export-request-0001"},
    )
    assert export_response.status_code == 202
    artifact = client.post(
        f"/api/v1/me/privacy/exports/{export_response.json()['id']}/download",
        json={"token": export_response.json()["download_token"]},
        headers=owner_headers,
    ).json()
    assert artifact["community"]["direct_messages"][0]["body"] == "导出用合成正文"
    assert artifact["community"]["direct_messages"][0]["conversation_id"] == conversation_id
    assert "ciphertext" not in artifact["community"]["direct_messages"][0]
    assert artifact["account"]["id"] == owner["user"]["id"]


def test_account_deletion_removes_direct_message_rows(client):
    owner, headers, conversation_id = _conversation_with_two_users(client)
    _send_direct_message(client, headers, conversation_id)
    reauth_token = _reauthenticate(client, headers)
    created = client.post(
        "/api/v1/me/privacy/deletion-requests",
        json={"reauth_token": reauth_token},
        headers={**headers, "Idempotency-Key": "privacy-dm-delete-request-0001"},
    )
    assert created.status_code == 202
    with client.app.state.database.session_factory() as db:
        record = db.get(PrivacyDeletionRequest, created.json()["id"])
        assert record is not None
        record.cancel_before = utc_now() - timedelta(seconds=1)
        db.commit()
        assert process_due_deletion_requests(db) == 1
        assert (
            db.scalars(
                select(CommunityDirectMessage).where(
                    CommunityDirectMessage.sender_id == owner["user"]["id"]
                )
            ).all()
            == []
        )
        assert (
            db.scalars(
                select(CommunityDirectConversationMember).where(
                    CommunityDirectConversationMember.user_id == owner["user"]["id"]
                )
            ).all()
            == []
        )
        assert db.get(CommunityDirectConversation, conversation_id) is None
        assert (
            db.scalars(
                select(CommunityNotification).where(
                    CommunityNotification.actor_id == owner["user"]["id"]
                )
            ).all()
            == []
        )
        assert (
            db.scalars(
                select(CommunityNotificationOutbox).where(
                    CommunityNotificationOutbox.recipient_id == owner["user"]["id"]
                )
            ).all()
            == []
        )

def test_reveal_history_masks_fingerprints_and_never_returns_plaintext(client):
    tokens, headers = _register_and_login(client)
    with client.app.state.database.session_factory() as db:
        archive = Archive(created_by=tokens["user"]["id"])
        db.add(archive)
        db.flush()
        db.add(
            ArchiveFingerprint(
                archive_id=archive.id,
                algorithm=FingerprintAlgorithm.SHA256,
                digest="a" * 64,
            )
        )
        audit = write_audit_log(
            db,
            actor_id=tokens["user"]["id"],
            action="archive.password_revealed",
            target_type="password_candidate",
            target_id="synthetic-candidate",
            result="success",
            details={"archive_id": archive.id, "quota_position": 1},
        )
        db.commit()
        audit_id = audit.id

    response = client.get("/api/v1/me/reveals", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["audit_id"] == audit_id
    assert body["items"][0]["fingerprint_summary"] == ["sha256:aaaaaaaa…aaaa"]
    assert "password" not in str(body).lower()
    assert "a" * 64 not in str(body)


def test_authorization_declaration_is_owned_versioned_and_idempotent(client):
    _, headers = _register_and_login(client)
    request_headers = {**headers, "Idempotency-Key": "privacy-auth-declaration-0001"}
    payload = {"purpose": "privacy_export", "source": "web", "accepted": True}
    first = client.post(
        "/api/v1/me/authorization-declarations", json=payload, headers=request_headers
    )
    replay = client.post(
        "/api/v1/me/authorization-declarations", json=payload, headers=request_headers
    )
    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
    assert first.json()["declaration_version"] == "authorization-v1"
    assert first.json()["active"] is True

    listed = client.get("/api/v1/me/authorization-declarations", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    with client.app.state.database.session_factory() as db:
        assert db.query(AuthorizationDeclaration).count() == 1


def test_privacy_export_is_owner_scoped_short_lived_and_one_time(client):
    _, owner_headers = _register_and_login(client, "owner")
    _, other_headers = _register_and_login(client, "other")
    response = client.post(
        "/api/v1/me/privacy/exports",
        headers={**owner_headers, "Idempotency-Key": "privacy-export-request-0001"},
    )
    assert response.status_code == 202
    export = response.json()
    assert export["status"] == "ready"
    assert export["download_available"] is True
    assert export["download_token"].startswith("pdx_")

    hidden = client.get(
        f"/api/v1/me/privacy/exports/{export['id']}", headers=other_headers
    )
    assert hidden.status_code == 404

    downloaded = client.post(
        f"/api/v1/me/privacy/exports/{export['id']}/download",
        json={"token": export["download_token"]},
        headers=owner_headers,
    )
    assert downloaded.status_code == 200
    artifact = downloaded.json()
    assert artifact["schema_version"] == "privacy-export-v1"
    assert artifact["account"]["email"] == "privacy-owner@example.com"
    assert "account_password" not in str(artifact)
    assert "totp_secret" not in str(artifact)
    assert "candidate_password" not in str(artifact)

    repeated = client.post(
        f"/api/v1/me/privacy/exports/{export['id']}/download",
        json={"token": export["download_token"]},
        headers=owner_headers,
    )
    assert repeated.status_code == 409
    status_response = client.get(
        f"/api/v1/me/privacy/exports/{export['id']}", headers=owner_headers
    )
    assert status_response.json()["status"] == "downloaded"
    assert status_response.json()["download_token"] is None


def test_privacy_export_expiry_clears_artifact(client):
    _, headers = _register_and_login(client)
    response = client.post(
        "/api/v1/me/privacy/exports",
        headers={**headers, "Idempotency-Key": "privacy-export-request-0002"},
    )
    export_id = response.json()["id"]
    with client.app.state.database.session_factory() as db:
        record = db.get(PrivacyExport, export_id)
        assert record is not None
        record.expires_at = utc_now() - timedelta(seconds=1)
        db.commit()

    status_response = client.get(f"/api/v1/me/privacy/exports/{export_id}", headers=headers)
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "expired"
    assert status_response.json()["download_available"] is False
    with client.app.state.database.session_factory() as db:
        record = db.get(PrivacyExport, export_id)
        assert record is not None
        assert record.artifact is None
        assert record.download_token_hash is None


def test_deletion_request_requires_reauthentication_and_can_be_cancelled(client):
    _, headers = _register_and_login(client)
    wrong = client.post(
        "/api/v1/me/security/reauthenticate",
        json={
            "purpose": "account_deletion",
            "current_password": "WrongPassword123!",
        },
        headers=headers,
    )
    assert wrong.status_code == 400
    assert wrong.json()["code"] == "auth.invalid_current_password"

    reauth_token = _reauthenticate(client, headers)
    created = client.post(
        "/api/v1/me/privacy/deletion-requests",
        json={"reauth_token": reauth_token},
        headers={**headers, "Idempotency-Key": "privacy-delete-request-0002"},
    )
    assert created.status_code == 202
    assert created.json()["status"] == "pending"
    assert created.json()["can_cancel"] is True
    replay = client.post(
        "/api/v1/me/privacy/deletion-requests",
        json={"reauth_token": reauth_token},
        headers={**headers, "Idempotency-Key": "privacy-delete-request-0002"},
    )
    assert replay.status_code == 202
    assert replay.json() == created.json()

    cancelled = client.post(
        f"/api/v1/me/privacy/deletion-requests/{created.json()['id']}/cancel",
        headers={**headers, "Idempotency-Key": "privacy-delete-cancel-0001"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["can_cancel"] is False


def test_due_deletion_anonymizes_account_and_revokes_access(client):
    tokens, headers = _register_and_login(client, "delete")
    reauth_token = _reauthenticate(client, headers)
    created = client.post(
        "/api/v1/me/privacy/deletion-requests",
        json={"reauth_token": reauth_token},
        headers={**headers, "Idempotency-Key": "privacy-delete-request-0003"},
    )
    assert created.status_code == 202
    with client.app.state.database.session_factory() as db:
        record = db.get(PrivacyDeletionRequest, created.json()["id"])
        assert record is not None
        record.cancel_before = utc_now() - timedelta(seconds=1)
        db.commit()
        assert process_due_deletion_requests(db) == 1

    profile = client.get("/api/v1/me/profile", headers=headers)
    assert profile.status_code in {401, 403}
    with client.app.state.database.session_factory() as db:
        user = db.get(User, tokens["user"]["id"])
        record = db.get(PrivacyDeletionRequest, created.json()["id"])
        assert user is not None and user.status == UserStatus.DISABLED
        assert user.email.endswith("@invalid.local")
        assert user.username.startswith("deleted_")
        assert record is not None and record.status == PrivacyDeletionStatus.COMPLETED
