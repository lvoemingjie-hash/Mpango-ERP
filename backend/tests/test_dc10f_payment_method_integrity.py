from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError


class _FakeToken:
    user_id = uuid.uuid4()


class _HttpFakeToken:
    user_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    tenant_schema = "t_test"
    type = "access"
    roles = ["super_admin"]

    @property
    def is_identity_only(self) -> bool:
        return False

    @property
    def is_super_admin(self) -> bool:
        return True


def _confirmed_order(total: Decimal = Decimal("5000")) -> MagicMock:
    order = MagicMock()
    order.id = uuid.uuid4()
    order.retailer_id = uuid.uuid4()
    order.wholesaler_id = uuid.uuid4()
    order.total_amount = total
    order.status.value = "confirmed"
    return order


@pytest.mark.asyncio
async def test_invalid_pay_order_method_is_rejected_before_financial_side_effects():
    from api.v1.orders import pay_order
    from core.domain.order_state import OrderState
    from schemas.order import PayOrderRequest

    order = _confirmed_order()
    payment_input = PayOrderRequest.model_construct(
        amount=Decimal("5000"),
        method="banana",
        transaction_id=None,
        notes=None,
    )

    with patch("api.v1.orders.get_order_by_id", new_callable=AsyncMock, return_value=order), \
         patch("repositories.payment_repository.PaymentRepository") as MockRepo, \
         patch("services.order_service.OrderService") as MockOrderService, \
         patch("services.payment_service.PaymentService._apply_outstanding_balance_delta", new_callable=AsyncMock) as apply_delta:

        repo = AsyncMock()
        repo.get_order_paid_total = AsyncMock(return_value=Decimal("0"))
        repo.count_order_payments = AsyncMock(return_value=0)
        repo.create = AsyncMock(return_value={
            "id": uuid.uuid4(),
            "amount": Decimal("5000"),
            "method": "banana",
        })
        MockRepo.return_value = repo

        order_service = AsyncMock()
        order_service.transition = AsyncMock(return_value=MagicMock(
            id=order.id,
            status=OrderState.PAID,
            total_amount=order.total_amount,
        ))
        MockOrderService.return_value = order_service

        with pytest.raises(HTTPException) as exc_info:
            await pay_order(
                order_id=str(order.id),
                token=_FakeToken(),
                db=MagicMock(),
                payment_input=payment_input,
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == {
        "code": "INVALID_PAYMENT_METHOD",
        "message": "Payment method must be one of: cash, transfer, credit",
    }
    repo.get_order_paid_total.assert_not_awaited()
    repo.create.assert_not_awaited()
    apply_delta.assert_not_awaited()
    order_service.transition.assert_not_awaited()


def test_pay_order_request_rejects_non_canonical_method():
    from schemas.order import PayOrderRequest

    with pytest.raises(ValidationError):
        PayOrderRequest(amount=Decimal("5000"), method="banana")


def test_pay_order_request_accepts_canonical_payment_methods():
    from schemas.order import PayOrderRequest
    from schemas.payment import PaymentMethod

    for method in PaymentMethod:
        req = PayOrderRequest(amount=Decimal("5000"), method=method.value)
        assert req.method == method


def test_http_pay_order_rejects_banana_method_without_financial_side_effects():
    from api.dependencies import get_tenant_db_session
    from api.middleware import rbac as rbac_module
    from main import app
    from fastapi.testclient import TestClient

    token = _HttpFakeToken()
    test_db = MagicMock()
    test_db.info = {"tenant_id": token.tenant_id, "tenant_schema": token.tenant_schema}

    original_get_auth_context = rbac_module.get_auth_context

    def _fake_auth_context(_request):
        return SimpleNamespace(token=token)

    def _fake_tenant_db_session():
        return test_db

    rbac_module.get_auth_context = _fake_auth_context
    app.dependency_overrides[get_tenant_db_session] = _fake_tenant_db_session
    try:
        client = TestClient(app, raise_server_exceptions=False)
        with patch("api.v1.orders.get_order_by_id", new_callable=AsyncMock) as get_order, \
             patch("repositories.payment_repository.PaymentRepository") as PaymentRepository, \
             patch("services.payment_service.PaymentService._apply_outstanding_balance_delta", new_callable=AsyncMock) as apply_delta, \
             patch("services.order_service.OrderService") as OrderService:
            response = client.post(
                f"/api/v1/orders/{uuid.uuid4()}/pay?request=test",
                json={"amount": "5000.00", "method": "banana"},
            )
    finally:
        rbac_module.get_auth_context = original_get_auth_context
        app.dependency_overrides.pop(get_tenant_db_session, None)

    assert 400 <= response.status_code < 500, response.text
    assert "traceback" not in response.text.lower()
    assert "banana" in response.text

    get_order.assert_not_awaited()
    PaymentRepository.assert_not_called()
    apply_delta.assert_not_awaited()
    OrderService.assert_not_called()
