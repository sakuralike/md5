from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from password_detective.core.config import Settings
from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.archive import Archive
from password_detective.db.models.archive_fingerprint import ArchiveFingerprint
from password_detective.db.models.desktop_verification import (
    ClientInstallation,
    InstallationStatus,
    ReceiptProtocol,
    VerificationChallenge,
    VerificationReceipt,
    VerificationTrustChannel,
)
from password_detective.db.models.password_candidate import CandidateStatus, PasswordCandidate
from password_detective.db.models.verification import VerificationSource
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.desktop_verification import service as desktop_service
from password_detective.modules.third_party_desktop.schemas import (
    ThirdPartyChallengeRequest,
    ThirdPartyChallengeResponse,
    ThirdPartyInstallationListResponse,
    ThirdPartyInstallationRegistrationRequest,
    ThirdPartyInstallationResponse,
    ThirdPartyReceiptRequest,
    ThirdPartyReceiptResponse,
)
from password_detective.modules.third_party_oauth.dependencies import ThirdPartyPrincipal
from password_detective.modules.verification.service import apply_candidate_evidence

CANONICAL_PAYLOAD_VERSION = ReceiptProtocol.THIRD_PARTY_DESKTOP_V1.value


def _official_principal(principal: ThirdPartyPrincipal) -> Principal:
    return Principal(
        user=principal.user,
        session_family_id=f"third-party:{principal.session.token_family_id}",
        mfa_verified=True,
    )


def _installation_response(
    installation: ClientInstallation, client_id: str
) -> ThirdPartyInstallationResponse:
    protocol = installation.receipt_protocol or ReceiptProtocol.THIRD_PARTY_DESKTOP_V1
    protocol_value = protocol.value if isinstance(protocol, ReceiptProtocol) else protocol
    return ThirdPartyInstallationResponse(
        installation_id=installation.id,
        status=installation.status,
        key_algorithm=installation.key_algorithm,
        public_key_fingerprint=installation.public_key_fingerprint,
        client_version=installation.client_version,
        receipt_count=installation.receipt_count,
        created_at=installation.created_at,
        last_seen_at=installation.last_seen_at,
        revoked_at=installation.revoked_at,
        client_id=client_id,
        receipt_protocol=protocol_value,
        operating_system=installation.operating_system,
        architecture=installation.architecture,
    )


def register_installation(
    db: Session,
    settings: Settings,
    *,
    payload: ThirdPartyInstallationRegistrationRequest,
    principal: ThirdPartyPrincipal,
    context: ClientContext,
) -> ThirdPartyInstallationResponse:
    installation_id = str(payload.installation_id)
    desktop_service._require_supported_client_version(db, payload.client_version, settings)
    public_key_der = desktop_service._decode_and_validate_public_key(payload.public_key)
    fingerprint = hashlib.sha256(public_key_der).hexdigest()
    installation = db.get(ClientInstallation, installation_id)
    if installation is not None:
        if installation.user_id != principal.user.id:
            raise AppError(
                "third_party_desktop.installation_account_mismatch",
                "该安装实例已绑定其他账号",
                status_code=409,
            )
        if installation.third_party_app_id != principal.app.id:
            raise AppError(
                "third_party_desktop.installation_app_mismatch",
                "该安装实例已绑定其他应用或官方桌面端",
                status_code=409,
            )
        if installation.status == InstallationStatus.REVOKED:
            raise AppError(
                "third_party_desktop.installation_revoked",
                "该安装实例已撤销，请生成新的安装实例",
                status_code=409,
            )
        if not hmac.compare_digest(installation.public_key_fingerprint, fingerprint):
            raise AppError(
                "third_party_desktop.installation_key_mismatch",
                "安装实例公钥与已注册记录不一致",
                status_code=409,
            )
        installation.client_version = payload.client_version
        installation.operating_system = payload.operating_system
        installation.architecture = payload.architecture
        installation.last_seen_at = utc_now()
        installation.last_ip_prefix = context.ip_prefix
    else:
        fingerprint_owner = db.scalar(
            select(ClientInstallation).where(
                ClientInstallation.public_key_fingerprint == fingerprint
            )
        )
        if fingerprint_owner is not None:
            raise AppError(
                "third_party_desktop.installation_key_reused",
                "安装公钥已绑定其他安装实例",
                status_code=409,
            )
        active_count = (
            db.scalar(
                select(func.count(ClientInstallation.id)).where(
                    ClientInstallation.user_id == principal.user.id,
                    ClientInstallation.status == InstallationStatus.ACTIVE,
                )
            )
            or 0
        )
        if active_count >= settings.desktop_max_installations_per_user:
            raise AppError(
                "third_party_desktop.installation_limit_reached",
                "安装实例数量已达到上限，请先撤销旧实例",
                status_code=409,
            )
        installation = ClientInstallation(
            id=installation_id,
            user_id=principal.user.id,
            third_party_app_id=principal.app.id,
            receipt_protocol=ReceiptProtocol.THIRD_PARTY_DESKTOP_V1.value,
            operating_system=payload.operating_system,
            architecture=payload.architecture,
            public_key_der=public_key_der,
            public_key_fingerprint=fingerprint,
            key_algorithm=payload.key_algorithm,
            status=InstallationStatus.ACTIVE,
            client_version=payload.client_version,
            first_ip_prefix=context.ip_prefix,
            last_ip_prefix=context.ip_prefix,
        )
        db.add(installation)
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="third_party_desktop.installation_registered",
        target_type="client_installation",
        target_id=installation_id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"client_id": principal.app.client_id, "client_version": payload.client_version},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            "third_party_desktop.installation_conflict",
            "安装实例或公钥已被注册",
            status_code=409,
        ) from exc
    db.refresh(installation)
    return _installation_response(installation, principal.app.client_id)


