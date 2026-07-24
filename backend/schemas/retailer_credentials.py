"""DC-12R1-S1 retailer credential request/response schemas.

All redemption endpoints accept tokens ONLY in the JSON body. Responses are
neutral (no account/relationship existence disclosure).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Retailer credential setup (POST /retailers/setup-credential)
# ---------------------------------------------------------------------------

class RetailerSetupCredentialRequest(BaseModel):
    """Public retailer credential setup. Token arrives in the body only."""

    setup_token: str = Field(..., min_length=1, description="Setup token (body only)")
    new_password: str = Field(..., min_length=1, description="New retailer password")

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)


class RetailerCredentialResponseData(BaseModel):
    """Neutral, empty response data (no internal IDs exposed)."""

    model_config = ConfigDict(populate_by_name=True)


class RetailerCredentialResponse(BaseModel):
    """Neutral retailer credential response."""

    success: bool = True
    data: RetailerCredentialResponseData = Field(default_factory=RetailerCredentialResponseData)
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Retailer password reset (POST /client/auth/forgot-password, /reset-password)
# ---------------------------------------------------------------------------

class RetailerForgotPasswordRequest(BaseModel):
    """Public retailer forgot-password. Response is always neutral."""

    email: EmailStr
    wholesaler_code: str = Field(..., min_length=1, description="Wholesaler portal code")

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)


class RetailerResetPasswordRequest(BaseModel):
    """Public retailer reset-password. Token arrives in the body only."""

    reset_token: str = Field(..., min_length=1, description="Reset token (body only)")
    new_password: str = Field(..., min_length=1, description="New retailer password")

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)


# ---------------------------------------------------------------------------
# Invitation lookup (POST /invitations/lookup) — JSON-body preflight
# ---------------------------------------------------------------------------

class InvitationLookupRequest(BaseModel):
    """JSON-body invitation lookup (replaces path-token preflight)."""

    code: str = Field(..., min_length=1, description="Invitation code")

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)


class InvitationRevokeRequest(BaseModel):
    """Optional reason for revoking an invitation."""

    reason: str | None = Field(default=None, description="Optional revocation reason")

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)
