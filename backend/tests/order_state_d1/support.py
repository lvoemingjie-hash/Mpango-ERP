"""MPANGO-ORDER-STATE-AUTHORITY-D1 — shared task-test support.

Task-private helpers for the six CTO regression matrices. This module adds
NO fixtures by itself and NEVER mutates ``os.environ`` at import time; the
shared ``tests/conftest.py`` owns environment resolution. Every helper that
touches the database takes an explicit session so proofs stay inside the
caller's transaction boundary.

Assertion-helpers discipline (CTO contract): each helper ships with a
legitimate-order positive control and a duplicate/effect negative control
test in ``test_matrix_assertion_controls.py`` — a helper that cannot fire
is not evidence.

Proof boundary: HTTP tests exercise the real ASGI app (JWT auth strategy,
tenant-context middleware, real commit at ``finalize_tenant_context``);
direct-service tests state their narrower boundary in each module header.
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (  # noqa: F401
    _create_binding,
    _create_retailer,
    provisioned_pool,  # noqa: F401 (module fixture, reused)
    s2_clean_db,  # noqa: F401 (fixture, reused)
)


def task_db_available() -> bool:
    """True when a task PostgreSQL URL is present (runner-provided)."""
    return bool(os.environ.get("ORDER_STATE_D1_TEST_DATABASE_URL")
                or os.environ.get("TEST_DATABASE_URL"))


def skip_without_task_db(reason: str = "task PostgreSQL URL not provided") -> None:
    if not task_db_available():
        pytest.skip(f"ORDER_STATE_D1_SKIP: {reason}")


# ---------------------------------------------------------------------------
# Assertion helpers (each has controls in test_matrix_assertion_controls.py)
# ---------------------------------------------------------------------------


async def fetch_order_state(db: AsyncSession, schema: str, order_id) -> dict[str, Any]:
    """Read the order's persisted state as plain scalars (post-rollback safe)."""
    row = (await db.execute(text(
        f'SELECT id, status, total_amount FROM "{schema}".orders WHERE id = :oid'
    ), {"oid": order_id})).fetchone()
    if row is None:
        return {"exists": False}
    return {"exists": True, "id": str(row.id), "status": row.status,
            "total_amount": str(row.total_amount)}


async def fetch_reservation_facts(db: AsyncSession, schema: str, order_id) -> dict[str, Any]:
    """Reservation + aggregate-reserved facts for one order.

    Used by the no-orphan-reservation oracle: a terminal-cancelled order must
    own zero ``reserved`` rows and must not leave aggregate reserved stock.
    """
    rows = (await db.execute(text(
        f'SELECT id, status, quantity, sku_id FROM "{schema}".inventory_reservations '
        "WHERE order_id = :oid ORDER BY id"
    ), {"oid": order_id})).fetchall()
    reserved_total = Decimal("0")
    reserved_rows = 0
    for row in rows:
        if row.status == "reserved":
            reserved_rows += 1
            reserved_total += Decimal(str(row.quantity))
    return {"rows": [{"id": str(r.id), "status": r.status,
                      "quantity": str(r.quantity)} for r in rows],
            "reserved_rows": reserved_rows,
            "reserved_total": str(reserved_total)}


async def assert_no_orphan_reservations(
    db: AsyncSession, schema: str, order_id, *, expect_status: str
) -> None:
    """A cancelled/voided order must not keep ``reserved`` inventory.

    Fails when the order is in a no-longer-active state (cancelled) while any
    owned reservation is still ``reserved`` — the confirm||cancel lost-update
    signature. Legitimate positive case: clean cancel leaves zero reserved.
    """
    state = await fetch_order_state(db, schema, order_id)
    assert state["exists"], "order row vanished"
    facts = await fetch_reservation_facts(db, schema, order_id)
    problems: list[str] = []
    if state["status"] == expect_status and expect_status in ("cancelled", "voided"):
        if facts["reserved_rows"]:
            problems.append(
                f"orphan reservations: order status={state['status']} but "
                f"{facts['reserved_rows']} reservation row(s) still reserved "
                f"(total {facts['reserved_total']})")
    assert not problems, "; ".join(problems)


async def fetch_payment_ledger_facts(
    db: AsyncSession, schema: str, order_id
) -> dict[str, Any]:
    """Payment rows + ledger entries + per-entry types for one order."""
    payments = (await db.execute(text(
        f'SELECT id, method, amount, status, idempotency_key FROM "{schema}".payments '
        "WHERE order_id = :oid ORDER BY created_at, id"
    ), {"oid": order_id})).fetchall()
    ledger = (await db.execute(text(
        f'SELECT id, account_type, amount, reference_type FROM "{schema}".ledger_entries '
        "WHERE reference_id = :oid AND reference_type = 'order' ORDER BY transaction_date, id"
    ), {"oid": order_id})).fetchall()
    return {
        "payments": [{"id": str(p.id), "method": p.method, "amount": str(p.amount),
                      "status": p.status, "key": p.idempotency_key} for p in payments],
        "ledger": [{"id": str(l.id), "account_type": str(l.account_type),
                    "amount": str(l.amount)} for l in ledger],
    }


async def assert_no_paid_cancelled_combo(
    db: AsyncSession, schema: str, order_id
) -> None:
    """A cancelled order must not carry completed payment + settlement ledger.

    The pay||cancel lost-update signature: money recorded and settled, order
    then silently overwritten to cancelled without any refund/reversal path.
    """
    state = await fetch_order_state(db, schema, order_id)
    facts = await fetch_payment_ledger_facts(db, schema, order_id)
    problems: list[str] = []
    if state.get("status") == "cancelled":
        completed = [p for p in facts["payments"] if p["status"] == "completed"]
        if completed:
            problems.append(
                f"cancelled order holds completed payment(s): {completed}")
        settled = [l for l in facts["ledger"] if str(l["account_type"]).lower() == "cash"]
        if settled:
            problems.append(
                f"cancelled order holds settlement ledger entries: {settled}")
    assert not problems, "; ".join(problems)


