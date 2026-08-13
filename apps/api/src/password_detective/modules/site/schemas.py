from __future__ import annotations

from pydantic import BaseModel, Field

from password_detective.db.models.archive_fingerprint import FingerprintAlgorithm
from password_detective.modules.admin.setting_schemas import SiteNavigationItem


class PublicSiteConfigResponse(BaseModel):
    site_name: str
    site_logo_url: str
    navigation: list[SiteNavigationItem]


class HotHashSummary(BaseModel):
    algorithm: FingerprintAlgorithm
    digest: str
    like_count: int = 0
    comment_count: int = 0
    useful_vote_count: int = 0
    heat_score: int = 0


class UserRankingSummary(BaseModel):
    rank: int = Field(ge=1, le=5)
    uid: str
    username: str
    score: int


class HomeDiscoveryResponse(BaseModel):
    hot_hashes: list[HotHashSummary]
    contribution_leaders: list[UserRankingSummary]
    points_leaders: list[UserRankingSummary]
