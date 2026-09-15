"""R1 implementation test support (MPANGO_ORDER_STATE_AUTHORITY_R1).

Task-private helpers. No os.environ mutation at import time; the shared
conftest owns environment resolution. Every DB helper takes an explicit
session. Ported semantics come from the D1 evidence anchor (474eaf35)
tests; the invalid R6 oracle was NOT ported (supervisor disposition).
"""
from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (  # noqa: F401
    _create_binding,
    _create_retailer,
    provisioned_pool,  # noqa: F401
    s2_clean_db,  # noqa: F401
)


def skip_without_task_db() -> None:
    if not os.environ.get("TEST_DATABASE_URL"):
        pytest.skip("R1_SKIP: task PostgreSQL URL not provided")


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


async def seed_sku_with_stock(
    db: AsyncSession, schema: str, retailer_id: str, *,
    quantity: int = 100, price: str = "50.00",
) -> tuple[str, str]:
    product = (await db.execute(text(
        f'INSERT INTO "{schema}".catalog_products (name, is_active, is_deleted) '
        "VALUES ('R1', true, false) RETURNING id"))).fetchone()
    code = f"R1{uuid.uuid4().hex[:8].upper()}"
    row = (await db.execute(text(
        f'INSERT INTO "{schema}".skus '
        "(sku_code, name, unit, is_active, is_deleted, catalog_product_id, package_quantity) "
        "VALUES (:c, 'R1', 'piece', true, false, :p, 1.000) RETURNING id"),
        {"c": code, "p": product.id})).fetchone()
    sid = str(row.id)
    await db.execute(text(
        f'INSERT INTO "{schema}".inventory_stocks (sku_id, quantity_on_hand, is_deleted) '
        "VALUES (:s, :q, false)"), {"s": sid, "q": quantity})
    await db.execute(text(
        f'INSERT INTO "{schema}".retailer_prices (sku_id, retailer_id, price, is_deleted) '
        "VALUES (:s, :r, :price, false)"), {"s": sid, "r": retailer_id, "price": price})
    await db.commit()
    return code, sid


async def make_bound_retailer(db, provisioned_pool, registry, user_id=None):
    """Yield (retailer_id, schema, ws_id) with registry-tracked cleanup."""
    from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (
        _create_binding,
        _create_retailer,
    )
    a = provisioned_pool.tenants["a"]
    ret_id = await _create_retailer(db, name="R1 Retailer", registry=registry)
    await _create_binding(
        db, wholesaler_id=a["ws_id"], retailer_id=ret_id,
        tenant_user_id=user_id or str(uuid.uuid4()), registry=registry)
    return str(ret_id), a["schema"], a["ws_id"]


# ---------------------------------------------------------------------------
# Fact vectors (persisted truth as plain scalars)
# ---------------------------------------------------------------------------


async def order_vector(db, schema, order_id) -> dict[str, Any]:
    row = (await db.execute(text(
        f'SELECT id, status, total_amount FROM "{schema}".orders WHERE id = :oid'
    ), {"oid": order_id})).fetchone()
    if row is None:
        return {"exists": False}
    return {"exists": True, "status": row.status,
            "total_amount": str(row.total_amount)}


async def inventory_vector(db, schema, sku_ids: list[str]) -> dict[str, str]:
    rows = (await db.execute(text(
        f'SELECT sku_id, quantity_on_hand, quantity_reserved FROM "{schema}".inventory_stocks '
        "WHERE sku_id = ANY(:s) ORDER BY sku_id"), {"s": sku_ids})).fetchall()
    def _fmt(v) -> str:
        d = Decimal(str(v))
        return str(int(d)) if d == d.to_integral_value() else str(d)

    return {str(r.sku_id): f"{_fmt(r.quantity_on_hand)}/"
            f"{_fmt(r.quantity_reserved)}" for r in rows}


async def reservation_vector(db, schema, order_id) -> list[dict[str, str]]:
    rows = (await db.execute(text(
        f'SELECT sku_id, quantity, status FROM "{schema}".inventory_reservations '
        "WHERE order_id = :oid ORDER BY id"), {"oid": order_id})).fetchall()
    return [{"sku": str(r.sku_id), "qty": str(r.quantity), "status": r.status}
            for r in rows]


