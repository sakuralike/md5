from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from password_detective.core.config import Settings
from password_detective.main import create_app


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        app_debug=False,
        app_secret_key="test-secret-key-that-is-long-and-synthetic",
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        auto_create_tables=True,
        cors_origins="http://testserver",
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
