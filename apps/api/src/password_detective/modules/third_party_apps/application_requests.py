from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.security import hash_opaque_token
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.third_party_app import (
    ThirdPartyApp,
    ThirdPartyApplicationRequest,
    ThirdPartyApplicationRequestStatus,
    ThirdPartyApplicationReviewEvent,
    ThirdPartyApplicationReviewEventKind,
    ThirdPartyAppRedirectUri,
    ThirdPartyAppSource,
    ThirdPartyAppStatus,
)
from password_detective.modules.third_party_apps.schemas import (
    ThirdPartyApplicationApprovalResponse,
    ThirdPartyApplicationCreateRequest,
    ThirdPartyApplicationDetail,
    ThirdPartyApplicationListResponse,
    ThirdPartyApplicationRejectRequest,
    ThirdPartyApplicationReviewEventResponse,
    ThirdPartyApplicationReviewRequest,
    ThirdPartyApplicationSafeApp,
    ThirdPartyApplicationUpdateRequest,
    ThirdPartyAppListItem,
)
from password_detective.modules.third_party_apps.service import ALLOWED_SCOPES, TRUSTED_SCOPE


def _json_list(value: str) -> list[str]:
    parsed = json.loads(value)
    return [str(item) for item in parsed]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _client_id() -> str:
    return "pdc_" + secrets.token_urlsafe(24)


def _management_secret() -> tuple[str, str]:
    secret = "pds_" + secrets.token_urlsafe(36)
    return secret, hash_opaque_token(secret)


def _redirect_hash(uri: str) -> str:
    return hashlib.sha256(uri.encode("utf-8")).hexdigest()


def _normalize_urls(values: list[str], *, field_name: str) -> list[str]:
    urls = [value.strip() for value in values]
    if len(urls) != len(set(urls)) or any(
        not value.startswith(("http://", "https://")) for value in urls
    ):
        raise AppError(
            "third_party_application.invalid_request",
            f"{field_name} 必须是唯一的 HTTP(S) 地址",
            status_code=422,
        )
    return urls


def _normalize_scopes(values: list[str]) -> list[str]:
    scopes = [value.strip() for value in values]
    if len(scopes) != len(set(scopes)) or any(value not in ALLOWED_SCOPES for value in scopes):
        raise AppError(
            "third_party_application.invalid_request", "申请 Scope 不合法或重复", status_code=422
        )
    return scopes


def _validate_application_urls(website_url: str, privacy_policy_url: str) -> tuple[str, str]:
    website = website_url.strip()
    privacy = privacy_policy_url.strip()
    if not website.startswith(("http://", "https://")) or not privacy.startswith(
        ("http://", "https://")
    ):
        raise AppError(
            "third_party_application.invalid_request",
            "官网与隐私政策必须使用 HTTP(S) 地址",
            status_code=422,
        )
    return website, privacy


def _event(
    db: Session,
    *,
    application: ThirdPartyApplicationRequest,
    actor_id: str | None,
    kind: ThirdPartyApplicationReviewEventKind,
    note: str | None = None,
) -> None:
    db.add(
        ThirdPartyApplicationReviewEvent(
            application_request_id=application.id,
            actor_user_id=actor_id,
            kind=kind,
            note=note,
            version=application.current_version,
        )
    )


def _audit(
    db: Session,
    *,
    actor_id: str,
    action: str,
    request_id: str,
    details: dict[str, object] | None = None,
) -> None:
    write_audit_log(
        db,
        action=action,
        target_type="third_party_application_request",
        target_id=request_id,
        result="success",
        actor_id=actor_id,
        details=details,
    )


def _get_request(db: Session, request_id: str) -> ThirdPartyApplicationRequest:
    application = db.get(ThirdPartyApplicationRequest, request_id)
    if application is None:
        raise AppError("third_party_application.not_found", "第三方应用申请不存在", status_code=404)
    return application


def _get_owned_request(
    db: Session, *, request_id: str, user_id: str
) -> ThirdPartyApplicationRequest:
    application = db.scalar(
        select(ThirdPartyApplicationRequest).where(
            ThirdPartyApplicationRequest.id == request_id,
            ThirdPartyApplicationRequest.submitted_by_user_id == user_id,
        )
    )
    if application is None:
        raise AppError("third_party_application.not_found", "第三方应用申请不存在", status_code=404)
    return application


