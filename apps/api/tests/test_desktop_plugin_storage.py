from __future__ import annotations

import asyncio
import hashlib

import pytest

from password_detective.core.config import Settings
from password_detective.core.errors import AppError
from password_detective.modules.desktop_plugins.storage import DesktopPluginStorage


def _storage(tmp_path) -> DesktopPluginStorage:
    settings = Settings.model_construct(
        desktop_plugin_storage_path=str(tmp_path),
        desktop_plugin_max_package_bytes=1024,
        desktop_plugin_max_expanded_bytes=2048,
    )
    return DesktopPluginStorage(settings)


def test_write_quarantine_writes_verified_artifact(tmp_path) -> None:
    storage = _storage(tmp_path)
    content = b"synthetic-plugin-package"

    async def chunks():
        yield content[:10]
        yield content[10:]

    total = asyncio.run(
        storage.write_quarantine(
            key="quarantine/version/windows-x64/session.pdpkg",
            chunks=chunks(),
            expected_size=len(content),
            expected_sha256=hashlib.sha256(content).hexdigest(),
        )
    )

    assert total == len(content)
    assert storage.quarantine_path(
        "quarantine/version/windows-x64/session.pdpkg"
    ).read_bytes() == content


def test_write_quarantine_rejects_public_storage_key(tmp_path) -> None:
    storage = _storage(tmp_path)

    async def chunks():
        yield b"x"

    with pytest.raises(AppError) as captured:
        asyncio.run(
            storage.write_quarantine(
                key="public/escaped.pdpkg",
                chunks=chunks(),
                expected_size=1,
                expected_sha256=hashlib.sha256(b"x").hexdigest(),
            )
        )

    assert captured.value.code == "desktop_plugin.invalid_storage_key"
    assert not (tmp_path / "public" / "escaped.pdpkg").exists()
