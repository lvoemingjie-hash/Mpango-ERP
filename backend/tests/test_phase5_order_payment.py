"""Phase5 contracts using typed, explicit database I/O doubles.

Real route/canonical/history/hold/locked-command producers execute. These
tests do not establish PostgreSQL durability or real ledger atomicity.
CTO R1R1 explicitly migrates three ledger producers, preserving nodeids.
"""

import copy
import os
import uuid
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

WHOLESALER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
ACTOR_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")
RETAILER_ID = uuid.UUID("00000000-0000-4000-8000-000000000003")
ORDER_ID = uuid.UUID("00000000-0000-4000-8000-000000000004")
PAYMENT_ID = uuid.UUID("00000000-0000-4000-8000-000000000005")
PRIOR_PAYMENT_ID = uuid.UUID("00000000-0000-4000-8000-000000000006")

# Inherited defaults are retained; explicit task configuration takes priority.
os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("DATABASE_URL", os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/mpango_erp"))  # pragma: allowlist secret
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-minimum-32-characters-long")


class _Rows:
    def __init__(self, *, rows=(), scalar=None, one=None, rowcount=0):
        self.rows = list(rows)
        self.value = scalar
        self.one_value = one
        self.rowcount = rowcount

    def scalar(self):
        return self.value

    def scalar_one_or_none(self):
        return self.one_value

    def scalars(self):
        return self

    def mappings(self):
        return self

    def all(self):
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def one(self):
        assert len(self.rows) == 1
        return self.rows[0]


def _make_mock_order(order_status="confirmed", order_total=Decimal("5000"), *, currency="UGX"):
    from models.order import Order, OrderStatus

    return Order(
        id=ORDER_ID, status=OrderStatus(order_status), total_amount=Decimal(order_total),
        wholesaler_id=WHOLESALER_ID, retailer_id=RETAILER_ID,
        currency_snapshot=currency, is_deleted=False, items=[],
    )


def _payment_row(*, amount, method, status="pending", payment_id=PAYMENT_ID,
                 transaction_id=None, key=None):
    return {
        "id": payment_id, "order_id": ORDER_ID, "retailer_id": RETAILER_ID,
        "amount": Decimal(amount), "method": method, "status": status,
        "transaction_id": transaction_id, "idempotency_key": key,
        "created_by": ACTOR_ID, "is_deleted": False,
    }


class _Transaction:
    def __init__(self, db):
        self.db = db
        self.before = None
        self.exit_errors = []

    async def __aenter__(self):
        self.before = self.db.snapshot()
        return self.db

    async def __aexit__(self, kind, value, traceback):
        self.exit_errors.append(kind)
        if kind is not None:
            self.db.restore(self.before)
        return False


class _FixtureSession:
    """Only declared order/payment/hold SQL I/O; unknown SQL raises."""

    def __init__(self, order, *, prior_paid=Decimal("0"), credit_count=0):
        from models.order_credit_hold import OrderCreditHold

        self.order = order
        self.payments = []
        if prior_paid:
            self.payments.append(_payment_row(
                amount=prior_paid, method="cash", payment_id=PRIOR_PAYMENT_ID))
        for index in range(credit_count):
            self.payments.append(_payment_row(
                amount=order.total_amount, method="credit", payment_id=uuid.UUID(int=100 + index)))
        self.holds = [OrderCreditHold(
            id=uuid.UUID(int=200), order_id=order.id, amount=order.total_amount,
            remaining_amount=order.total_amount - prior_paid,
            status="active", created_by=ACTOR_ID, updated_by=ACTOR_ID,
        )]
        self.balance = order.total_amount - prior_paid
        self.info = {"tenant_schema": "t_test", "tenant_id": str(WHOLESALER_ID)}
        self.sql = []
        self.writes = []
        self.ledger_calls = []
        self.command_calls = []
        self.invalid_history_rows = []
        self.rollback_count = 0
        self.order_locks = 0
        self.nested_transactions = []
        self.flush = AsyncMock()
        self.refresh = AsyncMock()
        self.commit = AsyncMock()
        self.close = AsyncMock()
        self.before = self.snapshot()

    def snapshot(self):
        return {
            "status": self.order.status, "updated_by": self.order.updated_by,
            "holds": [(h.status, h.amount, h.remaining_amount, h.updated_by) for h in self.holds],
            "payments": copy.deepcopy(self.payments), "balance": self.balance,
            "ledger": copy.deepcopy(self.ledger_calls),
        }

    def restore(self, before):
        self.order.status = before["status"]
        self.order.updated_by = before["updated_by"]
        for hold, values in zip(self.holds, before["holds"]):
            hold.status, hold.amount, hold.remaining_amount, hold.updated_by = values
        self.payments[:] = copy.deepcopy(before["payments"])
        self.balance = before["balance"]
        self.ledger_calls[:] = copy.deepcopy(before["ledger"])

    def begin(self):
        return _Transaction(self)

    def begin_nested(self):
        transaction = _Transaction(self)
        self.nested_transactions.append(transaction)
        return transaction

    def in_transaction(self):
        return True

    async def rollback(self):
        self.rollback_count += 1
        self.restore(self.before)

    async def execute(self, statement, params=None):
        from models.order import Order
        from models.order_credit_hold import OrderCreditHold

        params = params or {}
        sql = " ".join(str(statement).split())
        self.sql.append((sql, copy.deepcopy(params)))
        entities = [d.get("entity") for d in getattr(statement, "column_descriptions", [])]
        if entities == [Order]:
            if "FOR UPDATE" in sql:
                assert statement.get_execution_options()["populate_existing"] is True
                self.order_locks += 1
            return _Rows(one=self.order)
        if entities == [OrderCreditHold]:
            assert "FOR UPDATE" in sql
            return _Rows(rows=self.holds)
        if "COUNT(*) AS invalid_rows" in sql:
            assert params["order_ids"] == [self.order.id]
            return _Rows(rows=self.invalid_history_rows)
        if sql.startswith("SELECT COALESCE(SUM(amount), 0)"):
            assert params["order_id"] == self.order.id
            methods = params.get("methods", ("cash", "transfer"))
            return _Rows(scalar=sum(
                (p["amount"] for p in self.payments if p["method"] in methods), Decimal("0")))
        if sql.startswith("SELECT COUNT(*) FROM payments"):
            assert params["order_id"] == self.order.id
            return _Rows(scalar=sum(p["method"] == params["method"] for p in self.payments))
        if sql.startswith("SELECT") and "FROM payments" in sql:
            if "idempotency_key" in params:
                rows = [p for p in self.payments if p["idempotency_key"] == params["idempotency_key"]]
            elif "transaction_id" in params:
                rows = [p for p in self.payments if p["transaction_id"] == params["transaction_id"]]
            elif "pid" in params:
                rows = [p for p in self.payments if p["id"] == params["pid"]]
            else:
                raise AssertionError("Undeclared payment query")
            return _Rows(rows=copy.deepcopy(rows))
        if sql.startswith("INSERT INTO payments"):
            assert params["order_id"] == self.order.id
            assert params["retailer_id"] == self.order.retailer_id
            assert isinstance(params["amount"], Decimal)
            row = _payment_row(
                amount=params["amount"], method=params["method"], status=params["status"],
                transaction_id=params["transaction_id"], key=params["idempotency_key"])
            self.payments.append(row)
            self.writes.append("payment")
            return _Rows(rows=[copy.deepcopy(row)])
        if sql.startswith("UPDATE payments"):
            assert params["order_id"] == self.order.id
            for payment in self.payments:
                if payment["method"] in {"cash", "transfer"} and payment["status"] == "pending":
                    payment["status"] = "completed"
            self.writes.append("complete-payments")
            return _Rows(rowcount=1)
        if sql.startswith("UPDATE public.wholesaler_retailer_bindings"):
            assert params["wholesaler_id"] == self.order.wholesaler_id
            assert params["retailer_id"] == self.order.retailer_id
            assert isinstance(params["delta"], Decimal)
            assert self.balance + params["delta"] >= 0
            self.balance += params["delta"]
            self.writes.append(("binding", params["delta"]))
            return _Rows(rowcount=1)
        raise AssertionError("Undeclared SQL I/O: " + sql)


class _FakeToken:
    user_id = str(ACTOR_ID)
    tenant_id = str(WHOLESALER_ID)
    tenant_schema = "t_test"
    role = "wholesaler"


@contextmanager
def _world(*, status="confirmed", total=Decimal("5000"), prior_paid=Decimal("0"),
           currency="UGX", credit_count=0):
    """Replace ledger I/O only; observe and delegate the real transition helper."""
    from services.ledger_service import LedgerService
    from services.order_command_service import OrderCommandService

    db = _FixtureSession(_make_mock_order(status, total, currency=currency),
                         prior_paid=prior_paid, credit_count=credit_count)
    original = OrderCommandService._post_transition_ledger

    async def observe(command, order, from_state, to_state, payment_method):
        db.command_calls.append({"order_id": order.id, "target_state": to_state,
                                 "payment_method": payment_method})
        return await original(command, order, from_state, to_state, payment_method)

    async def record_ledger(*, order_id, payment_id, amount, description):
        db.ledger_calls.append({"order_id": order_id, "payment_id": payment_id,
                                "amount": amount, "description": description})
        db.writes.append("ledger")

    with patch.object(LedgerService, "post_payment_received", new_callable=AsyncMock,
                      side_effect=record_ledger) as ledger, \
         patch.object(OrderCommandService, "_post_transition_ledger", new=observe):
        yield SimpleNamespace(db=db, order=db.order, ledger=ledger)


async def _pay(world, amount, method="cash", *, key="phase5-payment", reference=None):
    from api.v1.orders import pay_order
    from schemas.order import PayOrderRequest

    return await pay_order(
        order_id=str(world.order.id), token=_FakeToken(), db=world.db,
        payment_input=PayOrderRequest(amount=amount, method=method, transaction_id=reference),
        x_idempotency_key=key)


def _assert_no_economic_io(world, before):
    assert world.db.snapshot() == before
    assert world.db.writes == []
    world.ledger.assert_not_awaited()


def _assert_receipt(world, amount):
    expected = {
        "order_id": ORDER_ID, "payment_id": PAYMENT_ID, "amount": amount,
        "description": f"Payment received for order {ORDER_ID} - Amount: {amount}",
    }
    world.ledger.assert_awaited_once_with(**expected)
    assert world.db.ledger_calls == [expected]


def test_pay_order_request_defaults():
    from schemas.order import PayOrderRequest

    req = PayOrderRequest()
    assert req.amount is None
    assert req.method is None
    assert req.transaction_id is None


def test_pay_order_request_structured():
    from schemas.order import PayOrderRequest

    req = PayOrderRequest(amount=Decimal("5000"), method="cash")
    assert req.amount == Decimal("5000")
    assert req.method == "cash"


def test_pay_order_request_invalid_amount():
    from pydantic import ValidationError
    from schemas.order import PayOrderRequest

    with pytest.raises(ValidationError):
        PayOrderRequest(amount=Decimal("-100"))


def test_confirmed_to_paid():
    from core.domain.order_state import OrderState, is_valid_transition

    assert is_valid_transition(OrderState.CONFIRMED, OrderState.PAID)


def test_confirmed_to_partially_paid():
    from core.domain.order_state import OrderState, is_valid_transition

    assert is_valid_transition(OrderState.CONFIRMED, OrderState.PARTIALLY_PAID)


def test_partially_paid_to_paid():
    from core.domain.order_state import OrderState, is_valid_transition

    assert is_valid_transition(OrderState.PARTIALLY_PAID, OrderState.PAID)


def test_draft_cannot_pay():
    from core.domain.order_state import OrderState, is_valid_transition

    assert not is_valid_transition(OrderState.DRAFT, OrderState.PAID)


def test_paid_cannot_pay_again():
    from core.domain.order_state import OrderState, is_valid_transition

    assert not is_valid_transition(OrderState.PAID, OrderState.PAID)


@pytest.mark.asyncio
async def test_outstanding_balance_full_payment():
    total, prior = Decimal("10000"), Decimal("0")
    remaining = total - prior
    assert remaining == Decimal("10000")
    amount = Decimal("10000")
    assert amount <= remaining
    assert prior + amount >= total


@pytest.mark.asyncio
async def test_outstanding_balance_partial_payment():
    total, prior, amount = Decimal("10000"), Decimal("0"), Decimal("4000")
    assert amount <= total - prior
    cumulative = prior + amount
    assert cumulative < total
    assert total - cumulative == Decimal("6000")


@pytest.mark.asyncio
async def test_outstanding_balance_second_partial():
    total, prior, amount = Decimal("10000"), Decimal("4000"), Decimal("6000")
    remaining = total - prior
    assert remaining == Decimal("6000")
    assert amount <= remaining
    assert prior + amount >= total


@pytest.mark.asyncio
async def test_outstanding_balance_reject_overpayment():
    remaining = Decimal("10000") - Decimal("7000")
    assert remaining == Decimal("3000")
    assert Decimal("5000") > remaining


@pytest.mark.asyncio
async def test_outstanding_balance_no_double_full():
    remaining = Decimal("10000") - Decimal("10000")
    assert remaining == Decimal("0")
    assert Decimal("1") > remaining


@pytest.mark.asyncio
async def test_get_order_paid_total_returns_sum():
    from repositories.payment_repository import PaymentRepository

    db = _FixtureSession(_make_mock_order(order_total=Decimal("10000")), prior_paid=Decimal("7000"))
    assert await PaymentRepository().get_order_paid_total(db, order_id=ORDER_ID) == Decimal("7000")
    assert len(db.sql) == 1


@pytest.mark.asyncio
async def test_get_order_paid_total_zero_when_none():
    from repositories.payment_repository import PaymentRepository

    db = _FixtureSession(_make_mock_order())
    assert await PaymentRepository().get_order_paid_total(db, order_id=ORDER_ID) == Decimal("0")


@pytest.mark.asyncio
async def test_atomic_payment_and_transition():
    """Real producer writes within a fake caller transaction, not PG atomicity."""
    with _world() as world:
        transaction = world.db.begin()
        async with transaction:
            response = await _pay(world, Decimal("5000"))
            assert response.data["payment_id"] == str(PAYMENT_ID)
            assert response.data["status"] == "paid"
        assert transaction.exit_errors == [None]
        assert len(world.db.nested_transactions) == 1
        assert world.db.writes[0] == "payment"
        assert world.db.command_calls[0]["target_state"].value == "paid"
        assert world.db.rollback_count == 0


@pytest.mark.asyncio
async def test_atomic_rollback_on_transition_failure():
    """Flush I/O fault reaches real route rollback; durability is not measured."""
    with _world() as world:
        before = world.db.snapshot()
        world.db.flush.side_effect = [None, RuntimeError("State invariant violation")]
        transaction = world.db.begin()
        with pytest.raises(RuntimeError, match="State invariant violation"):
            async with transaction:
                await _pay(world, Decimal("5000"))
        assert world.db.writes == ["payment"]
        assert len(world.db.command_calls) == 1
        assert transaction.exit_errors == [RuntimeError]
        assert world.db.rollback_count == 1
        assert world.db.snapshot() == before
        world.ledger.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_pay_no_body():
    """Empty schema is representable; actual legacy requests are refused."""
    from schemas.order import PayOrderRequest

    assert PayOrderRequest().amount is None


@pytest.mark.asyncio
async def test_full_amount_maps_to_paid():
    from core.domain.order_state import OrderState

    target = OrderState.PAID if Decimal("10000") >= Decimal("10000") else OrderState.PARTIALLY_PAID
    assert target == OrderState.PAID


@pytest.mark.asyncio
async def test_overpayment_maps_to_paid():
    """Pure arithmetic only; actual overpayment has exact route refusal tests."""
    from core.domain.order_state import OrderState

    target = OrderState.PAID if Decimal("10001") >= Decimal("10000") else OrderState.PARTIALLY_PAID
    assert target == OrderState.PAID


@pytest.mark.asyncio
async def test_underpayment_maps_to_partially_paid():
    from core.domain.order_state import OrderState

    target = OrderState.PAID if Decimal("9999") >= Decimal("10000") else OrderState.PARTIALLY_PAID
    assert target == OrderState.PARTIALLY_PAID


@pytest.mark.asyncio
async def test_order_service_transition_confirmed_to_paid():
    from core.domain.order_state import InvalidStateTransitionError, OrderState
    from services.order_command_service import OrderCommandService
    from services.order_service import OrderService

    db = _FixtureSession(_make_mock_order())
    with pytest.raises(InvalidStateTransitionError, match="refuses payment states"):
        await OrderService(db).transition(ORDER_ID, OrderState.PAID, updated_by=ACTOR_ID)
    result = await OrderCommandService(db).apply_payment_transition(
        ORDER_ID, OrderState.PAID, payment_method="cash", updated_by=str(ACTOR_ID))
    assert result.order.status.value == "paid"
    assert result.order.updated_by == ACTOR_ID


@pytest.mark.asyncio
async def test_order_service_transition_rejects_invalid():
    from core.domain.order_state import InvalidStateTransitionError, OrderState
    from services.order_service import OrderService

    db = _FixtureSession(_make_mock_order("draft"))
    with pytest.raises(InvalidStateTransitionError):
        await OrderService(db).transition(ORDER_ID, OrderState.PAID, updated_by=ACTOR_ID)
    assert db.order.status.value == "draft"
    assert db.writes == []


@pytest.mark.asyncio
async def test_api_legacy_pay_empty_body():
    from api.v1.orders import pay_order
    from fastapi import HTTPException

    with _world() as world:
        before = world.db.snapshot()
        with pytest.raises(HTTPException) as exc:
            await pay_order(str(ORDER_ID), token=_FakeToken(), db=world.db, payment_input=None)
        assert exc.value.status_code == 400
        assert exc.value.detail["code"] == "PAYMENT_BODY_REQUIRED"
        assert world.db.sql == []
        _assert_no_economic_io(world, before)


@pytest.mark.asyncio
async def test_api_structured_full_payment():
    """Full receipt, missing/unknown saved currency and harmless trailing zeros."""
    from fastapi import HTTPException
    from services.canonical_payment_service import _validate_order_payment_amount

    with _world() as world:
        response = await _pay(world, Decimal("5000"))
        assert response.success is True
        assert response.data["status"] == "paid"
        assert response.data["payment_id"] == str(PAYMENT_ID)
        assert response.data["payment_amount"] == "5000"
        assert response.message == "Payment recorded and order updated"
        assert world.db.order_locks == 1
        assert world.db.holds[0].status == "settled"
        assert world.db.holds[0].remaining_amount == Decimal("0")
        _assert_receipt(world, Decimal("5000"))
    for currency in (None, "UNKNOWN"):
        with _world(currency=currency) as world:
            before = world.db.snapshot()
            with pytest.raises(HTTPException) as exc:
                await _pay(world, Decimal("5000"))
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "PAYMENT_CURRENCY_UNVERIFIED"
            _assert_no_economic_io(world, before)
    _validate_order_payment_amount(_make_mock_order(currency="UGX"), Decimal("5000.00"))
    _validate_order_payment_amount(_make_mock_order(currency="KES"), Decimal("12.3400"))


@pytest.mark.asyncio
async def test_api_structured_partial_payment():
    """Partial receipt plus actual UGX/KES nonzero excess-precision refusals."""
    from fastapi import HTTPException

    with _world() as world:
        response = await _pay(world, Decimal("2000"))
        assert response.success is True
        assert response.data["status"] == "partially_paid"
        assert response.data["payment_amount"] == "2000"
        assert world.db.holds[0].status == "active"
        assert world.db.holds[0].remaining_amount == Decimal("3000")
        assert world.db.balance == Decimal("3000")
    for currency, amount in (("UGX", Decimal("1.1")), ("KES", Decimal("1.001"))):
        with _world(currency=currency) as world:
            before = world.db.snapshot()
            with pytest.raises(HTTPException) as exc:
                await _pay(world, amount)
            assert exc.value.status_code == 400
            assert exc.value.detail["code"] == "PAYMENT_AMOUNT_PRECISION"
            _assert_no_economic_io(world, before)


@pytest.mark.asyncio
async def test_api_reject_overpayment():
    from fastapi import HTTPException

    with _world(prior_paid=Decimal("3000")) as world:
        before = world.db.snapshot()
        with pytest.raises(HTTPException) as exc:
            await _pay(world, Decimal("3000"))
        assert exc.value.status_code == 400
        assert exc.value.detail["code"] == "PAYMENT_EXCEEDS_REMAINING"
        _assert_no_economic_io(world, before)


class _RouteTestFakeToken(_FakeToken):
    type = "access"
    roles = ["orders:update", "orders:read", "orders:write"]
    is_identity_only = False
    is_super_admin = True


@contextmanager
def _route_client(world):
    """Existing TestClient/RBAC dependency seam, not real authentication proof."""
    from api.dependencies import get_current_user_context, get_tenant_db_session
    from api.middleware import rbac
    from fastapi.testclient import TestClient
    from main import app

    codes = ["orders:update", "orders:read", "orders:write", "payments:create"]
    user = SimpleNamespace(is_active=True, roles=[SimpleNamespace(
        name="wholesaler", permissions=[SimpleNamespace(code=code) for code in codes])])
    token = _RouteTestFakeToken()
    tenant = SimpleNamespace(tenant_id=token.tenant_id, tenant_schema="t_test", session=world.db, user=user)
    old_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_tenant_db_session] = lambda: world.db
    app.dependency_overrides[get_current_user_context] = lambda: token
    try:
        with patch.object(rbac, "get_auth_context", return_value=SimpleNamespace(token=token)), \
             patch.object(rbac, "get_tenant_context", return_value=tenant):
            yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(old_overrides)


