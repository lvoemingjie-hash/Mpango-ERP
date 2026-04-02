"""
Phase 4 Tests — Wholesaler pricing-safe order creation.

Two test tiers:
  A. Schema-level: structural rejection of client-supplied prices (no DB needed)
  B. API request-level: mock-based tests that exercise the actual endpoint
     functions through controlled AsyncSession mocks (no DB needed)

CTO-required API coverage:
  1. Wholesaler order creation with slim request shape
  2. Missing price → ORDER_VALIDATION_FAILED
  3. Retailer not bound → RETAILER_NOT_BOUND
  4. Pricing list endpoint
  5. Pricing set/update endpoint
"""
import os
import uuid
from collections import namedtuple
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from pydantic import BaseModel

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-minimum-32-characters-long")
os.environ.setdefault("MPANGO_ENV", "test")


# ============================================================================
# Test-local token model (avoids importing core.security which needs full env)
# ============================================================================

class TokenPayload(BaseModel):
    user_id: str
    tenant_id: str
    tenant_schema: str
    exp: Optional[int] = None
    type: str = "access"


def make_token(tenant_id=None, user_id=None):
    return TokenPayload(
        user_id=user_id or str(uuid.uuid4()),
        tenant_id=tenant_id or str(uuid.uuid4()),
        tenant_schema="t_test",
    )


# ============================================================================
# Named-tuple rows returned by mocked db.execute().fetchall() / fetchone()
# ============================================================================

BindingRow = namedtuple("BindingRow", ["id"])

SkuRow = namedtuple("SkuRow", [
    "sku_id", "sku_code", "name", "is_active", "quantity_on_hand", "sell_price",
])

PriceRow = namedtuple("PriceRow", [
    "sku_id", "sku_code", "sku_name", "retailer_id", "price", "updated_at",
])

CountRow = namedtuple("CountRow", ["count"])
IdRow = namedtuple("IdRow", ["id"])


# ============================================================================
# Helpers to build mock db sessions
# ============================================================================

def _mock_result(rows=None, scalar=None, fetchone_val=None):
    """Return a MagicMock that behaves like a SQLAlchemy CursorResult."""
    r = MagicMock()
    if rows is not None:
        r.fetchall.return_value = rows
    if fetchone_val is not None:
        r.fetchone.return_value = fetchone_val
    else:
        r.fetchone.return_value = rows[0] if rows else None
    if scalar is not None:
        r.scalar_one.return_value = scalar
    return r


def _ordered_execute(call_results: list):
    """
    Return an async side_effect that yields successive results per call.
    Each element in call_results should be a MagicMock result.
    """
    it = iter(call_results)

    async def _side_effect(*args, **kwargs):
        return next(it)

    return _side_effect


# ============================================================================
# Mock order + CRUD for create_order happy path
# ============================================================================

class MockOrderItem:
    def __init__(self, product_name, sku_code, quantity, unit_price):
        self.id = uuid.uuid4()
        self.product_name = product_name
        self.sku_code = sku_code
        self.quantity = quantity
        self.unit_price = unit_price
        self.subtotal = Decimal(str(quantity)) * unit_price


class _StatusEnum:
    """Minimal enum-like object with .value for order_to_schema compatibility."""
    def __init__(self, val):
        self.value = val


class MockOrder:
    def __init__(self, wholesaler_id, retailer_id, items, notes=None, created_by=None):
        self.id = uuid.uuid4()
        self.wholesaler_id = wholesaler_id
        self.retailer_id = retailer_id
        self.status = _StatusEnum("draft")
        self.items = items
        self.total_amount = sum(i.subtotal for i in items)
        self.notes = notes
        self.created_by = created_by
        self.updated_by = None
        self.is_deleted = False
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


# ============================================================================
# A. Schema-level tests
# ============================================================================