async def movement_count(db, schema, order_id) -> int:
    return int((await db.execute(text(
        f'SELECT count(*) FROM "{schema}".inventory_movements '
        "WHERE reference_id = :oid"), {"oid": order_id})).scalar_one())


async def payment_ledger_vector(db, schema, order_id) -> dict[str, Any]:
    payments = (await db.execute(text(
        f'SELECT id, method, amount, status FROM "{schema}.payments"'.replace(
            f'"{schema}.payments"', f'"{schema}".payments') +
        " WHERE order_id = :oid ORDER BY created_at, id"),
        {"oid": order_id})).fetchall()
    ledger = (await db.execute(text(
        f'SELECT id, account_type, amount FROM "{schema}".ledger_entries '
        "WHERE reference_id = :oid AND reference_type = 'order' ORDER BY id"),
        {"oid": order_id})).fetchall()
    return {
        "payments": [{"method": p.method, "amount": str(p.amount),
                      "status": p.status} for p in payments],
        "ledger": [{"account": str(l.account_type), "amount": str(l.amount)}
                   for l in ledger],
    }


async def binding_balance(db, ws_id: str, retailer_id: str) -> Decimal:
    row = (await db.execute(text(
        "SELECT outstanding_balance FROM public.wholesaler_retailer_bindings "
        "WHERE wholesaler_id = :w AND retailer_id = :r AND is_deleted IS FALSE"),
        {"w": ws_id, "r": retailer_id})).fetchone()
    return Decimal(str(row.outstanding_balance)) if row else Decimal("0")


async def order_items_snapshot(db, schema, order_id) -> list[dict[str, Any]]:
    rows = (await db.execute(text(
        f'SELECT sellable_unit_id, identity_status, product_name, sku_code, '
        f'unit_snapshot, quantity, unit_price, subtotal '
        f'FROM "{schema}".order_items WHERE order_id = :oid ORDER BY id'
    ), {"oid": order_id})).fetchall()
    return [{
        "sellable_unit_id": str(r.sellable_unit_id) if r.sellable_unit_id else None,
        "identity_status": r.identity_status,
        "product_name": r.product_name,
        "sku_code": r.sku_code,
        "unit_snapshot": r.unit_snapshot,
        "quantity": r.quantity,
        "unit_price": str(r.unit_price),
        "subtotal": str(r.subtotal),
    } for r in rows]


# ---------------------------------------------------------------------------
# HTTP helpers (real ASGI app, JWT strategy)
# ---------------------------------------------------------------------------


def errcode(resp) -> str:
    body = resp.json()
    detail = body.get("detail") or body.get("error") or {}
    return detail.get("code") or body.get("code") or ""


