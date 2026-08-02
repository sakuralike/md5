from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,32}$")


def _validate_password(value: str) -> str:
    if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
        raise ValueError("密码至少包含一个字母和一个数字")
    return value


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip()
        if not _USERNAME_PATTERN.fullmatch(value):
            raise ValueError("用户名只能包含字母、数字和下划线")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password(value)


class LoginRequest(BaseModel):
    login: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    totp_code: str | None = Field(default=None, min_length=6, max_length=8)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=256)


class EmailTokenRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class PasswordForgotRequest(BaseModel):
    email: EmailStr


class PasswordResetRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password(value)


class TotpCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8, pattern=r"^[0-9]+$")


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: EmailStr
    email_verified: bool
    status: str
    role: str
    reputation_score: int
    totp_enabled: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    mfa_verified: bool = False
    user: UserResponse


class BrowserTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    mfa_verified: bool = False
    user: UserResponse

    @classmethod
    def from_token_response(cls, tokens: TokenResponse) -> BrowserTokenResponse:
        return cls(
            access_token=tokens.access_token,
            expires_in=tokens.expires_in,
            mfa_verified=tokens.mfa_verified,
            user=tokens.user,
        )


class SessionResponse(BaseModel):
    id: str
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    user_agent: str | None
    ip_prefix: str | None
    current: bool
    mfa_verified: bool


class TotpSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    message: str = "请使用认证器扫描或录入密钥，然后提交验证码确认"


class MessageResponse(BaseModel):
    message: str
