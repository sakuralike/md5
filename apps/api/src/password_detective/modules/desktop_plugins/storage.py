from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

from password_detective.core.config import Settings
from password_detective.core.errors import AppError


class DesktopPluginStorage:
    """Content-addressed plugin storage with a local or S3-compatible backend."""

    def __init__(self, settings: Settings, *, client: object | None = None) -> None:
        self.root = Path(settings.desktop_plugin_storage_path).resolve()
        self.backend = getattr(settings, "desktop_plugin_storage_backend", "filesystem")
        if self.backend not in {"filesystem", "s3"}:
            raise ValueError("DESKTOP_PLUGIN_STORAGE_BACKEND 配置无效")
        s3_endpoint = getattr(settings, "desktop_plugin_s3_endpoint_url", "")
        s3_bucket = getattr(settings, "desktop_plugin_s3_bucket", "")
        s3_region = getattr(settings, "desktop_plugin_s3_region", "us-east-1")
        s3_access_key = getattr(settings, "desktop_plugin_s3_access_key_id", "")
        s3_secret = getattr(settings, "desktop_plugin_s3_secret_access_key", None)
        s3_secret_value = s3_secret.get_secret_value() if s3_secret is not None else ""
        s3_path_style = getattr(settings, "desktop_plugin_s3_force_path_style", True)
        if self.backend == "s3" and (
            not s3_endpoint or not s3_bucket or not s3_access_key or not s3_secret_value
        ):
            raise ValueError("S3 插件存储缺少 endpoint、bucket 或凭据")

        self.cache_root = self.root if self.backend == "filesystem" else self.root / ".cache"
        self.quarantine_root = self.cache_root / "quarantine"
        self.evidence_root = self.cache_root / "evidence"
        self.public_root = self.cache_root / "public"
        self.revoked_root = self.cache_root / "revoked"
        self.max_package_bytes = settings.desktop_plugin_max_package_bytes
        self.max_expanded_bytes = settings.desktop_plugin_max_expanded_bytes
        self.s3_bucket = s3_bucket
        self._s3_client = client
        self._bucket_ready = False
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        self.public_root.mkdir(parents=True, exist_ok=True)
        self.revoked_root.mkdir(parents=True, exist_ok=True)
        if self.backend == "s3" and self._s3_client is None:
            import boto3
            from botocore.config import Config

            self._s3_client = boto3.client(
                "s3",
                endpoint_url=s3_endpoint,
                region_name=s3_region,
                aws_access_key_id=s3_access_key,
                aws_secret_access_key=s3_secret_value,
                config=Config(
                    s3={
                        "addressing_style": (
                            "path" if s3_path_style else "auto"
                        )
                    }
                ),
            )

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
        path = (self.cache_root / key).resolve()
        if not path.is_relative_to(self.cache_root):
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
            if self.backend == "s3":
                await asyncio.to_thread(self._upload_file, key, destination)
            return total
        finally:
            temporary.unlink(missing_ok=True)

    def read_public(self, key: str) -> Path:
        path = self.public_path(key)
        if not path.is_file():
            raise AppError("desktop_plugin.artifact_missing", "公开插件制品不存在", status_code=404)
        return path

    def write_evidence_json(self, key: str, payload: dict[str, Any]) -> None:
        destination = self.evidence_path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        temporary = destination.parent / f".{destination.name}.{uuid4().hex}.write"
        try:
            temporary.write_bytes(encoded)
            os.replace(temporary, destination)
            if self.backend == "s3":
                self._put_bytes(key, encoded, content_type="application/json")
        finally:
            temporary.unlink(missing_ok=True)

    def delete(self, key: str) -> None:
        path = self.path_for_key(key)
        path.unlink(missing_ok=True)
        if self.backend == "s3":
            self._delete_object(key)

    def publish(self, source_key: str, public_key: str) -> None:
        source = self.quarantine_path(source_key)
        if not source.is_file():
            raise AppError("desktop_plugin.artifact_missing", "隔离插件制品不存在", status_code=422)
        destination = self.public_path(public_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".publish")
        try:
            temporary.write_bytes(source.read_bytes())
            temporary.replace(destination)
            if self.backend == "s3":
                self._upload_file(public_key, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def move_to_revoked(self, source_keys: list[str], revoked_key: str) -> bool:
        source: Path | None = None
        source_key: str | None = None
        for candidate in source_keys:
            candidate_path = self.path_for_key(candidate)
            if candidate_path.is_file() or self._download_if_missing(candidate, candidate_path):
                source = candidate_path
                source_key = candidate
                break
        if source is None or source_key is None:
            return False
        destination = self.revoked_path(revoked_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".revoke")
        try:
            temporary.write_bytes(source.read_bytes())
            temporary.replace(destination)
            if self.backend == "s3":
                self._upload_file(revoked_key, destination)
                for candidate in source_keys:
                    self._delete_object(candidate)
            source.unlink(missing_ok=True)
            return True
        finally:
            temporary.unlink(missing_ok=True)

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
        if self.backend == "s3":
            self._download_if_missing(key, path)
        return path

    def _download_if_missing(self, key: str, destination: Path) -> bool:
        if self.backend != "s3":
            return destination.is_file()
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._ensure_bucket()
            if not self._object_exists(key):
                destination.unlink(missing_ok=True)
                return False
            if destination.is_file():
                return True
            self._s3().download_file(self.s3_bucket, key, str(destination))
            return destination.is_file()
        except Exception as exc:  # boto3 exposes backend-specific ClientError types
            if self._is_missing_error(exc):
                destination.unlink(missing_ok=True)
                return False
            raise AppError(
                "desktop_plugin.storage_unavailable", "插件对象存储暂不可用", status_code=503
            ) from exc

    def _object_exists(self, key: str) -> bool:
        try:
            self._s3().head_object(Bucket=self.s3_bucket, Key=key)
            return True
        except Exception as exc:  # boto3 exposes backend-specific ClientError types
            if self._is_missing_error(exc):
                return False
            raise AppError(
                "desktop_plugin.storage_unavailable", "插件对象存储暂不可用", status_code=503
            ) from exc

    def _s3(self) -> Any:
        if self._s3_client is None:
            raise AppError(
                "desktop_plugin.storage_unavailable", "插件对象存储未配置", status_code=503
            )
        return self._s3_client

    def _ensure_bucket(self) -> None:
        if self.backend != "s3" or self._bucket_ready:
            return
        client = self._s3()
        try:
            client.head_bucket(Bucket=self.s3_bucket)
        except Exception as exc:  # boto3 exposes backend-specific ClientError types
            if not self._is_missing_error(exc):
                raise AppError(
                    "desktop_plugin.storage_unavailable", "插件对象存储暂不可用", status_code=503
                ) from exc
            try:
                client.create_bucket(Bucket=self.s3_bucket)
            except Exception as create_exc:
                if not self._is_conflict_error(create_exc):
                    raise AppError(
                        "desktop_plugin.storage_unavailable",
                        "插件对象存储暂不可用",
                        status_code=503,
                    ) from create_exc
        self._bucket_ready = True

    def _upload_file(self, key: str, source: Path) -> None:
        self._ensure_bucket()
        self._s3().upload_file(str(source), self.s3_bucket, key)

    def _put_bytes(self, key: str, body: bytes, *, content_type: str) -> None:
        self._ensure_bucket()
        self._s3().put_object(
            Bucket=self.s3_bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )

    def _delete_object(self, key: str) -> None:
        self._ensure_bucket()
        self._s3().delete_object(Bucket=self.s3_bucket, Key=key)

    @staticmethod
    def _is_missing_error(error: Exception) -> bool:
        response = getattr(error, "response", {})
        metadata = response.get("ResponseMetadata", {}) if isinstance(response, dict) else {}
        code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
        return metadata.get("HTTPStatusCode") == 404 or code in {"404", "NoSuchKey", "NoSuchBucket"}

    @staticmethod
    def _is_conflict_error(error: Exception) -> bool:
        response = getattr(error, "response", {})
        metadata = response.get("ResponseMetadata", {}) if isinstance(response, dict) else {}
        code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
        return metadata.get("HTTPStatusCode") == 409 or code in {
            "BucketAlreadyExists",
            "BucketAlreadyOwnedByYou",
        }