def linearizable_final(final: dict[str, Any], histories: list[dict[str, Any]]) -> bool:
    """Racing final facts must equal EXACTLY ONE sequential history's facts.

    ``histories`` come from legitimately-ordered positive-control runs; a
    racing interleaving that matches none of them is a lost-update/outcome
    not achievable by any serial order.
    """
    return any(final == hist for hist in histories)


async def snapshot_order_items(
    db: AsyncSession, schema: str, order_id
) -> list[dict[str, Any]]:
    """Plain-scalar snapshot of order_items identity + pricing fields."""
    rows = (await db.execute(text(
        f'SELECT id, sellable_unit_id, identity_status, product_name, sku_code, '
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
# Seeding (registry-tracked through s2_clean_db ownership cleanup)
# ---------------------------------------------------------------------------


async def seed_sku_with_stock(
    db: AsyncSession, schema: str, retailer_id: str, *, quantity: int = 100,
    price: str = "50.00", registry=None,
) -> tuple[str, str]:
    """Seed one catalog product + SKU + stock + retailer price.

    Returns ``(sku_code, sku_id)``. Mirrors the S3 seeding helper; the rows
    live in the tenant's owned schema which the pool teardown removes.
    """
    product = (await db.execute(text(
        f'INSERT INTO "{schema}".catalog_products (name, is_active, is_deleted) '
        "VALUES ('OSD1', true, false) RETURNING id"
    ))).fetchone()
    code = f"OSD1{uuid.uuid4().hex[:8].upper()}"
    row = (await db.execute(text(
        f'INSERT INTO "{schema}".skus '
        "(sku_code, name, unit, is_active, is_deleted, catalog_product_id, package_quantity) "
        "VALUES (:c, 'OSD1', 'piece', true, false, :p, 1.000) RETURNING id"),
        {"c": code, "p": product.id},
    )).fetchone()
    sid = str(row.id)
    await db.execute(text(
        f'INSERT INTO "{schema}".inventory_stocks (sku_id, quantity_on_hand, is_deleted) '
        "VALUES (:s, :q, false)"),
        {"s": sid, "q": quantity},
    )
    await db.execute(text(
        f'INSERT INTO "{schema}".retailer_prices (sku_id, retailer_id, price, is_deleted) '
        "VALUES (:s, :r, :price, false)"),
        {"s": sid, "r": retailer_id, "price": price},
    )
    await db.commit()
    return code, sid


async def seed_stock_row(db: AsyncSession, schema: str, sku_id: str, on_hand: int) -> None:
    await db.execute(text(
        f'INSERT INTO "{schema}".inventory_stocks (sku_id, quantity_on_hand, is_deleted) '
        "VALUES (:s, :q, false)"), {"s": sku_id, "quantity": on_hand})
    await db.commit()


async def http_create_wholesaler_order(
    client, token: str, retailer_id: str, sku_code: str, quantity: int
) -> dict[str, Any]:
    """POST /api/v1/orders with server-side pricing; returns parsed JSON."""
    resp = await client.post(
        "/api/v1/orders",
        json={"retailer_id": retailer_id,
              "items": [{"sku_code": sku_code, "quantity": quantity}],
              "notes": "osd1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"create failed {resp.status_code}: {resp.text}"
    return resp.json()["data"]


async def http_action(client, token: str, order_id: str, action: str,
                      json_body: dict | None = None) -> Any:
    """POST /api/v1/orders/{id}/{action}; returns the httpx response."""
    return await client.post(
        f"/api/v1/orders/{order_id}/{action}",
        json=json_body,
        headers={"Authorization": f"Bearer {token}",
                 "X-Idempotency-Key": f"osd1-{uuid.uuid4().hex}"}
        if action == "pay" else {"Authorization": f"Bearer {token}"},
    )


# ---------------------------------------------------------------------------
# HTTP client fixture (real app + JWT strategy, unique rate-limit IP)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def osd1_client():
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


@pytest_asyncio.fixture
async def osd1_cashier(cashier_identity):
    """Pass-through of the I2B cashier fixture (canonical owner lifecycle).

    Full ADMIN permission set via OwnerCredentialSetupService (includes
    orders:update / payments:create). Use :func:`osd1_cashier_token` to mint
    the tenant-scoped JWT.
    """
    skip_without_task_db()
    return cashier_identity


async def osd1_cashier_token(client, identity: dict) -> str:
    """Login + select-tenant on the given client; returns access token."""
    from tests.test_dc12r1_s3_s2b_i2b_payment_declarations import (
        _cashier_token,
    )

    return await _cashier_token(client, identity)


@asynccontextmanager
async def bound_retailer(db: AsyncSession, provisioned_pool, registry, user_id: str | None = None):
    """A retailer bound to tenant A; yields (retailer_id, schema, ws_id).

    Rows are registered in the s2 ownership registry so cleanup is exact.
    """
    a = provisioned_pool.tenants["a"]
    ret_id = await _create_retailer(db, name="OSD1 Retailer", registry=registry)
    await _create_binding(
        db,
        wholesaler_id=a["ws_id"],
        retailer_id=ret_id,
        tenant_user_id=user_id or str(uuid.uuid4()),
        registry=registry,
    )
    yield str(ret_id), a["schema"], a["ws_id"]