class TestSchemaRejectsPrice:
    """WholesalerOrderCreateRequest must NOT accept unit_price."""

    def test_schema_rejects_unit_price_field(self):
        from schemas.order import WholesalerOrderItemCreate
        fields = WholesalerOrderItemCreate.model_fields
        assert "unit_price" not in fields, "unit_price must NOT be in wholesaler item schema"
        assert "product_name" not in fields, "product_name must NOT be in wholesaler item schema"

    def test_schema_accepts_only_sku_and_quantity(self):
        from schemas.order import WholesalerOrderItemCreate
        fields = set(WholesalerOrderItemCreate.model_fields.keys())
        assert fields == {"sku_code", "quantity"}

    def test_extra_fields_ignored_or_rejected(self):
        from schemas.order import WholesalerOrderItemCreate
        item = WholesalerOrderItemCreate(sku_code="TEST-SKU", quantity=5)
        assert item.sku_code == "TEST-SKU"
        assert item.quantity == 5
        assert not hasattr(item, "unit_price")

    def test_wholesaler_request_shape(self):
        from schemas.order import WholesalerOrderCreateRequest
        fields = set(WholesalerOrderCreateRequest.model_fields.keys())
        assert fields == {"retailer_id", "items", "notes"}


# ============================================================================
# B. API request-level tests — Wholesaler order creation
# ============================================================================

TENANT_ID = str(uuid.uuid4())
RETAILER_ID = str(uuid.uuid4())
USER_ID = str(uuid.uuid4())
SKU_ID = str(uuid.uuid4())


