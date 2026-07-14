"""Platform operator lifecycle API schemas (DC-11P2)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class PlatformOperatorData(BaseModel):
    id: str
    email: EmailStr
    status: str
    role: str
    failed_login_attempts: int
    locked_until: datetime | None = None
    auth_version: int
    last_login_at: datetime | None = None
    revoked_at: datetime | None = None
    invited_by: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlatformOperatorInviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="platform_operator", pattern="^(platform_admin|platform_operator)$")


class PlatformOperatorSetupCredentialRequest(BaseModel):
    setup_token: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8)


class PlatformOperatorForgotPasswordRequest(BaseModel):
    email: EmailStr


class PlatformOperatorResetPasswordRequest(BaseModel):
    reset_token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


class PlatformOperatorPublicResponseData(BaseModel):
    """Empty data object for public token lifecycle responses."""


class PlatformOperatorActionResponseData(BaseModel):
    operator_id: str | None = None
    status: str | None = None
