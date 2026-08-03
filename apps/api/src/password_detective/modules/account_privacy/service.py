from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.orm import Session

from password_detective.core.config import Settings
from password_detective.core.errors import AppError
from password_detective.core.security import (
    hash_account_password,
    hash_opaque_token,
)
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.account_action_token import AccountActionToken
from password_detective.db.models.archive_fingerprint import ArchiveFingerprint
from password_detective.db.models.audit_log import AuditLog
from password_detective.db.models.authorization_declaration import AuthorizationDeclaration
from password_detective.db.models.privacy_request import (
    PrivacyDeletionRequest,
    PrivacyDeletionStatus,
    PrivacyExport,
    PrivacyExportStatus,
)
from password_detective.db.models.reauthentication_grant import ReauthenticationPurpose
from password_detective.db.models.submission import Submission
from password_detective.db.models.user import User, UserRole, UserStatus
from password_detective.db.models.user_session import UserSession
from password_detective.modules.account_privacy.schemas import (
    AuthorizationDeclarationCreateRequest,
    AuthorizationDeclarationListResponse,
    AuthorizationDeclarationResponse,
    PrivacyDeletionResponse,
    PrivacyExportResponse,
    RevealHistoryItem,
    RevealHistoryResponse,
)
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.auth.reauthentication import (
    consume_reauthentication_grant,
    revoke_reauthentication_grants,
)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _token_fernet(settings: Settings) -> Fernet:
    key = base64.urlsafe_b64encode(
        hashlib.sha256(
            f"password-detective:privacy-download:{settings.app_secret_key}".encode()
        ).digest()
    )
    return Fernet(key)


def _mask_digest(algorithm: str, digest: str) -> str:
    masked = (
        digest[:4] + "…" + digest[-2:]
        if len(digest) <= 16
        else digest[:8] + "…" + digest[-4:]
    )
    return f"{algorithm}:{masked}"


