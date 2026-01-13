"""
Authentication Pydantic schemas.
Implements openapi.yaml auth component schemas.
"""
from typing import List
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """
    Login request schema.
    Implements openapi.yaml LoginRequest schema.
    """
    tenant_code: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Wholesaler code (e.g., ACME01)"
    )
    email: EmailStr = Field(..., description="User email")
    password: str = Field(
        ...,
        min_length=8,
        description="User password"
    )
    
    model_config = {"from_attributes": True}


class TokenData(BaseModel):
    """
    Token data in login response.
    Implements openapi.yaml LoginResponse.data schema.
    """
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    user_id: str = Field(..., description="User UUID")
    tenant_id: str = Field(..., description="Tenant UUID")
    tenant_schema: str = Field(
        ...,
        description="Tenant schema name (e.g., t_abc123...)"
    )
    
    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    """
    Login response schema.
    Implements openapi.yaml LoginResponse schema.
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
    Implements openapi.yaml CurrentUserResponse.data schema.
    """
    id: str = Field(..., description="User UUID")
    email: EmailStr = Field(..., description="User email")
    full_name: str | None = Field(None, description="User full name")
    tenant_id: str = Field(..., description="Tenant UUID")
    tenant_schema: str = Field(..., description="Tenant schema name")
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
    JWT token payload schema.
    Used for encoding/decoding JWT claims.
    
    Per multi_tenancy_spec.md section 4.1, JWT must contain:
    - user_id: UUID
    - tenant_id: UUID
    - tenant_schema: string
    - exp: expiration timestamp
    - type: "access" or "refresh"
    """
    user_id: str = Field(..., description="User UUID")
    tenant_id: str = Field(..., description="Tenant UUID")
    tenant_schema: str = Field(..., description="Tenant schema name")
    exp: int | None = Field(None, description="Expiration timestamp")
    type: str = Field(default="access", description="Token type: access or refresh")
    
    model_config = {"from_attributes": True}