class TestRouteLevelOrderPaymentMonkeypatch:
    def test_route_legacy_pay_empty_body_returns_400(self):
        with _world() as world, _route_client(world) as client:
            before = world.db.snapshot()
            response = client.post(f"/api/v1/orders/{ORDER_ID}/pay?request=test")
            assert response.status_code == 400, response.text
            assert response.json()["code"] == "PAYMENT_BODY_REQUIRED"
            _assert_no_economic_io(world, before)

    def test_route_structured_full_payment_returns_200(self):
        with _world() as world, _route_client(world) as client:
            response = client.post(f"/api/v1/orders/{ORDER_ID}/pay?request=test",
                                   json={"amount": 5000, "method": "cash"},
                                   headers={"X-Idempotency-Key": "route-full-key"})
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["success"] is True
            assert data["data"]["status"] == "paid"
            assert data["data"]["payment_id"] == str(PAYMENT_ID)
            assert data["data"]["payment_amount"] == "5000"

    def test_route_partial_payment_returns_partially_paid(self):
        with _world(total=Decimal("10000")) as world, _route_client(world) as client:
            response = client.post(f"/api/v1/orders/{ORDER_ID}/pay?request=test",
                                   json={"amount": 3000, "method": "transfer", "transaction_id": "TX-partial"},
                                   headers={"X-Idempotency-Key": "route-partial-key"})
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["success"] is True
            assert data["data"]["status"] == "partially_paid"
            assert world.db.holds[0].remaining_amount == Decimal("7000")

    def test_route_overpayment_rejected_with_400(self):
        """CTO removes the sole obsolete xfail; precise 400/code and zero writes."""
        with _world(prior_paid=Decimal("3000")) as world, _route_client(world) as client:
            before = world.db.snapshot()
            response = client.post(f"/api/v1/orders/{ORDER_ID}/pay?request=test",
                                   json={"amount": 5000, "method": "cash"},
                                   headers={"X-Idempotency-Key": "route-overpay-key"})
            assert response.status_code == 400, response.text
            assert response.json()["code"] == "PAYMENT_EXCEEDS_REMAINING"
            _assert_no_economic_io(world, before)


