from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.security import hash_opaque_token
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.third_party_app import (
    ThirdPartyApp,
    ThirdPartyAppRedirectUri,
    ThirdPartyAppSource,
    ThirdPartyAppStatus,
)
from password_detective.modules.third_party_apps.schemas import (
    ThirdPartyAppCreateRequest,
    ThirdPartyAppListItem,
    ThirdPartyAppReviewRequest,
)

ALLOWED_SCOPES = {
    "profile:read",
    "hash:read",
    "announcements:read",
    "updates:read",
    "desktop:installations",
    "desktop:verification",
}
TRUSTED_SCOPE = "desktop:verification:trusted"


def _json_list(value: str) -> list[str]:
    parsed = json.loads(value)
    return [str(item) for item in parsed]


def _management_secret() -> tuple[str, str]:
    secret = "pds_" + secrets.token_urlsafe(36)
    return secret, hash_opaque_token(secret)


def _client_id() -> str:
    return "pdc_" + secrets.token_urlsafe(24)


def _validate_request(payload: ThirdPartyAppCreateRequest) -> tuple[list[str], list[str]]:
    scopes = [scope.strip() for scope in payload.scopes]
    if len(scopes) != len(set(scopes)) or any(scope not in ALLOWED_SCOPES for scope in scopes):
        raise AppError(
            "third_party_app.invalid_request",
            "Scope 不合法或重复；可信直入 Scope 只能由管理员审核授予",
            status_code=422,
        )
    if len(payload.redirect_uris) != len(set(payload.redirect_uris)):
        raise AppError(
            "third_party_app.invalid_request",
            "回调地址不能重复",
            status_code=422,
        )
    redirect_uris = [uri.strip() for uri in payload.redirect_uris]
    if any(not uri or not uri.startswith(("http://", "https://")) for uri in redirect_uris):
        raise AppError(
            "third_party_app.invalid_request",
            "回调地址必须使用 HTTP(S)",
            status_code=422,
        )
    return redirect_uris, scopes


def _audit(
    db: Session, *, actor_id: str, action: str, app_id: str, details: dict[str, Any] | None = None
) -> None:
    write_audit_log(
        db,
        action=action,
        target_type="third_party_app",
        target_id=app_id,
        result="success",
        actor_id=actor_id,
        details=details,
    )


