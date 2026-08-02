from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from api.v1.orders import pay_order
from database.session import AsyncSessionLocal
from database.session import async_engine
from schemas.order import PayOrderRequest
from services.canonical_payment_service import (
    CanonicalPaymentResult,
    CanonicalPaymentService,
)
from services.order_service import OrderService
from services.payment_service import PaymentService
from tests.test_dc11d_payment_replay_concurrency_integrity import (
    _Token,
    _bootstrap_minimal_tenant_schema,
    _pay_in_new_session,
    _seed_confirmed_order,
    _set_search_path,
    _snapshot,
    _tenant_id,
    _tenant_schema,
)


def _status(value: str):
    return SimpleNamespace(value=value)


def _result_order(order_id: uuid.UUID, status_value: str = "paid"):
    return SimpleNamespace(id=order_id, status=_status(status_value))


async def _confirm_in_new_session(
    *,
    schema: str,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    amount: Decimal,
    method: str,
    idempotency_key: str,
    transaction_id: str | None = None,
    force_completed: bool = False,
):
    async with AsyncSessionLocal() as session:
        session.info["tenant_schema"] = schema
        session.info["tenant_id"] = str(tenant_id)
        await _set_search_path(session, schema)
        token = _Token(tenant_id=tenant_id, tenant_schema=schema)
        service = CanonicalPaymentService()
        try:
            result = await service.confirm_payment(
                db=session,
                order_id=str(order_id),
                amount=amount,
                method=method,
                transaction_id=transaction_id,
                idempotency_key=idempotency_key,
                created_by=token.user_id,
                force_completed=force_completed,
            )
            await session.commit()
            return result
        except HTTPException as exc:
            await session.rollback()
            return exc


@pytest.mark.asyncio
async def test_route_uses_canonical_payment_service_with_behavior_preserving_defaults():
    token = SimpleNamespace(user_id=str(uuid.uuid4()))
    db = AsyncMock()
    order_id = uuid.uuid4()
    payment_id = uuid.uuid4()
    expected = CanonicalPaymentResult(
        order=_result_order(order_id, "paid"),
        payment_record={
            "id": payment_id,
            "amount": Decimal("100.00"),
            "method": "cash",
        },
        replayed=False,
        order_state="paid",
    )

    locked_order = SimpleNamespace(
        id=order_id,
        status=_status("confirmed"),
        total_amount=Decimal("100.00"),
        wholesaler_id=uuid.uuid4(),
        retailer_id=uuid.uuid4(),
    )

    with patch(
        "services.canonical_payment_service.CanonicalPaymentService.confirm_payment",
        new=AsyncMock(return_value=expected),
    ) as confirm_payment, patch(
        "repositories.payment_repository.PaymentRepository.get_by_idempotency_key",
        new=AsyncMock(return_value=None),
    ), patch(
        "repositories.payment_repository.PaymentRepository.get_order_paid_total",
        new=AsyncMock(return_value=Decimal("0.00")),
    ), patch(
        "api.v1.orders._get_order_by_id_for_update",
        new=AsyncMock(return_value=locked_order),
    ):
        response = await pay_order(
            order_id=str(order_id),
            token=token,
            db=db,
            payment_input=PayOrderRequest(amount=Decimal("100.00"), method="cash"),
            x_idempotency_key="i2a-route-default-key",
        )

    confirm_payment.assert_awaited_once()
    assert confirm_payment.await_args.kwargs["force_completed"] is False
    assert response.message == "Payment recorded and order updated"
    assert response.data["status"] == "paid"
    assert response.data["payment_id"] == str(payment_id)