def list_reveal_history(
    db: Session, *, principal: Principal, page: int, page_size: int
) -> RevealHistoryResponse:
    filters = (
        AuditLog.actor_id == principal.user.id,
        AuditLog.action == "archive.password_revealed",
    )
    total = db.scalar(select(func.count(AuditLog.id)).where(*filters)) or 0
    logs = db.scalars(
        select(AuditLog)
        .where(*filters)
        .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    archive_ids = {
        str(entry.details.get("archive_id"))
        for entry in logs
        if entry.details.get("archive_id")
    }
    fingerprints: dict[str, list[str]] = {archive_id: [] for archive_id in archive_ids}
    if archive_ids:
        rows = db.scalars(
            select(ArchiveFingerprint)
            .where(ArchiveFingerprint.archive_id.in_(archive_ids))
            .order_by(ArchiveFingerprint.algorithm, ArchiveFingerprint.digest)
        ).all()
        for row in rows:
            fingerprints[row.archive_id].append(
                _mask_digest(row.algorithm.value, row.digest)
            )
    items = []
    for entry in logs:
        archive_id = entry.details.get("archive_id")
        normalized_archive_id = str(archive_id) if archive_id else None
        items.append(
            RevealHistoryItem(
                audit_id=entry.id,
                archive_id=normalized_archive_id,
                fingerprint_summary=fingerprints.get(normalized_archive_id or "", []),
                result=entry.result,
                revealed_at=entry.created_at,
            )
        )
    return RevealHistoryResponse(items=items, page=page, page_size=page_size, total=total)


def _declaration_response(record: AuthorizationDeclaration) -> AuthorizationDeclarationResponse:
    return AuthorizationDeclarationResponse(
        id=record.id,
        declaration_version=record.declaration_version,
        purpose=record.purpose,
        source=record.source,
        confirmed_at=record.confirmed_at,
        withdrawn_at=record.withdrawn_at,
        active=record.withdrawn_at is None,
    )


def list_authorization_declarations(
    db: Session, *, principal: Principal, page: int, page_size: int
) -> AuthorizationDeclarationListResponse:
    total = db.scalar(
        select(func.count(AuthorizationDeclaration.id)).where(
            AuthorizationDeclaration.user_id == principal.user.id
        )
    ) or 0
    records = db.scalars(
        select(AuthorizationDeclaration)
        .where(AuthorizationDeclaration.user_id == principal.user.id)
        .order_by(
            desc(AuthorizationDeclaration.confirmed_at),
            desc(AuthorizationDeclaration.id),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return AuthorizationDeclarationListResponse(
        items=[_declaration_response(record) for record in records],
        page=page,
        page_size=page_size,
        total=total,
    )


def confirm_authorization_declaration(
    db: Session,
    settings: Settings,
    *,
    principal: Principal,
    payload: AuthorizationDeclarationCreateRequest,
    context: ClientContext,
) -> AuthorizationDeclarationResponse:
    record = db.scalar(
        select(AuthorizationDeclaration).where(
            AuthorizationDeclaration.user_id == principal.user.id,
            AuthorizationDeclaration.declaration_version
            == settings.authorization_declaration_version,
            AuthorizationDeclaration.purpose == payload.purpose,
            AuthorizationDeclaration.source == payload.source,
        )
    )
    if record is None:
        record = AuthorizationDeclaration(
            user_id=principal.user.id,
            declaration_version=settings.authorization_declaration_version,
            purpose=payload.purpose,
            source=payload.source,
        )
        db.add(record)
    elif record.withdrawn_at is not None:
        record.withdrawn_at = None
        record.confirmed_at = utc_now()
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="privacy.authorization.confirmed",
        target_type="authorization_declaration",
        target_id=record.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "declaration_version": settings.authorization_declaration_version,
            "purpose": payload.purpose,
            "source": payload.source.value,
        },
    )
    db.commit()
    db.refresh(record)
    return _declaration_response(record)


def _export_response(record: PrivacyExport, settings: Settings) -> PrivacyExportResponse:
    now = utc_now()
    available = (
        record.status == PrivacyExportStatus.READY
        and record.expires_at is not None
        and _aware(record.expires_at) > now
        and record.downloaded_at is None
        and record.download_token_ciphertext is not None
    )
    token = None
    if available and record.download_token_ciphertext:
        try:
            token = _token_fernet(settings).decrypt(
                record.download_token_ciphertext.encode("ascii")
            ).decode("utf-8")
        except InvalidToken:
            available = False
    return PrivacyExportResponse(
        id=record.id,
        status=record.status,
        requested_at=record.requested_at,
        completed_at=record.completed_at,
        expires_at=record.expires_at,
        downloaded_at=record.downloaded_at,
        download_available=available,
        download_token=token,
        artifact_sha256=record.artifact_sha256,
        failure_code=record.failure_code,
    )


def create_privacy_export(
    db: Session, *, principal: Principal, context: ClientContext
) -> PrivacyExport:
    active = db.scalar(
        select(PrivacyExport).where(
            PrivacyExport.user_id == principal.user.id,
            PrivacyExport.status.in_(
                [
                    PrivacyExportStatus.PENDING,
                    PrivacyExportStatus.PROCESSING,
                    PrivacyExportStatus.READY,
                ]
            ),
        ).order_by(desc(PrivacyExport.requested_at))
    )
    if active is not None:
        if (
            active.status == PrivacyExportStatus.READY
            and active.expires_at is not None
            and _aware(active.expires_at) <= utc_now()
        ):
            _expire_export(active)
            db.commit()
        else:
            return active
    record = PrivacyExport(user_id=principal.user.id)
    db.add(record)
    db.flush()
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="privacy.export.requested",
        target_type="privacy_export",
        target_id=record.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
    )
    db.commit()
    db.refresh(record)
    return record


