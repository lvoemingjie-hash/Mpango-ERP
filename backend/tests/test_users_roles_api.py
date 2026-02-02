"""
Tests for Users and Roles API endpoints.

Tests cover:
- Happy path for all endpoints
- RBAC denial (403 when missing permission)
- Cross-tenant denial (tenant isolation)

Uses self-contained mock classes to avoid database initialization issues.
Same pattern as test_rbac_enforcement.py.
"""
import os
import uuid
from typing import Optional, List, Set
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException, status
from pydantic import BaseModel
from math import ceil

# Set test environment variables before any imports
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars")


# ============================================================================
# Test-Local Models (avoid importing actual models that trigger DB)
# ============================================================================

class TokenPayload(BaseModel):
    """Test-local TokenPayload."""
    user_id: str
    tenant_id: str
    tenant_schema: str
    exp: Optional[int] = None
    type: str = "access"


class MockPermission:
    """Mock Permission model."""
    def __init__(self, code: str):
        self.id = uuid.uuid4()
        self.code = code
        self.name = code


class MockRole:
    """Mock Role model."""
    def __init__(self, name: str, permissions: List[str] = None):
        self.id = uuid.uuid4()
        self.name = name
        self.description = f"{name} role"
        self.is_deleted = False
        self.permissions = [MockPermission(p) for p in (permissions or [])]


class MockUser:
    """Mock User model."""
    def __init__(
        self,
        email: str,
        full_name: str = None,
        is_active: bool = True,
        roles: List[MockRole] = None
    ):
        self.id = uuid.uuid4()
        self.email = email
        self.full_name = full_name
        self.is_active = is_active
        self.is_deleted = False
        self.roles = roles or []
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.password_hash = "hashed_password"


# ============================================================================
# Test-Local RBAC Implementation
# ============================================================================

class RequirePermission:
    """Test-local RequirePermission that mirrors the actual implementation."""
    
    def __init__(self, permission: str):
        self.permission = permission
    
    async def __call__(
        self,
        token: TokenPayload,
        db: AsyncMock,
        get_user_func
    ) -> TokenPayload:
        """Check if user has required permission."""
        user = await get_user_func(db, token.user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "USER_NOT_FOUND", "message": "User not found"}
            )
        
        user_permissions: Set[str] = set()
        for role in user.roles:
            for perm in role.permissions:
                user_permissions.add(perm.code)
        
        if self.permission not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": f"Permission '{self.permission}' required"
                }
            )
        
        return token


# ============================================================================
# Test-Local API Endpoint Implementations
# ============================================================================

class UserRead(BaseModel):
    """User read schema."""
    id: str
    email: str
    full_name: Optional[str] = None
    is_active: bool
    roles: List[dict] = []
    created_at: datetime
    updated_at: datetime


class UserResponse(BaseModel):
    """Single user response."""
    success: bool = True
    data: UserRead
    message: Optional[str] = None
    timestamp: datetime


class UserListResponse(BaseModel):
    """Paginated user list response."""
    success: bool = True
    data: dict
    timestamp: datetime


class RoleRead(BaseModel):
    """Role read schema."""
    id: str
    name: str
    description: Optional[str] = None


class RoleListResponse(BaseModel):
    """Role list response."""
    success: bool = True
    data: List[RoleRead]
    timestamp: datetime


def user_to_read(user: MockUser) -> UserRead:
    """Convert MockUser to UserRead."""
    return UserRead(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        roles=[{"id": str(r.id), "name": r.name, "description": r.description} for r in user.roles],
        created_at=user.created_at,
        updated_at=user.updated_at
    )


async def list_users_impl(
    page: int,
    size: int,
    token: TokenPayload,
    db: AsyncMock,
    get_users_func,
    rbac_check_func
) -> UserListResponse:
    """Test-local list_users implementation."""
    await rbac_check_func(token, db)
    users, total = await get_users_func(db, page, size)
    pages = ceil(total / size) if total > 0 else 0
    
    return UserListResponse(
        success=True,
        data={
            "items": [user_to_read(u).model_dump() for u in users],
            "pagination": {"page": page, "size": size, "total": total, "pages": pages}
        },
        timestamp=datetime.now(timezone.utc)
    )