@pytest.mark.asyncio
async def test_service_does_not_commit_or_rollback_calls():
    order_id = uuid.uuid4()
    retailer_id = uuid.uuid4()
    wholesaler_id = uuid.uuid4()
    created_by = str(uuid.uuid4())
    payment_id = uuid.uuid4()
    service = CanonicalPaymentService()

    class _DB:
        async def commit(self):
            raise AssertionError("service must not call commit")

        async def rollback(self):
            raise AssertionError("service must not call rollback")

        async def refresh(self, _obj):
            return None

    service._get_order_by_id_for_update = AsyncMock(
        side_effect=[
            SimpleNamespace(
                id=order_id,
                retailer_id=retailer_id,
                wholesaler_id=wholesaler_id,
                total_amount=Decimal("100.00"),
                status=_status("confirmed"),
            )
        ]
    )
    service._get_order_for_payment_record = AsyncMock(return_value=_result_order(order_id, "partially_paid"))
    service._repo.get_by_idempotency_key = AsyncMock(return_value=None)
    service._repo.get_order_paid_total = AsyncMock(return_value=Decimal("0.00"))
    service._repo.get_by_transaction_id = AsyncMock(return_value=None)
    service._repo.create = AsyncMock(
        return_value={
            "id": payment_id,
            "order_id": order_id,
            "amount": Decimal("25.00"),
            "method": "transfer",
            "status": "completed",
        }
    )
    service._repo.get_by_id = AsyncMock(
        return_value={
            "id": payment_id,
            "order_id": order_id,
            "amount": Decimal("25.00"),
            "method": "transfer",
            "status": "completed",
        }
    )
    service._repo.update_cash_transfer_to_completed = AsyncMock(return_value=0)

    with patch.object(OrderService, "transition", new=AsyncMock(return_value=_result_order(order_id, "partially_paid"))):
        result = await service.confirm_payment(
            db=_DB(),
            order_id=str(order_id),
            amount=Decimal("25.00"),
            method="transfer",
            transaction_id="I2A-TX-COMMIT-GUARD",
            idempotency_key="i2a-commit-guard-key",
            created_by=created_by,
            force_completed=True,
        )

    assert result.payment_record["status"] == "completed"
    assert result.order_state == "partially_paid"


@pytest.mark.asyncio
async def test_service_cash_partial_and_final_matches_route_outcomes(async_session):
    tenant_id = _tenant_id(async_session)
    route_order, route_retailer, route_token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    svc_order, svc_retailer, svc_token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    service = CanonicalPaymentService()

    await pay_order(
        order_id=str(route_order),
        token=route_token,
        db=async_session,
        payment_input=PayOrderRequest(amount=Decimal("40.00"), method="cash"),
        x_idempotency_key="i2a-route-cash-partial",
    )
    await pay_order(
        order_id=str(route_order),
        token=route_token,
        db=async_session,
        payment_input=PayOrderRequest(amount=Decimal("60.00"), method="cash"),
        x_idempotency_key="i2a-route-cash-final",
    )

    await service.confirm_payment(
        db=async_session,
        order_id=str(svc_order),
        amount=Decimal("40.00"),
        method="cash",
        transaction_id=None,
        idempotency_key="i2a-svc-cash-partial",
        created_by=svc_token.user_id,
    )
    await service.confirm_payment(
        db=async_session,
        order_id=str(svc_order),
        amount=Decimal("60.00"),
        method="cash",
        transaction_id=None,
        idempotency_key="i2a-svc-cash-final",
        created_by=svc_token.user_id,
    )

    route_snapshot = await _snapshot(
        async_session, order_id=route_order, tenant_id=tenant_id, retailer_id=route_retailer
    )
    service_snapshot = await _snapshot(
        async_session, order_id=svc_order, tenant_id=tenant_id, retailer_id=svc_retailer
    )
    assert service_snapshot == route_snapshot


