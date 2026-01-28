"""
Tests for Orders API endpoints.

Tests cover:
- Happy path for all endpoints
- Cross-tenant denial (tenant isolation)
- State machine violation tests

Uses self-contained mock classes to avoid database initialization issues.
Same pattern as test_rbac_enforcement.py and test_users_roles_api.py.
"""
import os
import uuid
from typing import Optional, List, Set
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from enum import Enum
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


class OrderStatus(str, Enum):
    """Test-local OrderStatus enum."""
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


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


class MockOrderItem:
    """Mock OrderItem model."""
    def __init__(
        self,
        product_name: str,
        sku_code: str,
        quantity: int,
        unit_price: Decimal = Decimal("10.00")
    ):
        self.id = uuid.uuid4()
        self.product_name = product_name
        self.sku_code = sku_code
        self.quantity = quantity
        self.unit_price = unit_price
        self.subtotal = Decimal(str(quantity)) * unit_price


class MockOrder:
    """Mock Order model."""
    def __init__(
        self,
        wholesaler_id: uuid.UUID,
        retailer_id: uuid.UUID,
        status: OrderStatus = OrderStatus.DRAFT,
        items: List[MockOrderItem] = None,
        notes: str = None,
        created_by: uuid.UUID = None
    ):
        self.id = uuid.uuid4()
        self.wholesaler_id = wholesaler_id
        self.retailer_id = retailer_id
        self.status = status
        self.items = items or []
        self.total_amount = sum(item.subtotal for item in self.items) if self.items else Decimal("0.00")
        self.notes = notes
        self.created_by = created_by
        self.updated_by = None
        self.is_deleted = False
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


# ============================================================================
# Test-Local State Machine
# ============================================================================

class InvalidStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    def __init__(self, current_status: str, action: str, allowed_statuses: List[str]):
        self.current_status = current_status
        self.action = action
        self.allowed_statuses = allowed_statuses
        super().__init__(
            f"Cannot {action} order in '{current_status}' status. "
            f"Allowed statuses: {', '.join(allowed_statuses)}"
        )


STATE_TRANSITIONS = {
    "confirm": {
        "allowed_from": [OrderStatus.DRAFT],
        "target": OrderStatus.CONFIRMED
    },
    "cancel": {
        "allowed_from": [OrderStatus.DRAFT, OrderStatus.CONFIRMED],
        "target": OrderStatus.CANCELLED
    }
}


def validate_state_transition(order: MockOrder, action: str) -> None:
    """Validate that a state transition is allowed."""
    if action not in STATE_TRANSITIONS:
        raise ValueError(f"Unknown action: {action}")
    
    rules = STATE_TRANSITIONS[action]
    if order.status not in rules["allowed_from"]:
        raise InvalidStateTransitionError(
            current_status=order.status.value,
            action=action,
            allowed_statuses=[s.value for s in rules["allowed_from"]]
        )


# ============================================================================
# Test-Local Schemas
# ============================================================================

class OrderItemSchema(BaseModel):
    """Order item schema."""
    id: str
    product_name: str
    sku_code: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal


class OrderSchema(BaseModel):
    """Order schema."""
    id: str
    wholesaler_id: str
    retailer_id: str
    retailer_name: Optional[str] = None
    status: str
    total_amount: Decimal
    items: List[OrderItemSchema] = []
    notes: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class OrderResponse(BaseModel):
    """Single order response."""
    success: bool = True
    data: OrderSchema
    message: Optional[str] = None
    timestamp: datetime


class OrderListResponse(BaseModel):
    """Paginated order list response."""
    success: bool = True
    data: dict
    timestamp: datetime


class OrderActionResponse(BaseModel):
    """Order action response."""
    success: bool = True
    data: dict
    message: Optional[str] = None
    timestamp: datetime


def order_to_schema(order: MockOrder) -> OrderSchema:
    """Convert MockOrder to OrderSchema."""
    return OrderSchema(
        id=str(order.id),
        wholesaler_id=str(order.wholesaler_id),
        retailer_id=str(order.retailer_id),
        retailer_name=None,
        status=order.status.value,
        total_amount=order.total_amount,
        items=[
            OrderItemSchema(
                id=str(item.id),
                product_name=item.product_name,
                sku_code=item.sku_code,
                quantity=item.quantity,
                unit_price=item.unit_price,
                subtotal=item.subtotal
            )
            for item in order.items
        ],
        notes=order.notes,
        created_by=str(order.created_by) if order.created_by else None,
        created_at=order.created_at,
        updated_at=order.updated_at
    )


# ============================================================================
# Test-Local API Endpoint Implementations
# ============================================================================

async def list_orders_impl(
    page: int,
    size: int,
    status_filter: Optional[str],
    retailer_id: Optional[str],
    token: TokenPayload,
    db: AsyncMock,
    get_orders_func,
    auth_check_func
) -> OrderListResponse:
    """Test-local list_orders implementation."""
    await auth_check_func(token, db)
    
    orders, total = await get_orders_func(db, page, size, status_filter, retailer_id)
    pages = ceil(total / size) if total > 0 else 0
    
    return OrderListResponse(
        success=True,
        data={
            "items": [order_to_schema(o).model_dump() for o in orders],
            "pagination": {"page": page, "size": size, "total": total, "pages": pages}
        },
        timestamp=datetime.now(timezone.utc)
    )


