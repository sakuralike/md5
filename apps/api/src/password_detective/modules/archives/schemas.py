from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from password_detective.db.models.archive_fingerprint import FingerprintAlgorithm
from password_detective.db.models.password_candidate import CandidateStatus
from password_detective.db.models.verification import FeedbackOutcome


class FingerprintInput(BaseModel):
    algorithm: FingerprintAlgorithm | None = None
    digest: str = Field(min_length=32, max_length=128)

    @field_validator("digest")
    @classmethod
    def normalize_digest(cls, value: str) -> str:
        return value.strip().lower()


class SubmissionRequest(BaseModel):
    fingerprints: list[FingerprintInput] = Field(min_length=1, max_length=4)
    password: str = Field(min_length=1, max_length=512)
    authorization_confirmed: bool
    authorization_version: str = Field(min_length=1, max_length=32)
    optional_size: int | None = Field(default=None, ge=0)
    optional_format: str | None = Field(default=None, max_length=16)

    @field_validator("optional_format")
    @classmethod
    def normalize_format(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else None

    @model_validator(mode="after")
    def require_authorization(self) -> SubmissionRequest:
        if not self.authorization_confirmed:
            raise ValueError("必须确认拥有或获授权处理该压缩包")
        return self


class NormalizedFingerprint(BaseModel):
    algorithm: FingerprintAlgorithm
    digest: str


class CandidateSummary(BaseModel):
    id: str
    status: CandidateStatus
    confidence_score: float
    masked_secret: str = "••••••••"
    submission_count: int
    success_evidence_count: int = 0
    failure_evidence_count: int = 0
    my_feedback: FeedbackOutcome | None = None
    last_verified_at: datetime | None


class ArchiveSearchResult(BaseModel):
    id: str
    optional_size: int | None
    optional_format: str | None
    fingerprints: list[NormalizedFingerprint]
    candidate_count: int
    status_counts: dict[str, int]
    candidates: list[CandidateSummary]


class ArchiveSearchResponse(BaseModel):
    matched: bool
    query: NormalizedFingerprint
    authenticated: bool
    archive: ArchiveSearchResult | None = None


class SubmissionResponse(BaseModel):
    submission_id: str
    archive_id: str
    candidate_id: str
    candidate_status: CandidateStatus
    archive_created: bool
    candidate_created: bool
    evidence_merged: bool
    pending_points: int
    created_at: datetime


class RevealResponse(BaseModel):
    archive_id: str
    candidate_id: str
    password: str
    candidate_status: CandidateStatus
    remaining_daily_quota: int


class MySubmissionItem(BaseModel):
    id: str
    archive_id: str
    candidate_id: str
    candidate_status: CandidateStatus
    fingerprints: list[NormalizedFingerprint]
    source: str
    authorization_version: str
    created_at: datetime


class MySubmissionsResponse(BaseModel):
    items: list[MySubmissionItem]
    page: int
    page_size: int
    total: int
