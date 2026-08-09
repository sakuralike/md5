from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from password_detective.core.config import Settings
from password_detective.core.security import hash_account_password
from password_detective.core.time import utc_now
from password_detective.db.database import Database
from password_detective.db.models.user import User, UserRole, UserStatus


def main() -> None:
    settings = Settings()
    database = Database(settings)
    database.create_tables()
    username = os.environ["E2E_ADMIN_USERNAME"]
    password = os.environ["E2E_ADMIN_PASSWORD"]
    email = os.environ["E2E_ADMIN_EMAIL"]
    with database.session_factory() as db:
        existing = db.scalar(select(User).where(User.username == username))
        if existing is None:
            db.add(
                User(
                    username=username,
                    email=email,
                    email_verified_at=utc_now(),
                    account_password_hash=hash_account_password(password),
                    role=UserRole.ADMIN,
                    status=UserStatus.ACTIVE,
                )
            )
            db.commit()
    database.dispose()


if __name__ == "__main__":
    main()