def _events(db: Session, request_id: str) -> list[ThirdPartyApplicationReviewEventResponse]:
    rows = db.scalars(
        select(ThirdPartyApplicationReviewEvent)
        .where(ThirdPartyApplicationReviewEvent.application_request_id == request_id)
        .order_by(
            ThirdPartyApplicationReviewEvent.created_at.asc(),
            ThirdPartyApplicationReviewEvent.id.asc(),
        )
    ).all()
    return [
        ThirdPartyApplicationReviewEventResponse(
            id=row.id,
            kind=row.kind,
            note=row.note,
            version=row.version,
            created_at=row.created_at.isoformat(),
        )
        for row in rows
    ]


def _safe_app(
    db: Session, application: ThirdPartyApplicationRequest
) -> ThirdPartyApplicationSafeApp | None:
    if application.approved_application_id is None:
        return None
    app = db.get(ThirdPartyApp, application.approved_application_id)
    if app is None:
        return None
    redirect_uris = list(
        db.scalars(
            select(ThirdPartyAppRedirectUri.redirect_uri)
            .where(ThirdPartyAppRedirectUri.app_id == app.id)
            .order_by(ThirdPartyAppRedirectUri.created_at.asc(), ThirdPartyAppRedirectUri.id.asc())
        ).all()
    )
    return ThirdPartyApplicationSafeApp(
        id=app.id,
        client_id=app.client_id,
        name=app.name,
        status=app.status,
        application_source=app.application_source,
        approved_scopes=_json_list(app.approved_scopes_json),
        redirect_uris=redirect_uris,
        trusted_verification_enabled=app.trusted_verification_enabled,
    )


def _detail(
    db: Session, application: ThirdPartyApplicationRequest, *, include_events: bool = True
) -> ThirdPartyApplicationDetail:
    return ThirdPartyApplicationDetail(
        id=application.id,
        name=application.name,
        developer_name=application.developer_name,
        description=application.description,
        website_url=application.website_url,
        privacy_policy_url=application.privacy_policy_url,
        redirect_uris=_json_list(application.redirect_uris_json),
        requested_scopes=_json_list(application.requested_scopes_json),
        windows_release_info=application.windows_release_info,
        use_case=application.use_case,
        status=application.status,
        resubmission_count=application.resubmission_count,
        current_version=application.current_version,
        review_note=application.review_note,
        reviewed_at=_iso(application.reviewed_at),
        created_at=application.created_at.isoformat(),
        updated_at=application.updated_at.isoformat(),
        approved_application=_safe_app(db, application),
        events=_events(db, application.id) if include_events else [],
    )


def _app_item(app: ThirdPartyApp, redirects: list[str], secret: str) -> ThirdPartyAppListItem:
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
        redirect_uris=redirects,
        trusted_verification_enabled=app.trusted_verification_enabled,
        request_count=app.request_count,
        last_used_at=_iso(app.last_used_at),
        reviewed_at=_iso(app.reviewed_at),
        created_at=app.created_at.isoformat(),
        updated_at=app.updated_at.isoformat(),
        revoked_at=_iso(app.revoked_at),
        management_secret=secret,
    )


def create_application_request(
    db: Session,
    *,
    user_id: str,
    payload: ThirdPartyApplicationCreateRequest,
) -> ThirdPartyApplicationDetail:
    website, privacy = _validate_application_urls(payload.website_url, payload.privacy_policy_url)
    redirects = _normalize_urls(payload.redirect_uris, field_name="回调地址")
    scopes = _normalize_scopes(payload.scopes)
    application = ThirdPartyApplicationRequest(
        submitted_by_user_id=user_id,
        name=payload.name.strip(),
        developer_name=payload.developer_name.strip(),
        description=payload.description.strip(),
        website_url=website,
        privacy_policy_url=privacy,
        redirect_uris_json=json.dumps(redirects, ensure_ascii=False),
        requested_scopes_json=json.dumps(scopes, ensure_ascii=False),
        windows_release_info=payload.windows_release_info.strip(),
        use_case=payload.use_case.strip(),
        status=ThirdPartyApplicationRequestStatus.DRAFT,
    )
    db.add(application)
    db.flush()
    _event(
        db,
        application=application,
        actor_id=user_id,
        kind=ThirdPartyApplicationReviewEventKind.CREATED,
    )
    _audit(
        db, actor_id=user_id, action="third_party_application.created", request_id=application.id
    )
    db.commit()
    db.refresh(application)
    return _detail(db, application)