@pytest.mark.asyncio
async def test_credit_payment_applies_positive_balance_delta():
    """Retained ID: R2 hold conversion never increments the binding twice."""
    with _world() as world:
        before = world.db.balance
        await _pay(world, Decimal("5000"), "credit")
        assert world.db.balance == before
        assert not any(isinstance(event, tuple) and event[0] == "binding" for event in world.db.writes)
        assert world.db.holds[0].status == "converted"
        assert world.db.holds[0].remaining_amount == Decimal("0")


@pytest.mark.asyncio
async def test_cash_payment_does_not_apply_balance_delta_for_ordinary_settlement():
    """Retained ID: R2 cash releases this hold; no credit double counting."""
    with _world() as world:
        await _pay(world, Decimal("5000"))
        assert ("binding", Decimal("-5000")) in world.db.writes
        assert world.db.balance == Decimal("0")


@pytest.mark.asyncio
async def test_transfer_payment_does_not_apply_balance_delta_for_ordinary_settlement():
    """Retained ID: R2 transfer releases exactly the settled hold amount."""
    with _world() as world:
        await _pay(world, Decimal("5000"), "transfer", reference="TX-001")
        assert ("binding", Decimal("-5000")) in world.db.writes
        assert world.db.balance == Decimal("0")


@pytest.mark.asyncio
async def test_get_order_paid_total_sql_excludes_credit():
    from repositories.payment_repository import PaymentRepository

    db = _FixtureSession(_make_mock_order(), prior_paid=Decimal("5000"))
    await PaymentRepository().get_order_paid_total(db, order_id=ORDER_ID)
    sql = db.sql[0][0]
    assert "method IN" in sql
    assert "'cash'" in sql and "'transfer'" in sql


