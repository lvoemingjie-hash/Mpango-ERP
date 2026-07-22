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


@pytest.mark.asyncio
async def test_b6_create_payment_rollback_on_balance_update_failure():
    """Failure propagates so the caller-owned session lifecycle can roll back."""
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
        "transaction_id": None,
        "amount": Decimal("10.00"),
        "method": "credit",
        "status": "pending",
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
            method="credit",
            transaction_id=None,
            idempotency_key="IK-FAIL",
            created_by=str(uuid.uuid4()),
        )

    assert exc.value.detail["code"] == "FORCED_FAILURE"

    assert txn.entered == 0
    assert txn.exited == 0
    assert txn.exited_with_exception == 0
