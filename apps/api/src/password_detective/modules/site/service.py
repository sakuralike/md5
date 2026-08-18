from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from password_detective.db.models.archive_fingerprint import ArchiveFingerprint
from password_detective.db.models.hash_detail import (
    HashComment,
    HashLike,
    HashVote,
    HashVoteOutcome,
)
from password_detective.db.models.points_ledger import PointsLedger, PointsLedgerStatus
from password_detective.db.models.submission import Submission
from password_detective.db.models.system_setting import SystemSetting
from password_detective.db.models.user import User, UserStatus
from password_detective.modules.admin.seo_settings import default_seo_settings
from password_detective.modules.admin.setting_schemas import (
    SeoSettings,
    SiteNavigationItem,
    default_site_navigation,
)
from password_detective.modules.site.schemas import (
    HomeDiscoveryResponse,
    HotHashSummary,
    PublicSeoConfig,
    PublicSiteConfigResponse,
    UserRankingSummary,
)


def _setting_value(db: Session, key: str, default: object) -> object:
    record = db.get(SystemSetting, key)
    if record is None:
        return default
    return record.value_json.get("value", default)


def _public_seo_config(db: Session) -> PublicSeoConfig:
    defaults = default_seo_settings()
    raw_settings = _setting_value(
        db,
        "seo_settings",
        defaults.model_dump(mode="json"),
    )
    try:
        settings = SeoSettings.model_validate(raw_settings)
    except (TypeError, ValueError):
        settings = defaults

    if not settings.enabled:
        settings = SeoSettings(
            enabled=False,
            indexing_enabled=False,
            title_separator=settings.title_separator,
            open_graph_enabled=False,
            sitemap_enabled=settings.sitemap_enabled,
        )

    return PublicSeoConfig.model_validate(
        settings.model_dump(mode="json", exclude={"sitemap_enabled"})
    )


def get_public_site_config(db: Session) -> PublicSiteConfigResponse:
    raw_name = _setting_value(db, "site_name", "密码侦探社")
    raw_logo = _setting_value(db, "site_logo_url", "")
    raw_navigation = _setting_value(
        db, "site_navigation", [item.model_dump(mode="json") for item in default_site_navigation()]
    )
    try:
        navigation = [SiteNavigationItem.model_validate(item) for item in raw_navigation]
    except (TypeError, ValueError):
        navigation = default_site_navigation()
    return PublicSiteConfigResponse(
        site_name=raw_name if isinstance(raw_name, str) and raw_name.strip() else "密码侦探社",
        site_logo_url=raw_logo if isinstance(raw_logo, str) else "",
        navigation=[item for item in navigation if item.enabled],
        seo=_public_seo_config(db),
    )


def get_home_discovery(db: Session, *, limit: int = 5) -> HomeDiscoveryResponse:
    like_count = func.count(func.distinct(HashLike.id))
    comment_count = func.count(func.distinct(HashComment.id))
    useful_vote_count = func.count(
        func.distinct(case((HashVote.outcome == HashVoteOutcome.USEFUL, HashVote.id)))
    )
    hot_rows = db.execute(
        select(
            ArchiveFingerprint.algorithm,
            ArchiveFingerprint.digest,
            like_count.label("like_count"),
            comment_count.label("comment_count"),
            useful_vote_count.label("useful_vote_count"),
        )
        .outerjoin(HashLike, HashLike.fingerprint_id == ArchiveFingerprint.id)
        .outerjoin(HashComment, HashComment.fingerprint_id == ArchiveFingerprint.id)
        .outerjoin(HashVote, HashVote.fingerprint_id == ArchiveFingerprint.id)
        .group_by(ArchiveFingerprint.id, ArchiveFingerprint.algorithm, ArchiveFingerprint.digest)
        .having(like_count + comment_count + useful_vote_count > 0)
        .order_by(
            (like_count * 3 + comment_count * 2 + useful_vote_count * 2).desc(),
            ArchiveFingerprint.created_at.desc(),
        )
        .limit(limit)
    ).all()
    hot_hashes = [
        HotHashSummary(
            algorithm=row.algorithm,
            digest=row.digest,
            like_count=row.like_count,
            comment_count=row.comment_count,
            useful_vote_count=row.useful_vote_count,
            heat_score=row.like_count * 3 + row.comment_count * 2 + row.useful_vote_count * 2,
        )
        for row in hot_rows
    ]

    contribution_count = func.count(Submission.id)
    contribution_rows = db.execute(
        select(User.id, User.username, contribution_count.label("score"))
        .join(Submission, Submission.user_id == User.id)
        .where(User.status == UserStatus.ACTIVE)
        .group_by(User.id, User.username)
        .order_by(contribution_count.desc(), User.created_at.asc(), User.id.asc())
        .limit(limit)
    ).all()

    points_score = func.coalesce(func.sum(PointsLedger.amount), 0)
    points_rows = db.execute(
        select(User.id, User.username, points_score.label("score"))
        .join(PointsLedger, PointsLedger.user_id == User.id)
        .where(User.status == UserStatus.ACTIVE, PointsLedger.status == PointsLedgerStatus.POSTED)
        .group_by(User.id, User.username)
        .having(points_score > 0)
        .order_by(points_score.desc(), User.created_at.asc(), User.id.asc())
        .limit(limit)
    ).all()

    return HomeDiscoveryResponse(
        hot_hashes=hot_hashes,
        contribution_leaders=[
            UserRankingSummary(rank=index, uid=row.id, username=row.username, score=row.score)
            for index, row in enumerate(contribution_rows, start=1)
        ],
        points_leaders=[
            UserRankingSummary(rank=index, uid=row.id, username=row.username, score=row.score)
            for index, row in enumerate(points_rows, start=1)
        ],
    )
