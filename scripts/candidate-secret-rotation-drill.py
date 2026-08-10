from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from password_detective.core.candidate_secret_rotation import rotate_candidate_secrets
from password_detective.core.candidate_secrets import CandidateSecretVault
from password_detective.core.config import Settings
from password_detective.db.database import Database
from password_detective.db.models.archive import Archive
from password_detective.db.models.password_candidate import PasswordCandidate

SYNTHETIC_PASSWORDS = ("synthetic-rotation-one", "synthetic-rotation-two")
LEGACY_KEY = "synthetic-legacy-candidate-key-0001"
CURRENT_KEY = "synthetic-current-candidate-key-0002"
DEDUP_KEY = "synthetic-stable-candidate-dedup-key"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run candidate secret key rotation and rollback drill")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".local/candidate-secret-rotation-wp4-iteration-10"),
    )
    return parser.parse_args()


def snapshot(db) -> list[dict[str, str]]:
    return [
        {
            "ciphertext_sha256": hashlib.sha256(row.secret_ciphertext.encode()).hexdigest(),
            "key_version": row.secret_key_version,
            "dedup_tag": row.secret_dedup_tag,
        }
        for row in db.scalars(select(PasswordCandidate).order_by(PasswordCandidate.id)).all()
    ]


def main() -> int:
    args = parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    settings = Settings(
        app_env="test",
        app_secret_key="synthetic-drill-app-key-that-is-not-production",
        database_url=f"sqlite:///{(output / 'rotation-drill.db').as_posix()}",
        desktop_update_storage_path=str(output / "desktop-updates"),
    )
    database = Database(settings)
    database.create_tables()
    legacy = CandidateSecretVault(LEGACY_KEY, key_version="v1", dedup_secret=DEDUP_KEY)
    current = CandidateSecretVault(
        CURRENT_KEY,
        key_version="v2",
        decryption_secrets={"v1": LEGACY_KEY},
        dedup_secret=DEDUP_KEY,
    )
    rollback = CandidateSecretVault(
        LEGACY_KEY,
        key_version="v1",
        decryption_secrets={"v2": CURRENT_KEY},
        dedup_secret=DEDUP_KEY,
    )
    try:
        with database.session_factory() as db:
            archive = Archive(optional_format="zip")
            db.add(archive)
            db.flush()
            for plaintext in SYNTHETIC_PASSWORDS:
                encrypted = legacy.encrypt(plaintext)
                db.add(
                    PasswordCandidate(
                        archive_id=archive.id,
                        secret_ciphertext=encrypted.ciphertext,
                        secret_nonce=encrypted.nonce,
                        secret_key_version=encrypted.key_version,
                        secret_dedup_tag=encrypted.dedup_tag,
                    )
                )
            db.commit()

        with database.session_factory() as db:
            initial = snapshot(db)
            old_key_read = all(
                current.decrypt(
                    ciphertext=row.secret_ciphertext,
                    nonce=row.secret_nonce,
                    key_version=row.secret_key_version,
                )
                in SYNTHETIC_PASSWORDS
                for row in db.scalars(select(PasswordCandidate)).all()
            )
            dry_run = rotate_candidate_secrets(db, current, dry_run=True)
            db.rollback()
            after_dry_run = snapshot(db)

        with database.session_factory() as db:
            rotation = rotate_candidate_secrets(db, current, dry_run=False)
            db.commit()
            after_rotation = snapshot(db)
            rotation_read = {
                current.decrypt(
                    ciphertext=row.secret_ciphertext,
                    nonce=row.secret_nonce,
                    key_version=row.secret_key_version,
                )
                for row in db.scalars(select(PasswordCandidate)).all()
            }

        with database.session_factory() as db:
            rollback_summary = rotate_candidate_secrets(db, rollback, dry_run=False)
            db.commit()
            after_rollback = snapshot(db)
            rollback_read = {
                rollback.decrypt(
                    ciphertext=row.secret_ciphertext,
                    nonce=row.secret_nonce,
                    key_version=row.secret_key_version,
                )
                for row in db.scalars(select(PasswordCandidate)).all()
            }

        checks = {
            "old_key_read_succeeded": old_key_read,
            "dry_run_left_database_unchanged": initial == after_dry_run,
            "rotation_wrote_current_version": {row["key_version"] for row in after_rotation} == {"v2"},
            "rotation_plaintexts_verified": rotation_read == set(SYNTHETIC_PASSWORDS),
            "rollback_wrote_legacy_version": {row["key_version"] for row in after_rollback} == {"v1"},
            "rollback_plaintexts_verified": rollback_read == set(SYNTHETIC_PASSWORDS),
            "dedup_tags_stable": [row["dedup_tag"] for row in initial]
            == [row["dedup_tag"] for row in after_rotation]
            == [row["dedup_tag"] for row in after_rollback],
            "ciphertexts_changed_on_rotation": [row["ciphertext_sha256"] for row in initial]
            != [row["ciphertext_sha256"] for row in after_rotation],
        }
        report = {
            "schema_version": 1,
            "drill": "candidate-secret-key-rotation",
            "status": "passed" if all(checks.values()) else "failed",
            "synthetic_record_count": len(SYNTHETIC_PASSWORDS),
            "checks": checks,
            "dry_run": dry_run.as_dict(),
            "rotation": rotation.as_dict(),
            "rollback": rollback_summary.as_dict(),
            "versions": {"initial": "v1", "current": "v2", "rollback": "v1"},
        }
        report_path = output / "rotation-report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(report_path)
        return 0 if report["status"] == "passed" else 1
    finally:
        database.dispose()
        database_path = output / "rotation-drill.db"
        if database_path.exists():
            database_path.unlink()
        desktop_path = output / "desktop-updates"
        if desktop_path.exists():
            shutil.rmtree(desktop_path)


if __name__ == "__main__":
    raise SystemExit(main())
