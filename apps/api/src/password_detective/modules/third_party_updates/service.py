from __future__ import annotations

from sqlalchemy.orm import Session

from password_detective.db.audit import write_audit_log
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.desktop_updates.schemas import DesktopUpdateCheckResponse
from password_detective.modules.desktop_updates.service import check_for_update
from password_detective.modules.third_party_oauth.dependencies import ThirdPartyPrincipal
from password_detective.modules.third_party_updates.schemas import ThirdPartyUpdateCheckResponse


def check_third_party_update(
    db: Session,
    *,
    current_version: str,
    channel,
    platform: str,
    architecture,
    download_url_builder,
    principal: ThirdPartyPrincipal,
    context: ClientContext,
) -> ThirdPartyUpdateCheckResponse:
    public_response: DesktopUpdateCheckResponse = check_for_update(
        db,
        current_version=current_version,
        channel=channel,
        platform=platform,
        architecture=architecture,
        download_url_builder=download_url_builder,
    )
    response = ThirdPartyUpdateCheckResponse(
        update_available=public_response.update_available,
        mandatory=public_response.mandatory,
        current_version=public_response.current_version,
        latest_version=public_response.latest_version,
        minimum_supported_version=public_response.minimum_supported_version,
        channel=public_response.channel,
        platform=public_response.platform,
        architecture=public_response.architecture,
        release_id=public_response.release_id,
        release_notes=public_response.release_notes,
        published_at=public_response.published_at,
        download_url=public_response.download_url,
        artifact_filename=public_response.artifact_filename,
        artifact_sha256=public_response.artifact_sha256,
        artifact_size_bytes=public_response.artifact_size_bytes,
        artifact_integrity=public_response.artifact_integrity,
    )
    write_audit_log(
        db,
        actor_id=principal.user.id,
        action="third_party_update.check",
        target_type="third_party_app",
        target_id=principal.app.id,
        result="success",
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "client_id": principal.app.client_id,
            "current_version": current_version,
            "latest_version": response.latest_version or "",
            "update_available": response.update_available,
        },
    )
    db.commit()
    return response