def list_installations(
    db: Session, *, principal: ThirdPartyPrincipal
) -> ThirdPartyInstallationListResponse:
    rows = list(
        db.scalars(
            select(ClientInstallation)
            .where(
                ClientInstallation.user_id == principal.user.id,
                ClientInstallation.third_party_app_id == principal.app.id,
            )
            .order_by(ClientInstallation.created_at.desc())
        )
    )
    return ThirdPartyInstallationListResponse(
        items=[_installation_response(row, principal.app.client_id) for row in rows]
    )


def revoke_installation(
    db: Session,
    *,
    installation_id: str,
    principal: ThirdPartyPrincipal,
    context: ClientContext,
) -> ThirdPartyInstallationResponse:
    installation = db.scalar(
        select(ClientInstallation)
        .where(
            ClientInstallation.id == installation_id,
            ClientInstallation.user_id == principal.user.id,
            ClientInstallation.third_party_app_id == principal.app.id,
        )
        .with_for_update()
    )
    if installation is None:
        raise AppError(
            "third_party_desktop.installation_not_found",
            "未找到第三方安装实例",
            status_code=404,
        )
    if installation.status != InstallationStatus.REVOKED:
        installation.status = InstallationStatus.REVOKED
        installation.revoked_at = utc_now()
        write_audit_log(
            db,
            actor_id=principal.user.id,
            action="third_party_desktop.installation_revoked",
            target_type="client_installation",
            target_id=installation.id,
            result="success",
            ip_prefix=context.ip_prefix,
            request_id=context.request_id,
            details={"client_id": principal.app.client_id},
        )
        db.commit()
        db.refresh(installation)
    return _installation_response(installation, principal.app.client_id)


def create_challenge(
    db: Session,
    settings: Settings,
    *,
    payload: ThirdPartyChallengeRequest,
    principal: ThirdPartyPrincipal,
    context: ClientContext,
) -> ThirdPartyChallengeResponse:
    installation = _active_installation(db, str(payload.installation_id), principal)
    desktop_service._require_supported_client_version(db, payload.client_version, settings)
    normalized = desktop_service.normalize_fingerprint(
        payload.fingerprint_digest, payload.fingerprint_algorithm
    )
    candidate = db.get(PasswordCandidate, payload.candidate_id)
    if candidate is None or candidate.status == CandidateStatus.REJECTED:
        raise AppError(
            "third_party_desktop.candidate_unavailable",
            "候选记录不可用于验证",
            status_code=404,
        )
    fingerprint_exists = db.scalar(
        select(ArchiveFingerprint.id).where(
            ArchiveFingerprint.archive_id == candidate.archive_id,
            ArchiveFingerprint.algorithm == normalized.algorithm,
            ArchiveFingerprint.digest == normalized.digest,
        )
    )
    if fingerprint_exists is None:
        raise AppError(
            "third_party_desktop.fingerprint_candidate_mismatch",
            "文件指纹与候选记录不匹配",
            status_code=409,
        )
    nonce = secrets.token_urlsafe(32)
    now = utc_now()
    challenge = VerificationChallenge(
        installation_id=installation.id,
        user_id=principal.user.id,
        third_party_app_id=principal.app.id,
        receipt_protocol=ReceiptProtocol.THIRD_PARTY_DESKTOP_V1.value,
        candidate_id=candidate.id,
        nonce_hash=hashlib.sha256(nonce.encode()).hexdigest(),
        fingerprint_algorithm=normalized.algorithm,
        fingerprint_digest=normalized.digest,
        client_version=payload.client_version,
        expires_at=now + timedelta(seconds=settings.desktop_challenge_ttl_seconds),
    )
    db.add(challenge)
    installation.client_version = payload.client_version
    installation.last_seen_at = now
    installation.last_ip_prefix = context.ip_prefix
    db.commit()
    db.refresh(challenge)
    return ThirdPartyChallengeResponse(
        challenge_id=challenge.id,
        challenge_nonce=nonce,
        installation_id=installation.id,
        account_id=principal.user.id,
        candidate_id=candidate.id,
        fingerprint_algorithm=challenge.fingerprint_algorithm,
        fingerprint_digest=challenge.fingerprint_digest,
        client_version=challenge.client_version,
        canonical_payload_version=CANONICAL_PAYLOAD_VERSION,
        expires_at=challenge.expires_at,
        client_id=principal.app.client_id,
    )


