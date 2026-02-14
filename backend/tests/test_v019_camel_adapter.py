"""
v0.1.9: CamelModel Adapter Round-Trip Tests.

WHY THIS IS HARDENING:
    Proves that CamelModel accepts camelCase input while serializing
    to snake_case output (no behavior change). This is the foundation
    for future camelCase API adoption.

Tests:
    1. snake_case input → snake_case output (backward compat)
    2. camelCase input → snake_case output (new capability)
    3. All Read schemas accept both formats
    4. Response wrappers remain unaffected
"""
import pytest
from datetime import datetime
from decimal import Decimal

from schemas.base import CamelModel
from schemas.wholesaler import WholesalerRead
from schemas.payment import PaymentData, PaymentMethod, PaymentStatus
from schemas.order import Order, OrderItem, OrderStatus
from schemas.user import UserRead, RoleRead
from schemas.sku import SKURead
from schemas.inventory import StockViewRead
from schemas.invitation import InvitationData, InvitationLookupData
from schemas.retailer import RetailerData, BindingData


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
NOW = datetime(2026, 2, 14, 9, 0, 0)

WHOLESALER_SNAKE = {
    "id": "abc-123",
    "code": "TENANT1",
    "name": "Test Wholesaler",
    "address": "123 St",
    "contact": "+1234",
    "plan_type": "premium",
    "schema_name": "t_abc123",
    "created_at": NOW,
    "updated_at": NOW,
}

WHOLESALER_CAMEL = {
    "id": "abc-123",
    "code": "TENANT1",
    "name": "Test Wholesaler",
    "address": "123 St",
    "contact": "+1234",
    "planType": "premium",
    "schemaName": "t_abc123",
    "createdAt": NOW,
    "updatedAt": NOW,
}


# ---------------------------------------------------------------------------
# 1. CamelModel Base Class
# ---------------------------------------------------------------------------
class TestCamelModelBase:
    """Verify CamelModel infrastructure."""

    def test_camel_model_accepts_snake_case(self):
        """CamelModel accepts snake_case field names."""
        obj = WholesalerRead(**WHOLESALER_SNAKE)
        assert obj.plan_type == "premium"
        assert obj.schema_name == "t_abc123"

    def test_camel_model_accepts_camel_case(self):
        """CamelModel accepts camelCase validation aliases."""
        obj = WholesalerRead(**WHOLESALER_CAMEL)
        assert obj.plan_type == "premium"
        assert obj.schema_name == "t_abc123"

    def test_serialization_stays_snake_case(self):
        """model_dump() output stays snake_case (no behavior change)."""
        obj = WholesalerRead(**WHOLESALER_CAMEL)
        data = obj.model_dump()
        assert "plan_type" in data
        assert "schema_name" in data
        assert "planType" not in data
        assert "schemaName" not in data

    def test_json_serialization_stays_snake_case(self):
        """model_dump(mode='json') output stays snake_case."""
        obj = WholesalerRead(**WHOLESALER_SNAKE)
        data = obj.model_dump(mode="json")
        assert "plan_type" in data
        assert "created_at" in data
        assert "planType" not in data
        assert "createdAt" not in data

    def test_round_trip_snake_to_camel_to_snake(self):
        """Full round-trip: snake → model → dump(snake) → model → verify."""
        obj1 = WholesalerRead(**WHOLESALER_SNAKE)
        dumped = obj1.model_dump()
        obj2 = WholesalerRead(**dumped)
        assert obj2.plan_type == obj1.plan_type
        assert obj2.schema_name == obj1.schema_name
        assert obj2.created_at == obj1.created_at

    def test_round_trip_camel_to_snake(self):
        """Round-trip: camelCase input → snake_case dump → reconstruct."""
        obj1 = WholesalerRead(**WHOLESALER_CAMEL)
        dumped = obj1.model_dump()
        obj2 = WholesalerRead(**dumped)
        assert obj2.plan_type == "premium"
        assert obj2.schema_name == "t_abc123"