async def http_create_order(client, token, retailer_id, items: list[dict]) -> str:
    resp = await client.post(
        "/api/v1/orders",
        json={"retailer_id": retailer_id, "items": items, "notes": "r1"},
        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201, f"create failed: {resp.status_code} {resp.text}"
    return resp.json()["data"]["id"]


async def http_action(client, token, order_id, action, json_body=None):
    headers = {"Authorization": f"Bearer {token}"}
    if action == "pay":
        headers["X-Idempotency-Key"] = f"r1-{uuid.uuid4().hex}"
    return await client.post(f"/api/v1/orders/{order_id}/{action}",
                             json=json_body, headers=headers)


# ---------------------------------------------------------------------------
# Notification spy (wraps the real service instance methods)
# ---------------------------------------------------------------------------


@dataclass
class NotificationSpy:
    emails: list[dict[str, str]] = field(default_factory=list)
    sms: list[dict[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.emails) + len(self.sms)

    def recipients(self) -> list[str]:
        return [m["to"] for m in self.emails] + [m["phone"] for m in self.sms]


class notification_spy:
    """Context manager wrapping the REAL notification service instance."""

    def __enter__(self):
        from services import notification_service as ns

        self._ns = ns.notification_service
        self._real_email = self._ns.send_email
        self._real_sms = self._ns.send_sms
        self.spy = NotificationSpy()

        async def spy_email(*, to, subject, body):
            self.spy.emails.append({"to": to, "subject": subject, "body": body})
            return await self._real_email(to=to, subject=subject, body=body)

        async def spy_sms(*, phone, message):
            self.spy.sms.append({"phone": phone, "message": message})
            return await self._real_sms(phone=phone, message=message)

        self._ns.send_email = spy_email
        self._ns.send_sms = spy_sms
        return self.spy

    def __exit__(self, *exc):
        self._ns.send_email = self._real_email
        self._ns.send_sms = self._real_sms
        return False


# ---------------------------------------------------------------------------
# Race orchestration (bounded cleanup on every exit)
# ---------------------------------------------------------------------------


class RaceOrchestrator:
    def __init__(self, budget: float = 30.0):
        self.budget = budget
        self.tasks: list[asyncio.Task] = []
        self.timed_out = False

    def spawn(self, coro) -> asyncio.Task:
        t = asyncio.create_task(coro)
        self.tasks.append(t)
        return t

    async def gather_all(self):
        try:
            async with asyncio.timeout(self.budget):
                return await asyncio.gather(*self.tasks, return_exceptions=True)
        except TimeoutError:
            self.timed_out = True
            raise

    async def drain(self):
        for t in self.tasks:
            if not t.done():
                t.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()


class SharedGate:
    def __init__(self, expected: int):
        self.expected = expected
        self.arrived = asyncio.Event()
        self._count = 0

    async def wait_turn(self):
        self._count += 1
        if self._count >= self.expected:
            self.arrived.set()
        else:
            await asyncio.wait_for(self.arrived.wait(), 30.0)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def r1_client():
    from unittest import mock

    from api.app import configure_app
    from auth.strategies.jwt import JwtAuthStrategy
    from core.config import get_settings
    from core.error_codes import register_exception_handlers
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    skip_without_task_db()
    fresh_app = FastAPI()
    with mock.patch("auth.factory.get_auth_strategy", return_value=JwtAuthStrategy()):
        configure_app(fresh_app, get_settings())
    register_exception_handlers(fresh_app)
    ip_hex = uuid.uuid4().int
    async with AsyncClient(
        transport=ASGITransport(app=fresh_app),
        base_url="http://testserver",
        headers={
            "Content-Type": "application/json",
            "X-Forwarded-For": f"10.{(ip_hex >> 16) & 0xFF}.{(ip_hex >> 8) & 0xFF}.{ip_hex & 0xFF}",
        },
    ) as ac:
        yield ac


async def rebind_search_path(session: AsyncSession, schema: str) -> None:
    """Re-apply search_path after a rollback/commit (the pooled connection
    is returned with RESET ALL and silently loses it)."""
    await session.execute(text(f'SET search_path TO "{schema}", public'))


async def _second_session(schema: str, tenant_id: str) -> AsyncSession:
    """A second tenant-bound session for out-of-request writes/reads."""
    from database.session import AsyncSessionLocal

    session = AsyncSessionLocal()
    session.info["tenant_schema"] = schema
    session.info["tenant_id"] = tenant_id
    # NOTE: no commit here — the open implicit transaction pins the pooled
    # connection (commit would return it to the pool where the asyncpg
    # reset issues RESET ALL and drops the search_path).
    await session.execute(text(f'SET search_path TO "{schema}", public'))
    return session


async def make_tenant_cashier(db, registry, tenant: dict) -> dict:
    """Canonical owner-lifecycle cashier for ANY pool tenant (A or B)."""
    import uuid as _uuid

    from services.owner_credential_service import OwnerCredentialSetupService

    reg_id = _uuid.UUID(tenant["reg_id"])
    svc = OwnerCredentialSetupService(db)
    await db.execute(
        text("DELETE FROM public.owner_credential_setup_tokens "
             "WHERE registration_id = :rid"),
        {"rid": reg_id})
    await db.flush()
    issue = await svc.issue_setup_token(reg_id)
    assert issue.action == "issued", f"setup token issue failed: {issue}"
    consume = await svc.consume_setup_token(issue.raw_token, "CashierTestPass99!")
    result = await svc.create_first_admin_rbac(consume)
    await db.commit()
    registry.register_tenant_user(tenant["schema"], str(result.user_id))
    return {
        "email": result.owner_email,
        "password": "CashierTestPass99!",
        "user_id": result.user_id,
        "schema": tenant["schema"],
        "ws_id": tenant["ws_id"],
    }


async def osd1_cashier_token(client, identity: dict) -> str:
    """Login + select-tenant on the given client; returns access token."""
    from tests.test_dc12r1_s3_s2b_i2b_payment_declarations import (
        _cashier_token,
    )

    return await _cashier_token(client, identity)