def _item(
    app: ThirdPartyApp, redirects: Sequence[ThirdPartyAppRedirectUri], *, secret: str | None = None
) -> ThirdPartyAppListItem:
    def iso(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    return ThirdPartyAppListItem(
        id=app.id,
        client_id=app.client_id,
        name=app.name,
        developer_name=app.developer_name,
        description=app.description,
        status=app.status,
        application_source=app.application_source,
        requested_scopes=_json_list(app.requested_scopes_json),
        approved_scopes=_json_list(app.approved_scopes_json),
        redirect_uris=[redirect.redirect_uri for redirect in redirects],
        trusted_verification_enabled=app.trusted_verification_enabled,
        request_count=app.request_count,
        last_used_at=iso(app.last_used_at),
        reviewed_at=iso(app.reviewed_at),
        created_at=app.created_at.isoformat(),
        updated_at=app.updated_at.isoformat(),
        revoked_at=iso(app.revoked_at),
        management_secret=secret,
    )


def _get_app(db: Session, app_id: str) -> ThirdPartyApp:
    app = db.get(ThirdPartyApp, app_id)
    if app is None:
        raise AppError("third_party_app.not_found", "第三方应用不存在", status_code=404)
    return app


def _redirects(db: Session, app_id: str) -> list[ThirdPartyAppRedirectUri]:
    return list(
        db.scalars(
            select(ThirdPartyAppRedirectUri)
            .where(ThirdPartyAppRedirectUri.app_id == app_id)
            .order_by(ThirdPartyAppRedirectUri.created_at, ThirdPartyAppRedirectUri.id)
        ).all()
    )


def create_app(
    db: Session, *, actor_id: str, payload: ThirdPartyAppCreateRequest
) -> ThirdPartyAppListItem:
    redirect_uris, scopes = _validate_request(payload)
    secret, secret_hash = _management_secret()
    app = ThirdPartyApp(
        client_id=_client_id(),
        management_secret_hash=secret_hash,
        name=payload.name.strip(),
        developer_name=payload.developer_name.strip(),
        description=payload.description.strip(),
        status=ThirdPartyAppStatus.DRAFT,
        application_source=ThirdPartyAppSource.ADMIN,
        requested_scopes_json=json.dumps(scopes, ensure_ascii=False),
        approved_scopes_json=json.dumps(scopes, ensure_ascii=False),
    )
    db.add(app)
    db.flush()
    db.add_all(
        [
            ThirdPartyAppRedirectUri(
                app_id=app.id,
                redirect_uri=uri,
                redirect_uri_hash=hashlib.sha256(uri.encode("utf-8")).hexdigest(),
            )
            for uri in redirect_uris
        ]
    )
    _audit(db, actor_id=actor_id, action="third_party_app.create", app_id=app.id)
    db.commit()
    db.refresh(app)
    return _item(app, _redirects(db, app.id), secret=secret)


def list_apps(db: Session, *, page: int, page_size: int) -> tuple[list[ThirdPartyAppListItem], int]:
    total = int(db.scalar(select(func.count()).select_from(ThirdPartyApp)) or 0)
    apps = list(
        db.scalars(
            select(ThirdPartyApp)
            .order_by(ThirdPartyApp.created_at.desc(), ThirdPartyApp.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return [_item(app, _redirects(db, app.id)) for app in apps], total


def get_app(db: Session, app_id: str) -> ThirdPartyAppListItem:
    app = _get_app(db, app_id)
    return _item(app, _redirects(db, app.id))


def approve_app(
    db: Session,
    *,
    actor_id: str,
    app_id: str,
    payload: ThirdPartyAppReviewRequest,
) -> ThirdPartyAppListItem:
    app = _get_app(db, app_id)
    if app.status not in {ThirdPartyAppStatus.DRAFT, ThirdPartyAppStatus.PENDING_REVIEW}:
        raise AppError("third_party_app.invalid_state", "当前状态不能审核通过", status_code=409)
    approved_scopes = _json_list(app.approved_scopes_json)
    if payload.trusted_verification_enabled and "desktop:verification" not in approved_scopes:
        raise AppError(
            "third_party_app.invalid_request",
            "授予可信直入前必须先拥有桌面验证 Scope",
            status_code=422,
        )
    if payload.trusted_verification_enabled and TRUSTED_SCOPE not in approved_scopes:
        approved_scopes.append(TRUSTED_SCOPE)
    app.status = ThirdPartyAppStatus.APPROVED
    app.reviewer_user_id = actor_id
    app.reviewed_at = utc_now()
    app.review_note = payload.review_note.strip() if payload.review_note else None
    app.trusted_verification_enabled = payload.trusted_verification_enabled
    app.approved_scopes_json = json.dumps(approved_scopes, ensure_ascii=False)
    app.revoked_at = None
    _audit(
        db,
        actor_id=actor_id,
        action="third_party_app.approve",
        app_id=app.id,
        details={"trusted_verification_enabled": app.trusted_verification_enabled},
    )
    db.commit()
    db.refresh(app)
    return _item(app, _redirects(db, app.id))


def _set_status(
    db: Session, *, actor_id: str, app_id: str, status: ThirdPartyAppStatus
) -> ThirdPartyAppListItem:
    app = _get_app(db, app_id)
    if app.status == ThirdPartyAppStatus.REVOKED:
        raise AppError("third_party_app.invalid_state", "已撤销应用不能改变状态", status_code=409)
    if status == ThirdPartyAppStatus.SUSPENDED and app.status == ThirdPartyAppStatus.SUSPENDED:
        raise AppError("third_party_app.invalid_state", "应用已经暂停", status_code=409)
    if status == ThirdPartyAppStatus.DRAFT and app.status != ThirdPartyAppStatus.SUSPENDED:
        raise AppError("third_party_app.invalid_state", "只有暂停应用可以恢复", status_code=409)
    app.status = status
    if status == ThirdPartyAppStatus.DRAFT:
        app.revoked_at = None
    if status == ThirdPartyAppStatus.REVOKED:
        app.revoked_at = utc_now()
        app.trusted_verification_enabled = False
    action = {
        ThirdPartyAppStatus.SUSPENDED: "third_party_app.suspend",
        ThirdPartyAppStatus.DRAFT: "third_party_app.restore",
        ThirdPartyAppStatus.REVOKED: "third_party_app.revoke",
    }[status]
    _audit(db, actor_id=actor_id, action=action, app_id=app.id)
    db.commit()
    db.refresh(app)
    return _item(app, _redirects(db, app.id))


def suspend_app(db: Session, *, actor_id: str, app_id: str) -> ThirdPartyAppListItem:
    return _set_status(db, actor_id=actor_id, app_id=app_id, status=ThirdPartyAppStatus.SUSPENDED)


def restore_app(db: Session, *, actor_id: str, app_id: str) -> ThirdPartyAppListItem:
    return _set_status(db, actor_id=actor_id, app_id=app_id, status=ThirdPartyAppStatus.DRAFT)


def revoke_app(db: Session, *, actor_id: str, app_id: str) -> ThirdPartyAppListItem:
    return _set_status(db, actor_id=actor_id, app_id=app_id, status=ThirdPartyAppStatus.REVOKED)


def rotate_secret(db: Session, *, actor_id: str, app_id: str) -> ThirdPartyAppListItem:
    app = _get_app(db, app_id)
    if app.status == ThirdPartyAppStatus.REVOKED:
        raise AppError("third_party_app.invalid_state", "已撤销应用不能轮换密钥", status_code=409)
    secret, secret_hash = _management_secret()
    app.management_secret_hash = secret_hash
    app.updated_at = utc_now()
    _audit(db, actor_id=actor_id, action="third_party_app.rotate_secret", app_id=app.id)
    db.commit()
    db.refresh(app)
    return _item(app, _redirects(db, app.id), secret=secret)