# ---------------------------------------------------------------------------
# 2. Per-Schema Acceptance Tests (camelCase input)
# ---------------------------------------------------------------------------
class TestPaymentDataCamelAdapter:
    def test_accepts_camel_case(self):
        obj = PaymentData(
            id="p-1",
            orderId="o-1",
            retailerId="r-1",
            transactionId=None,
            amount=Decimal("100.00"),
            method=PaymentMethod.cash,
            status=PaymentStatus.completed,
            createdAt=NOW,
            updatedAt=NOW,
        )
        assert obj.order_id == "o-1"
        assert obj.retailer_id == "r-1"
        dump = obj.model_dump()
        assert "order_id" in dump
        assert "orderId" not in dump


class TestOrderCamelAdapter:
    def test_order_item_accepts_camel(self):
        item = OrderItem(
            id="i-1",
            productName="Widget",
            skuCode="SKU-001",
            quantity=5,
            unitPrice=Decimal("10.00"),
            subtotal=Decimal("50.00"),
        )
        assert item.product_name == "Widget"
        assert item.sku_code == "SKU-001"

    def test_order_accepts_camel(self):
        order = Order(
            id="ord-1",
            wholesalerId="w-1",
            retailerId="r-1",
            retailerName="Test Retailer",
            status=OrderStatus.DRAFT,
            totalAmount=Decimal("100.00"),
            items=[],
            notes=None,
            createdBy="u-1",
            createdAt=NOW,
            updatedAt=NOW,
        )
        assert order.wholesaler_id == "w-1"
        assert order.total_amount == Decimal("100.00")
        dump = order.model_dump()
        assert "wholesaler_id" in dump
        assert "total_amount" in dump


class TestUserCamelAdapter:
    def test_user_read_accepts_camel(self):
        user = UserRead(
            id="u-1",
            email="test@example.com",
            fullName="John Doe",
            isActive=True,
            roles=[],
            createdAt=NOW,
            updatedAt=NOW,
        )
        assert user.full_name == "John Doe"
        assert user.is_active is True

    def test_role_read_accepts_camel(self):
        role = RoleRead(id="r-1", name="admin", description="Admin role")
        assert role.name == "admin"


class TestSKUCamelAdapter:
    def test_sku_read_accepts_camel(self):
        sku = SKURead(
            id="s-1",
            skuCode="SKU-001",
            name="Widget",
            unit="pcs",
            isActive=True,
            createdAt=NOW,
            updatedAt=NOW,
        )
        assert sku.sku_code == "SKU-001"
        assert sku.is_active is True
        dump = sku.model_dump()
        assert "sku_code" in dump


class TestStockViewCamelAdapter:
    def test_stock_view_accepts_camel(self):
        sv = StockViewRead(
            skuId="s-1",
            skuCode="SKU-001",
            skuName="Widget",
            quantityOnHand=Decimal("100"),
            quantityReserved=Decimal("20"),
            quantityAvailable=Decimal("80"),
            updatedAt=NOW,
        )
        assert sv.quantity_on_hand == Decimal("100")
        dump = sv.model_dump()
        assert "quantity_on_hand" in dump


class TestInvitationCamelAdapter:
    def test_invitation_data_accepts_camel(self):
        inv = InvitationData(
            code="INV-001",
            status="active",
            wholesalerId="w-1",
            retailerPhone="+123",
            expiresAt=NOW,
            createdAt=NOW,
        )
        assert inv.wholesaler_id == "w-1"
        assert inv.retailer_phone == "+123"

    def test_invitation_lookup_accepts_camel(self):
        lookup = InvitationLookupData(
            code="INV-001",
            usable=True,
            wholesalerId="w-1",
            wholesalerName="Test WS",
            expiresAt=NOW,
        )
        assert lookup.wholesaler_id == "w-1"
        assert lookup.wholesaler_name == "Test WS"


class TestRetailerCamelAdapter:
    def test_retailer_data_accepts_camel(self):
        r = RetailerData(id="r-1", phone="+123", name="Shop")
        assert r.phone == "+123"

    def test_binding_data_accepts_camel(self):
        b = BindingData(
            id="b-1",
            wholesalerId="w-1",
            retailerId="r-1",
            status="active",
            createdAt=NOW,
        )
        assert b.wholesaler_id == "w-1"
        dump = b.model_dump()
        assert "wholesaler_id" in dump
        assert "wholesalerId" not in dump
