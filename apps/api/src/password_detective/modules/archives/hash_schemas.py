from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from password_detective.db.models.archive_fingerprint import FingerprintAlgorithm
from password_detective.db.models.hash_detail import HashVoteOutcome
from password_detective.modules.archives.schemas import ArchiveSearchResult
from password_detective.modules.community.schemas import CommunityAuthor


class HashCommentCreateRequest(BaseModel):
    content: str = Field(min_length=2, max_length=2000)
    parent_id: str | None = Field(default=None, max_length=36)
    rules_accepted: bool

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.replace("\x00", "").strip()
        if not normalized:
            raise ValueError("评论不能为空")
        return normalized


class HashCommentResponse(BaseModel):
    id: str
    parent_id: str | None
    content: str
    author: CommunityAuthor
    like_count: int = 0
    viewer_has_liked: bool = False
    created_at: datetime


class HashInteractionResponse(BaseModel):
    algorithm: FingerprintAlgorithm
    digest: str
    like_count: int = 0
    viewer_has_liked: bool = False
    vote_counts: dict[str, int]
    viewer_vote: HashVoteOutcome | None = None


class HashDetailResponse(HashInteractionResponse):
    matched: bool
    archive: ArchiveSearchResult | None = None
    comments: list[HashCommentResponse] = Field(default_factory=list)


class HashVoteRequest(BaseModel):
    outcome: HashVoteOutcome
