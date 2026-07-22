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


class _FakeBegin:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_b6_create_payment_route_is_disabled_before_service_call(monkeypatch):
    req = PaymentCreateRequest(
        order_id=str(uuid.uuid4()),
        amount=Decimal("10.00"),
        method=PaymentMethod.transfer,
        transaction_id="QWE12345",
    )

    async def _forbidden_service_call(*args, **kwargs):
        raise AssertionError("POST /payments must not call PaymentService.create_payment")

    monkeypatch.setattr(PaymentService, "create_payment", _forbidden_service_call)

    class _Token:
        user_id = str(uuid.uuid4())

    with pytest.raises(HTTPException) as exc:
        await create_payment(
            request_body=req,
            token=_Token(),
            tenant_db=None,
            idempotency_key=None,
            x_idempotency_key=None,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == {
        "code": "PAYMENT_WRITE_PATH_DISABLED",
        "message": "Use POST /api/v1/orders/{order_id}/pay so order status and ledger stay consistent.",
    }


@pytest.mark.asyncio
async def test_b6_idempotency_key_idempotent_same_payload():
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

    class _DB:
        async def execute(self, *args, **kwargs):
            return await _execute(*args, **kwargs)

        def begin(self):
            return _FakeBegin()

    tenant_db = _DB()

    created = {
        "id": uuid.uuid4(),
        "order_id": order.id,
        "retailer_id": order.retailer_id,
        "transaction_id": "QWE12345",
        "idempotency_key": "IK-123",
        "amount": Decimal("10.00"),
        "method": "transfer",
        "status": "completed",
        "created_at": None,
        "updated_at": None,
    }

    calls = {"get": 0}

    async def _get_by_idempotency_key(db, *, idempotency_key: str):
        calls["get"] += 1
        if calls["get"] == 1:
            return None
        return created

    async def _create(*args, **kwargs):
        return created

    service._repo.get_by_idempotency_key = _get_by_idempotency_key  # type: ignore[attr-defined]
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
        idempotency_key="IK-123",
        created_by=str(uuid.uuid4()),
    )
    second = await service.create_payment(
        tenant_db=tenant_db,
        order_id=str(order.id),
        amount=Decimal("10.00"),
        method="transfer",
        transaction_id="QWE12345",
        idempotency_key="IK-123",
        created_by=str(uuid.uuid4()),
    )

    assert first["id"] == created["id"]
    assert second["id"] == created["id"]


@pytest.mark.asyncio
async def test_b6_idempotency_key_conflict_returns_409():
    service = PaymentService()

    existing = {
        "id": uuid.uuid4(),
        "order_id": uuid.uuid4(),
        "retailer_id": uuid.uuid4(),
        "transaction_id": "QWE12345",
        "idempotency_key": "IK-123",
        "amount": Decimal("9.00"),
        "method": "transfer",
        "status": "completed",
        "created_at": None,
        "updated_at": None,
    }

    async def _get_by_idempotency_key(db, *, idempotency_key: str):
        return existing

    service._repo.get_by_idempotency_key = _get_by_idempotency_key  # type: ignore[attr-defined]

    class _DB:
        def begin(self):
            return _FakeBegin()

    tenant_db = _DB()

    with pytest.raises(HTTPException) as exc:
        await service.create_payment(
            tenant_db=tenant_db,
            order_id=str(existing["order_id"]),
            amount=Decimal("10.00"),
            method="transfer",
            transaction_id="QWE12345",
            idempotency_key="IK-123",
            created_by=str(uuid.uuid4()),
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_b6_cash_does_not_update_outstanding_balance():
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

    class _DB:
        async def execute(self, *args, **kwargs):
            return await _execute(*args, **kwargs)

        def begin(self):
            return _FakeBegin()

    tenant_db = _DB()

    async def _get_by_idempotency_key(db, *, idempotency_key: str):
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

    service._repo.get_by_idempotency_key = _get_by_idempotency_key  # type: ignore[attr-defined]
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
        idempotency_key=None,
        created_by=str(uuid.uuid4()),
    )

    assert payment["id"] == created["id"]
    assert apply_called["count"] == 0
