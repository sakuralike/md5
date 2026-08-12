from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_SRC = ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from password_detective.core.config import Settings
from password_detective.core.time import utc_now
from password_detective.db.database import Database
from password_detective.db.models.community import (
    CommunityBoardCode,
    CommunityComment,
    CommunityContentStatus,
    CommunityPost,
)
from password_detective.modules.community.projection import (
    rebuild_reply_count_projection,
)


def build_database(tmp_path: Path) -> Database:
    database = Database(
        Settings(
            app_env="test",
            app_secret_key="synthetic-reply-count-test-secret",
            database_url=f"sqlite:///{(tmp_path / 'reply-count.db').as_posix()}",
            auto_create_tables=True,
        )
    )
    database.create_tables()
    return database


def seed_projection_fixture(database: Database) -> tuple[str, str]:
    mismatched_post_id = "10000000-0000-0000-0000-000000000001"
    consistent_post_id = "10000000-0000-0000-0000-000000000002"
    synthetic_author_id = "20000000-0000-0000-0000-000000000001"
    with database.session_factory() as db:
        db.add_all(
            [
                CommunityPost(
                    id=mismatched_post_id,
                    board_code=CommunityBoardCode.GENERAL,
                    author_id=synthetic_author_id,
                    title="合成回复数异常主题",
                    content="仅用于验证回复数投影重建，不包含真实数据。",
                    reply_count=7,
                ),
                CommunityPost(
                    id=consistent_post_id,
                    board_code=CommunityBoardCode.GENERAL,
                    author_id=synthetic_author_id,
                    title="合成回复数正常主题",
                    content="仅用于验证无需修改的投影记录。",
                    reply_count=0,
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                CommunityComment(
                    id="30000000-0000-0000-0000-000000000001",
                    post_id=mismatched_post_id,
                    author_id=synthetic_author_id,
                    content="公开合成回复，应计入投影。",
                ),
                CommunityComment(
                    id="30000000-0000-0000-0000-000000000002",
                    post_id=mismatched_post_id,
                    author_id=synthetic_author_id,
                    content="作者删除占位回复，不应计入投影。",
                    deleted_by_author_at=utc_now(),
                ),
                CommunityComment(
                    id="30000000-0000-0000-0000-000000000003",
                    post_id=mismatched_post_id,
                    author_id=synthetic_author_id,
                    content="治理移除回复，不应计入投影。",
                    status=CommunityContentStatus.REMOVED,
                ),
            ]
        )
        db.commit()
    return mismatched_post_id, consistent_post_id


def test_reply_count_projection_dry_run_reports_without_mutation(tmp_path: Path) -> None:
    database = build_database(tmp_path)
    try:
        mismatched_post_id, _ = seed_projection_fixture(database)
        with database.session_factory() as db:
            summary = rebuild_reply_count_projection(db, apply=False)
            db.rollback()
        assert summary.scanned_posts == 2
        assert summary.inconsistent_posts == 1
        assert summary.updated_posts == 0
        assert summary.changes[0].as_dict() == {
            "post_id": mismatched_post_id,
            "stored_count": 7,
            "expected_count": 1,
        }
        with database.session_factory() as db:
            post = db.get(CommunityPost, mismatched_post_id)
            assert post is not None
            assert post.reply_count == 7
    finally:
        database.dispose()


def test_reply_count_projection_apply_repairs_only_mismatches(tmp_path: Path) -> None:
    database = build_database(tmp_path)
    try:
        mismatched_post_id, consistent_post_id = seed_projection_fixture(database)
        with database.session_factory() as db:
            summary = rebuild_reply_count_projection(db, apply=True)
            db.commit()
        assert summary.scanned_posts == 2
        assert summary.inconsistent_posts == 1
        assert summary.updated_posts == 1
        with database.session_factory() as db:
            mismatched = db.get(CommunityPost, mismatched_post_id)
            consistent = db.get(CommunityPost, consistent_post_id)
            assert mismatched is not None
            assert consistent is not None
            assert mismatched.reply_count == 1
            assert consistent.reply_count == 0
    finally:
        database.dispose()
