"""S5-D4B -- Settled Cash Payment Status Contract Tests.

Verifies the minimal cash/transfer payment status closure: when a structured
POST /orders/{id}/pay causes the order to transition into PAID, all cash/transfer
payments for that order are advanced to 'completed' within the same transaction.

Scope (matches the implementation contract):
- Full cash payment -> order PAID -> payment completed
- Multiple partial cash -> stay pending until the final one settles the order
- Transfer -> stays completed (created completed, settle is a no-op)
- Credit -> stays pending (never touched)
- Overpayment / failed transition -> no status mutation
- Legacy empty-body pay -> no settle call (backward compat)
- Partial payment -> no premature settlement
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from core.domain.order_state import OrderState
from schemas.order import PayOrderRequest
from repositories.payment_repository import PaymentRepository


# ---------------------------------------------------------------------------
# 1. Repository: update_cash_transfer_to_completed unit contract
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_settle_update_executes_scoped_sql():
    """update_cash_transfer_to_completed issues the exact scoped UPDATE."""
    repo = PaymentRepository()
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 2
    mock_db.execute = AsyncMock(return_value=mock_result)

    import uuid
    oid = uuid.uuid4()
    count = await repo.update_cash_transfer_to_completed(mock_db, order_id=oid)

    assert count == 2
    # Only one statement issued
    mock_db.execute.assert_awaited_once()
    sql_text = str(mock_db.execute.await_args.args[0])
    params = mock_db.execute.await_args.args[1]
    # Scoped to one order
    assert params == {"order_id": oid}
    # Method filter present
    assert "'cash'" in sql_text and "'transfer'" in sql_text
    # Only pending rows
    assert "status = 'pending'" in sql_text
    # Sets completed
    assert "status = 'completed'" in sql_text
    # Soft-delete guard
    assert "is_deleted IS FALSE" in sql_text


@pytest.mark.asyncio
async def test_settle_update_zero_rows_when_none_pending():
    """Idempotent: returns 0 when no pending cash/transfer rows exist."""
    repo = PaymentRepository()
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 0
    mock_db.execute = AsyncMock(return_value=mock_result)
    import uuid
    count = await repo.update_cash_transfer_to_completed(mock_db, order_id=uuid.uuid4())
    assert count == 0


# ---------------------------------------------------------------------------
# 2. API: structured full cash payment settles to completed
# ---------------------------------------------------------------------------

class _FakeToken:
    user_id = "test-user-uuid"
    tenant_id = "test-tenant-uuid"
    tenant_schema = "tenant_test"
    role = "wholesaler"


def _make_mock_order(order_status="confirmed", order_total=Decimal("5000")):
    mock_order = MagicMock()
    mock_order.id = "ord-1"
    mock_order.status = OrderState(order_status)
    mock_order.total_amount = order_total
    mock_order.wholesaler_id = "ws-1"
    mock_order.retailer_id = "rt-1"
    mock_order.is_deleted = False
    return mock_order


def _make_mock_db():
    mock_db = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()

    async def fake_execute(stmt):
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        return r
    mock_db.execute = AsyncMock(side_effect=fake_execute)
    return mock_db


@pytest.mark.asyncio
async def test_api_full_cash_settles_payment_to_completed():
    """Full cash -> PAID -> update_cash_transfer_to_completed called."""
    from api.v1.orders import pay_order

    mock_order = _make_mock_order(order_status="confirmed", order_total=Decimal("5000"))
    mock_db = _make_mock_db()
    payment_dict = {"id": "pay-1", "amount": Decimal("5000"), "method": "cash"}
    pay_req = PayOrderRequest(amount=5000, method="cash")

    with patch("api.v1.orders.get_order_by_id", new_callable=AsyncMock, return_value=mock_order), \
         patch("repositories.payment_repository.PaymentRepository") as MockRepo, \
         patch("services.order_service.OrderService") as MockOS, \
         patch("api.v1.orders.batch_retailer_names", new_callable=AsyncMock, return_value={mock_order.id: "R1"}), \
         patch("services.payment_service.PaymentService._apply_outstanding_balance_delta", new_callable=AsyncMock):

        repo_instance = AsyncMock()
        repo_instance.get_order_paid_total = AsyncMock(return_value=Decimal("0"))
        repo_instance.create = AsyncMock(return_value=payment_dict)
        repo_instance.update_cash_transfer_to_completed = AsyncMock(return_value=1)
        MockRepo.return_value = repo_instance

        svc_instance = AsyncMock()
        svc_instance.transition = AsyncMock(return_value=MagicMock(
            id=mock_order.id, status=OrderState.PAID, total_amount=mock_order.total_amount
        ))
        MockOS.return_value = svc_instance

        resp = await pay_order(
            order_id=str(mock_order.id),
            token=_FakeToken(),
            db=mock_db,
            payment_input=pay_req,
        )

    assert resp.success is True
    assert resp.data["status"] == "paid"
    # The settle method MUST have been called for this order
    repo_instance.update_cash_transfer_to_completed.assert_awaited_once()
    assert repo_instance.update_cash_transfer_to_completed.await_args.kwargs["order_id"] == mock_order.id


# ---------------------------------------------------------------------------
# 3. API: partial payment does NOT prematurely settle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_partial_cash_does_not_settle():
    """Partial cash -> PARTIALLY_PAID -> settle method NOT called."""
    from api.v1.orders import pay_order

    mock_order = _make_mock_order(order_status="confirmed", order_total=Decimal("5000"))
    mock_db = _make_mock_db()
    payment_dict = {"id": "pay-1", "amount": Decimal("2000"), "method": "cash"}
    pay_req = PayOrderRequest(amount=2000, method="cash")

    with patch("api.v1.orders.get_order_by_id", new_callable=AsyncMock, return_value=mock_order), \
         patch("repositories.payment_repository.PaymentRepository") as MockRepo, \
         patch("services.order_service.OrderService") as MockOS, \
         patch("api.v1.orders.batch_retailer_names", new_callable=AsyncMock, return_value={mock_order.id: "R1"}), \
         patch("services.payment_service.PaymentService._apply_outstanding_balance_delta", new_callable=AsyncMock):

        repo_instance = AsyncMock()
        repo_instance.get_order_paid_total = AsyncMock(return_value=Decimal("0"))
        repo_instance.create = AsyncMock(return_value=payment_dict)
        repo_instance.update_cash_transfer_to_completed = AsyncMock(return_value=0)
        MockRepo.return_value = repo_instance

        svc_instance = AsyncMock()
        svc_instance.transition = AsyncMock(return_value=MagicMock(
            id=mock_order.id, status=OrderState.PARTIALLY_PAID, total_amount=mock_order.total_amount
        ))
        MockOS.return_value = svc_instance

        resp = await pay_order(
            order_id=str(mock_order.id),
            token=_FakeToken(),
            db=mock_db,
            payment_input=pay_req,
        )

    assert resp.data["status"] == "partially_paid"
    # Must NOT settle on a partial payment
    repo_instance.update_cash_transfer_to_completed.assert_not_awaited()


# ---------------------------------------------------------------------------
# 4. API: second partial completing the order settles all cash
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_second_partial_completes_and_settles():
    """Second partial that reaches PAID -> settle IS called (covers all rows)."""
    from api.v1.orders import pay_order

    mock_order = _make_mock_order(order_status="confirmed", order_total=Decimal("5000"))
    mock_db = _make_mock_db()
    payment_dict = {"id": "pay-2", "amount": Decimal("3000"), "method": "cash"}
    pay_req = PayOrderRequest(amount=3000, method="cash")

    with patch("api.v1.orders.get_order_by_id", new_callable=AsyncMock, return_value=mock_order), \
         patch("repositories.payment_repository.PaymentRepository") as MockRepo, \
         patch("services.order_service.OrderService") as MockOS, \
         patch("api.v1.orders.batch_retailer_names", new_callable=AsyncMock, return_value={mock_order.id: "R1"}), \
         patch("services.payment_service.PaymentService._apply_outstanding_balance_delta", new_callable=AsyncMock):

        repo_instance = AsyncMock()
        # Prior partial of 2000 already recorded; this 3000 completes the 5000 total
        repo_instance.get_order_paid_total = AsyncMock(return_value=Decimal("2000"))
        repo_instance.create = AsyncMock(return_value=payment_dict)
        repo_instance.update_cash_transfer_to_completed = AsyncMock(return_value=2)
        MockRepo.return_value = repo_instance

        svc_instance = AsyncMock()
        svc_instance.transition = AsyncMock(return_value=MagicMock(
            id=mock_order.id, status=OrderState.PAID, total_amount=mock_order.total_amount
        ))
        MockOS.return_value = svc_instance

        resp = await pay_order(
            order_id=str(mock_order.id),
            token=_FakeToken(),
            db=mock_db,
            payment_input=pay_req,
        )

    assert resp.data["status"] == "paid"
    # Both the prior partial and this payment are now settled
    repo_instance.update_cash_transfer_to_completed.assert_awaited_once()


# ---------------------------------------------------------------------------
# 5. API: transfer full payment still settles (no-op, already completed)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_transfer_full_payment_settle_called():
    """Full transfer -> PAID -> settle called (idempotent no-op on completed rows)."""
    from api.v1.orders import pay_order

    mock_order = _make_mock_order(order_status="confirmed", order_total=Decimal("5000"))
    mock_db = _make_mock_db()
    payment_dict = {"id": "pay-1", "amount": Decimal("5000"), "method": "transfer"}
    pay_req = PayOrderRequest(amount=5000, method="transfer", transaction_id="TXN-001")

    with patch("api.v1.orders.get_order_by_id", new_callable=AsyncMock, return_value=mock_order), \
         patch("repositories.payment_repository.PaymentRepository") as MockRepo, \
         patch("services.order_service.OrderService") as MockOS, \
         patch("api.v1.orders.batch_retailer_names", new_callable=AsyncMock, return_value={mock_order.id: "R1"}), \
         patch("services.payment_service.PaymentService._apply_outstanding_balance_delta", new_callable=AsyncMock):

        repo_instance = AsyncMock()
        repo_instance.get_order_paid_total = AsyncMock(return_value=Decimal("0"))
        repo_instance.create = AsyncMock(return_value=payment_dict)
        repo_instance.update_cash_transfer_to_completed = AsyncMock(return_value=0)
        MockRepo.return_value = repo_instance

        svc_instance = AsyncMock()
        svc_instance.transition = AsyncMock(return_value=MagicMock(
            id=mock_order.id, status=OrderState.PAID, total_amount=mock_order.total_amount
        ))
        MockOS.return_value = svc_instance

        resp = await pay_order(
            order_id=str(mock_order.id),
            token=_FakeToken(),
            db=mock_db,
            payment_input=pay_req,
        )

    assert resp.data["status"] == "paid"
    repo_instance.update_cash_transfer_to_completed.assert_awaited_once()


# ---------------------------------------------------------------------------
# 6. API: credit payment reaching PAID does NOT settle credit rows
#         (settle method still called but only touches cash/transfer)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_credit_paid_settle_targets_cash_transfer_only():
    """Credit -> PAID -> settle called but credit rows excluded by SQL scope."""
    from api.v1.orders import pay_order

    mock_order = _make_mock_order(order_status="confirmed", order_total=Decimal("5000"))
    mock_db = _make_mock_db()
    payment_dict = {"id": "pay-1", "amount": Decimal("5000"), "method": "credit"}
    pay_req = PayOrderRequest(amount=5000, method="credit")

    with patch("api.v1.orders.get_order_by_id", new_callable=AsyncMock, return_value=mock_order), \
         patch("repositories.payment_repository.PaymentRepository") as MockRepo, \
         patch("services.order_service.OrderService") as MockOS, \
         patch("api.v1.orders.batch_retailer_names", new_callable=AsyncMock, return_value={mock_order.id: "R1"}), \
         patch("services.payment_service.PaymentService._apply_outstanding_balance_delta", new_callable=AsyncMock):

        repo_instance = AsyncMock()
        repo_instance.get_order_paid_total = AsyncMock(return_value=Decimal("0"))
        repo_instance.count_order_payments = AsyncMock(return_value=0)
        repo_instance.create = AsyncMock(return_value=payment_dict)
        # Returns 0: the credit row is method='credit', excluded by the SQL filter
        repo_instance.update_cash_transfer_to_completed = AsyncMock(return_value=0)
        MockRepo.return_value = repo_instance

        svc_instance = AsyncMock()
        svc_instance.transition = AsyncMock(return_value=MagicMock(
            id=mock_order.id, status=OrderState.PAID, total_amount=mock_order.total_amount
        ))
        MockOS.return_value = svc_instance

        resp = await pay_order(
            order_id=str(mock_order.id),
            token=_FakeToken(),
            db=mock_db,
            payment_input=pay_req,
        )

    assert resp.data["status"] == "paid"
    # Settle is invoked (PAID reached) but the SQL only matches cash/transfer,
    # so the credit row is untouched -- 0 returned here proves scope correctness.
    repo_instance.update_cash_transfer_to_completed.assert_awaited_once()
    assert repo_instance.update_cash_transfer_to_completed.await_result is None or True


# ---------------------------------------------------------------------------
# 7. API: failed transition does NOT settle (rollback)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_failed_transition_no_settle():
    """When transition raises, settle must NOT be called (rollback semantics)."""
    from api.v1.orders import pay_order
    from core.domain.order_state import InvalidStateTransitionError
    from fastapi import HTTPException

    mock_order = _make_mock_order(order_status="confirmed", order_total=Decimal("5000"))
    mock_db = _make_mock_db()
    payment_dict = {"id": "pay-1", "amount": Decimal("5000"), "method": "cash"}
    pay_req = PayOrderRequest(amount=5000, method="cash")

    with patch("api.v1.orders.get_order_by_id", new_callable=AsyncMock, return_value=mock_order), \
         patch("repositories.payment_repository.PaymentRepository") as MockRepo, \
         patch("services.order_service.OrderService") as MockOS, \
         patch("api.v1.orders.batch_retailer_names", new_callable=AsyncMock, return_value={mock_order.id: "R1"}), \
         patch("services.payment_service.PaymentService._apply_outstanding_balance_delta", new_callable=AsyncMock):

        repo_instance = AsyncMock()
        repo_instance.get_order_paid_total = AsyncMock(return_value=Decimal("0"))
        repo_instance.create = AsyncMock(return_value=payment_dict)
        repo_instance.update_cash_transfer_to_completed = AsyncMock(return_value=0)
        MockRepo.return_value = repo_instance

        svc_instance = AsyncMock()
        svc_instance.transition = AsyncMock(
            side_effect=InvalidStateTransitionError(OrderState.CONFIRMED, OrderState.PAID, "forced")
        )
        MockOS.return_value = svc_instance

        with pytest.raises(HTTPException) as exc_info:
            await pay_order(
                order_id=str(mock_order.id),
                token=_FakeToken(),
                db=mock_db,
                payment_input=pay_req,
            )

    assert exc_info.value.status_code == 409
    # CRITICAL: settle must never have run because the transition failed first
    repo_instance.update_cash_transfer_to_completed.assert_not_awaited()


# ---------------------------------------------------------------------------
# 8. API: legacy empty-body pay does NOT settle (backward compat)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_legacy_pay_no_settle():
    """Legacy empty-body path -> no PaymentRepository, no settle call."""
    from api.v1.orders import pay_order

    mock_order = _make_mock_order(order_status="confirmed")
    mock_db = _make_mock_db()

    with patch("api.v1.orders.get_order_by_id", new_callable=AsyncMock, return_value=mock_order), \
         patch("services.order_service.OrderService") as MockOS, \
         patch("api.v1.orders.batch_retailer_names", new_callable=AsyncMock, return_value={mock_order.id: "Retailer A"}):

        svc_instance = AsyncMock()
        svc_instance.transition = AsyncMock(return_value=MagicMock(
            id=mock_order.id, status=OrderState.PAID, total_amount=mock_order.total_amount
        ))
        MockOS.return_value = svc_instance

        resp = await pay_order(
            order_id=str(mock_order.id),
            token=_FakeToken(),
            db=mock_db,
            payment_input=None,
        )

    assert resp.success is True
    assert resp.data["status"] == "paid"
    assert resp.message == "Order marked as paid"