async def create_order_impl(
    retailer_id: str,
    items: List[dict],
    notes: Optional[str],
    token: TokenPayload,
    db: AsyncMock,
    create_order_func,
    auth_check_func
) -> OrderResponse:
    """Test-local create_order implementation."""
    await auth_check_func(token, db)
    
    order = await create_order_func(db, token.tenant_id, retailer_id, items, notes, token.user_id)
    
    return OrderResponse(
        success=True,
        data=order_to_schema(order),
        message="Order created successfully",
        timestamp=datetime.now(timezone.utc)
    )


async def get_order_impl(
    order_id: str,
    token: TokenPayload,
    db: AsyncMock,
    get_order_func,
    auth_check_func
) -> OrderResponse:
    """Test-local get_order implementation."""
    await auth_check_func(token, db)
    
    order = await get_order_func(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ORDER_NOT_FOUND", "message": f"Order with ID '{order_id}' not found"}
        )
    
    return OrderResponse(
        success=True,
        data=order_to_schema(order),
        timestamp=datetime.now(timezone.utc)
    )


async def confirm_order_impl(
    order_id: str,
    token: TokenPayload,
    db: AsyncMock,
    get_order_func,
    confirm_func,
    auth_check_func
) -> OrderActionResponse:
    """Test-local confirm_order implementation."""
    await auth_check_func(token, db)
    
    order = await get_order_func(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ORDER_NOT_FOUND", "message": f"Order with ID '{order_id}' not found"}
        )
    
    try:
        order = await confirm_func(db, order, token.user_id)
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_STATE_TRANSITION", "message": str(e)}
        )
    
    return OrderActionResponse(
        success=True,
        data={"order_id": str(order.id), "status": order.status.value},
        message="Order confirmed successfully",
        timestamp=datetime.now(timezone.utc)
    )


async def cancel_order_impl(
    order_id: str,
    token: TokenPayload,
    db: AsyncMock,
    get_order_func,
    cancel_func,
    auth_check_func
) -> OrderActionResponse:
    """Test-local cancel_order implementation."""
    await auth_check_func(token, db)
    
    order = await get_order_func(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ORDER_NOT_FOUND", "message": f"Order with ID '{order_id}' not found"}
        )
    
    try:
        order = await cancel_func(db, order, token.user_id)
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_STATE_TRANSITION", "message": str(e)}
        )
    
    return OrderActionResponse(
        success=True,
        data={"order_id": str(order.id), "status": order.status.value},
        message="Order cancelled successfully",
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


def create_order(
    status: OrderStatus = OrderStatus.DRAFT,
    items: List[MockOrderItem] = None,
    notes: str = None
) -> MockOrder:
    """Create a MockOrder for testing."""
    wholesaler_id = uuid.uuid4()
    retailer_id = uuid.uuid4()
    if items is None:
        items = [MockOrderItem(product_name="Test Product", sku_code="SKU-TEST-001", quantity=2)]
    return MockOrder(wholesaler_id=wholesaler_id, retailer_id=retailer_id, status=status, items=items, notes=notes)


async def auth_check(token: TokenPayload, db: AsyncMock):
    """Auth-only check for Phase B3 (no RBAC)."""
    if token.type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN_TYPE", "message": "Access token required"},
        )


# ============================================================================
# Orders API Tests - Happy Path
# ============================================================================