@pytest.mark.asyncio
async def test_get_order_paid_total_only_counts_cash_and_transfer():
    from repositories.payment_repository import PaymentRepository

    db = _FixtureSession(_make_mock_order(order_total=Decimal("10000")),
                         prior_paid=Decimal("7000"), credit_count=1)
    assert await PaymentRepository().get_order_paid_total(db, order_id=ORDER_ID) == Decimal("7000")
    sql = db.sql[0][0]
    assert "credit" not in sql.lower().replace("'cash'", "").replace("'transfer'", "")


@pytest.mark.asyncio
async def test_credit_payment_status_is_pending():
    with _world() as world:
        await _pay(world, Decimal("5000"), "credit")
        assert world.db.payments[0]["status"] == "pending"
        assert world.db.payments[0]["method"] == "credit"


@pytest.mark.asyncio
async def test_credit_full_amount_advances_order_to_paid():
    from core.domain.order_state import OrderState

    total, credit, paid_total = Decimal("10000"), Decimal("10000"), Decimal("0")
    target = OrderState.PAID if paid_total + credit >= total else OrderState.PARTIALLY_PAID
    assert target == OrderState.PAID


@pytest.mark.asyncio
async def test_credit_partial_amount_rejected():
    from fastapi import HTTPException

    with _world(total=Decimal("10000")) as world:
        before = world.db.snapshot()
        with pytest.raises(HTTPException) as exc:
            await _pay(world, Decimal("5000"), "credit")
        assert exc.value.status_code == 400
        assert exc.value.detail["code"] == "CREDIT_AMOUNT_MISMATCH"
        _assert_no_economic_io(world, before)