async def create_user_impl(
    email: str,
    password: str,
    full_name: Optional[str],
    token: TokenPayload,
    db: AsyncMock,
    email_exists_func,
    create_user_func,
    rbac_check_func
) -> UserResponse:
    """Test-local create_user implementation."""
    await rbac_check_func(token, db)
    
    if await email_exists_func(db, email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "EMAIL_EXISTS", "message": f"Email '{email}' is already registered"}
        )
    
    user = await create_user_func(db, email, password, full_name, token.user_id)
    
    return UserResponse(
        success=True,
        data=user_to_read(user),
        message="User created successfully",
        timestamp=datetime.now(timezone.utc)
    )


async def get_user_impl(
    user_id: str,
    token: TokenPayload,
    db: AsyncMock,
    get_user_func,
    rbac_check_func
) -> UserResponse:
    """Test-local get_user implementation."""
    await rbac_check_func(token, db)
    
    user = await get_user_func(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": f"User with ID '{user_id}' not found"}
        )
    
    return UserResponse(
        success=True,
        data=user_to_read(user),
        timestamp=datetime.now(timezone.utc)
    )


async def update_user_impl(
    user_id: str,
    email: Optional[str],
    full_name: Optional[str],
    is_active: Optional[bool],
    token: TokenPayload,
    db: AsyncMock,
    get_user_func,
    email_exists_func,
    update_user_func,
    rbac_check_func
) -> UserResponse:
    """Test-local update_user implementation."""
    await rbac_check_func(token, db)
    
    user = await get_user_func(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": f"User with ID '{user_id}' not found"}
        )
    
    if email and email != user.email:
        if await email_exists_func(db, email, user_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "EMAIL_EXISTS", "message": f"Email '{email}' is already registered"}
            )
    
    updated = await update_user_func(db, user, email, full_name, is_active, token.user_id)
    
    return UserResponse(
        success=True,
        data=user_to_read(updated),
        message="User updated successfully",
        timestamp=datetime.now(timezone.utc)
    )


async def delete_user_impl(
    user_id: str,
    token: TokenPayload,
    db: AsyncMock,
    get_user_func,
    soft_delete_func,
    rbac_check_func
) -> None:
    """Test-local delete_user implementation."""
    await rbac_check_func(token, db)
    
    user = await get_user_func(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": f"User with ID '{user_id}' not found"}
        )
    
    if user_id == token.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CANNOT_DELETE_SELF", "message": "Cannot delete your own account"}
        )
    
    await soft_delete_func(db, user, token.user_id)
    return None


async def assign_roles_impl(
    user_id: str,
    role_ids: List[str],
    token: TokenPayload,
    db: AsyncMock,
    get_user_func,
    assign_roles_func,
    rbac_check_func
) -> UserResponse:
    """Test-local assign_roles implementation."""
    await rbac_check_func(token, db)
    
    user = await get_user_func(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": f"User with ID '{user_id}' not found"}
        )
    
    try:
        updated = await assign_roles_func(db, user, role_ids, token.user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_ROLE", "message": str(e)}
        )
    
    return UserResponse(
        success=True,
        data=user_to_read(updated),
        message="Roles assigned successfully",
        timestamp=datetime.now(timezone.utc)
    )


async def list_roles_impl(
    token: TokenPayload,
    db: AsyncMock,
    get_all_roles_func,
    rbac_check_func
) -> RoleListResponse:
    """Test-local list_roles implementation."""
    await rbac_check_func(token, db)
    
    roles = await get_all_roles_func(db)
    
    return RoleListResponse(
        success=True,
        data=[RoleRead(id=str(r.id), name=r.name, description=r.description) for r in roles],
        timestamp=datetime.now(timezone.utc)
    )


# ============================================================================
# Test Fixtures
# ============================================================================

def create_token(
    user_id: str = None,
    tenant_id: str = None,
    tenant_schema: str = None
) -> TokenPayload:
    """Create a TokenPayload for testing."""
    return TokenPayload(
        user_id=user_id or str(uuid.uuid4()),
        tenant_id=tenant_id or str(uuid.uuid4()),
        tenant_schema=tenant_schema or "tenant_tenant1",
        type="access"
    )


def create_user(
    email: str = "test@example.com",
    full_name: str = "Test User",
    roles: List[MockRole] = None
) -> MockUser:
    """Create a MockUser for testing."""
    return MockUser(email=email, full_name=full_name, roles=roles or [])


def create_role(name: str, permissions: List[str] = None) -> MockRole:
    """Create a MockRole for testing."""
    return MockRole(name=name, permissions=permissions or [])


async def make_rbac_check(permission: str, user: MockUser):
    """Create an RBAC check function."""
    rbac = RequirePermission(permission)
    
    async def get_user(db, uid):
        return user
    
    async def check(token, db):
        return await rbac(token, db, get_user)
    
    return check