@pytest.mark.asyncio
async def test_service_transfer_pending_then_completed_matches_route_outcomes(async_session):
    tenant_id = _tenant_id(async_session)
    route_order, route_retailer, route_token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    svc_order, svc_retailer, svc_token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    service = CanonicalPaymentService()

    await pay_order(
        order_id=str(route_order),
        token=route_token,
        db=async_session,
        payment_input=PayOrderRequest(
            amount=Decimal("40.00"), method="transfer", transaction_id="I2A-ROUTE-XFER-1"
        ),
        x_idempotency_key="i2a-route-transfer-partial",
    )
    await pay_order(
        order_id=str(route_order),
        token=route_token,
        db=async_session,
        payment_input=PayOrderRequest(
            amount=Decimal("60.00"), method="transfer", transaction_id="I2A-ROUTE-XFER-2"
        ),
        x_idempotency_key="i2a-route-transfer-final",
    )

    await service.confirm_payment(
        db=async_session,
        order_id=str(svc_order),
        amount=Decimal("40.00"),
        method="transfer",
        transaction_id="I2A-SVC-XFER-1",
        idempotency_key="i2a-svc-transfer-partial",
        created_by=svc_token.user_id,
    )
    await service.confirm_payment(
        db=async_session,
        order_id=str(svc_order),
        amount=Decimal("60.00"),
        method="transfer",
        transaction_id="I2A-SVC-XFER-2",
        idempotency_key="i2a-svc-transfer-final",
        created_by=svc_token.user_id,
    )

    route_snapshot = await _snapshot(
        async_session, order_id=route_order, tenant_id=tenant_id, retailer_id=route_retailer
    )
    service_snapshot = await _snapshot(
        async_session, order_id=svc_order, tenant_id=tenant_id, retailer_id=svc_retailer
    )
    assert service_snapshot == route_snapshot


@pytest.mark.asyncio
async def test_service_credit_collection_reduces_outstanding_balance_like_route(async_session):
    tenant_id = _tenant_id(async_session)
    route_order, route_retailer, route_token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    svc_order, svc_retailer, svc_token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    service = CanonicalPaymentService()

    await pay_order(
        order_id=str(route_order),
        token=route_token,
        db=async_session,
        payment_input=PayOrderRequest(amount=Decimal("100.00"), method="credit"),
        x_idempotency_key="i2a-route-credit-sale",
    )
    await pay_order(
        order_id=str(route_order),
        token=route_token,
        db=async_session,
        payment_input=PayOrderRequest(amount=Decimal("40.00"), method="cash"),
        x_idempotency_key="i2a-route-credit-collection",
    )

    await service.confirm_payment(
        db=async_session,
        order_id=str(svc_order),
        amount=Decimal("100.00"),
        method="credit",
        transaction_id=None,
        idempotency_key="i2a-svc-credit-sale",
        created_by=svc_token.user_id,
    )
    await service.confirm_payment(
        db=async_session,
        order_id=str(svc_order),
        amount=Decimal("40.00"),
        method="cash",
        transaction_id=None,
        idempotency_key="i2a-svc-credit-collection",
        created_by=svc_token.user_id,
    )

    route_snapshot = await _snapshot(
        async_session, order_id=route_order, tenant_id=tenant_id, retailer_id=route_retailer
    )
    service_snapshot = await _snapshot(
        async_session, order_id=svc_order, tenant_id=tenant_id, retailer_id=svc_retailer
    )
    assert service_snapshot == route_snapshot


