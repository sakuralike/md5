from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest
from pydantic import SecretStr

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


class _FakeS3Error(Exception):
    def __init__(self, status_code: int) -> None:
        self.response = {"ResponseMetadata": {"HTTPStatusCode": status_code}}


class _FakeS3Client:
    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], bytes] = {}

    def head_bucket(self, *, Bucket: str) -> None:
        if Bucket not in self.buckets:
            raise _FakeS3Error(404)

    def create_bucket(self, *, Bucket: str) -> None:
        self.buckets.add(Bucket)

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        self.objects[(bucket, key)] = Path(filename).read_bytes()

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        try:
            content = self.objects[(bucket, key)]
        except KeyError as exc:
            raise _FakeS3Error(404) from exc
        Path(filename).write_bytes(content)

    def head_object(self, *, Bucket: str, Key: str) -> None:
        if (Bucket, Key) not in self.objects:
            raise _FakeS3Error(404)

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        self.objects[(Bucket, Key)] = Body

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.objects.pop((Bucket, Key), None)


def _s3_storage(tmp_path, client: _FakeS3Client) -> DesktopPluginStorage:
    settings = Settings.model_construct(
        desktop_plugin_storage_path=str(tmp_path),
        desktop_plugin_storage_backend="s3",
        desktop_plugin_s3_endpoint_url="http://synthetic-minio:9000",
        desktop_plugin_s3_bucket="synthetic-plugins",
        desktop_plugin_s3_region="us-east-1",
        desktop_plugin_s3_access_key_id="synthetic-access",
        desktop_plugin_s3_secret_access_key=SecretStr("synthetic-secret"),
        desktop_plugin_s3_force_path_style=True,
        desktop_plugin_max_package_bytes=1024,
        desktop_plugin_max_expanded_bytes=2048,
    )
    return DesktopPluginStorage(settings, client=client)


def test_s3_backend_round_trips_publish_and_revoke(tmp_path) -> None:
    client = _FakeS3Client()
    storage = _s3_storage(tmp_path, client)
    content = b"synthetic-s3-plugin"
    quarantine_key = "quarantine/version/windows-x64/session.pdpkg"

    async def chunks():
        yield content

    asyncio.run(
        storage.write_quarantine(
            key=quarantine_key,
            chunks=chunks(),
            expected_size=len(content),
            expected_sha256=hashlib.sha256(content).hexdigest(),
        )
    )
    storage.quarantine_path(quarantine_key).unlink()
    assert storage.quarantine_path(quarantine_key).read_bytes() == content

    public_key = "public/version/windows-x64/artifact.pdpkg"
    storage.publish(quarantine_key, public_key)
    storage.public_path(public_key).unlink()
    assert storage.read_public(public_key).read_bytes() == content

    revoked_key = "revoked/version/windows-x64/artifact.pdpkg"
    assert storage.move_to_revoked([public_key, quarantine_key], revoked_key)
    assert storage.revoked_path(revoked_key).read_bytes() == content
    with pytest.raises(AppError, match="公开插件制品不存在"):
        storage.read_public(public_key)


def test_s3_backend_requires_connection_settings(tmp_path) -> None:
    settings = Settings.model_construct(
        desktop_plugin_storage_path=str(tmp_path),
        desktop_plugin_storage_backend="s3",
        desktop_plugin_max_package_bytes=1024,
        desktop_plugin_max_expanded_bytes=2048,
    )
    with pytest.raises(ValueError, match="S3 插件存储缺少"):
        DesktopPluginStorage(settings)