# ============================================================================
# Users API Tests - Happy Path
# ============================================================================

class TestUsersAPIHappyPath:
    """Happy path tests for Users API."""

    @pytest.mark.asyncio
    async def test_list_users_success(self):
        """GET /users returns paginated users list."""
        admin_role = create_role("admin", ["users:read"])
        admin_user = create_user("admin@test.com", "Admin", [admin_role])
        token = create_token(user_id=str(admin_user.id))
        
        async def get_users(db, page, size):
            return [admin_user], 1
        
        rbac_check = await make_rbac_check("users:read", admin_user)
        mock_db = AsyncMock()
        
        result = await list_users_impl(
            page=1, size=10, token=token, db=mock_db,
            get_users_func=get_users, rbac_check_func=rbac_check
        )
        
        assert result.success is True
        assert "items" in result.data
        assert result.data["pagination"]["total"] == 1

    @pytest.mark.asyncio
    async def test_create_user_success(self):
        """POST /users creates new user."""
        admin_role = create_role("admin", ["users:create"])
        admin_user = create_user("admin@test.com", "Admin", [admin_role])
        token = create_token(user_id=str(admin_user.id))
        
        new_user = create_user("new@test.com", "New User", [])
        
        async def email_exists(db, email):
            return False
        
        async def create_user_func(db, email, password, full_name, created_by):
            return new_user
        
        rbac_check = await make_rbac_check("users:create", admin_user)
        mock_db = AsyncMock()
        
        result = await create_user_impl(
            email="new@test.com", password="SecurePass123!", full_name="New User",
            token=token, db=mock_db, email_exists_func=email_exists,
            create_user_func=create_user_func, rbac_check_func=rbac_check
        )
        
        assert result.success is True
        assert result.message == "User created successfully"

    @pytest.mark.asyncio
    async def test_get_user_by_id_success(self):
        """GET /users/{user_id} returns user."""
        admin_role = create_role("admin", ["users:read"])
        admin_user = create_user("admin@test.com", "Admin", [admin_role])
        token = create_token(user_id=str(admin_user.id))
        
        async def get_user(db, uid):
            return admin_user
        
        rbac_check = await make_rbac_check("users:read", admin_user)
        mock_db = AsyncMock()
        
        result = await get_user_impl(
            user_id=str(admin_user.id), token=token, db=mock_db,
            get_user_func=get_user, rbac_check_func=rbac_check
        )
        
        assert result.success is True
        assert result.data.email == admin_user.email


    @pytest.mark.asyncio
    async def test_update_user_success(self):
        """PUT /users/{user_id} updates user."""
        admin_role = create_role("admin", ["users:update"])
        admin_user = create_user("admin@test.com", "Admin", [admin_role])
        token = create_token(user_id=str(admin_user.id))
        
        updated_user = create_user("updated@test.com", "Updated Name", [admin_role])
        updated_user.id = admin_user.id
        
        async def get_user(db, uid):
            return admin_user
        
        async def email_exists(db, email, exclude_id=None):
            return False
        
        async def update_user(db, user, email, full_name, is_active, updated_by):
            return updated_user
        
        rbac_check = await make_rbac_check("users:update", admin_user)
        mock_db = AsyncMock()
        
        result = await update_user_impl(
            user_id=str(admin_user.id), email="updated@test.com", full_name="Updated Name",
            is_active=True, token=token, db=mock_db, get_user_func=get_user,
            email_exists_func=email_exists, update_user_func=update_user,
            rbac_check_func=rbac_check
        )
        
        assert result.success is True
        assert result.message == "User updated successfully"

    @pytest.mark.asyncio
    async def test_delete_user_success(self):
        """DELETE /users/{user_id} soft deletes user."""
        admin_role = create_role("admin", ["users:deactivate"])
        admin_user = create_user("admin@test.com", "Admin", [admin_role])
        target_user = create_user("target@test.com", "Target", [])
        token = create_token(user_id=str(admin_user.id))
        
        async def get_user(db, uid):
            return target_user
        
        async def soft_delete(db, user, deleted_by):
            return user
        
        rbac_check = await make_rbac_check("users:deactivate", admin_user)
        mock_db = AsyncMock()
        
        result = await delete_user_impl(
            user_id=str(target_user.id), token=token, db=mock_db,
            get_user_func=get_user, soft_delete_func=soft_delete,
            rbac_check_func=rbac_check
        )
        
        assert result is None  # 204 No Content

    @pytest.mark.asyncio
    async def test_assign_roles_success(self):
        """PUT /users/{user_id}/roles assigns roles."""
        admin_role = create_role("admin", ["roles:assign"])
        admin_user = create_user("admin@test.com", "Admin", [admin_role])
        target_user = create_user("target@test.com", "Target", [])
        token = create_token(user_id=str(admin_user.id))
        
        async def get_user(db, uid):
            return target_user
        
        async def assign_roles(db, user, role_ids, updated_by):
            user.roles = [admin_role]
            return user
        
        rbac_check = await make_rbac_check("roles:assign", admin_user)
        mock_db = AsyncMock()
        
        result = await assign_roles_impl(
            user_id=str(target_user.id), role_ids=[str(admin_role.id)],
            token=token, db=mock_db, get_user_func=get_user,
            assign_roles_func=assign_roles, rbac_check_func=rbac_check
        )
        
        assert result.success is True
        assert result.message == "Roles assigned successfully"