def build_privacy_export(db: Session, settings: Settings, export_id: str) -> None:
    record = db.get(PrivacyExport, export_id)
    if record is None or record.status != PrivacyExportStatus.PENDING:
        return
    record.status = PrivacyExportStatus.PROCESSING
    db.commit()
    try:
        user = db.get(User, record.user_id)
        if user is None:
            raise RuntimeError("user_not_found")
        declarations = db.scalars(
            select(AuthorizationDeclaration)
            .where(AuthorizationDeclaration.user_id == user.id)
            .order_by(AuthorizationDeclaration.confirmed_at)
        ).all()
        submissions = db.scalars(
            select(Submission)
            .where(Submission.user_id == user.id)
            .order_by(Submission.created_at)
        ).all()
        reveal_history = list_reveal_history(
            db,
            principal=Principal(user=user, session_family_id="export", mfa_verified=False),
            page=1,
            page_size=100,
        )
        artifact: dict[str, Any] = {
            "schema_version": "privacy-export-v1",
            "generated_at": utc_now().isoformat(),
            "account": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "status": user.status.value,
                "role": user.role.value,
                "reputation_score": user.reputation_score,
                "created_at": user.created_at.isoformat(),
            },
            "authorization_declarations": [
                {
                    "id": item.id,
                    "declaration_version": item.declaration_version,
                    "purpose": item.purpose,
                    "source": item.source.value,
                    "confirmed_at": item.confirmed_at.isoformat(),
                    "withdrawn_at": (
                        item.withdrawn_at.isoformat() if item.withdrawn_at else None
                    ),
                }
                for item in declarations
            ],
            "submissions": [
                {
                    "id": item.id,
                    "archive_id": item.archive_id,
                    "candidate_id": item.candidate_id,
                    "source": item.source.value,
                    "authorization_version": item.authorization_version,
                    "created_at": item.created_at.isoformat(),
                }
                for item in submissions
            ],
            "reveal_history": [item.model_dump(mode="json") for item in reveal_history.items],
            "security_notice": "导出不包含账号密码、候选密码、TOTP 密钥或历史明文密码。",
        }
        canonical = json.dumps(
            artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        raw_token = "pdx_" + secrets.token_urlsafe(40)
        now = utc_now()
        record.artifact = artifact
        record.artifact_sha256 = hashlib.sha256(canonical).hexdigest()
        record.download_token_hash = hash_opaque_token(raw_token)
        record.download_token_ciphertext = _token_fernet(settings).encrypt(
            raw_token.encode("utf-8")
        ).decode("ascii")
        record.status = PrivacyExportStatus.READY
        record.completed_at = now
        record.expires_at = now + timedelta(minutes=settings.privacy_export_ttl_minutes)
        write_audit_log(
            db,
            actor_id=user.id,
            action="privacy.export.ready",
            target_type="privacy_export",
            target_id=record.id,
            result="success",
            details={"expires_at": record.expires_at.isoformat()},
        )
        db.commit()
    except Exception:
        db.rollback()
        record = db.get(PrivacyExport, export_id)
        if record is not None:
            record.status = PrivacyExportStatus.FAILED
            record.failure_code = "privacy_export_build_failed"
            db.commit()
        raise


def _expire_export(record: PrivacyExport) -> None:
    record.status = PrivacyExportStatus.EXPIRED
    record.artifact = None
    record.download_token_hash = None
    record.download_token_ciphertext = None


def get_privacy_export(
    db: Session, settings: Settings, *, export_id: str, principal: Principal
) -> PrivacyExportResponse:
    record = db.get(PrivacyExport, export_id)
    if record is None or record.user_id != principal.user.id:
        raise AppError("privacy.export_not_found", "未找到数据导出请求", status_code=404)
    if (
        record.status == PrivacyExportStatus.READY
        and record.expires_at is not None
        and _aware(record.expires_at) <= utc_now()
    ):
        _expire_export(record)
        db.commit()
    return _export_response(record, settings)


def consume_privacy_export(
    db: Session,
    *,
    export_id: str,
    principal: Principal,
    token: str,
    context: ClientContext,
) -> tuple[dict[str, Any], str]:
    record = db.get(PrivacyExport, export_id)
    if record is None or record.user_id != principal.user.id:
        raise AppError("privacy.export_not_found", "未找到数据导出请求", status_code=404)
    if record.status != PrivacyExportStatus.READY or record.downloaded_at is not None:
        raise AppError("privacy.export_unavailable", "导出文件当前不可下载", status_code=409)
    if record.expires_at is None or _aware(record.expires_at) <= utc_now():
        _expire_export(record)
        db.commit()
        raise AppError("privacy.export_expired", "导出下载凭证已过期", status_code=410)
    if not record.download_token_hash or not secrets.compare_digest(
        record.download_token_hash, hash_opaque_token(token)
    ):
        raise AppError("privacy.invalid_download_token", "下载凭证无效", status_code=403)
    if record.artifact is None or record.artifact_sha256 is None:
        raise AppError("privacy.export_unavailable", "导出文件当前不可下载", status_code=409)
    artifact = record.artifact
    digest = record.artifact_sha256
    record.status = PrivacyExportStatus.DOWNLOADED
    record.downloaded_at = utc_now()
    record.artifact = None
    record.download_token_hash = None
    record.download_token_ciphertext = None
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="privacy.export.downloaded",
        target_type="privacy_export",
        target_id=record.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
    )
    db.commit()
    return artifact, digest


def _deletion_response(record: PrivacyDeletionRequest) -> PrivacyDeletionResponse:
    return PrivacyDeletionResponse(
        id=record.id,
        status=record.status,
        requested_at=record.requested_at,
        cancel_before=record.cancel_before,
        cancelled_at=record.cancelled_at,
        processing_started_at=record.processing_started_at,
        completed_at=record.completed_at,
        can_cancel=(
            record.status == PrivacyDeletionStatus.PENDING
            and _aware(record.cancel_before) > utc_now()
        ),
    )


