import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from services.payment_service import PaymentService


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _TxnRecorder:
    """Tracks whether begin() was called on the session."""
    def __init__(self):
        self.entered = 0
        self.exited = 0
        self.exited_with_exception = 0

    def begin(self):
        recorder = self

        class _Begin:
            async def __aenter__(self_inner):
                recorder.entered += 1
                return self_inner

            async def __aexit__(self_inner, exc_type, exc, tb):
                recorder.exited += 1
                if exc_type is not None:
                    recorder.exited_with_exception += 1
                return False

        return _Begin()


def _make_db(scalar_result, txn=None):
    """Build a minimal fake DB session for payment tests."""
    txn = txn or _TxnRecorder()

    class _DB:
        async def execute(self, *args, **kwargs):
            return scalar_result

        def begin(self):
            return txn.begin()

    return _DB(), txn


@pytest.mark.asyncio
async def test_create_payment_does_not_open_nested_transaction():
    """
    After the nested-transaction fix, create_payment must NOT call
    tenant_db.begin().  Transaction lifecycle is owned by the
    get_tenant_db() dependency generator.
    """
    service = PaymentService()

    order = type(
        "_Order",
        (),
        {
            "id": uuid.uuid4(),
            "retailer_id": uuid.uuid4(),
            "wholesaler_id": uuid.uuid4(),
            "is_deleted": False,
        },
    )()

    async def _execute(*args, **kwargs):
        return _FakeScalarResult(order)

    txn = _TxnRecorder()

    class _DB:
        async def execute(self, *args, **kwargs):
            return await _execute(*args, **kwargs)

        def begin(self):
            return txn.begin()

    tenant_db = _DB()

    async def _get_by_idempotency_key(db, *, idempotency_key: str):
        return None

    created = {
        "id": uuid.uuid4(),
        "order_id": order.id,
        "retailer_id": order.retailer_id,
        "transaction_id": "TX-OK",
        "amount": Decimal("50.00"),
        "method": "cash",
        "status": "pending",
        "created_at": None,
        "updated_at": None,
    }

    async def _create(*args, **kwargs):
        return created

    balance_deltas = []

    async def _apply(db, *, wholesaler_id, retailer_id, delta):
        balance_deltas.append(delta)

    service._repo.create = _create  # type: ignore[attr-defined]
    service._repo.get_by_idempotency_key = _get_by_idempotency_key  # type: ignore[attr-defined]
    service._apply_outstanding_balance_delta = _apply  # type: ignore[assignment]

    result = await service.create_payment(
        tenant_db=tenant_db,
        order_id=str(order.id),
        amount=Decimal("50.00"),
        method="cash",
        transaction_id="TX-OK",
        idempotency_key=None,
        created_by=str(uuid.uuid4()),
    )

    assert result["method"] == "cash"
    assert result["amount"] == Decimal("50.00")
    # begin() must NOT have been called — transaction is managed externally
    assert txn.entered == 0
    # Outstanding balance delta applied for cash payment
    assert balance_deltas == [Decimal("-50.00")]


@pytest.mark.asyncio
async def test_create_payment_propagates_balance_update_failure():
    """
    If _apply_outstanding_balance_delta fails the exception propagates
    so the caller's session manager (get_tenant_db) can roll back.
    """
    service = PaymentService()

    order = type(
        "_Order",
        (),
        {
            "id": uuid.uuid4(),
            "retailer_id": uuid.uuid4(),
            "wholesaler_id": uuid.uuid4(),
            "is_deleted": False,
        },
    )()

    async def _execute(*args, **kwargs):
        return _FakeScalarResult(order)

    txn = _TxnRecorder()

    class _DB:
        async def execute(self, *args, **kwargs):
            return await _execute(*args, **kwargs)

        def begin(self):
            return txn.begin()

    tenant_db = _DB()

    async def _get_by_idempotency_key(db, *, idempotency_key: str):
        return None

    created = {
        "id": uuid.uuid4(),
        "order_id": order.id,
        "retailer_id": order.retailer_id,
        "transaction_id": "TX-FAIL",
        "amount": Decimal("10.00"),
        "method": "transfer",
        "status": "completed",
        "created_at": None,
        "updated_at": None,
    }

    async def _create(*args, **kwargs):
        return created

    service._repo.create = _create  # type: ignore[attr-defined]
    service._repo.get_by_idempotency_key = _get_by_idempotency_key  # type: ignore[attr-defined]

    async def _apply(*args, **kwargs):
        raise HTTPException(
            status_code=500,
            detail={"code": "FORCED_FAILURE", "message": "forced failure for atomicity test"},
        )

    service._apply_outstanding_balance_delta = _apply  # type: ignore[assignment]

    with pytest.raises(HTTPException) as exc:
        await service.create_payment(
            tenant_db=tenant_db,
            order_id=str(order.id),
            amount=Decimal("10.00"),
            method="transfer",
            transaction_id="TX-FAIL",
            idempotency_key="IK-FAIL",
            created_by=str(uuid.uuid4()),
        )

    assert exc.value.detail["code"] == "FORCED_FAILURE"

    # begin() must NOT have been called after the fix
    assert txn.entered == 0
