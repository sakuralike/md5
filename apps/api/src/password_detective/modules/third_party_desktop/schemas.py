from __future__ import annotations

from typing import Literal

from pydantic import Field

from password_detective.modules.desktop_verification.schemas import (
    ChallengeRequest,
    ChallengeResponse,
    InstallationListResponse,
    InstallationRegistrationRequest,
    InstallationResponse,
    ReceiptRequest,
    ReceiptResponse,
)

OperatingSystem = Literal["windows", "linux", "macos", "other"]
Architecture = Literal["x86", "x64", "arm64", "other"]


class ThirdPartyInstallationRegistrationRequest(InstallationRegistrationRequest):
    operating_system: OperatingSystem | None = None
    architecture: Architecture | None = None


class ThirdPartyInstallationResponse(InstallationResponse):
    client_id: str
    receipt_protocol: str
    operating_system: str | None
    architecture: str | None


class ThirdPartyInstallationListResponse(InstallationListResponse):
    items: list[ThirdPartyInstallationResponse]


class ThirdPartyChallengeRequest(ChallengeRequest):
    pass


class ThirdPartyChallengeResponse(ChallengeResponse):
    client_id: str


class ThirdPartyReceiptRequest(ReceiptRequest):
    client_id: str = Field(min_length=8, max_length=128)


class ThirdPartyReceiptResponse(ReceiptResponse):
    trust_channel: str