class TestWholesalerOrderCreationAPI:
    """
    Exercise the actual create_order endpoint function from
    backend/api/v1/orders.py with mocked DB session.
    """

    @pytest.mark.asyncio
    async def test_create_order_slim_shape_happy_path(self):
        """POST /orders with only sku_code+quantity succeeds when DB has binding, SKU, price, stock."""
        from schemas.order import WholesalerOrderCreateRequest, WholesalerOrderItemCreate

        request = WholesalerOrderCreateRequest(
            retailer_id=RETAILER_ID,
            items=[WholesalerOrderItemCreate(sku_code="SKU-001", quantity=3)],
            notes="test order",
        )
        token = make_token(tenant_id=TENANT_ID, user_id=USER_ID)

        # Mock DB: 1) binding found  2) SKU+price+stock resolved
        binding_result = _mock_result(fetchone_val=BindingRow(id=uuid.uuid4()))
        sku_result = _mock_result(rows=[
            SkuRow(
                sku_id=SKU_ID, sku_code="SKU-001", name="Widget A",
                is_active=True, quantity_on_hand=100, sell_price=Decimal("25.50"),
            )
        ])

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=_ordered_execute([binding_result, sku_result]))

        # Mock the CRUD create_order to return a MockOrder
        mock_items = [MockOrderItem("Widget A", "SKU-001", 3, Decimal("25.50"))]
        mock_order = MockOrder(TENANT_ID, RETAILER_ID, mock_items, "test order", USER_ID)

        with patch("api.v1.orders.crud_create_order", new_callable=AsyncMock, return_value=mock_order):
            from api.v1.orders import create_order
            result = await create_order(request=request, token=token, db=mock_db)

        assert result.success is True
        assert result.message == "Order created successfully"
        assert result.data.total_amount == Decimal("76.50")
        assert len(result.data.items) == 1
        assert result.data.items[0].unit_price == Decimal("25.50")
        assert result.data.items[0].product_name == "Widget A"

    @pytest.mark.asyncio
    async def test_missing_price_returns_order_validation_failed(self):
        """POST /orders where SKU has no retailer price → 400 ORDER_VALIDATION_FAILED."""
        from schemas.order import WholesalerOrderCreateRequest, WholesalerOrderItemCreate

        request = WholesalerOrderCreateRequest(
            retailer_id=RETAILER_ID,
            items=[WholesalerOrderItemCreate(sku_code="SKU-NOPR", quantity=2)],
        )
        token = make_token(tenant_id=TENANT_ID, user_id=USER_ID)

        # Mock: binding exists, SKU exists but sell_price is None
        binding_result = _mock_result(fetchone_val=BindingRow(id=uuid.uuid4()))
        sku_result = _mock_result(rows=[
            SkuRow(
                sku_id=str(uuid.uuid4()), sku_code="SKU-NOPR", name="Unpriced Widget",
                is_active=True, quantity_on_hand=50, sell_price=None,
            )
        ])

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=_ordered_execute([binding_result, sku_result]))

        with pytest.raises(HTTPException) as exc_info:
            from api.v1.orders import create_order
            await create_order(request=request, token=token, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail["code"] == "ORDER_VALIDATION_FAILED"
        assert any("No price configured" in e for e in exc_info.value.detail["errors"])

    @pytest.mark.asyncio
    async def test_unbound_retailer_returns_retailer_not_bound(self):
        """POST /orders with unbound retailer → 400 RETAILER_NOT_BOUND."""
        from schemas.order import WholesalerOrderCreateRequest, WholesalerOrderItemCreate

        request = WholesalerOrderCreateRequest(
            retailer_id=str(uuid.uuid4()),
            items=[WholesalerOrderItemCreate(sku_code="SKU-001", quantity=1)],
        )
        token = make_token(tenant_id=TENANT_ID, user_id=USER_ID)

        # Mock: binding NOT found (fetchone returns None)
        no_binding = _mock_result(fetchone_val=None)

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=_ordered_execute([no_binding]))

        with pytest.raises(HTTPException) as exc_info:
            from api.v1.orders import create_order
            await create_order(request=request, token=token, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail["code"] == "RETAILER_NOT_BOUND"

    @pytest.mark.asyncio
    async def test_inactive_sku_returns_validation_failed(self):
        """POST /orders with inactive SKU → 400 ORDER_VALIDATION_FAILED."""
        from schemas.order import WholesalerOrderCreateRequest, WholesalerOrderItemCreate

        request = WholesalerOrderCreateRequest(
            retailer_id=RETAILER_ID,
            items=[WholesalerOrderItemCreate(sku_code="SKU-DEAD", quantity=1)],
        )
        token = make_token(tenant_id=TENANT_ID, user_id=USER_ID)

        binding_result = _mock_result(fetchone_val=BindingRow(id=uuid.uuid4()))
        sku_result = _mock_result(rows=[
            SkuRow(
                sku_id=str(uuid.uuid4()), sku_code="SKU-DEAD", name="Dead Widget",
                is_active=False, quantity_on_hand=10, sell_price=Decimal("10.00"),
            )
        ])

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=_ordered_execute([binding_result, sku_result]))

        with pytest.raises(HTTPException) as exc_info:
            from api.v1.orders import create_order
            await create_order(request=request, token=token, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail["code"] == "ORDER_VALIDATION_FAILED"
        assert any("no longer available" in e for e in exc_info.value.detail["errors"])

    @pytest.mark.asyncio
    async def test_insufficient_stock_returns_validation_failed(self):
        """POST /orders requesting more than available stock → 400 ORDER_VALIDATION_FAILED."""
        from schemas.order import WholesalerOrderCreateRequest, WholesalerOrderItemCreate

        request = WholesalerOrderCreateRequest(
            retailer_id=RETAILER_ID,
            items=[WholesalerOrderItemCreate(sku_code="SKU-LOW", quantity=999)],
        )
        token = make_token(tenant_id=TENANT_ID, user_id=USER_ID)

        binding_result = _mock_result(fetchone_val=BindingRow(id=uuid.uuid4()))
        sku_result = _mock_result(rows=[
            SkuRow(
                sku_id=str(uuid.uuid4()), sku_code="SKU-LOW", name="Low Stock",
                is_active=True, quantity_on_hand=5, sell_price=Decimal("10.00"),
            )
        ])

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=_ordered_execute([binding_result, sku_result]))

        with pytest.raises(HTTPException) as exc_info:
            from api.v1.orders import create_order
            await create_order(request=request, token=token, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail["code"] == "ORDER_VALIDATION_FAILED"
        assert any("Insufficient stock" in e for e in exc_info.value.detail["errors"])

    @pytest.mark.asyncio
    async def test_unknown_sku_returns_validation_failed(self):
        """POST /orders with SKU not found in DB → 400 ORDER_VALIDATION_FAILED."""
        from schemas.order import WholesalerOrderCreateRequest, WholesalerOrderItemCreate

        request = WholesalerOrderCreateRequest(
            retailer_id=RETAILER_ID,
            items=[WholesalerOrderItemCreate(sku_code="SKU-GHOST", quantity=1)],
        )
        token = make_token(tenant_id=TENANT_ID, user_id=USER_ID)

        binding_result = _mock_result(fetchone_val=BindingRow(id=uuid.uuid4()))
        # SKU not in results → empty rows
        sku_result = _mock_result(rows=[], fetchone_val=None)

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=_ordered_execute([binding_result, sku_result]))

        with pytest.raises(HTTPException) as exc_info:
            from api.v1.orders import create_order
            await create_order(request=request, token=token, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail["code"] == "ORDER_VALIDATION_FAILED"
        assert any("not found" in e for e in exc_info.value.detail["errors"])


# ============================================================================
# C. API request-level tests — Pricing list endpoint
# ============================================================================

class TestPricingListAPI:
    """Exercise the list_retailer_prices endpoint with mocked DB."""

    @pytest.mark.asyncio
    async def test_list_prices_happy_path(self):
        """GET /pricing/prices returns prices for a bound retailer."""
        token = make_token(tenant_id=TENANT_ID, user_id=USER_ID)
        retailer_id = RETAILER_ID
        now = datetime.now(timezone.utc)

        # Mock: 1) binding found  2) COUNT(*)  3) price rows
        binding_result = _mock_result(fetchone_val=BindingRow(id=uuid.uuid4()))
        count_result = _mock_result(scalar=2)
        price_rows = _mock_result(rows=[
            PriceRow(sku_id=str(uuid.uuid4()), sku_code="SKU-A", sku_name="Widget A",
                     retailer_id=retailer_id, price=Decimal("25.00"), updated_at=now),
            PriceRow(sku_id=str(uuid.uuid4()), sku_code="SKU-B", sku_name="Widget B",
                     retailer_id=retailer_id, price=Decimal("30.00"), updated_at=now),
        ])

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=_ordered_execute([binding_result, count_result, price_rows])
        )

        from api.v1.pricing import list_retailer_prices
        result = await list_retailer_prices(
            retailer_id=retailer_id, page=1, size=50, token=token, db=mock_db,
        )

        assert result.success is True
        assert result.data.total == 2
        assert len(result.data.items) == 2
        assert result.data.items[0].sku_code == "SKU-A"
        assert result.data.items[1].price == Decimal("30.00")

    @pytest.mark.asyncio
    async def test_list_prices_unbound_retailer_rejected(self):
        """GET /pricing/prices for unbound retailer → 400 RETAILER_NOT_BOUND."""
        token = make_token(tenant_id=TENANT_ID, user_id=USER_ID)

        no_binding = _mock_result(fetchone_val=None)
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=_ordered_execute([no_binding]))

        with pytest.raises(HTTPException) as exc_info:
            from api.v1.pricing import list_retailer_prices
            await list_retailer_prices(
                retailer_id=str(uuid.uuid4()), page=1, size=50,
                token=token, db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail["code"] == "RETAILER_NOT_BOUND"


# ============================================================================
# D. API request-level tests — Pricing set/update endpoint
# ============================================================================

class TestPricingSetAPI:
    """Exercise the set_retailer_price endpoint with mocked DB."""

    @pytest.mark.asyncio
    async def test_set_price_creates_new(self):
        """PUT /pricing/prices creates a new price (action=created)."""
        from api.v1.pricing import SetPriceRequest

        token = make_token(tenant_id=TENANT_ID, user_id=USER_ID)
        sku_id = str(uuid.uuid4())
        request = SetPriceRequest(
            retailer_id=RETAILER_ID, sku_id=sku_id, price=Decimal("42.00"),
        )

        # Mock: 1) binding found  2) SKU exists  3) no existing price  4) set_price call
        binding_result = _mock_result(fetchone_val=BindingRow(id=uuid.uuid4()))
        sku_exists = _mock_result(fetchone_val=IdRow(id=sku_id))
        no_existing_price = _mock_result(fetchone_val=None)

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=_ordered_execute([binding_result, sku_exists, no_existing_price])
        )

        with patch("api.v1.pricing.set_price", new_callable=AsyncMock) as mock_set:
            from api.v1.pricing import set_retailer_price
            result = await set_retailer_price(request=request, token=token, db=mock_db)

        assert result.success is True
        assert result.data.action == "created"
        assert result.data.price == Decimal("42.00")
        mock_set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_price_updates_existing(self):
        """PUT /pricing/prices updates an existing price (action=updated)."""
        from api.v1.pricing import SetPriceRequest

        token = make_token(tenant_id=TENANT_ID, user_id=USER_ID)
        sku_id = str(uuid.uuid4())
        request = SetPriceRequest(
            retailer_id=RETAILER_ID, sku_id=sku_id, price=Decimal("99.00"),
        )

        # Mock: 1) binding  2) SKU exists  3) existing price found
        binding_result = _mock_result(fetchone_val=BindingRow(id=uuid.uuid4()))
        sku_exists = _mock_result(fetchone_val=IdRow(id=sku_id))
        has_existing = _mock_result(fetchone_val=IdRow(id=uuid.uuid4()))

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=_ordered_execute([binding_result, sku_exists, has_existing])
        )

        with patch("api.v1.pricing.set_price", new_callable=AsyncMock) as mock_set:
            from api.v1.pricing import set_retailer_price
            result = await set_retailer_price(request=request, token=token, db=mock_db)

        assert result.success is True
        assert result.data.action == "updated"
        assert result.data.price == Decimal("99.00")

    @pytest.mark.asyncio
    async def test_set_price_unknown_sku_rejected(self):
        """PUT /pricing/prices with unknown SKU → 404 SKU_NOT_FOUND."""
        from api.v1.pricing import SetPriceRequest

        token = make_token(tenant_id=TENANT_ID, user_id=USER_ID)
        request = SetPriceRequest(
            retailer_id=RETAILER_ID,
            sku_id=str(uuid.uuid4()),
            price=Decimal("10.00"),
        )

        binding_result = _mock_result(fetchone_val=BindingRow(id=uuid.uuid4()))
        no_sku = _mock_result(fetchone_val=None)

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=_ordered_execute([binding_result, no_sku])
        )

        with pytest.raises(HTTPException) as exc_info:
            from api.v1.pricing import set_retailer_price
            await set_retailer_price(request=request, token=token, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail["code"] == "SKU_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_set_price_unbound_retailer_rejected(self):
        """PUT /pricing/prices for unbound retailer → 400 RETAILER_NOT_BOUND."""
        from api.v1.pricing import SetPriceRequest

        token = make_token(tenant_id=TENANT_ID, user_id=USER_ID)
        request = SetPriceRequest(
            retailer_id=str(uuid.uuid4()),
            sku_id=str(uuid.uuid4()),
            price=Decimal("10.00"),
        )

        no_binding = _mock_result(fetchone_val=None)
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=_ordered_execute([no_binding]))

        with pytest.raises(HTTPException) as exc_info:
            from api.v1.pricing import set_retailer_price
            await set_retailer_price(request=request, token=token, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail["code"] == "RETAILER_NOT_BOUND"

    def test_set_price_schema_rejects_zero_price(self):
        """SetPriceRequest rejects price=0."""
        from api.v1.pricing import SetPriceRequest
        with pytest.raises(Exception):
            SetPriceRequest(
                retailer_id=str(uuid.uuid4()),
                sku_id=str(uuid.uuid4()),
                price=Decimal("0"),
            )

    def test_set_price_schema_rejects_negative_price(self):
        """SetPriceRequest rejects price < 0."""
        from api.v1.pricing import SetPriceRequest
        with pytest.raises(Exception):
            SetPriceRequest(
                retailer_id=str(uuid.uuid4()),
                sku_id=str(uuid.uuid4()),
                price=Decimal("-5.00"),
            )