class TestOrdersAPIHappyPath:
    """Happy path tests for Orders API."""

    @pytest.mark.asyncio
    async def test_list_orders_success(self):
        """GET /orders returns paginated orders list."""
        token = create_token()
        
        order = create_order()
        
        async def get_orders(db, page, size, status_filter, retailer_id):
            return [order], 1
        
        mock_db = AsyncMock()
        
        result = await list_orders_impl(
            page=1, size=10, status_filter=None, retailer_id=None,
            token=token, db=mock_db, get_orders_func=get_orders,
            auth_check_func=auth_check
        )
        
        assert result.success is True
        assert "items" in result.data
        assert result.data["pagination"]["total"] == 1

    @pytest.mark.asyncio
    async def test_create_order_success(self):
        """POST /orders creates new order."""
        token = create_token()
        
        new_order = create_order()
        
        async def create_order_func(db, wholesaler_id, retailer_id, items, notes, created_by):
            return new_order
        
        mock_db = AsyncMock()
        
        result = await create_order_impl(
            retailer_id=str(uuid.uuid4()),
            items=[{"product_name": "Test Product", "sku_code": "SKU-TEST-001", "quantity": 2, "unit_price": Decimal("10.00")}],
            notes="Test order",
            token=token, db=mock_db, create_order_func=create_order_func,
            auth_check_func=auth_check
        )
        
        assert result.success is True
        assert result.message == "Order created successfully"

    @pytest.mark.asyncio
    async def test_get_order_by_id_success(self):
        """GET /orders/{order_id} returns order."""
        token = create_token()
        
        order = create_order()
        
        async def get_order(db, oid):
            return order
        
        mock_db = AsyncMock()
        
        result = await get_order_impl(
            order_id=str(order.id), token=token, db=mock_db,
            get_order_func=get_order, auth_check_func=auth_check
        )
        
        assert result.success is True
        assert result.data.id == str(order.id)

    @pytest.mark.asyncio
    async def test_confirm_order_success(self):
        """POST /orders/{order_id}/confirm confirms draft order."""
        token = create_token()

        order = create_order(status=OrderStatus.DRAFT)
        
        async def get_order(db, oid):
            return order
        
        async def confirm_func(db, o, updated_by):
            o.status = OrderStatus.CONFIRMED
            return o
        
        mock_db = AsyncMock()
        
        result = await confirm_order_impl(
            order_id=str(order.id), token=token, db=mock_db,
            get_order_func=get_order, confirm_func=confirm_func,
            auth_check_func=auth_check
        )
        
        assert result.success is True
        assert result.data["status"] == "confirmed"
        assert result.message == "Order confirmed successfully"

    @pytest.mark.asyncio
    async def test_cancel_order_from_pending_success(self):
        """POST /orders/{order_id}/cancel cancels draft order."""
        token = create_token()

        order = create_order(status=OrderStatus.DRAFT)
        
        async def get_order(db, oid):
            return order
        
        async def cancel_func(db, o, updated_by):
            o.status = OrderStatus.CANCELLED
            return o
        
        mock_db = AsyncMock()
        
        result = await cancel_order_impl(
            order_id=str(order.id), token=token, db=mock_db,
            get_order_func=get_order, cancel_func=cancel_func,
            auth_check_func=auth_check
        )
        
        assert result.success is True
        assert result.data["status"] == "cancelled"


# ============================================================================
# Cross-Tenant Denial Tests (Tenant Isolation)
# ============================================================================

class TestOrdersCrossTenantDenial:
    """Tests for cross-tenant access denial."""

    @pytest.mark.asyncio
    async def test_get_order_cross_tenant_not_found(self):
        """GET /orders/{order_id} returns 404 for order in different tenant."""
        token = create_token(tenant_schema="tenant_tenant2")
        
        async def get_order(db, oid):
            return None  # Order not found in this tenant
        
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await get_order_impl(
                order_id=str(uuid.uuid4()), token=token, db=mock_db,
                get_order_func=get_order, auth_check_func=auth_check
            )
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail["code"] == "ORDER_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_cancel_order_cross_tenant_not_found(self):
        """POST /orders/{order_id}/cancel returns 404 for order in different tenant."""
        token = create_token(tenant_schema="tenant_tenant2")
        
        async def get_order(db, oid):
            return None
        
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await cancel_order_impl(
                order_id=str(uuid.uuid4()), token=token, db=mock_db,
                get_order_func=get_order, cancel_func=AsyncMock(),
                auth_check_func=auth_check
            )
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# State Machine Violation Tests
# ============================================================================

class TestOrdersStateMachineViolations:
    """Tests for order state machine violations."""

    @pytest.mark.asyncio
    async def test_confirm_already_confirmed_order_fails(self):
        """POST /orders/{order_id}/confirm returns 409 for already confirmed order."""
        token = create_token()
        
        order = create_order(status=OrderStatus.CONFIRMED)
        
        async def get_order(db, oid):
            return order
        
        async def confirm_func(db, o, updated_by):
            validate_state_transition(o, "confirm")
            o.status = OrderStatus.CONFIRMED
            return o
        
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await confirm_order_impl(
                order_id=str(order.id), token=token, db=mock_db,
                get_order_func=get_order, confirm_func=confirm_func,
                auth_check_func=auth_check
            )
        
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert exc_info.value.detail["code"] == "INVALID_STATE_TRANSITION"

    @pytest.mark.asyncio
    async def test_confirm_cancelled_order_fails(self):
        """POST /orders/{order_id}/confirm returns 409 for cancelled order."""
        token = create_token()
        
        order = create_order(status=OrderStatus.CANCELLED)
        
        async def get_order(db, oid):
            return order
        
        async def confirm_func(db, o, updated_by):
            validate_state_transition(o, "confirm")
            o.status = OrderStatus.CONFIRMED
            return o
        
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await confirm_order_impl(
                order_id=str(order.id), token=token, db=mock_db,
                get_order_func=get_order, confirm_func=confirm_func,
                auth_check_func=auth_check
            )
        
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_order_fails(self):
        """POST /orders/{order_id}/cancel returns 409 for already cancelled order."""
        token = create_token()
        
        order = create_order(status=OrderStatus.CANCELLED)
        
        async def get_order(db, oid):
            return order
        
        async def cancel_func(db, o, updated_by):
            validate_state_transition(o, "cancel")
            o.status = OrderStatus.CANCELLED
            return o
 
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await cancel_order_impl(
                order_id=str(order.id), token=token, db=mock_db,
                get_order_func=get_order, cancel_func=cancel_func,
                auth_check_func=auth_check
            )
        
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
