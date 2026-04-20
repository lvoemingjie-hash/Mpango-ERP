"""
Authentication Pydantic schemas.

H-Fix-01: Decoupled Identity from Tenant Context.
- LoginRequest no longer requires tenant_code.
- Login returns an Identity JWT + available_tenants list.
- POST /auth/select-tenant upgrades to a Contextual JWT.
"""
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Login (Identity phase)
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    """
    Login request schema.

    H-Fix-01: tenant_code removed.  Login requires ONLY email + password.
    """
    email: EmailStr = Field(..., description="User email")
    password: str = Field(
        ...,
        min_length=8,
        description="User password"
    )

    model_config = {"from_attributes": True}


class TenantInfo(BaseModel):
    """Lightweight tenant descriptor returned after login."""
    id: str = Field(..., description="Tenant (wholesaler) UUID")
    code: str = Field(..., description="Tenant code (e.g., JAMBO01)")
    name: str = Field(..., description="Tenant display name")

    model_config = {"from_attributes": True}


class IdentityTokenData(BaseModel):
    """
    Data returned at login (identity phase).

    The access_token is an *Identity JWT* — it has no tenant context.
    Frontend uses `available_tenants` to show a tenant picker.
    """
    access_token: str = Field(..., description="Identity JWT access token")
    refresh_token: str = Field(..., description="Identity JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    user_id: str = Field(..., description="User UUID")
    roles: List[str] = Field(default_factory=list, description="Aggregated role names")
    available_tenants: List[TenantInfo] = Field(
        default_factory=list,
        description="Tenants this user can access"
    )

    model_config = {"from_attributes": True}


class IdentityLoginResponse(BaseModel):
    """Response for POST /auth/login (identity phase)."""
    success: bool = Field(True, description="Always true for successful login")
    data: IdentityTokenData = Field(..., description="Identity token data")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp"
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Select-Tenant (context phase)
# ---------------------------------------------------------------------------

class SelectTenantRequest(BaseModel):
    """Request to upgrade an Identity JWT to a Contextual JWT."""
    tenant_id: str = Field(..., description="Tenant UUID to switch into")

    model_config = {"from_attributes": True}


class TokenData(BaseModel):
    """
    Token data in contextual login / select-tenant response.
    """
    access_token: str = Field(..., description="Contextual JWT access token")
    refresh_token: str = Field(..., description="Contextual JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    user_id: str = Field(..., description="User UUID")
    tenant_id: str = Field(..., description="Tenant UUID")
    tenant_schema: str = Field(
        ...,
        description="Tenant schema name (e.g., t_abc123...)"
    )
    roles: List[str] = Field(default_factory=list, description="Roles in this tenant")

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    """
    Contextual login response (used by select-tenant and refresh).
    """
    success: bool = Field(True, description="Always true for successful login")
    data: TokenData = Field(..., description="Token data")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp"
    )

    model_config = {"from_attributes": True}


class RefreshTokenRequest(BaseModel):
    """
    Refresh token request schema.
    Implements openapi.yaml RefreshTokenRequest schema.
    """
    refresh_token: str = Field(..., description="Refresh token to exchange")

    model_config = {"from_attributes": True}


class CurrentUserData(BaseModel):
    """
    Current user data in /auth/me response.
    """
    id: str = Field(..., description="User UUID")
    email: EmailStr | None = Field(None, description="User email")
    full_name: str | None = Field(None, description="User full name")

    tenant_id: Optional[str] = Field(None, description="Tenant UUID (None for identity-only)")
    tenant_schema: Optional[str] = Field(None, description="Tenant schema name")
    roles: List[str] = Field(default_factory=list, description="User role names")
    permissions: List[str] = Field(
        default_factory=list,
        description="User permission codes"
    )

    model_config = {"from_attributes": True}


class CurrentUserResponse(BaseModel):
    """
    Current user response schema.
    Implements openapi.yaml CurrentUserResponse schema.
    """
    success: bool = Field(True, description="Always true for successful response")
    data: CurrentUserData = Field(..., description="Current user data")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp"
    )

    model_config = {"from_attributes": True}


class TokenPayload(BaseModel):
    """
    JWT token payload schema (kept for reference; canonical version in core.security).
    """
    user_id: str = Field(..., description="User UUID")
    tenant_id: Optional[str] = Field(None, description="Tenant UUID (None for identity JWT)")
    tenant_schema: Optional[str] = Field(None, description="Tenant schema name")
    roles: List[str] = Field(default_factory=list, description="Role names")
    exp: int | None = Field(None, description="Expiration timestamp")
    type: str = Field(default="access", description="Token type: access or refresh")

    model_config = {"from_attributes": True}
