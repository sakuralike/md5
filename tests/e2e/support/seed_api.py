from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from password_detective.core.candidate_secrets import CandidateSecretVault
from password_detective.core.config import Settings
from password_detective.core.ids import new_id
from password_detective.core.security import hash_account_password
from password_detective.core.time import utc_now
from password_detective.db.database import Database
from password_detective.db.models.archive import Archive
from password_detective.db.models.archive_fingerprint import (
    ArchiveFingerprint,
    FingerprintAlgorithm,
)
from password_detective.db.models.password_candidate import (
    CandidateStatus,
    PasswordCandidate,
)
from password_detective.db.models.user import User, UserRole, UserStatus


def main() -> None:
    settings = Settings()
    database = Database(settings)
    database.create_tables()
    admin_username = os.environ["E2E_ADMIN_USERNAME"]
    admin_password = os.environ["E2E_ADMIN_PASSWORD"]
    admin_email = os.environ["E2E_ADMIN_EMAIL"]
    web_username = os.environ["E2E_WEB_USERNAME"]
    web_password = os.environ["E2E_WEB_PASSWORD"]
    web_email = os.environ["E2E_WEB_EMAIL"]
    verified_sha256 = os.environ["E2E_VERIFIED_SHA256"]
    verified_md5 = os.environ["E2E_VERIFIED_MD5"]
    verified_password = os.environ["E2E_VERIFIED_PASSWORD"]
    with database.session_factory() as db:
        admin = db.scalar(select(User).where(User.username == admin_username))
        if admin is None:
            admin = User(
                username=admin_username,
                email=admin_email,
                email_verified_at=utc_now(),
                account_password_hash=hash_account_password(admin_password),
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
            )
            db.add(admin)

        web_user = db.scalar(select(User).where(User.username == web_username))
        if web_user is None:
            web_user = User(
                username=web_username,
                email=web_email,
                email_verified_at=utc_now(),
                account_password_hash=hash_account_password(web_password),
                role=UserRole.USER,
                status=UserStatus.ACTIVE,
            )
            db.add(web_user)
            db.flush()

        existing_fingerprint = db.scalar(
            select(ArchiveFingerprint).where(
                ArchiveFingerprint.algorithm == FingerprintAlgorithm.SHA256,
                ArchiveFingerprint.digest == verified_sha256,
            )
        )
        if existing_fingerprint is None:
            archive = Archive(
                id=new_id(),
                created_by=web_user.id,
                optional_size=4096,
                optional_format="zip",
            )
            encrypted = CandidateSecretVault(settings.app_secret_key).encrypt(verified_password)
            candidate = PasswordCandidate(
                id=new_id(),
                archive_id=archive.id,
                secret_ciphertext=encrypted.ciphertext,
                secret_nonce=encrypted.nonce,
                secret_key_version=encrypted.key_version,
                secret_dedup_tag=encrypted.dedup_tag,
                status=CandidateStatus.VERIFIED,
                confidence_score=0.95,
                last_verified_at=utc_now(),
            )
            db.add(archive)
            db.add_all(
                [
                    ArchiveFingerprint(
                        archive_id=archive.id,
                        algorithm=FingerprintAlgorithm.SHA256,
                        digest=verified_sha256,
                    ),
                    ArchiveFingerprint(
                        archive_id=archive.id,
                        algorithm=FingerprintAlgorithm.MD5,
                        digest=verified_md5,
                    ),
                    candidate,
                ]
            )
        db.commit()
    database.dispose()


if __name__ == "__main__":
    main()