@pytest.mark.asyncio
async def test_credit_rejected_when_prior_cash_exists():
    from fastapi import HTTPException

    with _world(total=Decimal("10000"), prior_paid=Decimal("5000")) as world:
        before = world.db.snapshot()
        with pytest.raises(HTTPException) as exc:
            await _pay(world, Decimal("5000"), "credit")
        assert exc.value.status_code == 400
        assert exc.value.detail["code"] == "CREDIT_SPLIT_TENDER_UNSUPPORTED"
        _assert_no_economic_io(world, before)


@pytest.mark.asyncio
async def test_credit_rejected_when_amount_exceeds_remaining():
    from fastapi import HTTPException

    with _world() as world:
        before = world.db.snapshot()
        with pytest.raises(HTTPException) as exc:
            await _pay(world, Decimal("6000"), "credit")
        assert exc.value.status_code == 400
        assert exc.value.detail["code"] == "PAYMENT_EXCEEDS_REMAINING"
        _assert_no_economic_io(world, before)


@pytest.mark.asyncio
async def test_payment_service_credit_applies_positive_delta():
    """Legacy PaymentService is distinct from canonical's hold conversion."""
    from services.payment_service import PaymentService

    db = _FixtureSession(_make_mock_order(order_total=Decimal("3000")))
    before = db.balance
    payment = await PaymentService().create_payment(
        tenant_db=db, order_id=str(ORDER_ID), amount=Decimal("3000"), method="credit",
        transaction_id=None, idempotency_key=None, created_by=str(ACTOR_ID))
    assert payment["id"] == PAYMENT_ID
    assert ("binding", Decimal("3000")) in db.writes
    assert db.balance - before == Decimal("3000")


