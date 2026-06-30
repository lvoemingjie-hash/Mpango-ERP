"""S5-D6 -- multi-partial structured payment state-machine tests."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from api.v1.orders import pay_order
from schemas.order import PayOrderRequest


class _Token:
    def __init__(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
        self.tenant_id = str(tenant_id)
        self.user_id = str(user_id)
        self.tenant_schema = "t_test"
        self.roles = ["super_admin"]


async def _seed_confirmed_order(async_session, *, total: Decimal):
    tenant_id = uuid.UUID(async_session.info["tenant_id"])
    user_id = uuid.uuid4()
    retailer_id = uuid.uuid4()
    order_id = uuid.uuid4()

    await async_session.execute(
        text(
            """
            INSERT INTO public.wholesalers (id, code, name, status, is_deleted)
            VALUES (:tenant_id, :code, 'S5D6 Test Wholesaler', 'active', FALSE)
            ON CONFLICT (id) DO UPDATE
            SET status = 'active', is_deleted = FALSE, updated_at = now()
            """
        ),
        {"tenant_id": tenant_id, "code": f"S5D6{str(order_id).replace('-', '')[:8]}"},
    )
    await async_session.execute(
        text(
            """
            INSERT INTO public.retailers (id, phone, name, is_deleted)
            VALUES (:retailer_id, :phone, 'S5D6 Test Retailer', FALSE)
            ON CONFLICT (id) DO UPDATE
            SET is_deleted = FALSE, updated_at = now()
            """
        ),
        {"retailer_id": retailer_id, "phone": f"+1888{str(order_id).replace('-', '')[:10]}"},
    )
    await async_session.execute(
        text(
            """
            INSERT INTO public.wholesaler_retailer_bindings (
                wholesaler_id, retailer_id, status, outstanding_balance, is_deleted
            )
            VALUES (:tenant_id, :retailer_id, 'active', :total, FALSE)
            ON CONFLICT (wholesaler_id, retailer_id) DO UPDATE
            SET status = 'active',
                outstanding_balance = :total,
                is_deleted = FALSE,
                updated_at = now()
            """
        ),
        {"tenant_id": tenant_id, "retailer_id": retailer_id, "total": total},
    )
    await async_session.execute(
        text(
            """
            INSERT INTO orders (id, wholesaler_id, retailer_id, status, total_amount)
            VALUES (:order_id, :tenant_id, :retailer_id, 'confirmed', :total)
            """
        ),
        {"order_id": order_id, "tenant_id": tenant_id, "retailer_id": retailer_id, "total": total},
    )

    return order_id, _Token(tenant_id=tenant_id, user_id=user_id)


async def _pay(async_session, *, order_id: uuid.UUID, token: _Token, amount: Decimal, method: str):
    return await pay_order(
        order_id=str(order_id),
        token=token,
        db=async_session,
        payment_input=PayOrderRequest(amount=amount, method=method),
    )


async def _payment_ledger_snapshot(async_session, *, order_id: uuid.UUID):
    result = await async_session.execute(
        text(
            """
            SELECT
                (SELECT status::text FROM orders WHERE id = :order_id) AS order_status,
                (SELECT COALESCE(SUM(amount), 0)
                 FROM payments
                 WHERE order_id = :order_id
                   AND method IN ('cash', 'transfer')
                   AND status = 'completed'
                   AND is_deleted IS FALSE) AS completed_total,
                (SELECT COUNT(*)
                 FROM payments
                 WHERE order_id = :order_id
                   AND method IN ('cash', 'transfer')
                   AND status = 'completed'
                   AND is_deleted IS FALSE) AS completed_count,
                (SELECT COUNT(*)
                 FROM payments
                 WHERE order_id = :order_id
                   AND method IN ('cash', 'transfer')
                   AND status = 'pending'
                   AND is_deleted IS FALSE) AS pending_cash_transfer_count,
                COALESCE(SUM(CASE WHEN account_type::text = 'cash' THEN amount ELSE 0 END), 0) AS cash_debit,
                COALESCE(SUM(CASE WHEN account_type::text = 'receivable' AND amount < 0 THEN -amount ELSE 0 END), 0) AS receivable_credit,
                COALESCE(SUM(CASE WHEN account_type::text IN ('cash', 'receivable') THEN amount ELSE 0 END), 0) AS settlement_sum,
                COUNT(*) FILTER (WHERE account_type::text IN ('cash', 'receivable')) AS settlement_entry_count
            FROM ledger_entries
            WHERE reference_type = 'order'
              AND reference_id = :order_id
            """
        ),
        {"order_id": order_id},
    )
    return result.mappings().one()


def _assert_settlement_covered(snapshot, *, expected_total: Decimal, completed_count: int) -> None:
    assert snapshot["order_status"] == "paid"
    assert snapshot["completed_count"] == completed_count
    assert Decimal(str(snapshot["completed_total"])) == expected_total
    assert Decimal(str(snapshot["cash_debit"])) == expected_total
    assert Decimal(str(snapshot["receivable_credit"])) == expected_total
    assert Decimal(str(snapshot["settlement_sum"])) == Decimal("0.0000")
    assert snapshot["settlement_entry_count"] == 2


@pytest.mark.asyncio
async def test_cash_allows_multiple_partials_then_final_balanced_settlement(async_session):
    order_id, token = await _seed_confirmed_order(async_session, total=Decimal("100.00"))

    first = await _pay(
        async_session,
        order_id=order_id,
        token=token,
        amount=Decimal("30.00"),
        method="cash",
    )
    after_first = await _payment_ledger_snapshot(async_session, order_id=order_id)

    assert first.data["status"] == "partially_paid"
    assert after_first["completed_count"] == 0
    assert after_first["pending_cash_transfer_count"] == 1
    assert Decimal(str(after_first["cash_debit"])) == Decimal("0")
    assert Decimal(str(after_first["receivable_credit"])) == Decimal("0")

    second = await _pay(
        async_session,
        order_id=order_id,
        token=token,
        amount=Decimal("40.00"),
        method="cash",
    )
    after_second = await _payment_ledger_snapshot(async_session, order_id=order_id)

    assert second.data["status"] == "partially_paid"
    assert after_second["completed_count"] == 0
    assert after_second["pending_cash_transfer_count"] == 2
    assert Decimal(str(after_second["cash_debit"])) == Decimal("0")
    assert Decimal(str(after_second["receivable_credit"])) == Decimal("0")

    final = await _pay(
        async_session,
        order_id=order_id,
        token=token,
        amount=Decimal("30.00"),
        method="cash",
    )
    after_final = await _payment_ledger_snapshot(async_session, order_id=order_id)

    assert final.data["status"] == "paid"
    _assert_settlement_covered(
        after_final,
        expected_total=Decimal("100.00"),
        completed_count=3,
    )

    with pytest.raises(HTTPException) as exc_info:
        await _pay(
            async_session,
            order_id=order_id,
            token=token,
            amount=Decimal("1.00"),
            method="cash",
        )
    assert exc_info.value.status_code in (400, 409)

    assert await _payment_ledger_snapshot(async_session, order_id=order_id) == after_final


@pytest.mark.asyncio
async def test_transfer_allows_multiple_partials_then_final_balanced_settlement(async_session):
    order_id, token = await _seed_confirmed_order(async_session, total=Decimal("100.00"))

    first = await _pay(
        async_session,
        order_id=order_id,
        token=token,
        amount=Decimal("30.00"),
        method="transfer",
    )
    after_first = await _payment_ledger_snapshot(async_session, order_id=order_id)

    assert first.data["status"] == "partially_paid"
    assert after_first["completed_count"] == 0
    assert after_first["pending_cash_transfer_count"] == 1
    assert Decimal(str(after_first["cash_debit"])) == Decimal("0")
    assert Decimal(str(after_first["receivable_credit"])) == Decimal("0")

    second = await _pay(
        async_session,
        order_id=order_id,
        token=token,
        amount=Decimal("40.00"),
        method="transfer",
    )
    after_second = await _payment_ledger_snapshot(async_session, order_id=order_id)

    assert second.data["status"] == "partially_paid"
    assert after_second["completed_count"] == 0
    assert after_second["pending_cash_transfer_count"] == 2
    assert Decimal(str(after_second["cash_debit"])) == Decimal("0")
    assert Decimal(str(after_second["receivable_credit"])) == Decimal("0")

    final = await _pay(
        async_session,
        order_id=order_id,
        token=token,
        amount=Decimal("30.00"),
        method="transfer",
    )
    after_final = await _payment_ledger_snapshot(async_session, order_id=order_id)

    assert final.data["status"] == "paid"
    _assert_settlement_covered(
        after_final,
        expected_total=Decimal("100.00"),
        completed_count=3,
    )