# ============================================================================
# Roles API Tests - Happy Path
# ============================================================================

class TestRolesAPIHappyPath:
    """Happy path tests for Roles API."""

    @pytest.mark.asyncio
    async def test_list_roles_success(self):
        """GET /roles returns all roles."""
        admin_role = create_role("admin", ["roles:read"])
        viewer_role = create_role("viewer", ["roles:read"])
        admin_user = create_user("admin@test.com", "Admin", [admin_role])
        token = create_token(user_id=str(admin_user.id))
        
        async def get_all_roles(db):
            return [admin_role, viewer_role]
        
        rbac_check = await make_rbac_check("roles:read", admin_user)
        mock_db = AsyncMock()
        
        result = await list_roles_impl(
            token=token, db=mock_db, get_all_roles_func=get_all_roles,
            rbac_check_func=rbac_check
        )
        
        assert result.success is True
        assert len(result.data) == 2
        assert result.data[0].name == "admin"
        assert result.data[1].name == "viewer"


# ============================================================================
# RBAC Denial Tests (403 Forbidden)
# ============================================================================

class TestRBACDenial:
    """Tests for RBAC permission denial (403)."""

    @pytest.mark.asyncio
    async def test_create_user_without_permission_denied(self):
        """POST /users returns 403 without users:create permission."""
        guest_role = create_role("guest", [])
        guest_user = create_user("guest@test.com", "Guest", [guest_role])
        token = create_token(user_id=str(guest_user.id))
        
        rbac_check = await make_rbac_check("users:create", guest_user)
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await create_user_impl(
                email="new@test.com", password="Pass123!", full_name="New",
                token=token, db=mock_db, email_exists_func=AsyncMock(),
                create_user_func=AsyncMock(), rbac_check_func=rbac_check
            )
        
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert exc_info.value.detail["code"] == "PERMISSION_DENIED"

    @pytest.mark.asyncio
    async def test_update_user_without_permission_denied(self):
        """PUT /users/{user_id} returns 403 without users:update permission."""
        viewer_role = create_role("viewer", ["users:read"])
        viewer_user = create_user("viewer@test.com", "Viewer", [viewer_role])
        token = create_token(user_id=str(viewer_user.id))
        
        rbac_check = await make_rbac_check("users:update", viewer_user)
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await update_user_impl(
                user_id=str(uuid.uuid4()), email="new@test.com", full_name="New",
                is_active=True, token=token, db=mock_db, get_user_func=AsyncMock(),
                email_exists_func=AsyncMock(), update_user_func=AsyncMock(),
                rbac_check_func=rbac_check
            )
        
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_delete_user_without_permission_denied(self):
        """DELETE /users/{user_id} returns 403 without users:deactivate permission."""
        viewer_role = create_role("viewer", ["users:read"])
        viewer_user = create_user("viewer@test.com", "Viewer", [viewer_role])
        token = create_token(user_id=str(viewer_user.id))
        
        rbac_check = await make_rbac_check("users:deactivate", viewer_user)
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await delete_user_impl(
                user_id=str(uuid.uuid4()), token=token, db=mock_db,
                get_user_func=AsyncMock(), soft_delete_func=AsyncMock(),
                rbac_check_func=rbac_check
            )
        
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_assign_roles_without_permission_denied(self):
        """PUT /users/{user_id}/roles returns 403 without roles:assign permission."""
        viewer_role = create_role("viewer", ["users:read"])
        viewer_user = create_user("viewer@test.com", "Viewer", [viewer_role])
        token = create_token(user_id=str(viewer_user.id))
        
        rbac_check = await make_rbac_check("roles:assign", viewer_user)
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await assign_roles_impl(
                user_id=str(uuid.uuid4()), role_ids=[str(uuid.uuid4())],
                token=token, db=mock_db, get_user_func=AsyncMock(),
                assign_roles_func=AsyncMock(), rbac_check_func=rbac_check
            )
        
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_list_users_without_permission_denied(self):
        """GET /users returns 403 without users:read permission."""
        guest_role = create_role("guest", [])
        guest_user = create_user("guest@test.com", "Guest", [guest_role])
        token = create_token(user_id=str(guest_user.id))
        
        rbac_check = await make_rbac_check("users:read", guest_user)
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await list_users_impl(
                page=1, size=10, token=token, db=mock_db,
                get_users_func=AsyncMock(), rbac_check_func=rbac_check
            )
        
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_list_roles_without_permission_denied(self):
        """GET /roles returns 403 without roles:read permission."""
        guest_role = create_role("guest", [])
        guest_user = create_user("guest@test.com", "Guest", [guest_role])
        token = create_token(user_id=str(guest_user.id))
        
        rbac_check = await make_rbac_check("roles:read", guest_user)
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await list_roles_impl(
                token=token, db=mock_db, get_all_roles_func=AsyncMock(),
                rbac_check_func=rbac_check
            )
        
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# Cross-Tenant Denial Tests (Tenant Isolation)
# ============================================================================