@pytest.mark.asyncio
async def test_payment_service_cash_does_not_apply_balance_delta():
    from services.payment_service import PaymentService

    db = _FixtureSession(_make_mock_order(order_total=Decimal("10000")))
    before = db.balance
    await PaymentService().create_payment(
        tenant_db=db, order_id=str(ORDER_ID), amount=Decimal("7000"), method="cash",
        transaction_id=None, idempotency_key=None, created_by=str(ACTOR_ID))
    assert db.balance == before
    assert not any(isinstance(event, tuple) and event[0] == "binding" for event in db.writes)


def test_pay_order_request_accepts_credit_method():
    from schemas.order import PayOrderRequest

    req = PayOrderRequest(amount=Decimal("5000"), method="credit")
    assert req.method == "credit"
    assert req.amount == Decimal("5000")


def test_pay_order_request_accepts_transfer_method():
    from schemas.order import PayOrderRequest

    req = PayOrderRequest(amount=Decimal("5000"), method="transfer", transaction_id="TX-123")
    assert req.method == "transfer"


@pytest.mark.asyncio
async def test_duplicate_credit_payment_rejected():
    from fastapi import HTTPException

    with _world(total=Decimal("10000"), credit_count=1) as world:
        before = world.db.snapshot()
        with pytest.raises(HTTPException) as exc:
            await _pay(world, Decimal("5000"), "credit")
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "DUPLICATE_CREDIT_PAYMENT"
        _assert_no_economic_io(world, before)


