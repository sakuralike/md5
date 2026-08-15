from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OAuthTokenRequest(BaseModel):
    grant_type: str = Field(min_length=1, max_length=64)
    client_id: str = Field(min_length=8, max_length=128)
    code: str | None = Field(default=None, min_length=16, max_length=256)
    redirect_uri: str | None = Field(default=None, min_length=1, max_length=2_000)
    code_verifier: str | None = Field(default=None, min_length=43, max_length=128)
    refresh_token: str | None = Field(default=None, min_length=16, max_length=256)


class OAuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: str
    scope: str


class ThirdPartyPrincipalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    client_id: str
    app_id: str
    scopes: list[str]


class OAuthRevokeRequest(BaseModel):
    client_id: str = Field(min_length=8, max_length=128)
    token: str = Field(min_length=16, max_length=256)
    token_type_hint: str | None = Field(default=None, max_length=32)

    @field_validator("token_type_hint")
    @classmethod
    def normalize_hint(cls, value: str | None) -> str | None:
        return value.lower() if value else value


class ThirdPartyAuthorizationRequest(BaseModel):
    response_type: str = Field(min_length=1, max_length=32)
    client_id: str = Field(min_length=8, max_length=128)
    redirect_uri: str = Field(min_length=1, max_length=2_000)
    code_challenge: str = Field(min_length=43, max_length=128)
    state: str = Field(min_length=16, max_length=256)
    code_challenge_method: str = Field(default="S256", min_length=1, max_length=8)
    scope: str | None = Field(default=None, max_length=1_000)


class ThirdPartyAuthorizationDetails(BaseModel):
    client_id: str
    app_name: str
    developer_name: str
    description: str
    redirect_uri: str
    requested_scopes: list[str]
    approved_scopes: list[str]
    previously_authorized: bool


class ThirdPartyAuthorizationDecisionRequest(ThirdPartyAuthorizationRequest):
    decision: Literal["approve", "deny"]


class ThirdPartyAuthorizationDecisionResponse(BaseModel):
    redirect_url: str


class AuthorizedApplicationItem(BaseModel):
    app_id: str
    client_id: str
    app_name: str
    developer_name: str
    scopes: list[str]
    authorized_at: str
    last_used_at: str | None


class AuthorizedApplicationListResponse(BaseModel):
    items: list[AuthorizedApplicationItem]
