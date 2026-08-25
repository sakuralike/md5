from __future__ import annotations

import hashlib
import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

from password_detective.core.config import Settings
from password_detective.core.errors import AppError


class DesktopPluginStorage:
    def __init__(self, settings: Settings) -> None:
        self.root = Path(settings.desktop_plugin_storage_path).resolve()
        self.quarantine_root = self.root / "quarantine"
        self.evidence_root = self.root / "evidence"
        self.public_root = self.root / "public"
        self.revoked_root = self.root / "revoked"
        self.max_package_bytes = settings.desktop_plugin_max_package_bytes
        self.max_expanded_bytes = settings.desktop_plugin_max_expanded_bytes
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        self.public_root.mkdir(parents=True, exist_ok=True)
        self.revoked_root.mkdir(parents=True, exist_ok=True)

    def quarantine_key(self, version_id: str, architecture: str, session_id: str) -> str:
        return f"quarantine/{version_id}/{architecture}/{session_id}.pdpkg"

    def public_key(self, version_id: str, architecture: str, artifact_id: str) -> str:
        return f"public/{version_id}/{architecture}/{artifact_id}.pdpkg"

    def evidence_key(self, version_id: str, review_run_id: str, filename: str) -> str:
        return f"evidence/{version_id}/{review_run_id}/{filename}"

    def revoked_key(self, version_id: str, architecture: str, artifact_id: str) -> str:
        return f"revoked/{version_id}/{architecture}/{artifact_id}.pdpkg"

    def path_for_key(self, key: str) -> Path:
        if not key or "\\" in key or ".." in Path(key).parts or Path(key).is_absolute():
            raise AppError(
                "desktop_plugin.invalid_storage_key", "插件制品存储键无效", status_code=500
            )
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise AppError(
                "desktop_plugin.invalid_storage_key", "插件制品存储键无效", status_code=500
            )
        return path

    async def write_quarantine(
        self,
        *,
        key: str,
        chunks: AsyncIterator[bytes],
        expected_size: int,
        expected_sha256: str,
    ) -> int:
        if expected_size <= 0 or expected_size > self.max_package_bytes:
            raise AppError(
                "desktop_plugin.upload_too_large",
                "插件制品超过允许的大小",
                status_code=413,
                details={"expected_size_bytes": expected_size},
            )
        destination = self.quarantine_path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.parent / f".{destination.name}.{uuid4().hex}.upload"
        digest = hashlib.sha256()
        total = 0
        try:
            with temporary.open("xb") as stream:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > min(expected_size, self.max_package_bytes):
                        raise AppError(
                            "desktop_plugin.upload_too_large",
                            "插件制品超过允许的大小",
                            status_code=413,
                            details={"expected_size_bytes": expected_size},
                        )
                    digest.update(chunk)
                    stream.write(chunk)
            calculated = digest.hexdigest()
            if total != expected_size or calculated != expected_sha256:
                raise AppError(
                    "desktop_plugin.artifact_integrity_mismatch",
                    "插件制品大小或 SHA-256 不匹配",
                    status_code=422,
                    details={
                        "expected_size_bytes": expected_size,
                        "received_size_bytes": total,
                        "expected_sha256": expected_sha256,
                        "received_sha256": calculated,
                    },
                )
            os.replace(temporary, destination)
            return total
        finally:
            temporary.unlink(missing_ok=True)

    def read_public(self, key: str) -> Path:
        path = self.public_path(key)
        if not path.is_file():
            raise AppError("desktop_plugin.artifact_missing", "公开插件制品不存在", status_code=404)
        return path

    def quarantine_path(self, key: str) -> Path:
        return self._partition_path(key, self.quarantine_root, "隔离")

    def public_path(self, key: str) -> Path:
        return self._partition_path(key, self.public_root, "公开")

    def evidence_path(self, key: str) -> Path:
        return self._partition_path(key, self.evidence_root, "审核证据")

    def revoked_path(self, key: str) -> Path:
        return self._partition_path(key, self.revoked_root, "撤销")

    def _partition_path(self, key: str, partition_root: Path, label: str) -> Path:
        path = self.path_for_key(key)
        if not path.is_relative_to(partition_root):
            raise AppError(
                "desktop_plugin.invalid_storage_key",
                f"{label}制品存储键无效",
                status_code=500,
            )
        return path
