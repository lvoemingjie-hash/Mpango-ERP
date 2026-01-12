"""
User, Role, Permission Pydantic schemas.
Implements openapi.yaml user component schemas.
"""
from typing import List
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from uuid import UUID


# ============================================================================
# User Schemas
# ============================================================================

class UserCreateRequest(BaseModel):
    """
    User creation request.
    Implements openapi.yaml UserCreateRequest schema.
    """
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., min_length=8, description="User password")
    full_name: str | None = Field(
        None,
        max_length=100,
        description="User full name"
    )
    
    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    """
    User update request.
    Implements openapi.yaml UserUpdateRequest schema.
    """
    email: EmailStr | None = Field(None, description="User email")
    full_name: str | None = Field(
        None,
        max_length=100,
        description="User full name"
    )
    is_active: bool | None = Field(None, description="User active status")
    
    model_config = {"from_attributes": True}


class RoleRead(BaseModel):
    """
    Role read schema.
    Implements openapi.yaml Role schema.
    
    NOTE: password_hash is NEVER included in read schemas per requirement 5.3
    """
    id: str = Field(..., description="Role UUID")
    name: str = Field(..., description="Role name")
    description: str | None = Field(None, description="Role description")
    
    model_config = {"from_attributes": True}


class UserRead(BaseModel):
    """
    User read schema.
    Implements openapi.yaml User schema.
    
    CRITICAL: password_hash is NEVER included per requirement 5.3
    """
    id: str = Field(..., description="User UUID")
    email: EmailStr = Field(..., description="User email")
    full_name: str | None = Field(None, description="User full name")
    is_active: bool = Field(..., description="User active status")
    roles: List[RoleRead] = Field(default_factory=list, description="User roles")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    """
    Single user response.
    Implements openapi.yaml UserResponse schema.
    """
    success: bool = Field(True, description="Always true for successful response")
    data: UserRead = Field(..., description="User data")
    message: str | None = Field(None, description="Optional message")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp"
    )
    
    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """
    Paginated user list response.
    Implements openapi.yaml UserListResponse schema.
    """
    success: bool = Field(True, description="Always true for successful response")
    data: dict = Field(
        ...,
        description="Data object with items and pagination"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp"
    )
    
    model_config = {"from_attributes": True}


class AssignRolesRequest(BaseModel):
    """
    Assign roles to user request.
    Implements openapi.yaml AssignRolesRequest schema.
    """
    role_ids: List[str] = Field(
        ...,
        min_length=1,
        description="List of role UUIDs to assign"
    )
    
    model_config = {"from_attributes": True}


# ============================================================================
# Role Schemas
# ============================================================================

class RoleListResponse(BaseModel):
    """
    Role list response.
    Implements openapi.yaml RoleListResponse schema.
    """
    success: bool = Field(True, description="Always true for successful response")
    data: List[RoleRead] = Field(..., description="List of roles")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp"
    )
    
    model_config = {"from_attributes": True}
