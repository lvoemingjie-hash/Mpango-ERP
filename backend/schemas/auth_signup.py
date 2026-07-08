"""Signup schemas for U6-C tenant onboarding."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class SignupRequest(BaseModel):
    """Public tenant signup request."""

    company_name: str = Field(..., alias="companyName", min_length=2, max_length=255)
    country: str = Field(..., min_length=2, max_length=2)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    phone: str | None = Field(None, max_length=32)
    business_type: str | None = Field(None, alias="businessType", max_length=64)

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    @field_validator("company_name")
    @classmethod
    def normalize_company_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("country")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("phone", "business_type")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class SignupResponseData(BaseModel):
    """Neutral signup response data."""

    registration_id: UUID | None = Field(None, alias="registrationId")
    status: str
    email_verification_required: bool = Field(True, alias="emailVerificationRequired")
    resend_available_at: datetime | None = Field(None, alias="resendAvailableAt")

    model_config = ConfigDict(populate_by_name=True)


class SignupResponse(BaseModel):
    """Neutral public signup response."""

    success: bool = True
    data: SignupResponseData
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(populate_by_name=True)


class VerifyEmailRequest(BaseModel):
    """Public email verification request."""

    token: str | None = Field(None, min_length=1, max_length=512)

    model_config = ConfigDict(str_strip_whitespace=True)


class VerifyEmailResponseData(BaseModel):
    """Neutral email verification response data."""

    accepted: bool = True


class VerifyEmailResponse(BaseModel):
    """Neutral public email verification response."""

    success: bool = True
    data: VerifyEmailResponseData = Field(default_factory=VerifyEmailResponseData)
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(populate_by_name=True)


class OnboardingStatusRequest(BaseModel):
    """Public onboarding status request."""

    status_token: str | None = Field(None, alias="statusToken", min_length=1, max_length=512)

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)


class OnboardingStatusResponseData(BaseModel):
    """Coarse public onboarding status data."""

    status: str


class OnboardingStatusResponse(BaseModel):
    """Neutral public onboarding status response."""

    success: bool = True
    data: OnboardingStatusResponseData
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(populate_by_name=True)


class OwnerCredentialSetupRequest(BaseModel):
    """Public owner credential setup request."""

    setup_token: str | None = Field(None, alias="setupToken", max_length=512)
    password: str = Field(..., min_length=8, max_length=128)

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)


class OwnerCredentialSetupResponseData(BaseModel):
    """Neutral owner credential setup response data."""

    registration_id: UUID | None = Field(None, alias="registrationId")

    model_config = ConfigDict(populate_by_name=True)


class OwnerCredentialSetupResponse(BaseModel):
    """Neutral public owner credential setup response."""

    success: bool = True
    data: OwnerCredentialSetupResponseData = Field(default_factory=OwnerCredentialSetupResponseData)
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(populate_by_name=True)
