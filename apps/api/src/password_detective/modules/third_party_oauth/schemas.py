from __future__ import annotations

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