def list_owned_application_requests(
    db: Session, *, user_id: str, page: int, page_size: int
) -> ThirdPartyApplicationListResponse:
    statement = select(ThirdPartyApplicationRequest).where(
        ThirdPartyApplicationRequest.submitted_by_user_id == user_id
    )
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    rows = db.scalars(
        statement.order_by(
            ThirdPartyApplicationRequest.updated_at.desc(), ThirdPartyApplicationRequest.id.desc()
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return ThirdPartyApplicationListResponse(
        items=[_detail(db, row, include_events=False) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_owned_application_request(
    db: Session, *, user_id: str, request_id: str
) -> ThirdPartyApplicationDetail:
    return _detail(db, _get_owned_request(db, request_id=request_id, user_id=user_id))


def update_application_request(
    db: Session,
    *,
    user_id: str,
    request_id: str,
    payload: ThirdPartyApplicationUpdateRequest,
) -> ThirdPartyApplicationDetail:
    application = _get_owned_request(db, request_id=request_id, user_id=user_id)
    if application.status not in {
        ThirdPartyApplicationRequestStatus.DRAFT,
        ThirdPartyApplicationRequestStatus.REJECTED,
    }:
        raise AppError(
            "third_party_application.not_editable", "当前申请状态不允许编辑", status_code=409
        )
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise AppError(
            "third_party_application.invalid_request", "至少需要修改一项申请信息", status_code=422
        )
    if "redirect_uris" in changes:
        application.redirect_uris_json = json.dumps(
            _normalize_urls(changes.pop("redirect_uris"), field_name="回调地址"), ensure_ascii=False
        )
    if "scopes" in changes:
        application.requested_scopes_json = json.dumps(
            _normalize_scopes(changes.pop("scopes")), ensure_ascii=False
        )
    proposed_website = str(changes.pop("website_url", application.website_url))
    proposed_privacy = str(changes.pop("privacy_policy_url", application.privacy_policy_url))
    application.website_url, application.privacy_policy_url = _validate_application_urls(
        proposed_website, proposed_privacy
    )
    for field_name, value in changes.items():
        if isinstance(value, str):
            setattr(application, field_name, value.strip())
    rejected = application.status == ThirdPartyApplicationRequestStatus.REJECTED
    if rejected:
        application.status = ThirdPartyApplicationRequestStatus.DRAFT
        application.resubmission_count += 1
        application.current_version += 1
        application.review_note = None
        application.reviewed_at = None
        application.reviewer_user_id = None
        _event(
            db,
            application=application,
            actor_id=user_id,
            kind=ThirdPartyApplicationReviewEventKind.RESUBMITTED,
        )
        _audit(
            db,
            actor_id=user_id,
            action="third_party_application.resubmitted",
            request_id=application.id,
        )
    else:
        _audit(
            db,
            actor_id=user_id,
            action="third_party_application.updated",
            request_id=application.id,
        )
    db.commit()
    db.refresh(application)
    return _detail(db, application)


def submit_application_request(
    db: Session, *, user_id: str, request_id: str
) -> ThirdPartyApplicationDetail:
    application = _get_owned_request(db, request_id=request_id, user_id=user_id)
    if application.status != ThirdPartyApplicationRequestStatus.DRAFT:
        raise AppError(
            "third_party_application.invalid_state", "只有草稿申请可以提交审核", status_code=409
        )
    application.status = ThirdPartyApplicationRequestStatus.PENDING_REVIEW
    _event(
        db,
        application=application,
        actor_id=user_id,
        kind=ThirdPartyApplicationReviewEventKind.SUBMITTED,
    )
    _audit(
        db, actor_id=user_id, action="third_party_application.submitted", request_id=application.id
    )
    db.commit()
    db.refresh(application)
    return _detail(db, application)


def list_application_requests_for_admin(
    db: Session,
    *,
    page: int,
    page_size: int,
    status: ThirdPartyApplicationRequestStatus | None,
) -> ThirdPartyApplicationListResponse:
    statement = select(ThirdPartyApplicationRequest)
    if status is not None:
        statement = statement.where(ThirdPartyApplicationRequest.status == status)
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    rows = db.scalars(
        statement.order_by(
            ThirdPartyApplicationRequest.updated_at.desc(), ThirdPartyApplicationRequest.id.desc()
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return ThirdPartyApplicationListResponse(
        items=[_detail(db, row, include_events=False) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_application_request_for_admin(
    db: Session, *, request_id: str
) -> ThirdPartyApplicationDetail:
    return _detail(db, _get_request(db, request_id))


def reject_application_request(
    db: Session,
    *,
    actor_id: str,
    request_id: str,
    payload: ThirdPartyApplicationRejectRequest,
) -> ThirdPartyApplicationDetail:
    application = _get_request(db, request_id)
    if application.status != ThirdPartyApplicationRequestStatus.PENDING_REVIEW:
        raise AppError("third_party_application.invalid_state", "当前申请不能驳回", status_code=409)
    application.status = ThirdPartyApplicationRequestStatus.REJECTED
    application.reviewer_user_id = actor_id
    application.reviewed_at = utc_now()
    application.review_note = payload.review_note
    _event(
        db,
        application=application,
        actor_id=actor_id,
        kind=ThirdPartyApplicationReviewEventKind.REJECTED,
        note=payload.review_note,
    )
    _audit(
        db, actor_id=actor_id, action="third_party_application.rejected", request_id=application.id
    )
    db.commit()
    db.refresh(application)
    return _detail(db, application)


def approve_application_request(
    db: Session,
    *,
    actor_id: str,
    request_id: str,
    payload: ThirdPartyApplicationReviewRequest,
) -> ThirdPartyApplicationApprovalResponse:
    application = _get_request(db, request_id)
    if application.status != ThirdPartyApplicationRequestStatus.PENDING_REVIEW:
        raise AppError(
            "third_party_application.invalid_state", "当前申请不能审核通过", status_code=409
        )
    requested_scopes = _json_list(application.requested_scopes_json)
    approved_scopes = _normalize_scopes(payload.approved_scopes)
    if any(scope not in requested_scopes for scope in approved_scopes):
        raise AppError(
            "third_party_application.invalid_request",
            "批准 Scope 必须包含在申请 Scope 内",
            status_code=422,
        )
    if payload.trusted_verification_enabled and "desktop:verification" not in approved_scopes:
        raise AppError(
            "third_party_application.invalid_request",
            "可信直入前必须先批准桌面验证 Scope",
            status_code=422,
        )
    if payload.trusted_verification_enabled:
        approved_scopes.append(TRUSTED_SCOPE)
    secret, secret_hash = _management_secret()
    app = ThirdPartyApp(
        client_id=_client_id(),
        management_secret_hash=secret_hash,
        name=application.name,
        developer_name=application.developer_name,
        description=application.description,
        status=ThirdPartyAppStatus.APPROVED,
        application_source=ThirdPartyAppSource.DEVELOPER_SELF_SERVICE,
        requested_scopes_json=application.requested_scopes_json,
        approved_scopes_json=json.dumps(approved_scopes, ensure_ascii=False),
        submitted_by_user_id=application.submitted_by_user_id,
        reviewer_user_id=actor_id,
        reviewed_at=utc_now(),
        review_note=payload.review_note.strip() if payload.review_note else None,
        trusted_verification_enabled=payload.trusted_verification_enabled,
    )
    db.add(app)
    db.flush()
    redirects = _json_list(application.redirect_uris_json)
    db.add_all(
        [
            ThirdPartyAppRedirectUri(
                app_id=app.id, redirect_uri=uri, redirect_uri_hash=_redirect_hash(uri)
            )
            for uri in redirects
        ]
    )
    application.status = ThirdPartyApplicationRequestStatus.APPROVED
    application.approved_application_id = app.id
    application.reviewer_user_id = actor_id
    application.reviewed_at = app.reviewed_at
    application.review_note = app.review_note
    _event(
        db,
        application=application,
        actor_id=actor_id,
        kind=ThirdPartyApplicationReviewEventKind.APPROVED,
        note=application.review_note,
    )
    _audit(
        db,
        actor_id=actor_id,
        action="third_party_application.approved",
        request_id=application.id,
        details={"app_id": app.id},
    )
    db.commit()
    db.refresh(application)
    db.refresh(app)
    return ThirdPartyApplicationApprovalResponse(
        application=_detail(db, application),
        created_app=_app_item(app, redirects, secret),
    )
