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
- Empty-body pay -> controlled rejection with no financial side effects
- Partial payment -> no premature settlement
"""
import pytest
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import text

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


@pytest.mark.asyncio
async def test_settle_update_leaves_credit_rows_pending(async_session):
    """Real DB: settling cash/transfer rows must not mutate credit rows."""
    repo = PaymentRepository()
    order_id = uuid.uuid4()
    retailer_id = uuid.uuid4()
    wholesaler_id = uuid.uuid4()

    await async_session.execute(
        text(
            """
            INSERT INTO orders (id, wholesaler_id, retailer_id, status, total_amount)
            VALUES (:order_id, :wholesaler_id, :retailer_id, 'paid', 5000.00)
            """
        ),
        {
            "order_id": order_id,
            "wholesaler_id": wholesaler_id,
            "retailer_id": retailer_id,
        },
    )
    await async_session.execute(
        text(
            """
            INSERT INTO payments (order_id, retailer_id, amount, method, status)
            VALUES
                (:order_id, :retailer_id, 2500.00, 'cash', 'pending'),
                (:order_id, :retailer_id, 2500.00, 'credit', 'pending')
            """
        ),
        {"order_id": order_id, "retailer_id": retailer_id},
    )

    updated_count = await repo.update_cash_transfer_to_completed(
        async_session, order_id=order_id,
    )

    rows = (
        await async_session.execute(
            text(
                """
                SELECT method, status
                FROM payments
                WHERE order_id = :order_id
                ORDER BY method
                """
            ),
            {"order_id": order_id},
        )
    ).mappings().all()

    assert updated_count == 1
    assert [dict(row) for row in rows] == [
        {"method": "cash", "status": "completed"},
        {"method": "credit", "status": "pending"},
    ]


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


def _payment_key(name: str) -> str:
    return f"s5d4b-{name}-{uuid.uuid4().hex[:12]}"


def _patch_payment_route(mock_order):
    return patch(
        "api.v1.orders._get_order_by_id_for_update",
        new_callable=AsyncMock,
        return_value=mock_order,
    )


@pytest.mark.asyncio
async def test_api_full_cash_settles_payment_to_completed():
    """Full cash -> PAID -> update_cash_transfer_to_completed called."""
    from api.v1.orders import pay_order

    mock_order = _make_mock_order(order_status="confirmed", order_total=Decimal("5000"))
    mock_db = _make_mock_db()
    payment_dict = {"id": "pay-1", "amount": Decimal("5000"), "method": "cash"}
    pay_req = PayOrderRequest(amount=5000, method="cash")

    with patch("api.v1.orders.get_order_by_id", new_callable=AsyncMock, return_value=mock_order), \
         _patch_payment_route(mock_order), \
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
            x_idempotency_key=_payment_key("full-cash"),
        )

    assert resp.success is True
    assert resp.data["status"] == "paid"
    # The settle method MUST have been called for this order
    repo_instance.update_cash_transfer_to_completed.assert_awaited_once()
    assert repo_instance.update_cash_transfer_to_completed.await_args.kwargs["order_id"] == mock_order.id


@pytest.mark.asyncio
async def test_api_proposed_paid_but_returned_non_paid_does_not_settle():
    """Settlement is guarded by the actual returned order status, not target_state."""
    from api.v1.orders import pay_order

    mock_order = _make_mock_order(order_status="confirmed", order_total=Decimal("5000"))
    mock_db = _make_mock_db()
    payment_dict = {"id": "pay-1", "amount": Decimal("5000"), "method": "cash"}
    pay_req = PayOrderRequest(amount=5000, method="cash")

    with patch("api.v1.orders.get_order_by_id", new_callable=AsyncMock, return_value=mock_order), \
         _patch_payment_route(mock_order), \
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
            id=mock_order.id,
            status=OrderState.PARTIALLY_PAID,
            total_amount=mock_order.total_amount,
        ))
        MockOS.return_value = svc_instance

        resp = await pay_order(
            order_id=str(mock_order.id),
            token=_FakeToken(),
            db=mock_db,
            payment_input=pay_req,
            x_idempotency_key=_payment_key("returned-non-paid"),
        )

    assert resp.data["status"] == "partially_paid"
    repo_instance.update_cash_transfer_to_completed.assert_not_awaited()


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
         _patch_payment_route(mock_order), \
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
            x_idempotency_key=_payment_key("partial-cash"),
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
         _patch_payment_route(mock_order), \
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
            x_idempotency_key=_payment_key("second-partial"),
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
         _patch_payment_route(mock_order), \
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
            x_idempotency_key=_payment_key("transfer-full"),
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
         _patch_payment_route(mock_order), \
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
            x_idempotency_key=_payment_key("credit-full"),
        )

    assert resp.data["status"] == "paid"
    # Settle is invoked (PAID reached) but the SQL only matches cash/transfer,
    # so the real-DB repository test above proves credit rows are untouched.
    repo_instance.update_cash_transfer_to_completed.assert_awaited_once()
    assert repo_instance.update_cash_transfer_to_completed.await_args.kwargs["order_id"] == mock_order.id


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
         _patch_payment_route(mock_order), \
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
                x_idempotency_key=_payment_key("failed-transition"),
            )

    assert exc_info.value.status_code == 409
    # CRITICAL: settle must never have run because the transition failed first
    repo_instance.update_cash_transfer_to_completed.assert_not_awaited()


# ---------------------------------------------------------------------------
# 8. API: empty-body pay is controlled 400 with no side effects
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_legacy_pay_no_settle():
    """Empty-body path -> no payment/order/balance/ledger side effects."""
    from api.v1.orders import pay_order
    from fastapi import HTTPException

    mock_order = _make_mock_order(order_status="confirmed")
    mock_db = _make_mock_db()

    with patch("api.v1.orders.get_order_by_id", new_callable=AsyncMock) as get_order_mock, \
         patch("api.v1.orders._get_order_by_id_for_update", new_callable=AsyncMock) as lock_mock, \
         patch("repositories.payment_repository.PaymentRepository") as MockRepo, \
         patch("services.order_service.OrderService") as MockOS, \
         patch("services.payment_service.PaymentService._apply_outstanding_balance_delta", new_callable=AsyncMock) as balance_mock:
        with pytest.raises(HTTPException) as exc_info:
            await pay_order(
                order_id=str(mock_order.id),
                token=_FakeToken(),
                db=mock_db,
                payment_input=None,
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "PAYMENT_BODY_REQUIRED"
    get_order_mock.assert_not_awaited()
    lock_mock.assert_not_awaited()
    MockRepo.assert_not_called()
    MockOS.assert_not_called()
    balance_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# 9. Real request/session lifecycle: settlement failure rolls everything back
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_route_settlement_failure_rolls_back_payment_order_balance_and_ledger(async_session):
    """Real DB/request lifecycle: settlement failure after transition rolls back."""
    pytest.importorskip("httpx", reason="httpx required for ASGI transport")

    from fastapi import FastAPI
    import httpx

    from api.context import AuthContext, TenantContext
    from api.context.tenant import create_tenant_session
    from api.middleware.auth import AuthenticationMiddleware
    from api.v1.orders import router as orders_router
    from core.security import TokenPayload
    from database.session import AsyncSessionLocal

    tenant_schema = async_session.info["tenant_schema"]
    tenant_id = uuid.UUID(async_session.info["tenant_id"])
    user_id = uuid.uuid4()
    retailer_id = uuid.uuid4()
    order_id = uuid.uuid4()
    existing_payment_id = uuid.uuid4()
    starting_balance = Decimal("100.00")

    await async_session.execute(
        text(
            """
            INSERT INTO public.wholesalers (id, code, name, status, is_deleted)
            VALUES (:tenant_id, :code, 'S5D4B R1 Test Wholesaler', 'active', FALSE)
            ON CONFLICT (id) DO UPDATE
            SET status = 'active', is_deleted = FALSE, updated_at = now()
            """
        ),
        {"tenant_id": tenant_id, "code": f"S5D4B{str(order_id).replace('-', '')[:8]}"},
    )
    await async_session.execute(
        text(
            """
            INSERT INTO public.retailers (id, phone, name, is_deleted)
            VALUES (:retailer_id, :phone, 'S5D4B R1 Test Retailer', FALSE)
            ON CONFLICT (id) DO UPDATE
            SET is_deleted = FALSE, updated_at = now()
            """
        ),
        {"retailer_id": retailer_id, "phone": f"+1555{str(order_id).replace('-', '')[:10]}"},
    )
    await async_session.execute(
        text(
            """
            INSERT INTO public.wholesaler_retailer_bindings (
                wholesaler_id, retailer_id, status, outstanding_balance, is_deleted
            )
            VALUES (:tenant_id, :retailer_id, 'active', :balance, FALSE)
            ON CONFLICT (wholesaler_id, retailer_id) DO UPDATE
            SET status = 'active',
                outstanding_balance = :balance,
                is_deleted = FALSE,
                updated_at = now()
            """
        ),
        {"tenant_id": tenant_id, "retailer_id": retailer_id, "balance": starting_balance},
    )
    await async_session.execute(
        text(
            """
            INSERT INTO orders (id, wholesaler_id, retailer_id, status, total_amount)
            VALUES (:order_id, :tenant_id, :retailer_id, 'confirmed', 100.00)
            """
        ),
        {"order_id": order_id, "tenant_id": tenant_id, "retailer_id": retailer_id},
    )
    await async_session.execute(
        text(
            """
            INSERT INTO payments (id, order_id, retailer_id, amount, method, status)
            VALUES (:payment_id, :order_id, :retailer_id, 40.00, 'cash', 'pending')
            """
        ),
        {
            "payment_id": existing_payment_id,
            "order_id": order_id,
            "retailer_id": retailer_id,
        },
    )
    await async_session.execute(
        text(
            """
            INSERT INTO ledger_entries (account_type, amount, reference_type, reference_id, description)
            VALUES
                ('receivable', 100.00, 'order', :order_id, 'seed confirmation debit'),
                ('revenue', -100.00, 'order', :order_id, 'seed confirmation credit')
            """
        ),
        {"order_id": order_id},
    )
    await async_session.commit()

    async with AsyncSessionLocal() as before_session:
        await before_session.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))
        before_snapshot = (
            await before_session.execute(
                text(
                    """
                    SELECT
                        (SELECT status::text FROM orders WHERE id = :order_id) AS order_status,
                        (SELECT COUNT(*) FROM payments WHERE order_id = :order_id) AS payment_count,
                        (SELECT status FROM payments WHERE id = :payment_id) AS existing_payment_status,
                        (SELECT outstanding_balance FROM public.wholesaler_retailer_bindings
                         WHERE wholesaler_id = :tenant_id AND retailer_id = :retailer_id) AS balance,
                        (SELECT COUNT(*) FROM ledger_entries WHERE reference_id = :order_id) AS ledger_count,
                        (SELECT COALESCE(SUM(amount), 0) FROM ledger_entries WHERE reference_id = :order_id) AS ledger_sum
                    """
                ),
                {
                    "order_id": order_id,
                    "payment_id": existing_payment_id,
                    "tenant_id": tenant_id,
                    "retailer_id": retailer_id,
                },
            )
        ).mappings().one()

    class _LifecycleStrategy:
        async def authenticate(self, request):
            token = TokenPayload(
                user_id=str(user_id),
                tenant_id=str(tenant_id),
                tenant_schema=tenant_schema,
                roles=["super_admin"],
            )
            return AuthContext(token=token, raw_token="test-token")

        async def resolve_tenant_context(self, auth_ctx):
            session = await create_tenant_session(tenant_schema)
            return TenantContext(
                tenant_id=str(tenant_id),
                tenant_schema=tenant_schema,
                session=session,
                user=SimpleNamespace(roles=[]),
            )

    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware, strategy=_LifecycleStrategy())
    app.include_router(orders_router, prefix="/api/v1/orders")

    with patch(
        "repositories.payment_repository.PaymentRepository.update_cash_transfer_to_completed",
        new_callable=AsyncMock,
        side_effect=RuntimeError("forced settlement failure after transition"),
    ) as settle_mock:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver",
        ) as client:
            response = await client.post(
                f"/api/v1/orders/{order_id}/pay",
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Idempotency-Key": _payment_key("route-rollback"),
                },
                json={"amount": 60, "method": "cash"},
            )

    assert response.status_code == 500
    settle_mock.assert_awaited_once()

    async with AsyncSessionLocal() as verify_session:
        await verify_session.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))
        after_snapshot = (
            await verify_session.execute(
                text(
                    """
                    SELECT
                        (SELECT status::text FROM orders WHERE id = :order_id) AS order_status,
                        (SELECT COUNT(*) FROM payments WHERE order_id = :order_id) AS payment_count,
                        (SELECT status FROM payments WHERE id = :payment_id) AS existing_payment_status,
                        (SELECT COUNT(*) FROM payments WHERE order_id = :order_id AND amount = 60.00) AS new_payment_count,
                        (SELECT outstanding_balance FROM public.wholesaler_retailer_bindings
                         WHERE wholesaler_id = :tenant_id AND retailer_id = :retailer_id) AS balance,
                        (SELECT COUNT(*) FROM ledger_entries WHERE reference_id = :order_id) AS ledger_count,
                        (SELECT COALESCE(SUM(amount), 0) FROM ledger_entries WHERE reference_id = :order_id) AS ledger_sum
                    """
                ),
                {
                    "order_id": order_id,
                    "payment_id": existing_payment_id,
                    "tenant_id": tenant_id,
                    "retailer_id": retailer_id,
                },
            )
        ).mappings().one()

    assert dict(before_snapshot) == {
        "order_status": "confirmed",
        "payment_count": 1,
        "existing_payment_status": "pending",
        "balance": starting_balance,
        "ledger_count": 2,
        "ledger_sum": Decimal("0.0000"),
    }
    assert after_snapshot["order_status"] == "confirmed"
    assert after_snapshot["payment_count"] == before_snapshot["payment_count"]
    assert after_snapshot["existing_payment_status"] == "pending"
    assert after_snapshot["new_payment_count"] == 0
    assert after_snapshot["balance"] == before_snapshot["balance"]
    assert after_snapshot["ledger_count"] == before_snapshot["ledger_count"]
    assert after_snapshot["ledger_sum"] == before_snapshot["ledger_sum"]
