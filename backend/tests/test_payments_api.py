import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from api.v1.payments import create_payment
from schemas.payment import PaymentCreateRequest, PaymentMethod
from services.payment_service import PaymentService


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@pytest.mark.asyncio
async def test_transfer_requires_idempotency_key():
    req = PaymentCreateRequest(
        order_id=str(uuid.uuid4()),
        amount=Decimal("10.00"),
        method=PaymentMethod.transfer,
        transaction_id="QWE12345",
    )

    class _Token:
        user_id = str(uuid.uuid4())

    with pytest.raises(HTTPException) as exc:
        await create_payment(
            request_body=req,
            request=None,  # not used
            token=_Token(),
            tenant_db=None,
            idempotency_key=None,
            x_idempotency_key=None,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "MISSING_IDEMPOTENCY_KEY"


@pytest.mark.asyncio
async def test_transaction_id_idempotent_same_payload():
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

    tenant_db = type("_DB", (), {"execute": _execute})()

    created = {
        "id": uuid.uuid4(),
        "order_id": order.id,
        "retailer_id": order.retailer_id,
        "transaction_id": "QWE12345",
        "amount": Decimal("10.00"),
        "method": "transfer",
        "status": "completed",
        "created_at": None,
        "updated_at": None,
    }

    calls = {"get": 0}

    async def _get_by_transaction_id(db, *, transaction_id: str):
        calls["get"] += 1
        if calls["get"] == 1:
            return None
        return created

    async def _create(*args, **kwargs):
        return created

    service._repo.get_by_transaction_id = _get_by_transaction_id  # type: ignore[attr-defined]
    service._repo.create = _create  # type: ignore[attr-defined]

    async def _apply(*args, **kwargs):
        return None

    service._apply_outstanding_balance_delta = _apply  # type: ignore[assignment]

    first = await service.create_payment(
        tenant_db=tenant_db,
        order_id=str(order.id),
        amount=Decimal("10.00"),
        method="transfer",
        transaction_id="QWE12345",
        created_by=str(uuid.uuid4()),
    )
    second = await service.create_payment(
        tenant_db=tenant_db,
        order_id=str(order.id),
        amount=Decimal("10.00"),
        method="transfer",
        transaction_id="QWE12345",
        created_by=str(uuid.uuid4()),
    )

    assert first["id"] == created["id"]
    assert second["id"] == created["id"]


@pytest.mark.asyncio
async def test_transaction_id_conflict_returns_409():
    service = PaymentService()

    existing = {
        "id": uuid.uuid4(),
        "order_id": uuid.uuid4(),
        "retailer_id": uuid.uuid4(),
        "transaction_id": "QWE12345",
        "amount": Decimal("9.00"),
        "method": "transfer",
        "status": "completed",
        "created_at": None,
        "updated_at": None,
    }

    async def _get_by_transaction_id(db, *, transaction_id: str):
        return existing

    service._repo.get_by_transaction_id = _get_by_transaction_id  # type: ignore[attr-defined]

    tenant_db = object()

    with pytest.raises(HTTPException) as exc:
        await service.create_payment(
            tenant_db=tenant_db,
            order_id=str(existing["order_id"]),
            amount=Decimal("10.00"),
            method="transfer",
            transaction_id="QWE12345",
            created_by=str(uuid.uuid4()),
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "DUPLICATE_TRANSACTION_ID"


@pytest.mark.asyncio
async def test_cash_does_not_update_outstanding_balance():
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

    tenant_db = type("_DB", (), {"execute": _execute})()

    async def _get_by_transaction_id(db, *, transaction_id: str):
        return None

    created = {
        "id": uuid.uuid4(),
        "order_id": order.id,
        "retailer_id": order.retailer_id,
        "transaction_id": None,
        "amount": Decimal("10.00"),
        "method": "cash",
        "status": "pending",
        "created_at": None,
        "updated_at": None,
    }

    async def _create(*args, **kwargs):
        return created

    service._repo.get_by_transaction_id = _get_by_transaction_id  # type: ignore[attr-defined]
    service._repo.create = _create  # type: ignore[attr-defined]

    apply_called = {"count": 0}

    async def _apply(*args, **kwargs):
        apply_called["count"] += 1

    service._apply_outstanding_balance_delta = _apply  # type: ignore[assignment]

    payment = await service.create_payment(
        tenant_db=tenant_db,
        order_id=str(order.id),
        amount=Decimal("10.00"),
        method="cash",
        transaction_id=None,
        created_by=str(uuid.uuid4()),
    )

    assert payment["id"] == created["id"]
    assert apply_called["count"] == 0