def create_deletion_request(
    db: Session,
    settings: Settings,
    *,
    principal: Principal,
    reauth_token: str,
    context: ClientContext,
) -> PrivacyDeletionResponse:
    consume_reauthentication_grant(
        db,
        raw_token=reauth_token,
        user_id=principal.user.id,
        session_family_id=principal.session_family_id,
        expected_purpose=ReauthenticationPurpose.ACCOUNT_DELETION,
    )
    active = db.scalar(
        select(PrivacyDeletionRequest)
        .where(
            PrivacyDeletionRequest.user_id == principal.user.id,
            PrivacyDeletionRequest.status.in_(
                [PrivacyDeletionStatus.PENDING, PrivacyDeletionStatus.PROCESSING]
            ),
        )
        .order_by(desc(PrivacyDeletionRequest.requested_at))
    )
    if active is not None:
        return _deletion_response(active)
    now = utc_now()
    record = PrivacyDeletionRequest(
        user_id=principal.user.id,
        cancel_before=now + timedelta(hours=settings.privacy_deletion_grace_hours),
    )
    db.add(record)
    db.flush()
    revoke_reauthentication_grants(db, user_id=principal.user.id)
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="privacy.deletion.requested",
        target_type="privacy_deletion_request",
        target_id=record.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"cancel_before": record.cancel_before.isoformat()},
    )
    db.commit()
    db.refresh(record)
    return _deletion_response(record)


def get_current_deletion_request(
    db: Session, *, principal: Principal
) -> PrivacyDeletionResponse | None:
    record = db.scalar(
        select(PrivacyDeletionRequest)
        .where(PrivacyDeletionRequest.user_id == principal.user.id)
        .order_by(desc(PrivacyDeletionRequest.requested_at), desc(PrivacyDeletionRequest.id))
    )
    return _deletion_response(record) if record is not None else None


def cancel_deletion_request(
    db: Session,
    *,
    request_id: str,
    principal: Principal,
    context: ClientContext,
) -> PrivacyDeletionResponse:
    record = db.get(PrivacyDeletionRequest, request_id)
    if record is None or record.user_id != principal.user.id:
        raise AppError("privacy.deletion_not_found", "未找到账号删除请求", status_code=404)
    if record.status == PrivacyDeletionStatus.CANCELLED:
        return _deletion_response(record)
    if record.status != PrivacyDeletionStatus.PENDING:
        raise AppError("privacy.deletion_not_cancellable", "删除请求已无法撤销", status_code=409)
    if _aware(record.cancel_before) <= utc_now():
        raise AppError(
            "privacy.deletion_cancel_window_closed",
            "删除请求撤销期限已结束",
            status_code=409,
        )
    record.status = PrivacyDeletionStatus.CANCELLED
    record.cancelled_at = utc_now()
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="privacy.deletion.cancelled",
        target_type="privacy_deletion_request",
        target_id=record.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
    )
    db.commit()
    return _deletion_response(record)


def process_due_deletion_requests(db: Session) -> int:
    now = utc_now()
    records = db.scalars(
        select(PrivacyDeletionRequest).where(
            PrivacyDeletionRequest.status == PrivacyDeletionStatus.PENDING,
            PrivacyDeletionRequest.cancel_before <= now,
        )
    ).all()
    processed = 0
    for record in records:
        user = db.get(User, record.user_id)
        if user is None:
            continue
        record.status = PrivacyDeletionStatus.PROCESSING
        record.processing_started_at = now
        db.flush()
        synthetic_key = user.id.replace("-", "")[:20]
        user.username = f"deleted_{synthetic_key}"[:32]
        user.email = f"deleted+{synthetic_key}@invalid.local"
        user.email_verified_at = None
        user.account_password_hash = hash_account_password(secrets.token_urlsafe(48))
        user.status = UserStatus.DISABLED
        user.role = UserRole.USER
        user.totp_pending_secret_ciphertext = None
        user.totp_secret_ciphertext = None
        user.totp_enabled_at = None
        db.execute(delete(AccountActionToken).where(AccountActionToken.user_id == user.id))
        db.execute(
            delete(AuthorizationDeclaration).where(
                AuthorizationDeclaration.user_id == user.id
            )
        )
        db.execute(delete(PrivacyExport).where(PrivacyExport.user_id == user.id))
        db.execute(
            update(UserSession)
            .where(UserSession.user_id == user.id)
            .values(
                revoked_at=now,
                revoked_reason="account_deleted",
                user_agent=None,
                ip_prefix=None,
                mfa_verified_at=None,
            )
        )
        write_audit_log(
            db,
            actor_id=user.id,
            action="privacy.deletion.completed",
            target_type="privacy_deletion_request",
            target_id=record.id,
            result="success",
            details={"account_anonymized": True},
        )
        record.status = PrivacyDeletionStatus.COMPLETED
        record.completed_at = utc_now()
        db.commit()
        processed += 1
    return processed
