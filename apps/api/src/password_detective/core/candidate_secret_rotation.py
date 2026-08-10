from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from password_detective.core.candidate_secrets import CandidateSecretVault
from password_detective.core.errors import AppError
from password_detective.db.models.password_candidate import PasswordCandidate


@dataclass(frozen=True)
class CandidateSecretRotationSummary:
    scanned: int
    rotated: int
    skipped: int
    dry_run: bool
    target_version: str
    source_versions: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def rotate_candidate_secrets(
    db: Session,
    vault: CandidateSecretVault,
    *,
    dry_run: bool = True,
    source_versions: set[str] | None = None,
) -> CandidateSecretRotationSummary:
    """Re-encrypt candidate ciphertexts in place, preserving stable dedup tags."""
    source_filter = source_versions or set()
    counts: Counter[str] = Counter()
    scanned = rotated = skipped = 0
    candidates = db.scalars(select(PasswordCandidate).order_by(PasswordCandidate.id)).all()
    for candidate in candidates:
        scanned += 1
        counts[candidate.secret_key_version] += 1
        if candidate.secret_key_version == vault.key_version or (
            source_filter and candidate.secret_key_version not in source_filter
        ):
            skipped += 1
            continue
        secret = vault.decrypt(
            ciphertext=candidate.secret_ciphertext,
            nonce=candidate.secret_nonce,
            key_version=candidate.secret_key_version,
        )
        if vault.dedup_tag(secret) != candidate.secret_dedup_tag:
            raise AppError(
                "archive.secret_dedup_mismatch",
                "候选密码去重校验失败，已停止密钥轮换",
                status_code=500,
            )
        encrypted = vault.encrypt(secret)
        if not dry_run:
            candidate.secret_ciphertext = encrypted.ciphertext
            candidate.secret_nonce = encrypted.nonce
            candidate.secret_key_version = encrypted.key_version
        rotated += 1

    return CandidateSecretRotationSummary(
        scanned=scanned,
        rotated=rotated,
        skipped=skipped,
        dry_run=dry_run,
        target_version=vault.key_version,
        source_versions=dict(sorted(counts.items())),
    )