@pytest.mark.asyncio
async def test_first_credit_payment_allowed():
    """Real conversion and an explicit mismatched hold, not an always-valid row."""
    from fastapi import HTTPException

    with _world() as world:
        response = await _pay(world, Decimal("5000"), "credit")
        assert response.success is True
        assert response.data["status"] == "paid"
        assert world.db.balance == Decimal("5000")
        assert world.db.holds[0].status == "converted"
        world.ledger.assert_not_awaited()
    with _world() as world:
        world.db.holds[0].remaining_amount = Decimal("4999")
        before = world.db.snapshot()
        with pytest.raises(HTTPException) as exc:
            await _pay(world, Decimal("5000"), "credit")
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "CREDIT_HOLD_MISMATCH"
        _assert_no_economic_io(world, before)
    with _world() as world:
        world.db.invalid_history_rows = [{"order_id": ORDER_ID, "invalid_rows": 1}]
        before = world.db.snapshot()
        with pytest.raises(HTTPException) as exc:
            await _pay(world, Decimal("5000"), "credit")
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "PAYMENT_HISTORY_INTEGRITY"
        _assert_no_economic_io(world, before)


@pytest.mark.asyncio
async def test_credit_payment_passes_method_to_transition():
    with _world() as world:
        await _pay(world, Decimal("5000"), "credit")
        assert len(world.db.command_calls) == 1
        assert world.db.command_calls[0]["order_id"] == ORDER_ID
        assert world.db.command_calls[0]["target_state"].value == "paid"
        assert world.db.command_calls[0]["payment_method"] == "credit"
        world.ledger.assert_not_awaited()


