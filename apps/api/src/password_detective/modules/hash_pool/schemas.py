from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from password_detective.db.models.archive_fingerprint import FingerprintAlgorithm


class HashPoolFingerprint(BaseModel):
    algorithm: FingerprintAlgorithm
    digest: str


class HashPoolOverview(BaseModel):
    verified_candidates: int
    unique_archives: int
    unique_fingerprints: int
    pending_candidates: int
    quarantined_candidates: int


class HashPoolItem(BaseModel):
    candidate_id: str
    archive_id: str
    fingerprints: list[HashPoolFingerprint]
    confidence_score: float
    submission_count: int
    feedback_count: int
    last_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


class HashPoolListResponse(BaseModel):
    overview: HashPoolOverview
    items: list[HashPoolItem]
    page: int
    page_size: int
    total: int
