from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from password_detective.core.config import Settings
from password_detective.core.errors import AppError
from password_detective.core.security import (
    create_refresh_token,
    create_third_party_access_token,
    hash_opaque_token,
    hash_refresh_token,
)
from password_detective.core.time import utc_now
from password_detective.db.models.third_party_app import (
    ThirdPartyApp,
    ThirdPartyAppRedirectUri,
    ThirdPartyAppStatus,
)
from password_detective.db.models.third_party_oauth import (
    OAuthAuthorizationCode,
    OAuthTokenSession,
    ThirdPartyAuthorization,
)
from password_detective.db.models.user import User, UserStatus
from password_detective.modules.third_party_apps.service import TRUSTED_SCOPE
from password_detective.modules.third_party_oauth.schemas import (
    AuthorizedApplicationItem,
    ThirdPartyAuthorizationDetails,
    ThirdPartyAuthorizationRequest,
)

ACCESS_TOKEN_TTL_MINUTES = 15
AUTHORIZATION_CODE_TTL_MINUTES = 5
REFRESH_TOKEN_TTL_DAYS = 30


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _invalid(message: str = "OAuth 请求无效") -> AppError:
    return AppError("third_party_oauth.invalid_request", message, status_code=400)


def _grant_invalid(message: str = "授权凭据无效") -> AppError:
    return AppError("third_party_oauth.invalid_grant", message, status_code=400)


def _scopes(raw: str | None) -> list[str]:
    if not raw:
        return []
    values = [item for item in raw.split() if item]
    if len(values) != len(set(values)):
        raise _invalid("Scope 不能重复")
    return values


def _scope_json(scopes: list[str]) -> str:
    return json.dumps(scopes, ensure_ascii=False)


def _decode_scopes(raw: str) -> list[str]:
    parsed = json.loads(raw)
    return [str(scope) for scope in parsed]


def _approved_app(db: Session, client_id: str) -> ThirdPartyApp:
    app = db.scalar(select(ThirdPartyApp).where(ThirdPartyApp.client_id == client_id))
    if app is None or app.status != ThirdPartyAppStatus.APPROVED:
        raise _invalid("应用未通过审核或当前不可用")
    return app


def _validate_redirect(db: Session, app_id: str, redirect_uri: str) -> None:
    exact = db.scalar(
        select(ThirdPartyAppRedirectUri.id).where(
            ThirdPartyAppRedirectUri.app_id == app_id,
            ThirdPartyAppRedirectUri.redirect_uri == redirect_uri,
        )
    )
    if exact is None:
        raise _invalid("redirect_uri 未在应用白名单中")


def _validate_scopes(app: ThirdPartyApp, requested: list[str]) -> list[str]:
    approved = _decode_scopes(app.approved_scopes_json)
    if any(scope not in approved for scope in requested):
        raise _invalid("请求的 Scope 未获管理员批准")
    if TRUSTED_SCOPE in requested and not app.trusted_verification_enabled:
        raise _invalid("应用未获准使用可信验证 Scope")
    return requested


