from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from password_detective.db.models.archive_fingerprint import FingerprintAlgorithm
from password_detective.db.models.desktop_verification import InstallationStatus
from password_detective.db.models.password_candidate import CandidateStatus
from password_detective.db.models.verification import FeedbackOutcome
from password_detective.modules.verification.schemas import VerificationSnapshot

KeyAlgorithm = Literal["ecdsa-p256-sha256"]
ArchiveFormat = Literal["zip", "7z"]


class InstallationRegistrationRequest(BaseModel):
    installation_id: UUID
    public_key: str = Field(min_length=80, max_length=2048)
    key_algorithm: KeyAlgorithm = "ecdsa-p256-sha256"
    client_version: str = Field(min_length=5, max_length=32)


class InstallationResponse(BaseModel):
    installation_id: str
    status: InstallationStatus
    key_algorithm: str
    public_key_fingerprint: str
    client_version: str
    receipt_count: int
    created_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None


class InstallationListResponse(BaseModel):
    items: list[InstallationResponse]


class ChallengeRequest(BaseModel):
    installation_id: UUID
    candidate_id: str = Field(min_length=36, max_length=36)
    fingerprint_algorithm: FingerprintAlgorithm
    fingerprint_digest: str = Field(min_length=32, max_length=128)
    client_version: str = Field(min_length=5, max_length=32)

    @field_validator("fingerprint_digest")
    @classmethod
    def normalize_digest(cls, value: str) -> str:
        return value.strip().lower()


class ChallengeResponse(BaseModel):
    challenge_id: str
    challenge_nonce: str
    installation_id: str
    account_id: str
    candidate_id: str
    fingerprint_algorithm: FingerprintAlgorithm
    fingerprint_digest: str
    client_version: str
    canonical_payload_version: str
    expires_at: datetime


class ReceiptRequest(BaseModel):
    challenge_id: str = Field(min_length=36, max_length=36)
    challenge_nonce: str = Field(min_length=32, max_length=256)
    installation_id: UUID
    account_id: str = Field(min_length=36, max_length=36)
    candidate_id: str = Field(min_length=36, max_length=36)
    fingerprint_algorithm: FingerprintAlgorithm
    fingerprint_digest: str = Field(min_length=32, max_length=128)
    candidate_digest: str = Field(min_length=64, max_length=64)
    outcome: FeedbackOutcome
    archive_format: ArchiveFormat
    client_version: str = Field(min_length=5, max_length=32)
    verified_at: datetime
    signature: str = Field(min_length=64, max_length=2048)

    @field_validator("fingerprint_digest", "candidate_digest")
    @classmethod
    def normalize_digest(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("verified_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("verified_at 必须包含时区")
        return value.astimezone(UTC)


class ReceiptResponse(BaseModel):
    receipt_id: str
    evidence_event_id: str | None
    candidate_id: str
    outcome: FeedbackOutcome
    candidate_status: CandidateStatus
    snapshot: VerificationSnapshot
    accepted_at: datetime
