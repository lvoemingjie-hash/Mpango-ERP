"""Saved-currency fixture controls, not a real-DB transaction acceptance.

Only repository lookup I/O is substituted. The currency guard and locked
canonical producer run unchanged; unexpected economic I/O fails the test.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

from fastapi import HTTPException
import pytest

from core.domain.order_state import OrderState
from services.canonical_payment_service import (
    CanonicalPaymentService,
    _validate_order_payment_amount,
)


def _order(currency):
    return SimpleNamespace(
        id=UUID(int=1),
        retailer_id=UUID(int=2),
        wholesaler_id=UUID(int=3),
        status=OrderState.CONFIRMED,
        total_amount=Decimal("100.00"),
        currency_snapshot=currency,
    )


def _read_only_io(existing=None):
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=AssertionError("UNEXPECTED_DATABASE_IO")),
        flush=AsyncMock(side_effect=AssertionError("UNEXPECTED_FINANCIAL_FLUSH")),
        add=Mock(side_effect=AssertionError("UNEXPECTED_FINANCIAL_ADD")),
        begin_nested=Mock(side_effect=AssertionError("UNEXPECTED_WRITE_SAVEPOINT")),
    )
    repo = SimpleNamespace(
        get_by_idempotency_key=AsyncMock(return_value=existing),
        create=AsyncMock(side_effect=AssertionError("UNEXPECTED_PAYMENT_INSERT")),
    )
    service = CanonicalPaymentService()
    service._repo = repo
    return service, db, repo


def _assert_no_financial_io(db, repo):
    db.execute.assert_not_awaited()
    db.flush.assert_not_awaited()
    db.add.assert_not_called()
    db.begin_nested.assert_not_called()
    repo.create.assert_not_awaited()


async def _assert_new_write_refused(currency, amount, status, code):
    service, db, repo = _read_only_io()
    with pytest.raises(HTTPException) as caught:
        await service._confirm_payment_for_locked_order(
            db=db,
            order=_order(currency),
            amount=Decimal(amount),
            method="cash",
            transaction_id=None,
            idempotency_key="fixture-currency-new-write",
            created_by=str(UUID(int=4)),
        )
    assert caught.value.status_code == status
    assert caught.value.detail["code"] == code
    repo.get_by_idempotency_key.assert_awaited_once_with(
        db, idempotency_key="fixture-currency-new-write"
    )
    _assert_no_financial_io(db, repo)


def test_saved_currency_accepts_ugx_kes_and_legal_trailing_zeros():
    for currency, amount in (
        ("UGX", "100"),
        ("UGX", "100.0000"),
        ("KES", "100.25"),
        ("KES", "100.2500"),
    ):
        _validate_order_payment_amount(_order(currency), Decimal(amount))


@pytest.mark.asyncio
async def test_missing_saved_currency_refuses_new_write_without_economic_io():
    await _assert_new_write_refused(None, "100", 409, "PAYMENT_CURRENCY_UNVERIFIED")


@pytest.mark.asyncio
async def test_unknown_saved_currency_refuses_new_write_without_economic_io():
    await _assert_new_write_refused("ZZZ", "100", 409, "PAYMENT_CURRENCY_UNVERIFIED")


@pytest.mark.asyncio
async def test_ugx_nonzero_fraction_refuses_new_write_without_economic_io():
    await _assert_new_write_refused("UGX", "10.1", 400, "PAYMENT_AMOUNT_PRECISION")


@pytest.mark.asyncio
async def test_kes_excess_precision_refuses_new_write_without_economic_io():
    await _assert_new_write_refused("KES", "10.001", 400, "PAYMENT_AMOUNT_PRECISION")


@pytest.mark.asyncio
async def test_legacy_null_currency_allows_only_exact_zero_write_replay():
    order = _order(None)
    existing = {
        "id": UUID(int=5),
        "order_id": order.id,
        "retailer_id": order.retailer_id,
        "amount": Decimal("40.00"),
        "method": "cash",
        "transaction_id": None,
        "idempotency_key": "fixture-currency-legacy-replay",
    }
    service, db, repo = _read_only_io(existing)
    arguments = dict(
        db=db,
        order=order,
        amount=Decimal("40.000"),
        method="cash",
        transaction_id=None,
        idempotency_key="fixture-currency-legacy-replay",
        created_by=str(UUID(int=4)),
    )
    replay = await service._confirm_payment_for_locked_order(**arguments)
    assert replay.replayed is True
    assert replay.order is order
    assert replay.payment_record is existing
    repo.get_by_idempotency_key.assert_awaited_once_with(
        db, idempotency_key="fixture-currency-legacy-replay"
    )
    _assert_no_financial_io(db, repo)

    with pytest.raises(HTTPException) as mismatch:
        await service._confirm_payment_for_locked_order(
            **dict(arguments, amount=Decimal("41.00"))
        )
    assert mismatch.value.status_code == 409
    assert mismatch.value.detail["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    _assert_no_financial_io(db, repo)

    existing["retailer_id"] = UUID(int=6)
    with pytest.raises(HTTPException) as attribution:
        await service._confirm_payment_for_locked_order(**arguments)
    assert attribution.value.status_code == 409
    assert attribution.value.detail["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    _assert_no_financial_io(db, repo)
