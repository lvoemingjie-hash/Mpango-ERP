"""
Basic tests for Wholesaler CRUD endpoints (test-local implementation).

These tests avoid real DB initialization by using mock objects and
local helper functions, following the pattern in test_orders_api.py.
"""
import uuid
from datetime import datetime, timezone
from math import ceil
from typing import List, Optional
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, status
from pydantic import BaseModel


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


class MockRole:
    """Mock Role model."""

    def __init__(self, name: str, permissions: List[str] = None):
        self.id = uuid.uuid4()
        self.name = name
        self.permissions = [MockPermission(p) for p in (permissions or [])]


class MockUser:
    """Mock User model."""

    def __init__(self, roles: List[MockRole]):
        self.id = uuid.uuid4()
        self.roles = roles


class RequirePermission:
    """Test-local RequirePermission that mirrors actual RBAC logic."""

    def __init__(self, permission: str):
        self.permission = permission

    async def __call__(self, token: TokenPayload, db: AsyncMock, get_user_func) -> TokenPayload:
        user = await get_user_func(db, token.user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "USER_NOT_FOUND", "message": "User not found"},
            )

        user_permissions = set()
        for role in user.roles:
            for perm in role.permissions:
                user_permissions.add(perm.code)

        if self.permission not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": f"Permission '{self.permission}' required",
                },
            )

        return token


class WholesalerCreate(BaseModel):
    code: str
    name: str
    address: Optional[str] = None
    contact: Optional[str] = None
    plan_type: Optional[str] = None


class WholesalerRead(BaseModel):
    id: str
    code: str
    name: str
    address: Optional[str] = None
    contact: Optional[str] = None
    plan_type: Optional[str] = None
    schema_name: str
    created_at: datetime
    updated_at: datetime


class WholesalerResponse(BaseModel):
    success: bool = True
    data: WholesalerRead
    message: Optional[str] = None
    timestamp: datetime


class WholesalerListResponse(BaseModel):
    success: bool = True
    data: dict
    timestamp: datetime


class MockWholesaler:
    def __init__(self, code: str, name: str, address: Optional[str], contact: Optional[str], plan_type: Optional[str]):
        self.id = uuid.uuid4()
        self.code = code
        self.name = name
        self.address = address
        self.contact = contact
        self.plan_type = plan_type
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def get_tenant_schema(self) -> str:
        return f"t_{str(self.id).replace('-', '')}"


def wholesaler_to_read(obj: MockWholesaler) -> WholesalerRead:
    return WholesalerRead(
        id=str(obj.id),
        code=obj.code,
        name=obj.name,
        address=obj.address,
        contact=obj.contact,
        plan_type=obj.plan_type,
        schema_name=obj.get_tenant_schema(),
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


async def create_wholesaler_impl(
    request: WholesalerCreate,
    token: TokenPayload,
    db: AsyncMock,
    auth_check_func,
    storage: List[MockWholesaler],
) -> WholesalerResponse:
    await auth_check_func(token, db)

    if any(w.code == request.code for w in storage):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "WHOLESALER_CODE_EXISTS",
                "message": f"Wholesaler code '{request.code}' already exists",
            },
        )

    created = MockWholesaler(
        code=request.code,
        name=request.name,
        address=request.address,
        contact=request.contact,
        plan_type=request.plan_type,
    )
    storage.append(created)

    return WholesalerResponse(
        success=True,
        data=wholesaler_to_read(created),
        timestamp=datetime.now(timezone.utc),
    )


async def list_wholesalers_impl(
    skip: int,
    limit: int,
    token: TokenPayload,
    db: AsyncMock,
    auth_check_func,
    storage: List[MockWholesaler],
) -> WholesalerListResponse:
    await auth_check_func(token, db)
    total = len(storage)
    pages = ceil(total / limit) if total > 0 else 0

    items = [wholesaler_to_read(w).model_dump() for w in storage[skip : skip + limit]]

    return WholesalerListResponse(
        success=True,
        data={"items": items, "pagination": {"page": 1, "size": limit, "total": total, "pages": pages}},
        timestamp=datetime.now(timezone.utc),
    )


def create_token() -> TokenPayload:
    return TokenPayload(
        user_id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        tenant_schema=f"t_{'a' * 32}",
        type="access",
    )


def create_user_with_permissions(permissions: List[str]) -> MockUser:
    role = MockRole(name="admin", permissions=permissions)
    return MockUser(roles=[role])


async def make_auth_check(permission: str, user: MockUser):
    rbac = RequirePermission(permission)

    async def get_user(db, uid):
        return user

    async def check(token, db):
        return await rbac(token, db, get_user)

    return check


@pytest.mark.asyncio
async def test_create_wholesaler():
    storage: List[MockWholesaler] = []
    token = create_token()
    user = create_user_with_permissions(["wholesalers:write"])
    auth_check = await make_auth_check("wholesalers:write", user)
    db = AsyncMock()

    request = WholesalerCreate(code="ACME01", name="Acme")
    response = await create_wholesaler_impl(request, token, db, auth_check, storage)

    assert response.success is True
    assert response.data.code == "ACME01"
    assert len(storage) == 1


@pytest.mark.asyncio
async def test_get_wholesaler_list():
    storage = [MockWholesaler(code="TENANT1", name="Tenant One", address=None, contact=None, plan_type=None)]
    token = create_token()
    user = create_user_with_permissions(["wholesalers:read"])
    auth_check = await make_auth_check("wholesalers:read", user)
    db = AsyncMock()

    response = await list_wholesalers_impl(0, 100, token, db, auth_check, storage)

    assert response.success is True
    assert response.data["pagination"]["total"] == 1
    assert response.data["items"][0]["code"] == "TENANT1"


@pytest.mark.asyncio
async def test_create_duplicate_code_fails():
    storage: List[MockWholesaler] = [
        MockWholesaler(code="DUP01", name="Dup", address=None, contact=None, plan_type=None)
    ]
    token = create_token()
    user = create_user_with_permissions(["wholesalers:write"])
    auth_check = await make_auth_check("wholesalers:write", user)
    db = AsyncMock()

    request = WholesalerCreate(code="DUP01", name="Duplicate")

    with pytest.raises(HTTPException) as exc_info:
        await create_wholesaler_impl(request, token, db, auth_check, storage)

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