@pytest.mark.asyncio
async def test_service_duplicate_transaction_id_exact_error(async_session):
    tenant_id = _tenant_id(async_session)
    order_a, _retailer_a, token_a = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    order_b, _retailer_b, token_b = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    service = CanonicalPaymentService()

    await service.confirm_payment(
        db=async_session,
        order_id=str(order_a),
        amount=Decimal("100.00"),
        method="transfer",
        transaction_id="I2A-DUPLICATE-XFER",
        idempotency_key="i2a-dup-xfer-a",
        created_by=token_a.user_id,
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.confirm_payment(
            db=async_session,
            order_id=str(order_b),
            amount=Decimal("100.00"),
            method="transfer",
            transaction_id="I2A-DUPLICATE-XFER",
            idempotency_key="i2a-dup-xfer-b",
            created_by=token_b.user_id,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "DUPLICATE_TRANSFER_REFERENCE"


@pytest.mark.asyncio
async def test_service_idempotent_replay_creates_one_financial_result(async_session):
    tenant_id = _tenant_id(async_session)
    order_id, retailer_id, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    service = CanonicalPaymentService()

    first = await service.confirm_payment(
        db=async_session,
        order_id=str(order_id),
        amount=Decimal("100.00"),
        method="cash",
        transaction_id=None,
        idempotency_key="i2a-service-replay",
        created_by=token.user_id,
    )
    replay = await service.confirm_payment(
        db=async_session,
        order_id=str(order_id),
        amount=Decimal("100.00"),
        method="cash",
        transaction_id=None,
        idempotency_key="i2a-service-replay",
        created_by=token.user_id,
    )

    snapshot = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )
    assert replay.replayed is True
    assert replay.payment_record["id"] == first.payment_record["id"]
    assert snapshot["payment_count"] == 1
    assert snapshot["ledger_count"] == 2


@pytest.mark.asyncio
async def test_service_overpayment_rejection_exact_error(async_session):
    tenant_id = _tenant_id(async_session)
    order_id, _retailer_id, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    service = CanonicalPaymentService()

    with pytest.raises(HTTPException) as exc_info:
        await service.confirm_payment(
            db=async_session,
            order_id=str(order_id),
            amount=Decimal("150.00"),
            method="cash",
            transaction_id=None,
            idempotency_key="i2a-service-overpay",
            created_by=token.user_id,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "PAYMENT_EXCEEDS_REMAINING"


@pytest.mark.asyncio
async def test_service_force_completed_cannot_create_pending_payment(async_session):
    tenant_id = _tenant_id(async_session)
    order_id, retailer_id, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    service = CanonicalPaymentService()

    result = await service.confirm_payment(
        db=async_session,
        order_id=str(order_id),
        amount=Decimal("40.00"),
        method="transfer",
        transaction_id="I2A-FORCE-COMPLETED",
        idempotency_key="i2a-force-completed",
        created_by=token.user_id,
        force_completed=True,
    )

    snapshot = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )
    assert result.payment_record["status"] == "completed"
    assert snapshot["completed_count"] == 1
    assert Decimal(str(snapshot["completed_total"])) == Decimal("40.00")


@pytest.mark.asyncio
async def test_service_cross_tenant_same_key_isolated(async_session):
    first_schema = _tenant_schema(async_session)
    first_tenant_id = _tenant_id(async_session)
    second_schema = "t_33333333333333333333333333333333"
    second_tenant_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    shared_key = "i2a-shared-key"

    first_order_id, first_retailer_id, first_token = await _seed_confirmed_order(
        async_session, tenant_id=first_tenant_id, total=Decimal("100.00")
    )
    first_service = CanonicalPaymentService()
    await first_service.confirm_payment(
        db=async_session,
        order_id=str(first_order_id),
        amount=Decimal("100.00"),
        method="cash",
        transaction_id=None,
        idempotency_key=shared_key,
        created_by=first_token.user_id,
    )

    await async_session.commit()
    await _bootstrap_minimal_tenant_schema(async_session, second_schema)
    await async_session.execute(
        text(
            f'TRUNCATE TABLE "{second_schema}".order_items, '
            f'"{second_schema}".payments, '
            f'"{second_schema}".ledger_entries, '
            f'"{second_schema}".orders '
            "RESTART IDENTITY CASCADE"
        )
    )
    await _set_search_path(async_session, second_schema)
    second_order_id, _second_retailer_id, _second_token = await _seed_confirmed_order(
        async_session, tenant_id=second_tenant_id, total=Decimal("100.00")
    )
    await async_session.commit()

    await async_engine.dispose()

    second = await _confirm_in_new_session(
        schema=second_schema,
        tenant_id=second_tenant_id,
        order_id=second_order_id,
        amount=Decimal("100.00"),
        method="cash",
        idempotency_key=shared_key,
    )

    assert not isinstance(second, HTTPException)
    await _set_search_path(async_session, first_schema)
    first_snapshot = await _snapshot(
        async_session,
        order_id=first_order_id,
        tenant_id=first_tenant_id,
        retailer_id=first_retailer_id,
    )
    assert first_snapshot["payment_count"] == 1


@pytest.mark.asyncio
async def test_service_failures_after_mutation_stages_rollback_all_effects(async_session, monkeypatch):
    tenant_id = _tenant_id(async_session)
    order_create, retailer_create, token_create = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    order_credit, retailer_credit, token_credit = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    order_transition, retailer_transition, token_transition = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    order_complete, retailer_complete, token_complete = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    await async_session.commit()

    async def _assert_stage_rollback(order_id, retailer_id, coro):
        before = await _snapshot(
            async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
        )
        with pytest.raises(RuntimeError):
            await coro()
        await async_session.rollback()
        after = await _snapshot(
            async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
        )
        assert after == before

    service_create = CanonicalPaymentService()
    original_create = service_create._repo.create

    async def _failing_create(*args, **kwargs):
        await original_create(*args, **kwargs)
        raise RuntimeError("after-create")

    monkeypatch.setattr(service_create._repo, "create", _failing_create)
    await _assert_stage_rollback(
        order_create,
        retailer_create,
        lambda: service_create.confirm_payment(
            db=async_session,
            order_id=str(order_create),
            amount=Decimal("100.00"),
            method="cash",
            transaction_id=None,
            idempotency_key="i2a-stage-create",
            created_by=token_create.user_id,
        ),
    )

    service_delta = CanonicalPaymentService()
    original_delta = PaymentService._apply_outstanding_balance_delta

    async def _failing_delta(self, tenant_db, *, wholesaler_id, retailer_id, delta):
        await original_delta(self, tenant_db, wholesaler_id=wholesaler_id, retailer_id=retailer_id, delta=delta)
        raise RuntimeError("after-delta")

    monkeypatch.setattr(PaymentService, "_apply_outstanding_balance_delta", _failing_delta)
    await _assert_stage_rollback(
        order_credit,
        retailer_credit,
        lambda: service_delta.confirm_payment(
            db=async_session,
            order_id=str(order_credit),
            amount=Decimal("100.00"),
            method="credit",
            transaction_id=None,
            idempotency_key="i2a-stage-delta",
            created_by=token_credit.user_id,
        ),
    )

    monkeypatch.setattr(PaymentService, "_apply_outstanding_balance_delta", original_delta)
    service_transition = CanonicalPaymentService()
    original_transition = OrderService.transition

    async def _failing_transition(self, *args, **kwargs):
        await original_transition(self, *args, **kwargs)
        raise RuntimeError("after-transition")

    monkeypatch.setattr(OrderService, "transition", _failing_transition)
    await _assert_stage_rollback(
        order_transition,
        retailer_transition,
        lambda: service_transition.confirm_payment(
            db=async_session,
            order_id=str(order_transition),
            amount=Decimal("100.00"),
            method="cash",
            transaction_id=None,
            idempotency_key="i2a-stage-transition",
            created_by=token_transition.user_id,
        ),
    )

    monkeypatch.setattr(OrderService, "transition", original_transition)
    service_complete = CanonicalPaymentService()
    original_complete = service_complete._repo.update_cash_transfer_to_completed

    async def _failing_complete(*args, **kwargs):
        await original_complete(*args, **kwargs)
        raise RuntimeError("after-complete")

    monkeypatch.setattr(service_complete._repo, "update_cash_transfer_to_completed", _failing_complete)
    await _assert_stage_rollback(
        order_complete,
        retailer_complete,
        lambda: service_complete.confirm_payment(
            db=async_session,
            order_id=str(order_complete),
            amount=Decimal("100.00"),
            method="cash",
            transaction_id=None,
            idempotency_key="i2a-stage-complete",
            created_by=token_complete.user_id,
        ),
    )


# ---------------------------------------------------------------------------
# I2A-R3: Amount integrity boundary tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_r3_negative_cash_amount_rejected_with_zero_mutation(async_session):
    tenant_id = _tenant_id(async_session)
    order_id, retailer_id, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    service = CanonicalPaymentService()

    before = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.confirm_payment(
            db=async_session,
            order_id=str(order_id),
            amount=Decimal("-1.00"),
            method="cash",
            transaction_id=None,
            idempotency_key="i2a-r3-negative",
            created_by=token.user_id,
        )

    after = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_PAYMENT_AMOUNT"
    assert after == before


@pytest.mark.asyncio
async def test_r3_zero_amount_rejected(async_session):
    tenant_id = _tenant_id(async_session)
    order_id, retailer_id, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    service = CanonicalPaymentService()

    with pytest.raises(HTTPException) as exc_info:
        await service.confirm_payment(
            db=async_session,
            order_id=str(order_id),
            amount=Decimal("0"),
            method="cash",
            transaction_id=None,
            idempotency_key="i2a-r3-zero",
            created_by=token.user_id,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_PAYMENT_AMOUNT"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_amount",
    [
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
    ids=["nan", "pos_inf", "neg_inf"],
)
async def test_r3_nan_and_infinity_rejected_without_500(async_session, bad_amount):
    tenant_id = _tenant_id(async_session)
    order_id, retailer_id, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    service = CanonicalPaymentService()

    with pytest.raises(HTTPException) as exc_info:
        await service.confirm_payment(
            db=async_session,
            order_id=str(order_id),
            amount=bad_amount,
            method="cash",
            transaction_id=None,
            idempotency_key=f"i2a-r3-special-{bad_amount}",
            created_by=token.user_id,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_PAYMENT_AMOUNT"


@pytest.mark.asyncio
async def test_r3_skip_prechecks_cannot_bypass_amount_guard():
    order_id = uuid.uuid4()
    locked_order = SimpleNamespace(
        id=order_id,
        status=_status("confirmed"),
        total_amount=Decimal("100.00"),
        wholesaler_id=uuid.uuid4(),
        retailer_id=uuid.uuid4(),
    )
    db = AsyncMock()
    service = CanonicalPaymentService()

    with pytest.raises(HTTPException) as exc_info:
        await service.confirm_payment(
            db=db,
            order_id=str(order_id),
            amount=Decimal("-50.00"),
            method="cash",
            transaction_id=None,
            idempotency_key="i2a-r3-skip-bypass",
            created_by=str(uuid.uuid4()),
            locked_order=locked_order,
            target_state=SimpleNamespace(value="paid"),
            is_credit_collection=False,
            skip_prechecks=True,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_PAYMENT_AMOUNT"


@pytest.mark.asyncio
async def test_r3_failed_attempt_leaves_transaction_retryable(async_session):
    tenant_id = _tenant_id(async_session)
    order_id, retailer_id, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    service = CanonicalPaymentService()

    with pytest.raises(HTTPException):
        await service.confirm_payment(
            db=async_session,
            order_id=str(order_id),
            amount=Decimal("-1.00"),
            method="cash",
            transaction_id=None,
            idempotency_key="i2a-r3-retry-invalid",
            created_by=token.user_id,
        )

    result = await service.confirm_payment(
        db=async_session,
        order_id=str(order_id),
        amount=Decimal("100.00"),
        method="cash",
        transaction_id=None,
        idempotency_key="i2a-r3-retry-valid",
        created_by=token.user_id,
    )

    assert result.order_state == "paid"
    snapshot = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )
    assert snapshot["payment_count"] == 1
    assert snapshot["ledger_count"] == 2
