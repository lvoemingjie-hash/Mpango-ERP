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
# Retailer login (POST /client/auth/login) — supplier-scoped, DC-12R1-S2
# ---------------------------------------------------------------------------

# Wholesaler portal codes follow the database_contract.md regex ^[A-Z0-9]+$.
# A pre-compiled regex check is applied before any DB query so malformed codes
# raise a controlled 422 without touching SQL.
import re as _re

WHOLESALER_CODE_RE = _re.compile(r"^[A-Z0-9]+$")


class RetailerLoginRequest(BaseModel):
    """Supplier-scoped retailer login body.

    The wholesaler_code identifies the single portal/tenant the retailer is
    authenticating against. No cross-tenant discovery is performed.
    """

    email: EmailStr
    password: str = Field(..., min_length=1, description="Retailer password")
    wholesaler_code: str = Field(
        ..., min_length=1, description="Wholesaler portal code"
    )

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)


class RetailerLoginTokens(BaseModel):
    """Contextual tokens for the single selected wholesaler only."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str = Field(..., description="Tenant-local user id")
    tenant_id: str = Field(..., description="Selected wholesaler id")
    tenant_schema: str = Field(..., description="Selected wholesaler schema")
    roles: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class RetailerLoginData(BaseModel):
    """Response data for supplier-scoped retailer login.

    Contains only the authenticated user, current retailer and current
    wholesaler. No identity token, tmap, available_tenants, workspace picker
    or second supplier information.
    """

    tokens: RetailerLoginTokens
    user: "RetailerLoginUser"
    retailer: "RetailerLoginRetailer"
    wholesaler: "RetailerLoginWholesaler"

    model_config = ConfigDict(populate_by_name=True)


class RetailerLoginUser(BaseModel):
    """Authenticated user for the current session."""

    id: str
    email: EmailStr | None = None
    full_name: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class RetailerLoginRetailer(BaseModel):
    """Current retailer (derived server-side from the active binding)."""

    id: str
    name: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class RetailerLoginWholesaler(BaseModel):
    """Current wholesaler (the single selected portal)."""

    id: str
    code: str
    name: str

    model_config = ConfigDict(populate_by_name=True)


class RetailerLoginResponse(BaseModel):
    """Response for POST /api/v1/client/auth/login."""

    success: bool = True
    data: RetailerLoginData
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(populate_by_name=True)


# Forward-ref resolution (RetailerLoginData references the three models above).
RetailerLoginData.model_rebuild()


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
