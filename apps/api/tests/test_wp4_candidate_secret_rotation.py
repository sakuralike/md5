from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from password_detective.core.candidate_secret_rotation import rotate_candidate_secrets
from password_detective.core.candidate_secrets import CandidateSecretVault
from password_detective.core.config import Settings
from password_detective.db.database import Database
from password_detective.db.models.archive import Archive
from password_detective.db.models.password_candidate import PasswordCandidate


def _settings(tmp_path) -> Settings:
    return Settings(
        app_env="test",
        app_secret_key="synthetic-app-secret-key-for-tests",
        database_url=f"sqlite:///{(tmp_path / 'rotation.db').as_posix()}",
        candidate_secret_key_version="v2",
        candidate_secret_keyring='{"v1":"synthetic-legacy-key","v2":"synthetic-current-key"}',
        candidate_secret_dedup_key="synthetic-stable-dedup-key",
        desktop_update_storage_path=str(tmp_path / "desktop-updates"),
    )


def test_settings_parse_keyring_without_exposing_secret_values(tmp_path) -> None:
    settings = _settings(tmp_path)

    assert settings.candidate_secret_key_map == {
        "v1": "synthetic-legacy-key",
        "v2": "synthetic-current-key",
    }
    assert "synthetic-current-key" not in repr(settings)


def test_settings_reject_keyring_without_stable_dedup_key(tmp_path) -> None:
    with pytest.raises(ValidationError, match="稳定去重密钥"):
        Settings(
            app_env="test",
            app_secret_key="synthetic-app-secret-key-for-tests",
            database_url=f"sqlite:///{(tmp_path / 'invalid.db').as_posix()}",
            candidate_secret_key_version="v2",
            candidate_secret_keyring='{"v1":"legacy","v2":"current"}',
            desktop_update_storage_path=str(tmp_path / "desktop-updates"),
        )


def test_settings_reject_duplicate_keyring_versions(tmp_path) -> None:
    with pytest.raises(ValidationError, match="无重复键"):
        Settings(
            app_env="test",
            app_secret_key="synthetic-app-secret-key-for-tests",
            database_url=f"sqlite:///{(tmp_path / 'duplicate.db').as_posix()}",
            candidate_secret_key_version="v2",
            candidate_secret_keyring='{"v2":"first","v2":"second"}',
            candidate_secret_dedup_key="stable-dedup",
            desktop_update_storage_path=str(tmp_path / "desktop-updates"),
        )


def test_rotation_supports_dry_run_apply_and_rollback(tmp_path) -> None:
    settings = _settings(tmp_path)
    database = Database(settings)
    database.create_tables()
    legacy = CandidateSecretVault(
        "synthetic-legacy-key", key_version="v1", dedup_secret="synthetic-stable-dedup-key"
    )
    current = CandidateSecretVault(
        "synthetic-current-key",
        key_version="v2",
        decryption_secrets={"v1": "synthetic-legacy-key"},
        dedup_secret="synthetic-stable-dedup-key",
    )
    with database.session_factory() as db:
        archive = Archive(optional_format="zip")
        db.add(archive)
        db.flush()
        first = legacy.encrypt("synthetic-one")
        second = legacy.encrypt("synthetic-two")
        db.add_all([
            PasswordCandidate(
                archive_id=archive.id,
                secret_ciphertext=first.ciphertext,
                secret_nonce=first.nonce,
                secret_key_version=first.key_version,
                secret_dedup_tag=first.dedup_tag,
            ),
            PasswordCandidate(
                archive_id=archive.id,
                secret_ciphertext=second.ciphertext,
                secret_nonce=second.nonce,
                secret_key_version=second.key_version,
                secret_dedup_tag=second.dedup_tag,
            ),
        ])
        db.commit()

    with database.session_factory() as db:
        before = [
            (row.secret_ciphertext, row.secret_key_version, row.secret_dedup_tag)
            for row in db.scalars(select(PasswordCandidate)).all()
        ]
        dry = rotate_candidate_secrets(db, current, dry_run=True)
        db.rollback()
        assert dry.rotated == 2 and dry.dry_run
        after = [
            (row.secret_ciphertext, row.secret_key_version, row.secret_dedup_tag)
            for row in db.scalars(select(PasswordCandidate)).all()
        ]
        assert after == before

    with database.session_factory() as db:
        applied = rotate_candidate_secrets(db, current, dry_run=False)
        db.commit()
        assert applied.rotated == 2
        rows = db.scalars(select(PasswordCandidate)).all()
        assert {row.secret_key_version for row in rows} == {"v2"}
        plaintexts = {
            current.decrypt(
                ciphertext=row.secret_ciphertext,
                nonce=row.secret_nonce,
                key_version=row.secret_key_version,
            )
            for row in rows
        }
        assert plaintexts == {"synthetic-one", "synthetic-two"}
        dedup_tags = {row.secret_dedup_tag for row in rows}

    rollback = CandidateSecretVault(
        "synthetic-legacy-key",
        key_version="v1",
        decryption_secrets={"v2": "synthetic-current-key"},
        dedup_secret="synthetic-stable-dedup-key",
    )
    with database.session_factory() as db:
        rolled = rotate_candidate_secrets(db, rollback, dry_run=False)
        db.commit()
        assert rolled.rotated == 2
        rows = db.scalars(select(PasswordCandidate)).all()
        assert {row.secret_key_version for row in rows} == {"v1"}
        assert {row.secret_dedup_tag for row in rows} == dedup_tags
    database.dispose()
