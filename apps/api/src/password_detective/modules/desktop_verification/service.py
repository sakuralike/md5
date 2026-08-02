from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from password_detective.core.candidate_secrets import CandidateSecretVault
from password_detective.core.config import Settings
from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.archive import Archive
from password_detective.db.models.archive_fingerprint import ArchiveFingerprint
from password_detective.db.models.desktop_verification import (
    ClientInstallation,
    InstallationStatus,
    VerificationChallenge,
    VerificationReceipt,
)
from password_detective.db.models.password_candidate import CandidateStatus, PasswordCandidate
from password_detective.db.models.verification import VerificationSource
from password_detective.modules.archives.service import normalize_fingerprint
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.desktop_verification.schemas import (
    ChallengeRequest,
    ChallengeResponse,
    InstallationListResponse,
    InstallationRegistrationRequest,
    InstallationResponse,
    ReceiptRequest,
    ReceiptResponse,
)
from password_detective.modules.verification.service import apply_candidate_evidence

CANONICAL_PAYLOAD_VERSION = "desktop-receipt-v1"
_VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$")


def register_installation(
    db: Session,
    settings: Settings,
    *,
    payload: InstallationRegistrationRequest,
    principal: Principal,
    context: ClientContext,
) -> InstallationResponse:
    installation_id = str(payload.installation_id)
    _require_supported_client_version(payload.client_version, settings)
    public_key_der = _decode_and_validate_public_key(payload.public_key)
    public_key_fingerprint = hashlib.sha256(public_key_der).hexdigest()
    installation = db.get(ClientInstallation, installation_id)
    if installation is not None:
        if installation.user_id != principal.user.id:
            raise AppError(
                "desktop.installation_account_mismatch",
                "该安装实例已绑定其他账号",
                status_code=409,
            )
        if installation.status == InstallationStatus.REVOKED:
            raise AppError(
                "desktop.installation_revoked",
                "该安装实例已撤销，请生成新的安装实例",
                status_code=409,
            )
        if not hmac.compare_digest(installation.public_key_fingerprint, public_key_fingerprint):
            raise AppError(
                "desktop.installation_key_mismatch",
                "安装实例公钥与已注册记录不一致",
                status_code=409,
            )
        installation.client_version = payload.client_version
        installation.last_seen_at = utc_now()
        installation.last_ip_prefix = context.ip_prefix
    else:
        active_count = db.scalar(
            select(func.count(ClientInstallation.id)).where(
                ClientInstallation.user_id == principal.user.id,
                ClientInstallation.status == InstallationStatus.ACTIVE,
            )
        ) or 0
        if active_count >= settings.desktop_max_installations_per_user:
            raise AppError(
                "desktop.installation_limit_reached",
                "安装实例数量已达到上限，请先撤销旧实例",
                status_code=409,
            )
        installation = ClientInstallation(
            id=installation_id,
            user_id=principal.user.id,
            public_key_der=public_key_der,
            public_key_fingerprint=public_key_fingerprint,
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
        action="desktop.installation_registered",
        target_type="client_installation",
        target_id=installation_id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "key_algorithm": payload.key_algorithm,
            "client_version": payload.client_version,
            "existing": installation.created_at is not None,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            "desktop.installation_conflict",
            "安装实例或公钥已被注册",
            status_code=409,
        ) from exc
    db.refresh(installation)
    return _installation_response(installation)


def list_installations(db: Session, *, principal: Principal) -> InstallationListResponse:
    installations = list(
        db.scalars(
            select(ClientInstallation)
            .where(ClientInstallation.user_id == principal.user.id)
            .order_by(ClientInstallation.created_at.desc())
        )
    )
    return InstallationListResponse(items=[_installation_response(item) for item in installations])


def revoke_installation(
    db: Session,
    *,
    installation_id: str,
    principal: Principal,
    context: ClientContext,
) -> InstallationResponse:
    installation = db.scalar(
        select(ClientInstallation)
        .where(
            ClientInstallation.id == installation_id,
            ClientInstallation.user_id == principal.user.id,
        )
        .with_for_update()
    )
    if installation is None:
        raise AppError("desktop.installation_not_found", "未找到安装实例", status_code=404)
    if installation.status != InstallationStatus.REVOKED:
        installation.status = InstallationStatus.REVOKED
        installation.revoked_at = utc_now()
        installation.last_seen_at = utc_now()
        write_audit_log(
            db,
            actor_id=principal.user.id,
            action="desktop.installation_revoked",
            target_type="client_installation",
            target_id=installation.id,
            result="success",
            ip_prefix=context.ip_prefix,
            request_id=context.request_id,
            details={},
        )
        db.commit()
        db.refresh(installation)
    return _installation_response(installation)