def _append_query(url: str, values: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.extend(values.items())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _pkce_digest(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def issue_authorization_code(
    db: Session,
    *,
    app: ThirdPartyApp,
    user: User,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    requested_scopes: list[str],
) -> str:
    now = utc_now()
    authorization = db.scalar(
        select(ThirdPartyAuthorization).where(
            ThirdPartyAuthorization.app_id == app.id,
            ThirdPartyAuthorization.user_id == user.id,
        )
    )
    if authorization is None:
        authorization = ThirdPartyAuthorization(
            app_id=app.id,
            user_id=user.id,
            scope_json=_scope_json(requested_scopes),
        )
        db.add(authorization)
        db.flush()
    else:
        if authorization.revoked_at is not None:
            authorization.revoked_at = None
        authorization.scope_json = _scope_json(requested_scopes)
        authorization.last_used_at = now

    raw_code = "oc_" + secrets.token_urlsafe(32)
    db.add(
        OAuthAuthorizationCode(
            app_id=app.id,
            authorization_id=authorization.id,
            user_id=user.id,
            code_hash=hash_opaque_token(raw_code),
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            scope_json=_scope_json(requested_scopes),
            expires_at=now + timedelta(minutes=AUTHORIZATION_CODE_TTL_MINUTES),
        )
    )
    app.request_count += 1
    app.last_used_at = now
    db.commit()
    return raw_code


def authorize(
    db: Session,
    *,
    client_id: str,
    redirect_uri: str,
    response_type: str,
    code_challenge: str,
    code_challenge_method: str,
    scope: str | None,
    state: str,
    user: User,
) -> str:
    if response_type != "code":
        raise _invalid("仅支持 response_type=code")
    if code_challenge_method != "S256":
        raise _invalid("PKCE 仅支持 S256")
    if len(state) < 16:
        raise _invalid("state 长度至少为 16")
    if not code_challenge or len(code_challenge) < 43 or len(code_challenge) > 128:
        raise _invalid("code_challenge 格式无效")
    if user.status != UserStatus.ACTIVE:
        raise AppError("auth.account_unavailable", "账号当前不可用", status_code=403)
    app = _approved_app(db, client_id)
    _validate_redirect(db, app.id, redirect_uri)
    requested = _validate_scopes(app, _scopes(scope))
    code = issue_authorization_code(
        db,
        app=app,
        user=user,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        requested_scopes=requested,
    )
    return _append_query(redirect_uri, {"code": code, "state": state})


def _issue_response(
    db: Session,
    settings: Settings,
    *,
    app: ThirdPartyApp,
    authorization: ThirdPartyAuthorization,
    user: User,
    scopes: list[str],
    family_id: str,
) -> tuple[str, str]:
    now = utc_now()
    refresh_token = create_refresh_token()
    session = OAuthTokenSession(
        app_id=app.id,
        authorization_id=authorization.id,
        user_id=user.id,
        token_family_id=family_id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        scope_json=_scope_json(scopes),
        refresh_issued_at=now,
        access_expires_at=now + timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES),
        refresh_expires_at=now + timedelta(days=REFRESH_TOKEN_TTL_DAYS),
    )
    db.add(session)
    db.flush()
    access_token = create_third_party_access_token(
        secret_key=settings.app_secret_key,
        ttl_minutes=ACCESS_TOKEN_TTL_MINUTES,
        user_id=user.id,
        app_id=app.id,
        client_id=app.client_id,
        token_session_id=session.id,
        token_family_id=family_id,
        scopes=tuple(scopes),
    )
    return access_token, refresh_token


def exchange_authorization_code(
    db: Session,
    settings: Settings,
    *,
    client_id: str,
    raw_code: str,
    redirect_uri: str,
    code_verifier: str,
) -> tuple[str, str, int, list[str]]:
    app = _approved_app(db, client_id)
    row = db.scalar(
        select(OAuthAuthorizationCode).where(
            OAuthAuthorizationCode.code_hash == hash_opaque_token(raw_code),
            OAuthAuthorizationCode.app_id == app.id,
        )
    )
    now = utc_now()
    if row is None or row.consumed_at is not None or _aware(row.expires_at) <= now:
        raise _grant_invalid()
    if row.redirect_uri != redirect_uri or not hmac.compare_digest(
        row.code_challenge, _pkce_digest(code_verifier)
    ):
        raise _grant_invalid("PKCE 校验失败或 redirect_uri 不匹配")
    authorization = db.get(ThirdPartyAuthorization, row.authorization_id)
    user = db.get(User, row.user_id)
    if (
        authorization is None
        or authorization.revoked_at is not None
        or user is None
        or user.status != UserStatus.ACTIVE
    ):
        raise _grant_invalid("用户授权已失效")
    claimed = db.execute(
        update(OAuthAuthorizationCode)
        .where(OAuthAuthorizationCode.id == row.id, OAuthAuthorizationCode.consumed_at.is_(None))
        .values(consumed_at=now)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise _grant_invalid()
    access_token, refresh_token = _issue_response(
        db,
        settings,
        app=app,
        authorization=authorization,
        user=user,
        scopes=_decode_scopes(row.scope_json),
        family_id=secrets.token_urlsafe(18),
    )
    authorization.last_used_at = now
    db.commit()
    return (
        access_token,
        refresh_token,
        ACCESS_TOKEN_TTL_MINUTES * 60,
        _decode_scopes(row.scope_json),
    )


def _revoke_family(db: Session, family_id: str) -> None:
    db.execute(
        update(OAuthTokenSession)
        .where(
            OAuthTokenSession.token_family_id == family_id, OAuthTokenSession.revoked_at.is_(None)
        )
        .values(revoked_at=utc_now())
    )


def rotate_refresh_token(
    db: Session,
    settings: Settings,
    *,
    client_id: str,
    raw_refresh_token: str,
) -> tuple[str, str, int, list[str]]:
    app = _approved_app(db, client_id)
    row = db.scalar(
        select(OAuthTokenSession).where(
            OAuthTokenSession.refresh_token_hash == hash_refresh_token(raw_refresh_token),
            OAuthTokenSession.app_id == app.id,
        )
    )
    now = utc_now()
    if row is None:
        raise _grant_invalid("刷新令牌无效")
    if row.refresh_rotated_at is not None or row.revoked_at is not None:
        _revoke_family(db, row.token_family_id)
        db.commit()
        raise AppError(
            "third_party_oauth.refresh_token_reused",
            "检测到刷新令牌重复使用，令牌族已撤销",
            status_code=400,
        )
    if _aware(row.refresh_expires_at) <= now:
        row.revoked_at = now
        db.commit()
        raise AppError("third_party_oauth.refresh_token_expired", "刷新令牌已过期", status_code=400)
    authorization = db.get(ThirdPartyAuthorization, row.authorization_id)
    user = db.get(User, row.user_id)
    if (
        authorization is None
        or authorization.revoked_at is not None
        or user is None
        or user.status != UserStatus.ACTIVE
    ):
        raise _grant_invalid("用户授权已失效")
    claimed = db.execute(
        update(OAuthTokenSession)
        .where(
            OAuthTokenSession.id == row.id,
            OAuthTokenSession.refresh_rotated_at.is_(None),
            OAuthTokenSession.revoked_at.is_(None),
        )
        .values(refresh_rotated_at=now, last_used_at=now)
    )
    if claimed.rowcount != 1:
        _revoke_family(db, row.token_family_id)
        db.commit()
        raise AppError(
            "third_party_oauth.refresh_token_reused",
            "检测到刷新令牌重复使用，令牌族已撤销",
            status_code=400,
        )
    access_token, refresh_token = _issue_response(
        db,
        settings,
        app=app,
        authorization=authorization,
        user=user,
        scopes=_decode_scopes(row.scope_json),
        family_id=row.token_family_id,
    )
    db.commit()
    return (
        access_token,
        refresh_token,
        ACCESS_TOKEN_TTL_MINUTES * 60,
        _decode_scopes(row.scope_json),
    )


def revoke_token(db: Session, *, client_id: str, token: str) -> None:
    app = db.scalar(select(ThirdPartyApp).where(ThirdPartyApp.client_id == client_id))
    if app is None:
        return
    row = db.scalar(
        select(OAuthTokenSession).where(
            OAuthTokenSession.app_id == app.id,
            OAuthTokenSession.refresh_token_hash == hash_refresh_token(token),
        )
    )
    if row is not None:
        _revoke_family(db, row.token_family_id)
        db.commit()



def _authorization_request_context(
    db: Session, *, user: User, request: ThirdPartyAuthorizationRequest
) -> tuple[ThirdPartyApp, list[str]]:
    if user.status != UserStatus.ACTIVE:
        raise AppError("auth.account_unavailable", "账号当前不可用", status_code=403)
    if request.response_type != "code":
        raise _invalid("仅支持 response_type=code")
    if request.code_challenge_method != "S256":
        raise _invalid("PKCE 仅支持 S256")
    if len(request.state) < 16:
        raise _invalid("state 长度至少为 16")
    if len(request.code_challenge) < 43 or len(request.code_challenge) > 128:
        raise _invalid("code_challenge 格式无效")
    app = _approved_app(db, request.client_id)
    _validate_redirect(db, app.id, request.redirect_uri)
    return app, _validate_scopes(app, _scopes(request.scope))


def get_authorization_details(
    db: Session, *, user: User, request: ThirdPartyAuthorizationRequest
) -> ThirdPartyAuthorizationDetails:
    app, requested_scopes = _authorization_request_context(db, user=user, request=request)
    authorization = db.scalar(
        select(ThirdPartyAuthorization).where(
            ThirdPartyAuthorization.app_id == app.id,
            ThirdPartyAuthorization.user_id == user.id,
            ThirdPartyAuthorization.revoked_at.is_(None),
        )
    )
    return ThirdPartyAuthorizationDetails(
        client_id=app.client_id,
        app_name=app.name,
        developer_name=app.developer_name,
        description=app.description,
        redirect_uri=request.redirect_uri,
        requested_scopes=requested_scopes,
        approved_scopes=_decode_scopes(app.approved_scopes_json),
        previously_authorized=authorization is not None,
    )


def decide_authorization(
    db: Session,
    *,
    user: User,
    request: ThirdPartyAuthorizationRequest,
    decision: str,
) -> str:
    app, requested_scopes = _authorization_request_context(db, user=user, request=request)
    if decision == "deny":
        return _append_query(
            request.redirect_uri,
            {"error": "access_denied", "state": request.state},
        )
    if decision != "approve":
        raise _invalid("授权决定无效")
    code = issue_authorization_code(
        db,
        app=app,
        user=user,
        redirect_uri=request.redirect_uri,
        code_challenge=request.code_challenge,
        code_challenge_method=request.code_challenge_method,
        requested_scopes=requested_scopes,
    )
    return _append_query(request.redirect_uri, {"code": code, "state": request.state})


def list_authorized_applications(
    db: Session, *, user: User
) -> list[AuthorizedApplicationItem]:
    rows = db.execute(
        select(ThirdPartyAuthorization, ThirdPartyApp)
        .join(ThirdPartyApp, ThirdPartyApp.id == ThirdPartyAuthorization.app_id)
        .where(
            ThirdPartyAuthorization.user_id == user.id,
            ThirdPartyAuthorization.revoked_at.is_(None),
        )
        .order_by(ThirdPartyAuthorization.created_at.desc())
    ).all()
    return [
        AuthorizedApplicationItem(
            app_id=authorization.app_id,
            client_id=app.client_id,
            app_name=app.name,
            developer_name=app.developer_name,
            scopes=_decode_scopes(authorization.scope_json),
            authorized_at=authorization.created_at.isoformat(),
            last_used_at=(
                authorization.last_used_at.isoformat()
                if authorization.last_used_at is not None
                else None
            ),
        )
        for authorization, app in rows
    ]


def revoke_authorization(db: Session, *, user: User, app_id: str) -> None:
    authorization = db.scalar(
        select(ThirdPartyAuthorization).where(
            ThirdPartyAuthorization.app_id == app_id,
            ThirdPartyAuthorization.user_id == user.id,
            ThirdPartyAuthorization.revoked_at.is_(None),
        )
    )
    if authorization is None:
        return
    now = utc_now()
    authorization.revoked_at = now
    db.execute(
        update(OAuthTokenSession)
        .where(
            OAuthTokenSession.authorization_id == authorization.id,
            OAuthTokenSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    db.commit()