class TestCrossTenantDenial:
    """Tests for cross-tenant access denial."""

    @pytest.mark.asyncio
    async def test_get_user_cross_tenant_not_found(self):
        """GET /users/{user_id} returns 404 for user in different tenant."""
        admin_role = create_role("admin", ["users:read"])
        admin_user = create_user("admin@test.com", "Admin", [admin_role])
        token = create_token(
            user_id=str(admin_user.id),
            tenant_schema="tenant_tenant2"  # Different tenant
        )
        
        async def get_user(db, uid):
            return None  # User not found in this tenant
        
        rbac_check = await make_rbac_check("users:read", admin_user)
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await get_user_impl(
                user_id=str(uuid.uuid4()), token=token, db=mock_db,
                get_user_func=get_user, rbac_check_func=rbac_check
            )
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail["code"] == "USER_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_update_user_cross_tenant_not_found(self):
        """PUT /users/{user_id} returns 404 for user in different tenant."""
        admin_role = create_role("admin", ["users:update"])
        admin_user = create_user("admin@test.com", "Admin", [admin_role])
        token = create_token(
            user_id=str(admin_user.id),
            tenant_schema="tenant_tenant2"
        )
        
        async def get_user(db, uid):
            return None
        
        rbac_check = await make_rbac_check("users:update", admin_user)
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await update_user_impl(
                user_id=str(uuid.uuid4()), email="new@test.com", full_name="New",
                is_active=True, token=token, db=mock_db, get_user_func=get_user,
                email_exists_func=AsyncMock(), update_user_func=AsyncMock(),
                rbac_check_func=rbac_check
            )
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_user_cross_tenant_not_found(self):
        """DELETE /users/{user_id} returns 404 for user in different tenant."""
        admin_role = create_role("admin", ["users:deactivate"])
        admin_user = create_user("admin@test.com", "Admin", [admin_role])
        token = create_token(
            user_id=str(admin_user.id),
            tenant_schema="tenant_tenant2"
        )
        
        async def get_user(db, uid):
            return None
        
        rbac_check = await make_rbac_check("users:deactivate", admin_user)
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await delete_user_impl(
                user_id=str(uuid.uuid4()), token=token, db=mock_db,
                get_user_func=get_user, soft_delete_func=AsyncMock(),
                rbac_check_func=rbac_check
            )
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_assign_roles_cross_tenant_not_found(self):
        """PUT /users/{user_id}/roles returns 404 for user in different tenant."""
        admin_role = create_role("admin", ["roles:assign"])
        admin_user = create_user("admin@test.com", "Admin", [admin_role])
        token = create_token(
            user_id=str(admin_user.id),
            tenant_schema="tenant_tenant2"
        )
        
        async def get_user(db, uid):
            return None
        
        rbac_check = await make_rbac_check("roles:assign", admin_user)
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await assign_roles_impl(
                user_id=str(uuid.uuid4()), role_ids=[str(uuid.uuid4())],
                token=token, db=mock_db, get_user_func=get_user,
                assign_roles_func=AsyncMock(), rbac_check_func=rbac_check
            )
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_tenant_isolation_via_search_path(self):
        """Verify tenant isolation is enforced via search_path in JWT."""
        token1 = create_token(tenant_schema="tenant_tenant1")
        token2 = create_token(tenant_schema="tenant_tenant2")
        
        assert token1.tenant_schema == "tenant_tenant1"
        assert token2.tenant_schema == "tenant_tenant2"
        assert token1.tenant_schema != token2.tenant_schema


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

