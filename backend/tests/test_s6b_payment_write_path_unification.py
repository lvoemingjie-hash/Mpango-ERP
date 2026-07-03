"""S6-B payment write-path unification gate tests."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from api.v1.payments import create_payment
from schemas.payment import PaymentCreateRequest, PaymentMethod


class _Token:
    user_id = str(uuid.uuid4())


class _NoWriteSession:
    """Fails if the disabled legacy route attempts DB side effects."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute(self, *args, **kwargs):
        self.calls.append("execute")
        raise AssertionError("POST /payments must not touch the database")

    async def flush(self, *args, **kwargs):
        self.calls.append("flush")
        raise AssertionError("POST /payments must not flush writes")

    async def commit(self, *args, **kwargs):
        self.calls.append("commit")
        raise AssertionError("POST /payments must not commit writes")

    async def rollback(self, *args, **kwargs):
        self.calls.append("rollback")
        raise AssertionError("POST /payments must not need rollback")


@pytest.mark.asyncio
async def test_legacy_payments_post_is_disabled_before_any_db_side_effect():
    db = _NoWriteSession()

    with pytest.raises(HTTPException) as exc_info:
        await create_payment(
            request_body=PaymentCreateRequest(
                order_id=str(uuid.uuid4()),
                amount=Decimal("100.00"),
                method=PaymentMethod.transfer,
                transaction_id="S6B-TRANSFER-1",
            ),
            token=_Token(),
            tenant_db=db,
            idempotency_key=None,
            x_idempotency_key="s6b-transfer-1",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "code": "PAYMENT_WRITE_PATH_DISABLED",
        "message": "Use POST /api/v1/orders/{order_id}/pay so order status and ledger stay consistent.",
    }
    assert db.calls == []
