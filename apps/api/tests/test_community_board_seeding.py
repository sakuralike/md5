from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from password_detective.db.database import Database
from password_detective.db.models.community import CommunityBoard
from password_detective.modules.community.boards import SEED_BOARDS, ensure_seed_boards


def test_seed_boards_is_safe_across_concurrent_database_instances(
    client: TestClient,
) -> None:
    with client.app.state.database.session_factory() as db:
        db.execute(delete(CommunityBoard))
        db.commit()

    databases = [Database(client.app.state.settings), Database(client.app.state.settings)]
    barrier = Barrier(len(databases))

    def initialize_boards(database: Database) -> None:
        barrier.wait(timeout=5)
        with database.session_factory() as db:
            ensure_seed_boards(db)

    try:
        with ThreadPoolExecutor(max_workers=len(databases)) as executor:
            futures = [executor.submit(initialize_boards, database) for database in databases]
            for future in futures:
                future.result(timeout=10)
    finally:
        for database in databases:
            database.dispose()

    with client.app.state.database.session_factory() as db:
        board_count = db.scalar(select(func.count()).select_from(CommunityBoard))
        board_codes = set(db.scalars(select(CommunityBoard.code)).all())

    assert board_count == len(SEED_BOARDS)
    assert board_codes == {board[0] for board in SEED_BOARDS}