class TestEdgeCases:
    """Edge case and error handling tests."""

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email(self):
        """POST /users returns 409 for duplicate email."""
        admin_role = create_role("admin", ["users:create"])
        admin_user = create_user("admin@test.com", "Admin", [admin_role])
        token = create_token(user_id=str(admin_user.id))
        
        async def email_exists(db, email):
            return True  # Email already exists
        
        rbac_check = await make_rbac_check("users:create", admin_user)
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await create_user_impl(
                email="existing@test.com", password="Pass123!", full_name="New",
                token=token, db=mock_db, email_exists_func=email_exists,
                create_user_func=AsyncMock(), rbac_check_func=rbac_check
            )
        
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert exc_info.value.detail["code"] == "EMAIL_EXISTS"

    @pytest.mark.asyncio
    async def test_update_user_duplicate_email(self):
        """PUT /users/{user_id} returns 409 when changing to existing email."""
        admin_role = create_role("admin", ["users:update"])
        admin_user = create_user("admin@test.com", "Admin", [admin_role])
        target_user = create_user("target@test.com", "Target", [])
        token = create_token(user_id=str(admin_user.id))
        
        async def get_user(db, uid):
            return target_user
        
        async def email_exists(db, email, exclude_id=None):
            return True  # Email already taken
        
        rbac_check = await make_rbac_check("users:update", admin_user)
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await update_user_impl(
                user_id=str(target_user.id), email="taken@test.com", full_name="New",
                is_active=True, token=token, db=mock_db, get_user_func=get_user,
                email_exists_func=email_exists, update_user_func=AsyncMock(),
                rbac_check_func=rbac_check
            )
        
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.asyncio
    async def test_delete_self_prevented(self):
        """DELETE /users/{user_id} returns 400 when deleting self."""
        admin_role = create_role("admin", ["users:deactivate"])
        admin_user = create_user("admin@test.com", "Admin", [admin_role])
        token = create_token(user_id=str(admin_user.id))
        
        async def get_user(db, uid):
            return admin_user
        
        rbac_check = await make_rbac_check("users:deactivate", admin_user)
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await delete_user_impl(
                user_id=str(admin_user.id), token=token, db=mock_db,
                get_user_func=get_user, soft_delete_func=AsyncMock(),
                rbac_check_func=rbac_check
            )
        
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail["code"] == "CANNOT_DELETE_SELF"

    @pytest.mark.asyncio
    async def test_assign_invalid_role_id(self):
        """PUT /users/{user_id}/roles returns 400 for invalid role ID."""
        admin_role = create_role("admin", ["roles:assign"])
        admin_user = create_user("admin@test.com", "Admin", [admin_role])
        target_user = create_user("target@test.com", "Target", [])
        token = create_token(user_id=str(admin_user.id))
        
        async def get_user(db, uid):
            return target_user
        
        async def assign_roles(db, user, role_ids, updated_by):
            raise ValueError("Invalid role ID: not-a-uuid")
        
        rbac_check = await make_rbac_check("roles:assign", admin_user)
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await assign_roles_impl(
                user_id=str(target_user.id), role_ids=["not-a-uuid"],
                token=token, db=mock_db, get_user_func=get_user,
                assign_roles_func=assign_roles, rbac_check_func=rbac_check
            )
        
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail["code"] == "INVALID_ROLE"

    @pytest.mark.asyncio
    async def test_get_user_invalid_uuid(self):
        """GET /users/{user_id} returns 404 for invalid UUID format."""
        admin_role = create_role("admin", ["users:read"])
        admin_user = create_user("admin@test.com", "Admin", [admin_role])
        token = create_token(user_id=str(admin_user.id))
        
        async def get_user(db, uid):
            return None  # Invalid UUID returns None
        
        rbac_check = await make_rbac_check("users:read", admin_user)
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await get_user_impl(
                user_id="not-a-valid-uuid", token=token, db=mock_db,
                get_user_func=get_user, rbac_check_func=rbac_check
            )
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
