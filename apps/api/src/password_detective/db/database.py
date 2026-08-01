from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from password_detective.core.config import Settings
from password_detective.db.base import Base


class Database:
    def __init__(self, settings: Settings) -> None:
        settings.ensure_local_directories()
        connect_args = {}
        engine_kwargs = {"pool_pre_ping": True}
        if settings.database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            if settings.database_url.endswith(":memory:"):
                engine_kwargs["poolclass"] = StaticPool
        self.engine = create_engine(
            settings.database_url,
            connect_args=connect_args,
            **engine_kwargs,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            autoflush=False,
            expire_on_commit=False,
        )

    def create_tables(self) -> None:
        from password_detective.db import models  # noqa: F401

        Base.metadata.create_all(self.engine)

    def session(self) -> Iterator[Session]:
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()

    def dispose(self) -> None:
        self.engine.dispose()