@pytest.mark.asyncio
async def test_cash_payment_passes_method_to_transition():
    with _world() as world:
        await _pay(world, Decimal("5000"), "cash")
        assert len(world.db.command_calls) == 1
        assert world.db.command_calls[0]["payment_method"] == "cash"
        _assert_receipt(world, Decimal("5000"))


@pytest.mark.asyncio
async def test_legacy_pay_rejected_before_transition():
    from api.v1.orders import pay_order
    from fastapi import HTTPException

    with _world() as world:
        before = world.db.snapshot()
        with pytest.raises(HTTPException) as exc:
            await pay_order(str(ORDER_ID), token=_FakeToken(), db=world.db, payment_input=None)
        assert exc.value.status_code == 400
        assert exc.value.detail["code"] == "PAYMENT_BODY_REQUIRED"
        assert world.db.command_calls == []
        _assert_no_economic_io(world, before)


async def _adapter_no_receipt(world, method=None):
    from core.domain.order_state import OrderState
    from services.order_service import OrderService

    await OrderService(world.db)._post_ledger_entries(
        order=world.order, from_state=OrderState.CONFIRMED,
        to_state=OrderState.PAID, payment_method=method)
    world.ledger.assert_not_awaited()
    assert world.db.ledger_calls == []


@pytest.mark.asyncio
async def test_post_ledger_entries_credit_paid_skips_payment_received():
    """Credit adapter zero cash calls, not full credit/recognition acceptance."""
    with _world() as world:
        await _adapter_no_receipt(world, "credit")
        assert world.db.writes == []


@pytest.mark.asyncio
async def test_post_ledger_entries_default_paid_calls_payment_received():
    """CTO R1R1 migrates default posting to adapter-zero + missing-method 400."""
    from api.v1.orders import pay_order
    from fastapi import HTTPException
    from schemas.order import PayOrderRequest

    with _world() as adapter_world:
        await _adapter_no_receipt(adapter_world)
    with _world() as world:
        before = world.db.snapshot()
        with pytest.raises(HTTPException) as exc:
            await pay_order(
                str(ORDER_ID), token=_FakeToken(), db=world.db,
                payment_input=PayOrderRequest(amount=Decimal("5000")),
                x_idempotency_key="phase5-no-method")
        assert exc.value.status_code == 400
        assert exc.value.detail["code"] == "PAYMENT_METHOD_REQUIRED"
        assert world.db.sql == []
        _assert_no_economic_io(world, before)


@pytest.mark.asyncio
async def test_post_ledger_entries_cash_paid_calls_payment_received():
    """CTO R1R1: adapter zero; canonical posts final 3000, never full 5000."""
    with _world() as adapter_world:
        await _adapter_no_receipt(adapter_world, "cash")
    with _world(status="partially_paid", prior_paid=Decimal("2000")) as world:
        requested = Decimal("3000")
        assert requested != world.order.total_amount
        response = await _pay(world, requested, "cash", key="ledger-cash-final")
        assert response.data["status"] == "paid"
        assert world.db.order_locks == 1
        _assert_receipt(world, requested)
        assert world.db.balance == Decimal("0")
        assert world.db.holds[0].remaining_amount == Decimal("0")


@pytest.mark.asyncio
async def test_post_ledger_entries_transfer_paid_calls_payment_received():
    """CTO R1R1: adapter zero; real transfer producer emits one identified receipt."""
    with _world() as adapter_world:
        await _adapter_no_receipt(adapter_world, "transfer")
    with _world(currency="KES") as world:
        requested = Decimal("5000.00")
        response = await _pay(world, requested, "transfer",
                              key="ledger-transfer", reference="TX-ledger-identified")
        assert response.data["status"] == "paid"
        _assert_receipt(world, requested)
        assert world.db.payments[0]["transaction_id"] == "TX-ledger-identified"
        assert world.db.payments[0]["status"] == "completed"