def create_challenge(
    db: Session,
    settings: Settings,
    *,
    payload: ChallengeRequest,
    principal: Principal,
    context: ClientContext,
) -> ChallengeResponse:
    installation = _active_installation(
        db,
        str(payload.installation_id),
        principal.user.id,
        for_update=True,
    )
    _require_supported_client_version(payload.client_version, settings)
    normalized = normalize_fingerprint(payload.fingerprint_digest, payload.fingerprint_algorithm)
    candidate = db.get(PasswordCandidate, payload.candidate_id)
    if candidate is None or candidate.status == CandidateStatus.REJECTED:
        raise AppError("desktop.candidate_unavailable", "候选记录不可用于验证", status_code=404)
    fingerprint_exists = db.scalar(
        select(ArchiveFingerprint.id).where(
            ArchiveFingerprint.archive_id == candidate.archive_id,
            ArchiveFingerprint.algorithm == normalized.algorithm,
            ArchiveFingerprint.digest == normalized.digest,
        )
    )
    if fingerprint_exists is None:
        raise AppError(
            "desktop.fingerprint_candidate_mismatch",
            "文件指纹与候选记录不匹配",
            status_code=409,
        )
    nonce = secrets.token_urlsafe(32)
    now = utc_now()
    challenge = VerificationChallenge(
        installation_id=installation.id,
        user_id=principal.user.id,
        candidate_id=candidate.id,
        nonce_hash=_sha256_text(nonce),
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
    return ChallengeResponse(
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
    )


def submit_receipt(
    db: Session,
    settings: Settings,
    *,
    payload: ReceiptRequest,
    principal: Principal,
    context: ClientContext,
) -> ReceiptResponse:
    now = utc_now()
    installation = _active_installation(
        db,
        str(payload.installation_id),
        principal.user.id,
        for_update=True,
    )
    challenge = db.scalar(
        select(VerificationChallenge)
        .where(VerificationChallenge.id == payload.challenge_id)
        .with_for_update()
    )
    if challenge is None:
        raise AppError("desktop.challenge_not_found", "验证挑战不存在", status_code=404)
    if challenge.used_at is not None:
        raise AppError("desktop.challenge_replayed", "验证挑战已使用，拒绝重放", status_code=409)
    if _as_utc(challenge.expires_at) <= now:
        raise AppError("desktop.challenge_expired", "验证挑战已过期", status_code=409)
    _validate_challenge_binding(challenge, payload, principal.user.id, installation.id)
    if not hmac.compare_digest(challenge.nonce_hash, _sha256_text(payload.challenge_nonce)):
        raise AppError("desktop.challenge_nonce_invalid", "验证挑战随机值无效", status_code=409)
    _require_supported_client_version(payload.client_version, settings)
    if payload.client_version != challenge.client_version:
        raise AppError(
            "desktop.client_version_changed",
            "挑战与回执客户端版本不一致",
            status_code=409,
        )
    verified_at = _as_utc(payload.verified_at)
    if abs((now - verified_at).total_seconds()) > settings.desktop_receipt_clock_skew_seconds:
        raise AppError("desktop.receipt_clock_skew", "验证回执时间超出允许窗口", status_code=409)

    candidate = db.scalar(
        select(PasswordCandidate)
        .where(PasswordCandidate.id == payload.candidate_id)
        .with_for_update()
    )
    if candidate is None:
        raise AppError("desktop.candidate_unavailable", "候选记录不可用于验证", status_code=404)
    archive = db.get(Archive, candidate.archive_id)
    if archive is None:
        raise AppError("desktop.archive_unavailable", "压缩包记录不可用", status_code=404)
    if archive.optional_format and archive.optional_format.lower() != payload.archive_format:
        raise AppError("desktop.archive_format_mismatch", "压缩格式与记录不一致", status_code=409)

    expected_candidate_digest = _candidate_digest(settings, candidate)
    if not hmac.compare_digest(expected_candidate_digest, payload.candidate_digest):
        raise AppError("desktop.candidate_digest_mismatch", "候选密码摘要不匹配", status_code=409)

    canonical_payload = build_canonical_receipt_payload(payload)
    canonical_payload_hash = hashlib.sha256(canonical_payload).hexdigest()
    _verify_signature(installation.public_key_der, canonical_payload, payload.signature)

    mutation = apply_candidate_evidence(
        db,
        settings,
        candidate=candidate,
        outcome=payload.outcome,
        source=VerificationSource.DESKTOP_RECEIPT,
        principal=principal,
        context=context,
        installation_id_hash=_installation_correlation_hash(settings, installation.id),
    )
    receipt = VerificationReceipt(
        challenge_id=challenge.id,
        installation_id=installation.id,
        user_id=principal.user.id,
        candidate_id=candidate.id,
        outcome=payload.outcome,
        archive_format=payload.archive_format,
        fingerprint_algorithm=payload.fingerprint_algorithm,
        fingerprint_digest=payload.fingerprint_digest,
        candidate_digest_hash=_sensitive_digest_hash(settings, payload.candidate_digest),
        client_version=payload.client_version,
        verified_at=verified_at,
        canonical_payload_hash=canonical_payload_hash,
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
        action="desktop.verification_receipt_accepted",
        target_type="password_candidate",
        target_id=candidate.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "installation_id": installation.id,
            "outcome": payload.outcome.value,
            "archive_format": payload.archive_format,
            "client_version": payload.client_version,
            "rule_version": mutation.feedback.rule_version,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            "desktop.receipt_replayed",
            "该验证回执已提交，拒绝重放",
            status_code=409,
        ) from exc
    db.refresh(receipt)
    return ReceiptResponse(
        receipt_id=receipt.id,
        evidence_event_id=receipt.evidence_event_id,
        candidate_id=candidate.id,
        outcome=receipt.outcome,
        candidate_status=candidate.status,
        snapshot=mutation.totals.to_snapshot(),
        accepted_at=receipt.created_at,
    )


def build_canonical_receipt_payload(payload: ReceiptRequest) -> bytes:
    verified_at = _format_timestamp(payload.verified_at)
    values = (
        ("version", CANONICAL_PAYLOAD_VERSION),
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
        ("verified_at", verified_at),
    )
    return ("\n".join(f"{key}={value}" for key, value in values) + "\n").encode("utf-8")


def _validate_challenge_binding(
    challenge: VerificationChallenge,
    payload: ReceiptRequest,
    user_id: str,
    installation_id: str,
) -> None:
    expected = (
        challenge.installation_id,
        challenge.user_id,
        challenge.candidate_id,
        challenge.fingerprint_algorithm.value,
        challenge.fingerprint_digest,
    )
    actual = (
        installation_id,
        payload.account_id,
        payload.candidate_id,
        payload.fingerprint_algorithm.value,
        payload.fingerprint_digest,
    )
    if challenge.user_id != user_id or expected != actual:
        raise AppError(
            "desktop.challenge_binding_mismatch",
            "回执字段与挑战不匹配",
            status_code=409,
        )


def _active_installation(
    db: Session,
    installation_id: str,
    user_id: str,
    *,
    for_update: bool,
) -> ClientInstallation:
    query = select(ClientInstallation).where(
        ClientInstallation.id == installation_id,
        ClientInstallation.user_id == user_id,
    )
    installation = db.scalar(query.with_for_update() if for_update else query)
    if installation is None:
        raise AppError("desktop.installation_not_found", "未找到安装实例", status_code=404)
    if installation.status != InstallationStatus.ACTIVE:
        raise AppError("desktop.installation_revoked", "安装实例已撤销", status_code=403)
    return installation


def _decode_and_validate_public_key(encoded: str) -> bytes:
    try:
        der = base64.b64decode(encoded, validate=True)
        key = serialization.load_der_public_key(der)
    except (ValueError, binascii.Error) as exc:
        raise AppError("desktop.invalid_public_key", "安装公钥格式无效", status_code=422) from exc
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(
        key.curve, ec.SECP256R1
    ):
        raise AppError(
            "desktop.unsupported_public_key",
            "仅支持 ECDSA P-256 安装公钥",
            status_code=422,
        )
    return der


def _verify_signature(public_key_der: bytes, message: bytes, encoded_signature: str) -> None:
    try:
        signature = base64.b64decode(encoded_signature, validate=True)
        public_key = serialization.load_der_public_key(public_key_der)
        assert isinstance(public_key, ec.EllipticCurvePublicKey)
        public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
    except (ValueError, binascii.Error, InvalidSignature, AssertionError) as exc:
        raise AppError("desktop.signature_invalid", "验证回执签名无效", status_code=403) from exc


def _candidate_digest(settings: Settings, candidate: PasswordCandidate) -> str:
    secret = CandidateSecretVault(
        settings.app_secret_key,
        key_version=settings.candidate_secret_key_version,
    ).decrypt(
        ciphertext=candidate.secret_ciphertext,
        nonce=candidate.secret_nonce,
        key_version=candidate.secret_key_version,
    )
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _installation_correlation_hash(settings: Settings, installation_id: str) -> str:
    return hmac.new(
        settings.app_secret_key.encode("utf-8"),
        f"desktop-installation:{installation_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _sensitive_digest_hash(settings: Settings, digest: str) -> str:
    return hmac.new(
        settings.app_secret_key.encode("utf-8"),
        f"desktop-candidate-digest:{digest}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _require_supported_client_version(version: str, settings: Settings) -> None:
    parsed = _parse_version(version)
    minimum = _parse_version(settings.desktop_min_client_version)
    if parsed < minimum:
        raise AppError(
            "desktop.client_version_unsupported",
            f"客户端版本过低，最低要求为 {settings.desktop_min_client_version}",
            status_code=426,
        )


def _parse_version(value: str) -> tuple[int, int, int]:
    match = _VERSION_PATTERN.fullmatch(value.strip())
    if match is None:
        raise AppError("desktop.client_version_invalid", "客户端版本格式无效", status_code=422)
    return tuple(int(part) for part in match.groups())


def _installation_response(installation: ClientInstallation) -> InstallationResponse:
    return InstallationResponse(
        installation_id=installation.id,
        status=installation.status,
        key_algorithm=installation.key_algorithm,
        public_key_fingerprint=installation.public_key_fingerprint,
        client_version=installation.client_version,
        receipt_count=installation.receipt_count,
        created_at=installation.created_at,
        last_seen_at=installation.last_seen_at,
        revoked_at=installation.revoked_at,
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _format_timestamp(value: datetime) -> str:
    return _as_utc(value).isoformat(timespec="milliseconds").replace("+00:00", "Z")
