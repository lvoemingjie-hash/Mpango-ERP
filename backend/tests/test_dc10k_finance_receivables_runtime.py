"""DC-10K runtime regressions for the customer-facing Finance page."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from api.v1.finance import get_receivable_orders
from core.security import TokenPayload
from models.order import Order, OrderStatus
from services.receivables_service import ReceivablesService


@pytest.mark.asyncio
async def test_receivable_orders_handle_postgres_timestamptz(async_session):
    """A real TIMESTAMPTZ created_at must not become a public 500."""
    tenant_id = uuid.UUID(str(async_session.info["tenant_id"]))
    retailer_id = uuid.uuid4()
    order = Order(
        wholesaler_id=tenant_id,
        retailer_id=retailer_id,
        status=OrderStatus.CONFIRMED,
        total_amount=Decimal("125.00"),
    )
    async_session.add(order)
    await async_session.flush()

    response = await get_receivable_orders(
        page=1,
        size=20,
        retailer_id=None,
        classification=None,
        status_filter=None,
        token=TokenPayload(
            user_id=str(uuid.uuid4()),
            tenant_id=str(tenant_id),
            tenant_schema=str(async_session.info["tenant_schema"]),
        ),
        db=async_session,
    )
    result = response.data

    assert result["pagination"]["total"] == 1
    assert result["items"][0]["order_id"] == str(order.id)
    assert result["items"][0]["age_days"] >= 0


@pytest.mark.asyncio
async def test_receivables_summary_is_scoped_to_current_wholesaler(async_session):
    """Public binding balances from another tenant must never be returned."""
    current_wholesaler_id = uuid.UUID(str(async_session.info["tenant_id"]))
    other_wholesaler_id = uuid.uuid4()
    current_retailer_id = uuid.uuid4()
    other_retailer_id = uuid.uuid4()

    await async_session.execute(
        text(
            "DELETE FROM public.wholesaler_retailer_bindings "
            "WHERE wholesaler_id IN (:current_id, :other_id)"
        ),
        {"current_id": current_wholesaler_id, "other_id": other_wholesaler_id},
    )
    await async_session.execute(
        text(
            """
            INSERT INTO public.wholesalers (id, code, name)
            VALUES
                (:current_id, :current_code, 'Current Tenant'),
                (:other_id, :other_code, 'Other Tenant')
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "current_id": current_wholesaler_id,
            "current_code": f"D{current_wholesaler_id.hex[:12].upper()}",
            "other_id": other_wholesaler_id,
            "other_code": f"D{other_wholesaler_id.hex[:12].upper()}",
        },
    )
    await async_session.execute(
        text(
            """
            INSERT INTO public.retailers (id, phone, name)
            VALUES
                (:current_id, :current_phone, 'Current Retailer'),
                (:other_id, :other_phone, 'Other Retailer')
            """
        ),
        {
            "current_id": current_retailer_id,
            "current_phone": f"dc10k-{current_retailer_id.hex[:20]}",
            "other_id": other_retailer_id,
            "other_phone": f"dc10k-{other_retailer_id.hex[:20]}",
        },
    )
    await async_session.execute(
        text(
            """
            INSERT INTO public.wholesaler_retailer_bindings
                (wholesaler_id, retailer_id, outstanding_balance)
            VALUES
                (:current_wholesaler, :current_retailer, 50.00),
                (:other_wholesaler, :other_retailer, 900.00)
            """
        ),
        {
            "current_wholesaler": current_wholesaler_id,
            "current_retailer": current_retailer_id,
            "other_wholesaler": other_wholesaler_id,
            "other_retailer": other_retailer_id,
        },
    )

    result = await ReceivablesService().get_receivables_summary(
        tenant_db=async_session,
        wholesaler_id=current_wholesaler_id,
    )

    assert result["total_outstanding"] == 50.0
    assert result["retailer_count"] == 1
    assert result["by_retailer"][0]["retailer_id"] == str(current_retailer_id)