def submit_receipt(
    db: Session,
    settings: Settings,
    *,
    payload: ThirdPartyReceiptRequest,
    principal: ThirdPartyPrincipal,
    context: ClientContext,
) -> ThirdPartyReceiptResponse:
    now = utc_now()
    challenge = db.scalar(
        select(VerificationChallenge)
        .where(
            VerificationChallenge.id == payload.challenge_id,
            VerificationChallenge.user_id == principal.user.id,
            VerificationChallenge.third_party_app_id == principal.app.id,
            VerificationChallenge.receipt_protocol == ReceiptProtocol.THIRD_PARTY_DESKTOP_V1.value,
        )
        .with_for_update()
    )
    if challenge is None:
        raise AppError(
            "third_party_desktop.challenge_not_found",
            "挑战不存在或不属于当前应用",
            status_code=404,
        )
    if challenge.used_at is not None:
        raise AppError(
            "third_party_desktop.challenge_replayed", "挑战已使用，拒绝重放", status_code=409
        )
    if desktop_service._as_utc(challenge.expires_at) <= now:
        raise AppError("third_party_desktop.challenge_expired", "挑战已过期", status_code=409)
    nonce_hash = hashlib.sha256(payload.challenge_nonce.encode()).hexdigest()
    if not hmac.compare_digest(challenge.nonce_hash, nonce_hash):
        raise AppError(
            "third_party_desktop.challenge_nonce_invalid", "挑战随机数无效", status_code=409
        )
    if payload.client_id != principal.app.client_id:
        raise AppError(
            "third_party_desktop.client_id_mismatch",
            "回执应用标识与访问令牌不一致",
            status_code=409,
        )
    installation = _active_installation(
        db, str(payload.installation_id), principal, for_update=True
    )
    if (
        challenge.installation_id != installation.id
        or payload.account_id != principal.user.id
        or payload.candidate_id != challenge.candidate_id
        or payload.fingerprint_algorithm != challenge.fingerprint_algorithm
        or payload.fingerprint_digest != challenge.fingerprint_digest
    ):
        raise AppError(
            "third_party_desktop.challenge_binding_mismatch",
            "回执字段与挑战不匹配",
            status_code=409,
        )
    if payload.client_version != challenge.client_version:
        raise AppError(
            "third_party_desktop.client_version_changed",
            "挑战与回执客户端版本不一致",
            status_code=409,
        )
    verified_at = desktop_service._as_utc(payload.verified_at)
    if abs((now - verified_at).total_seconds()) > settings.desktop_receipt_clock_skew_seconds:
        raise AppError(
            "third_party_desktop.receipt_clock_skew",
            "验证回执时间超出允许窗口",
            status_code=409,
        )
    candidate = db.scalar(
        select(PasswordCandidate)
        .where(PasswordCandidate.id == payload.candidate_id)
        .with_for_update()
    )
    if candidate is None:
        raise AppError(
            "third_party_desktop.candidate_unavailable",
            "候选记录不可用于验证",
            status_code=404,
        )
    archive = db.get(Archive, candidate.archive_id)
    if archive is None:
        raise AppError(
            "third_party_desktop.archive_unavailable", "压缩包记录不可用", status_code=404
        )
    if archive.optional_format and archive.optional_format.lower() != payload.archive_format:
        raise AppError(
            "third_party_desktop.archive_format_mismatch",
            "压缩格式与记录不一致",
            status_code=409,
        )
    expected_digest = desktop_service._candidate_digest(settings, candidate)
    if not hmac.compare_digest(expected_digest, payload.candidate_digest):
        raise AppError(
            "third_party_desktop.candidate_digest_mismatch",
            "候选密码摘要不匹配",
            status_code=409,
        )
    canonical_payload = build_canonical_receipt_payload(payload)
    desktop_service._verify_signature(
        installation.public_key_der, canonical_payload, payload.signature
    )
    trusted = (
        "desktop:verification:trusted" in principal.claims.scopes
        and principal.app.trusted_verification_enabled
    )
    mutation = apply_candidate_evidence(
        db,
        settings,
        candidate=candidate,
        outcome=payload.outcome,
        source=VerificationSource.DESKTOP_RECEIPT,
        principal=_official_principal(principal),
        context=context,
        installation_id_hash=desktop_service._installation_correlation_hash(
            settings, installation.id
        ),
        promote_verified_on_success=trusted,
    )
    trust_channel = (
        VerificationTrustChannel.THIRD_PARTY_TRUSTED
        if trusted
        else VerificationTrustChannel.THIRD_PARTY_PENDING
    )
    receipt = VerificationReceipt(
        challenge_id=challenge.id,
        installation_id=installation.id,
        user_id=principal.user.id,
        third_party_app_id=principal.app.id,
        receipt_protocol=ReceiptProtocol.THIRD_PARTY_DESKTOP_V1.value,
        trust_channel=trust_channel.value,
        candidate_id=candidate.id,
        outcome=payload.outcome,
        archive_format=payload.archive_format,
        fingerprint_algorithm=payload.fingerprint_algorithm,
        fingerprint_digest=payload.fingerprint_digest,
        candidate_digest_hash=desktop_service._sensitive_digest_hash(
            settings, payload.candidate_digest
        ),
        client_version=payload.client_version,
        verified_at=verified_at,
        canonical_payload_hash=hashlib.sha256(canonical_payload).hexdigest(),
        signature=payload.signature,
        evidence_event_id=mutation.evidence_event.id if mutation.evidence_event else None,
    )
    db.add(receipt)
    challenge.used_at = now
    installation.last_seen_at = now
    installation.last_ip_prefix = context.ip_prefix
    installation.receipt_count += 1
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="third_party_desktop.verification_receipt_accepted",
        target_type="password_candidate",
        target_id=candidate.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={"client_id": principal.app.client_id, "trust_channel": trust_channel.value},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            "third_party_desktop.receipt_replayed",
            "该验证回执已提交，拒绝重放",
            status_code=409,
        ) from exc
    db.refresh(receipt)
    return ThirdPartyReceiptResponse(
        receipt_id=receipt.id,
        evidence_event_id=receipt.evidence_event_id,
        candidate_id=candidate.id,
        outcome=receipt.outcome,
        candidate_status=candidate.status,
        snapshot=mutation.totals.to_snapshot(),
        accepted_at=receipt.created_at,
        trust_channel=trust_channel.value,
    )


