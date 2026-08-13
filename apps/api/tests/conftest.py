from __future__ import annotations

from collections.abc import Iterator

import fakeredis
import pytest
from fastapi.testclient import TestClient

from password_detective.core.config import Settings
from password_detective.core.notifications import MemoryNotificationGateway
from password_detective.main import create_app


@pytest.fixture
def notifications() -> MemoryNotificationGateway:
    return MemoryNotificationGateway()


@pytest.fixture
def client(tmp_path, notifications: MemoryNotificationGateway) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        app_debug=False,
        app_secret_key="test-secret-key-that-is-long-and-synthetic",
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        redis_url="redis://unused/0",
        rate_limit_backend="redis",
        rate_limit_namespace=f"test:{tmp_path.name}",
        notification_backend="memory",
        site_asset_storage_path=str(tmp_path / "site-assets"),
        desktop_update_storage_path=str(tmp_path / "desktop-updates"),
        auto_create_tables=True,
        cors_origins="http://testserver",
    )
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    app = create_app(
        settings,
        redis_client=redis_client,
        notification_gateway=notifications,
    )
    with TestClient(app) as test_client:
        yield test_client