def build_canonical_receipt_payload(payload: ThirdPartyReceiptRequest) -> bytes:
    values = (
        ("version", CANONICAL_PAYLOAD_VERSION),
        ("client_id", payload.client_id),
        ("challenge_id", payload.challenge_id),
        ("challenge_nonce", payload.challenge_nonce),
        ("installation_id", str(payload.installation_id)),
        ("account_id", payload.account_id),
        ("candidate_id", payload.candidate_id),
        ("fingerprint_algorithm", payload.fingerprint_algorithm.value),
        ("fingerprint_digest", payload.fingerprint_digest),
        ("candidate_digest", payload.candidate_digest),
        ("outcome", payload.outcome.value),
        ("archive_format", payload.archive_format),
        ("client_version", payload.client_version),
        ("verified_at", desktop_service._format_timestamp(payload.verified_at)),
    )
    return ("\n".join(f"{key}={value}" for key, value in values) + "\n").encode("utf-8")


def _active_installation(
    db: Session,
    installation_id: str,
    principal: ThirdPartyPrincipal,
    *,
    for_update: bool = False,
) -> ClientInstallation:
    query = select(ClientInstallation).where(
        ClientInstallation.id == installation_id,
        ClientInstallation.user_id == principal.user.id,
        ClientInstallation.third_party_app_id == principal.app.id,
    )
    installation = db.scalar(query.with_for_update() if for_update else query)
    if installation is None:
        raise AppError(
            "third_party_desktop.installation_not_found",
            "未找到第三方安装实例",
            status_code=404,
        )
    if installation.status != InstallationStatus.ACTIVE:
        raise AppError(
            "third_party_desktop.installation_revoked", "安装实例已撤销", status_code=403
        )
    return installation
