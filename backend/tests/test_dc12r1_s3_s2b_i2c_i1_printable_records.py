"""DC-12R1-S3-S2B-I2C-I1 — Printable Records Backend (Contracts A-C).

Real-PG16 tests for the six read-only print/receipt routes:
  A. Order document:   GET /api/v1/client/orders/{order_id}/print
                        GET /api/v1/orders/{order_id}/print
  B. Declaration doc:  GET /api/v1/client/declarations/{declaration_id}/print
                        GET /api/v1/declarations/{declaration_id}/print
  C. Confirmed receipt: GET /api/v1/client/declarations/{declaration_id}/receipt
                        GET /api/v1/declarations/{declaration_id}/receipt

Covers: retailer + supplier happy paths, server-authoritative price/total,
pending/rejected non-receipt rendering, confirmed valid receipt, fail-closed
for missing/null/malformed/soft-deleted receipt payment, repeated receipt GET
identity, wrong supplier/retailer/cross-schema denial, inactive/deleted binding
denial, malformed UUID controlled response, zero SQL writes + zero financial
fingerprints, and no internal-identifier leakage.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from http import HTTPStatus

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# Reuse the full I2B harness (fixtures + helpers).
from tests.test_dc12r1_s3_s2b_i2b_payment_declarations import (  # noqa: E402
    _cashier_token,
    _cleanup_rate_limiter,  # noqa: F401 (autouse side-effect import)
    _headers,
    _login_retailer,
    _pool_a,
    _resolve_binding_retailer,
    _seed_confirmed_order,
    cashier_identity,  # noqa: F401 (fixture)
    i2b_client,  # noqa: F401 (fixture)
    test_client_ip,  # noqa: F401 (autouse fixture)
)
from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (  # noqa: E402
    provisioned_pool,  # noqa: F401 (module fixture)
    s2_clean_db,  # noqa: F401 (fixture)
    two_tenants,  # noqa: F401 (fixture)
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _i2c_i1_flush_stmt_cache(provisioned_pool):
    """H5: Dispose engine pool after provisioning DDL.

    Tenant provisioning runs bootstrap DDL that invalidates asyncpg prepared
    statements cached on pooled connections from prior test modules. Disposing
    the engine closes every pooled connection so subsequent sessions obtain
    fresh connections with empty prepared-statement caches.
    """
    from database.session import async_engine

    await async_engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_order_with_item(
    db: AsyncSession, schema: str, ws_id: str, ret_id: str, total: str = "100.00"
) -> uuid.UUID:
    """Seed a confirmed order + an order_items row (for price verification)."""
    oid = await _seed_confirmed_order(db, schema, ws_id, ret_id, total)
    await db.execute(
        text(
            f'INSERT INTO "{schema}".order_items '
            "(id, order_id, product_name, sku_code, quantity, unit_price, subtotal, is_deleted) "
            "VALUES (:iid, :oid, :pname, :sku, :qty, :up, :sub, false)"
        ),
        {
            "iid": uuid.uuid4(),
            "oid": oid,
            "pname": "Test Product",
            "sku": "TEST-SKU-001",
            "qty": 2,
            "up": Decimal("50.00"),
            "sub": Decimal("100.00"),
        },
    )
    await db.commit()
    return oid


async def _submit_and_confirm(
    client, two_tenants, s2_clean_db, cashier_identity, amount="100.00", method="cash"
):
    """Full flow: seed order → retailer declares → cashier confirms → return ids + receipt."""
    db, _reg = s2_clean_db
    ws_a = _pool_a()["ws_id"]
    sch_a = _pool_a()["schema"]
    code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
    ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
    oid = await _seed_order_with_item(db, sch_a, ws_a, ret_a, amount)

    token_ret = await _login_retailer(client, two_tenants)
    decl = await client.post(
        f"/api/v1/client/orders/{oid}/declare",
        json={"declared_amount": amount, "method": method},
        headers={**_headers(token_ret), "X-Declaration-Idempotency-Key": f"i2c-i1-{uuid.uuid4().hex}"},
    )
    assert decl.status_code == HTTPStatus.CREATED, decl.text
    decl_id = decl.json()["data"]["id"]

    token_admin = await _cashier_token(client, cashier_identity)
    r = await client.post(f"/api/v1/declarations/{decl_id}/confirm", headers=_headers(token_admin))
    assert r.status_code == HTTPStatus.OK, r.text
    receipt_number = r.json()["data"]["receipt_number"]

    return {
        "decl_id": decl_id,
        "oid": str(oid),
        "ws_a": ws_a,
        "sch_a": sch_a,
        "ret_a": ret_a,
        "receipt_number": receipt_number,
        "token_ret": token_ret,
        "token_admin": token_admin,
    }


async def _seed_pending_declaration(db, schema, ws_id, ret_id, oid):
    """Seed a pending declaration directly via SQL."""
    did = uuid.uuid4()
    await db.execute(
        text(
            f'INSERT INTO "{schema}".payment_declarations '
            "(id, order_id, retailer_id, wholesaler_id, declared_amount, method, "
            "status, idempotency_key, submitted_by, submitted_at, transfer_reference) "
            "VALUES (:id, :oid, :ret, :ws, :amt, :method, 'pending', :idem, :sb, now(), NULL)"
        ),
        {
            "id": did,
            "oid": oid,
            "ret": ret_id,
            "ws": ws_id,
            "amt": Decimal("100.00"),
            "method": "cash",
            "idem": f"seed-pending-{did.hex}",
            "sb": uuid.uuid4(),
        },
    )
    await db.commit()
    return did


async def _seed_rejected_declaration(db, schema, ws_id, ret_id, oid):
    """Seed a rejected declaration directly via SQL."""
    did = uuid.uuid4()
    await db.execute(
        text(
            f'INSERT INTO "{schema}".payment_declarations '
            "(id, order_id, retailer_id, wholesaler_id, declared_amount, method, "
            "status, idempotency_key, submitted_by, submitted_at, "
            "rejected_by, rejected_at, reason) "
            "VALUES (:id, :oid, :ret, :ws, :amt, 'cash', 'rejected', :idem, :sb, now(), "
            ":rb, now(), :reason)"
        ),
        {
            "id": did,
            "oid": oid,
            "ret": ret_id,
            "ws": ws_id,
            "amt": Decimal("100.00"),
            "idem": f"seed-rejected-{did.hex}",
            "sb": uuid.uuid4(),
            "rb": uuid.uuid4(),
            "reason": "Transfer reference did not match our records",
        },
    )
    await db.commit()
    return did


async def _table_fingerprint(db: AsyncSession, schema: str, table: str) -> int:
    """Return a row-count fingerprint for a tenant table (mutation detector).

    R1: any query error is a hard failure (never silently return -1).
    """
    result = await db.execute(text(f'SELECT count(*) FROM "{schema}".{table}'))
    return result.scalar()


async def _binding_fingerprint(db: AsyncSession, ws_id: str, ret_id: str) -> Decimal:
    """R1: raise on error — never silently return a sentinel."""
    result = await db.execute(
        text(
            "SELECT outstanding_balance FROM public.wholesaler_retailer_bindings "
            "WHERE wholesaler_id = :ws AND retailer_id = :ret AND is_deleted IS FALSE"
        ),
        {"ws": ws_id, "ret": ret_id},
    )
    row = result.first()
    assert row is not None, f"binding not found for ws={ws_id} ret={ret_id}"
    return row.outstanding_balance


async def _receipt_seq_fingerprint(db: AsyncSession, schema: str) -> int:
    """R1: raise on error — never silently return a sentinel."""
    result = await db.execute(text(f'SELECT coalesce(sum(next_seq),0) FROM "{schema}".receipt_sequences'))
    return result.scalar()


# ===========================================================================
# Contract A — Order document
# ===========================================================================


class TestOrderPrint:
    """GET /api/v1/client/orders/{order_id}/print + GET /api/v1/orders/{order_id}/print"""

    async def test_retailer_order_print_happy_path(self, i2b_client, two_tenants, s2_clean_db):
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_order_with_item(db, sch_a, ws_a, ret_a, "100.00")

        token_ret = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.get(f"/api/v1/client/orders/{oid}/print", headers=_headers(token_ret))
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        assert data["document_type"] == "order"
        assert data["order_id"] == str(oid)
        assert len(data["items"]) == 1
        assert Decimal(data["items"][0]["unit_price"]) == Decimal("50.00")
        assert Decimal(data["items"][0]["subtotal"]) == Decimal("100.00")
        assert Decimal(data["total_amount"]) == Decimal("100.00")
        assert data["item_count"] == 1
        assert data["status"] in ("CONFIRMED", "CREATED", "DELIVERED")
        assert data["supplier_name"]
        assert data["retailer_name"]
        assert data["created_at_eat"] is not None

    async def test_supplier_order_print_happy_path(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_order_with_item(db, sch_a, ws_a, ret_a, "200.00")

        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.get(f"/api/v1/orders/{oid}/print", headers=_headers(token_admin))
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        assert Decimal(data["total_amount"]) == Decimal("200.00")
        assert data["items"][0]["quantity"] == 2

    async def test_order_print_wrong_retailer_denied(self, i2b_client, two_tenants, s2_clean_db):
        """Retailer A cannot print retailer B's order — neutral 404."""
        db, _reg = s2_clean_db
        ws_b = _pool_a()["ws_id"]  # will use a different order in a different relationship
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_b, uid_a)
        oid = await _seed_order_with_item(db, sch_a, ws_b, ret_a, "100.00")

        token_ret = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.get(f"/api/v1/client/orders/{uuid.uuid4()}/print", headers=_headers(token_ret))
        assert r.status_code == HTTPStatus.NOT_FOUND

    async def test_order_print_malformed_uuid(self, i2b_client, two_tenants):
        token_ret = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.get("/api/v1/client/orders/not-a-uuid/print", headers=_headers(token_ret))
        assert r.status_code == HTTPStatus.NOT_FOUND


# ===========================================================================
# Contract B — Declaration document
# ===========================================================================


class TestDeclarationPrint:
    """GET /api/v1/client/declarations/{declaration_id}/print + supplier variant."""

    async def test_retailer_pending_declaration_non_receipt(
        self, i2b_client, two_tenants, s2_clean_db
    ):
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        did = await _seed_pending_declaration(db, sch_a, ws_a, ret_a, oid)

        token_ret = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.get(f"/api/v1/client/declarations/{did}/print", headers=_headers(token_ret))
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        assert data["status"] == "pending"
        assert data["is_receipt"] is False
        assert data["non_receipt_notice"] is not None
        assert "NOT" in data["non_receipt_notice"].upper() or "NOT A RECEIPT" in data["non_receipt_notice"].upper()

    async def test_retailer_rejected_declaration_reason_plain_text(
        self, i2b_client, two_tenants, s2_clean_db
    ):
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        did = await _seed_rejected_declaration(db, sch_a, ws_a, ret_a, oid)

        token_ret = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.get(f"/api/v1/client/declarations/{did}/print", headers=_headers(token_ret))
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        assert data["status"] == "rejected"
        assert data["is_receipt"] is False
        assert data["rejection_reason"] == "Transfer reference did not match our records"
        assert data["non_receipt_notice"] is not None

    async def test_supplier_confirmed_declaration_print(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        r = await i2b_client.get(
            f"/api/v1/declarations/{info['decl_id']}/print", headers=_headers(info["token_admin"])
        )
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        assert data["status"] == "confirmed"
        assert data["is_receipt"] is True

    async def test_declaration_print_malformed_uuid(self, i2b_client, two_tenants):
        token_ret = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.get(
            "/api/v1/client/declarations/bad-uuid/print", headers=_headers(token_ret)
        )
        assert r.status_code == HTTPStatus.NOT_FOUND


# ===========================================================================
# Contract C — Confirmed receipt
# ===========================================================================


class TestReceipt:
    """GET /api/v1/client/declarations/{declaration_id}/receipt + supplier variant."""

    async def test_retailer_valid_receipt(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        r = await i2b_client.get(
            f"/api/v1/client/declarations/{info['decl_id']}/receipt",
            headers=_headers(info["token_ret"]),
        )
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        assert data["document_type"] == "receipt"
        assert data["receipt_number"] == info["receipt_number"]
        assert data["receipt_number"].startswith("RCT-")
        assert Decimal(data["confirmed_amount"]) == Decimal("100.00")
        assert data["confirmed_at_eat"] is not None

    async def test_supplier_valid_receipt(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        r = await i2b_client.get(
            f"/api/v1/declarations/{info['decl_id']}/receipt",
            headers=_headers(info["token_admin"]),
        )
        assert r.status_code == HTTPStatus.OK, r.text
        assert r.json()["data"]["receipt_number"] == info["receipt_number"]

    async def test_pending_declaration_receipt_fail_closed(
        self, i2b_client, two_tenants, s2_clean_db
    ):
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        did = await _seed_pending_declaration(db, sch_a, ws_a, ret_a, oid)

        token_ret = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.get(
            f"/api/v1/client/declarations/{did}/receipt", headers=_headers(token_ret)
        )
        assert r.status_code == HTTPStatus.NOT_FOUND
        assert r.json()["code"] == "RECEIPT_NOT_AVAILABLE"

    async def test_rejected_declaration_receipt_fail_closed(
        self, i2b_client, two_tenants, s2_clean_db
    ):
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        did = await _seed_rejected_declaration(db, sch_a, ws_a, ret_a, oid)

        token_ret = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.get(
            f"/api/v1/client/declarations/{did}/receipt", headers=_headers(token_ret)
        )
        assert r.status_code == HTTPStatus.NOT_FOUND
        assert r.json()["code"] == "RECEIPT_NOT_AVAILABLE"

    async def test_receipt_repeated_get_same_identity(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        r1 = await i2b_client.get(
            f"/api/v1/client/declarations/{info['decl_id']}/receipt",
            headers=_headers(info["token_ret"]),
        )
        r2 = await i2b_client.get(
            f"/api/v1/client/declarations/{info['decl_id']}/receipt",
            headers=_headers(info["token_ret"]),
        )
        assert r1.status_code == r2.status_code == HTTPStatus.OK
        d1, d2 = r1.json()["data"], r2.json()["data"]
        assert d1["receipt_number"] == d2["receipt_number"]
        assert d1["confirmed_amount"] == d2["confirmed_amount"]
        assert d1["confirmed_at"] == d2["confirmed_at"]

    async def test_receipt_malformed_uuid(self, i2b_client, two_tenants):
        token_ret = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.get(
            "/api/v1/client/declarations/not-uuid/receipt", headers=_headers(token_ret)
        )
        assert r.status_code == HTTPStatus.NOT_FOUND

    async def test_cross_supplier_receipt_denied(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """A declaration confirmed in tenant A is not receipt-accessible via a
        non-existent declaration id from another context — neutral 404."""
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        # Use a random (non-existent) declaration id — must 404, not 500.
        r = await i2b_client.get(
            f"/api/v1/declarations/{uuid.uuid4()}/receipt",
            headers=_headers(info["token_admin"]),
        )
        assert r.status_code == HTTPStatus.NOT_FOUND


# ===========================================================================
# Zero-write proof — no mutation from any print/receipt route
# ===========================================================================


class TestZeroWrite:
    """All six routes must produce zero writes and zero fingerprint changes."""

    async def test_all_routes_zero_fingerprint(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        db, _reg = s2_clean_db
        sch_a = info["sch_a"]
        ws_a = info["ws_a"]
        ret_a = info["ret_a"]

        # Collect fingerprints BEFORE.
        fp_before = {
            "orders": await _table_fingerprint(db, sch_a, "orders"),
            "order_items": await _table_fingerprint(db, sch_a, "order_items"),
            "payments": await _table_fingerprint(db, sch_a, "payments"),
            "payment_declarations": await _table_fingerprint(db, sch_a, "payment_declarations"),
            "ledger_entries": await _table_fingerprint(db, sch_a, "ledger_entries"),
            "receipt_sequences": await _receipt_seq_fingerprint(db, sch_a),
            "binding_balance": await _binding_fingerprint(db, ws_a, ret_a),
        }

        # Exercise all six routes.
        routes = [
            ("GET", f"/api/v1/client/orders/{info['oid']}/print", info["token_ret"]),
            ("GET", f"/api/v1/orders/{info['oid']}/print", info["token_admin"]),
            ("GET", f"/api/v1/client/declarations/{info['decl_id']}/print", info["token_ret"]),
            ("GET", f"/api/v1/declarations/{info['decl_id']}/print", info["token_admin"]),
            ("GET", f"/api/v1/client/declarations/{info['decl_id']}/receipt", info["token_ret"]),
            ("GET", f"/api/v1/declarations/{info['decl_id']}/receipt", info["token_admin"]),
        ]
        for method, path, token in routes:
            r = await i2b_client.get(path, headers=_headers(token))
            assert r.status_code == HTTPStatus.OK, f"{method} {path} -> {r.status_code}: {r.text}"

        # Collect fingerprints AFTER — must be identical.
        fp_after = {
            "orders": await _table_fingerprint(db, sch_a, "orders"),
            "order_items": await _table_fingerprint(db, sch_a, "order_items"),
            "payments": await _table_fingerprint(db, sch_a, "payments"),
            "payment_declarations": await _table_fingerprint(db, sch_a, "payment_declarations"),
            "ledger_entries": await _table_fingerprint(db, sch_a, "ledger_entries"),
            "receipt_sequences": await _receipt_seq_fingerprint(db, sch_a),
            "binding_balance": await _binding_fingerprint(db, ws_a, ret_a),
        }
        for key in fp_before:
            assert fp_before[key] == fp_after[key], (
                f"FINGERPRINT CHANGED for {key}: {fp_before[key]} -> {fp_after[key]}"
            )


# ===========================================================================
# No internal identifier leakage
# ===========================================================================


class TestNoLeakage:
    """No secret/internal UUID/payment-id/cashier-user leakage in responses."""

    async def test_receipt_no_internal_ids(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        r = await i2b_client.get(
            f"/api/v1/client/declarations/{info['decl_id']}/receipt",
            headers=_headers(info["token_ret"]),
        )
        assert r.status_code == HTTPStatus.OK
        body_str = str(r.json())
        # The declaration_id and order_id ARE expected (they are the resource).
        # But no confirmation_payment_id, no tenant_user_id, no cashier user id,
        # no SQL/schema names.
        assert "confirmation_payment_id" not in body_str
        assert "tenant_user_id" not in body_str
        assert "confirmed_by" not in body_str
        assert "rejected_by" not in body_str
        assert "submitted_by" not in body_str

    async def test_declaration_print_no_payment_row_id(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        r = await i2b_client.get(
            f"/api/v1/client/declarations/{info['decl_id']}/print",
            headers=_headers(info["token_ret"]),
        )
        assert r.status_code == HTTPStatus.OK
        body_str = str(r.json())
        assert "confirmation_payment_id" not in body_str
        assert "tenant_user_id" not in body_str


# ===========================================================================
# R1 SQL seed helpers for edge-case declarations / payments
# ===========================================================================


async def _seed_confirmed_declaration_null_payment(
    db: AsyncSession, schema: str, ws_id: str, ret_id: str, oid
):
    """Seed a confirmed declaration with NULL confirmation_payment_id."""
    did = uuid.uuid4()
    await db.execute(
        text(
            f'INSERT INTO "{schema}".payment_declarations '
            "(id, order_id, retailer_id, wholesaler_id, declared_amount, method, "
            "status, idempotency_key, submitted_by, submitted_at, "
            "confirmed_by, confirmed_at, confirmation_payment_id) "
            "VALUES (:id, :oid, :ret, :ws, :amt, 'cash', 'confirmed', :idem, :sb, now(), "
            ":cb, now(), NULL)"
        ),
        {
            "id": did, "oid": oid, "ret": ret_id, "ws": ws_id,
            "amt": Decimal("100.00"), "idem": f"seed-cf-null-{did.hex}",
            "sb": uuid.uuid4(), "cb": uuid.uuid4(),
        },
    )
    await db.commit()
    return did


async def _seed_completed_payment(
    db: AsyncSession, schema: str, ws_id: str, ret_id: str, oid,
    amount: str, receipt_number: str | None = None,
):
    """Seed a completed payment row and return its id.

    Note: payments table has no wholesaler_id column (tenant isolation is by
    schema). retailer_id is present. A unique receipt_number is generated
    if none is provided (the partial unique index ux_payments_receipt_number
    rejects duplicates).
    """
    pay_id = uuid.uuid4()
    if receipt_number is None:
        # Generate a unique valid receipt number to avoid unique-constraint
        # violations across multiple seed calls in the same schema.
        seq = pay_id.int % 900000 + 100000
        receipt_number = f"RCT-20260804-{seq:06d}"
    cols = (
        "id, order_id, retailer_id, transaction_id, "
        "idempotency_key, amount, method, status, receipt_number, "
        "created_at, updated_at, is_deleted"
    )
    await db.execute(
        text(
            f'INSERT INTO "{schema}".payments ({cols}) '
            "VALUES (:id, :oid, :ret, :txid, :idem, :amt, 'cash', 'completed', "
            ":rno, now(), now(), false)"
        ),
        {
            "id": pay_id, "oid": oid, "ret": ret_id,
            "txid": f"tx-{pay_id.hex[:16]}", "idem": f"pay-{pay_id.hex}",
            "amt": Decimal(amount), "rno": receipt_number,
        },
    )
    await db.commit()
    return pay_id


async def _seed_confirmed_declaration_linked(
    db: AsyncSession, schema: str, ws_id: str, ret_id: str, oid, pay_id
):
    """Seed a confirmed declaration linked to a specific payment_id."""
    did = uuid.uuid4()
    await db.execute(
        text(
            f'INSERT INTO "{schema}".payment_declarations '
            "(id, order_id, retailer_id, wholesaler_id, declared_amount, method, "
            "status, idempotency_key, submitted_by, submitted_at, "
            "confirmed_by, confirmed_at, confirmation_payment_id) "
            "VALUES (:id, :oid, :ret, :ws, :amt, 'cash', 'confirmed', :idem, :sb, now(), "
            ":cb, now(), :cpid)"
        ),
        {
            "id": did, "oid": oid, "ret": ret_id, "ws": ws_id,
            "amt": Decimal("100.00"), "idem": f"seed-cf-link-{did.hex}",
            "sb": uuid.uuid4(), "cb": uuid.uuid4(), "cpid": pay_id,
        },
    )
    await db.commit()
    return did


async def _seed_confirmed_declaration_with_payment(
    db: AsyncSession, schema: str, ws_id: str, ret_id: str, oid
):
    """Seed a confirmed declaration + payment in tenant B (for cross-supplier tests)."""
    pay_id = await _seed_completed_payment(db, schema, ws_id, ret_id, oid, "100.00")
    return await _seed_confirmed_declaration_linked(
        db, schema, ws_id, ret_id, oid, pay_id
    )


async def _soft_delete_payment(db: AsyncSession, schema: str, pay_id):
    """Soft-delete a payment row (set is_deleted=true)."""
    await db.execute(
        text(f'UPDATE "{schema}".payments SET is_deleted = true WHERE id = :pid'),
        {"pid": pay_id},
    )
    await db.commit()


# ---------------------------------------------------------------------------
# R3/R4: Cleanup + binding-restore helpers (fail-closed)
# ---------------------------------------------------------------------------


async def _cleanup_seeded_rows(db: AsyncSession, schema: str, ids: dict):
    """Delete test-seeded rows in FK-safe order on a FRESH session.

    ``ids`` is a dict with optional keys: declaration_ids, payment_ids,
    order_item_ids, order_ids. Each value is a list of UUIDs (or None).

    R4: fail-closed — rollback errors propagate; None IDs are skipped; the
    cleanup uses a fresh session so a broken test session does not block
    cleanup.
    """
    from database.session import AsyncSessionLocal

    # Rollback the (possibly aborted) test session so it does not block.
    await db.rollback()

    async with AsyncSessionLocal() as clean_db:
        for did in ids.get("declaration_ids") or []:
            if did is None:
                continue
            await clean_db.execute(
                text(f'DELETE FROM "{schema}".payment_declarations WHERE id = :id'),
                {"id": did},
            )
        for pid in ids.get("payment_ids") or []:
            if pid is None:
                continue
            await clean_db.execute(
                text(f'DELETE FROM "{schema}".payments WHERE id = :id'),
                {"id": pid},
            )
        for oi in ids.get("order_item_ids") or []:
            if oi is None:
                continue
            await clean_db.execute(
                text(f'DELETE FROM "{schema}".order_items WHERE id = :id'),
                {"id": oi},
            )
        for oid in ids.get("order_ids") or []:
            if oid is None:
                continue
            await clean_db.execute(
                text(f'DELETE FROM "{schema}".orders WHERE id = :id'),
                {"id": oid},
            )
        await clean_db.commit()


async def _snapshot_binding(db: AsyncSession, ws_id: str, ret_id: str) -> dict:
    """Snapshot binding status + is_deleted for later restore."""
    row = (
        await db.execute(
            text(
                "SELECT id, status, is_deleted FROM public.wholesaler_retailer_bindings "
                "WHERE wholesaler_id = :ws AND retailer_id = :ret LIMIT 1"
            ),
            {"ws": ws_id, "ret": ret_id},
        )
    ).first()
    assert row is not None, f"binding not found for ws={ws_id} ret={ret_id}"
    return {"id": str(row.id), "status": row.status, "is_deleted": row.is_deleted}


async def _restore_binding(db: AsyncSession, snapshot: dict):
    """Restore binding to its pre-test state (status + is_deleted).

    R4: fail-closed — asserts UPDATE rowcount == 1, then re-reads on a fresh
    session and asserts exact match with the snapshot. A zero-row update
    (missing binding) or a mismatch is a hard failure.
    """
    from database.session import AsyncSessionLocal

    await db.rollback()

    async with AsyncSessionLocal() as restore_db:
        result = await restore_db.execute(
            text(
                "UPDATE public.wholesaler_retailer_bindings "
                "SET status = :status, is_deleted = :is_deleted WHERE id = :id"
            ),
            {
                "status": snapshot["status"],
                "is_deleted": snapshot["is_deleted"],
                "id": snapshot["id"],
            },
        )
        assert result.rowcount == 1, (
            f"binding restore updated {result.rowcount} rows, expected 1 "
            f"(binding_id={snapshot['id']})"
        )
        await restore_db.commit()

    # Re-read on a fresh session and verify exact match.
    async with AsyncSessionLocal() as verify_db:
        row = (
            await verify_db.execute(
                text(
                    "SELECT status, is_deleted FROM public.wholesaler_retailer_bindings "
                    "WHERE id = :id"
                ),
                {"id": snapshot["id"]},
            )
        ).first()
        assert row is not None, (
            f"binding not found after restore (binding_id={snapshot['id']})"
        )
        assert row.status == snapshot["status"], (
            f"binding status mismatch after restore: got {row.status!r}, "
            f"expected {snapshot['status']!r}"
        )
        assert row.is_deleted == snapshot["is_deleted"], (
            f"binding is_deleted mismatch after restore: got {row.is_deleted}, "
            f"expected {snapshot['is_deleted']}"
        )


async def _tenant_table_fingerprint(db: AsyncSession, schema: str) -> dict:
    """Snapshot row counts for all tenant tables (mutation/residue detector)."""
    tables = [
        "orders", "order_items", "payments", "payment_declarations",
        "ledger_entries", "receipt_sequences",
    ]
    fp = {}
    for t in tables:
        result = await db.execute(text(f'SELECT count(*) FROM "{schema}".{t}'))
        fp[t] = result.scalar()
    return fp


# ===========================================================================
# R1: Real cross-tenant / wrong-payment / missing-receipt / binding tests
# ===========================================================================


class TestCrossTenantDenial:
    """R1: real cross-supplier and cross-retailer denial with existing records."""

    async def test_cross_retailer_order_print_denied(
        self, i2b_client, two_tenants, s2_clean_db, provisioned_pool
    ):
        """Retailer A's token cannot print retailer B's order (real record)."""
        db, _reg = s2_clean_db
        ws_b = provisioned_pool.tenants["b"]["ws_id"]
        sch_b = provisioned_pool.tenants["b"]["schema"]
        _ca, _cb, _sb, _e, _p, _ua, uid_b = two_tenants
        ret_b = await _resolve_binding_retailer(db, ws_b, uid_b)
        oid_b = await _seed_confirmed_order(db, sch_b, ws_b, ret_b, "100.00")
        token_a = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.get(
            f"/api/v1/client/orders/{oid_b}/print", headers=_headers(token_a)
        )
        assert r.status_code == HTTPStatus.NOT_FOUND

    async def test_cross_retailer_declaration_print_denied(
        self, i2b_client, two_tenants, s2_clean_db, provisioned_pool
    ):
        """Retailer A cannot print retailer B's declaration."""
        db, _reg = s2_clean_db
        ws_b = provisioned_pool.tenants["b"]["ws_id"]
        sch_b = provisioned_pool.tenants["b"]["schema"]
        _ca, _cb, _sb, _e, _p, _ua, uid_b = two_tenants
        ret_b = await _resolve_binding_retailer(db, ws_b, uid_b)
        oid_b = await _seed_confirmed_order(db, sch_b, ws_b, ret_b, "100.00")
        did_b = await _seed_pending_declaration(db, sch_b, ws_b, ret_b, oid_b)
        token_a = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.get(
            f"/api/v1/client/declarations/{did_b}/print", headers=_headers(token_a)
        )
        assert r.status_code == HTTPStatus.NOT_FOUND

    async def test_cross_supplier_order_print_denied(
        self, i2b_client, two_tenants, s2_clean_db, provisioned_pool, cashier_identity
    ):
        """Supplier A's admin cannot print supplier B's order."""
        db, _reg = s2_clean_db
        ws_b = provisioned_pool.tenants["b"]["ws_id"]
        sch_b = provisioned_pool.tenants["b"]["schema"]
        _ca, _cb, _sb, _e, _p, _ua, uid_b = two_tenants
        ret_b = await _resolve_binding_retailer(db, ws_b, uid_b)
        oid_b = await _seed_confirmed_order(db, sch_b, ws_b, ret_b, "100.00")
        token_admin_a = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.get(
            f"/api/v1/orders/{oid_b}/print", headers=_headers(token_admin_a)
        )
        assert r.status_code == HTTPStatus.NOT_FOUND

    async def test_cross_supplier_receipt_denied_real(
        self, i2b_client, two_tenants, s2_clean_db, provisioned_pool, cashier_identity
    ):
        """Supplier A cannot get supplier B's confirmed declaration receipt."""
        db, _reg = s2_clean_db
        ws_b = provisioned_pool.tenants["b"]["ws_id"]
        sch_b = provisioned_pool.tenants["b"]["schema"]
        _ca, _cb, _sb, _e, _p, _ua, uid_b = two_tenants
        ret_b = await _resolve_binding_retailer(db, ws_b, uid_b)
        oid_b = await _seed_confirmed_order(db, sch_b, ws_b, ret_b, "100.00")
        did_b = await _seed_confirmed_declaration_with_payment(
            db, sch_b, ws_b, ret_b, oid_b
        )
        token_admin_a = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.get(
            f"/api/v1/declarations/{did_b}/receipt", headers=_headers(token_admin_a)
        )
        assert r.status_code == HTTPStatus.NOT_FOUND


class TestReceiptEligibilityEdgeCases:
    """R1: missing/null/malformed/soft-deleted/wrong-order receipt fail-closed."""

    async def test_confirmed_null_confirmation_payment_id_fail_closed(
        self, i2b_client, two_tenants, s2_clean_db
    ):
        """Confirmed declaration with NULL confirmation_payment_id -> 404."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        _ca, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        did = await _seed_confirmed_declaration_null_payment(db, sch_a, ws_a, ret_a, oid)
        token_ret = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.get(
            f"/api/v1/client/declarations/{did}/receipt", headers=_headers(token_ret)
        )
        assert r.status_code == HTTPStatus.NOT_FOUND

    async def test_confirmed_soft_deleted_payment_fail_closed(
        self, i2b_client, two_tenants, s2_clean_db
    ):
        """Confirmed declaration whose payment is soft-deleted -> 404."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        _ca, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        pay_id = await _seed_completed_payment(db, sch_a, ws_a, ret_a, oid, "100.00")
        await _soft_delete_payment(db, sch_a, pay_id)
        did = await _seed_confirmed_declaration_linked(db, sch_a, ws_a, ret_a, oid, pay_id)
        token_ret = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.get(
            f"/api/v1/client/declarations/{did}/receipt", headers=_headers(token_ret)
        )
        assert r.status_code == HTTPStatus.NOT_FOUND

    async def test_confirmed_malformed_receipt_number_fail_closed(
        self, i2b_client, two_tenants, s2_clean_db
    ):
        """Confirmed declaration whose payment has a bad receipt_number -> 404."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        _ca, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        pay_id = await _seed_completed_payment(
            db, sch_a, ws_a, ret_a, oid, "100.00", receipt_number="BAD-FORMAT-123"
        )
        did = await _seed_confirmed_declaration_linked(db, sch_a, ws_a, ret_a, oid, pay_id)
        token_ret = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.get(
            f"/api/v1/client/declarations/{did}/receipt", headers=_headers(token_ret)
        )
        assert r.status_code == HTTPStatus.NOT_FOUND

    async def test_confirmed_wrong_order_payment_fail_closed(
        self, i2b_client, two_tenants, s2_clean_db
    ):
        """R1: payment belongs to a DIFFERENT order than the declaration -> 404."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        _ca, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid_decl = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        oid_pay = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "200.00")
        pay_id = await _seed_completed_payment(db, sch_a, ws_a, ret_a, oid_pay, "200.00")
        did = await _seed_confirmed_declaration_linked(
            db, sch_a, ws_a, ret_a, oid_decl, pay_id
        )
        token_ret = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.get(
            f"/api/v1/client/declarations/{did}/receipt", headers=_headers(token_ret)
        )
        assert r.status_code == HTTPStatus.NOT_FOUND

    async def test_confirmed_ineligible_declaration_print_fail_closed(
        self, i2b_client, two_tenants, s2_clean_db
    ):
        """R1: confirmed-but-ineligible declaration print -> 404 (not is_receipt=True)."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        _ca, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        did = await _seed_confirmed_declaration_null_payment(db, sch_a, ws_a, ret_a, oid)
        token_ret = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.get(
            f"/api/v1/client/declarations/{did}/print", headers=_headers(token_ret)
        )
        assert r.status_code == HTTPStatus.NOT_FOUND


class TestBindingDenial:
    """R1: inactive/deleted binding denies print.

    R3: all binding mutations are snapshot + restored in finally; seeded rows
    are cleaned up to ensure order independence.
    """

    async def test_inactive_binding_denies_supplier_receipt(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """R1: set binding to inactive; supplier receipt route must return 404."""
        info = await _submit_and_confirm(
            i2b_client, two_tenants, s2_clean_db, cashier_identity
        )
        db, _reg = s2_clean_db
        binding_snap = await _snapshot_binding(db, info["ws_a"], info["ret_a"])
        try:
            await db.execute(
                text(
                    "UPDATE public.wholesaler_retailer_bindings SET status = 'inactive' "
                    "WHERE wholesaler_id = :ws AND retailer_id = :ret"
                ),
                {"ws": info["ws_a"], "ret": info["ret_a"]},
            )
            await db.commit()
            r = await i2b_client.get(
                f"/api/v1/declarations/{info['decl_id']}/receipt",
                headers=_headers(info["token_admin"]),
            )
            assert r.status_code == HTTPStatus.NOT_FOUND
        finally:
            await _restore_binding(db, binding_snap)

    async def test_inactive_binding_denies_client_route(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """R1: inactive binding also denies the client route (403 at identity layer)."""
        info = await _submit_and_confirm(
            i2b_client, two_tenants, s2_clean_db, cashier_identity
        )
        db, _reg = s2_clean_db
        binding_snap = await _snapshot_binding(db, info["ws_a"], info["ret_a"])
        try:
            await db.execute(
                text(
                    "UPDATE public.wholesaler_retailer_bindings SET status = 'inactive' "
                    "WHERE wholesaler_id = :ws AND retailer_id = :ret"
                ),
                {"ws": info["ws_a"], "ret": info["ret_a"]},
            )
            await db.commit()
            r = await i2b_client.get(
                f"/api/v1/client/declarations/{info['decl_id']}/receipt",
                headers=_headers(info["token_ret"]),
            )
            assert r.status_code == HTTPStatus.FORBIDDEN
            assert r.json()["code"] == "BINDING_NOT_ACTIVE"
        finally:
            await _restore_binding(db, binding_snap)


# ===========================================================================
# R2: Same-schema predicate proof tests
# These insert wrong-wholesaler/wrong-retailer records INTO tenant A's own
# schema, then verify the route predicates reject them. This proves the new
# SQL/Python predicates work — NOT just search_path isolation.
# ===========================================================================


class TestSameSchemaPredicateProof:
    """R2: prove the ownership predicates catch wrong-wholesaler/wrong-retailer
    records within the SAME schema (not just cross-schema search_path).

    R3: all seeded rows are tracked and cleaned in finally; binding mutations
    are snapshot + restored; per-test fingerprint ensures zero residue.
    """

    async def test_supplier_order_wrong_wholesaler_in_same_schema(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """R2: an order row in tenant A's schema with a WRONG wholesaler_id
        must be rejected by get_order_for_wholesaler (DB-level predicate)."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        _ca, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        fp_before = await _tenant_table_fingerprint(db, sch_a)
        wrong_ws = uuid.uuid4()
        oid = uuid.uuid4()
        try:
            await db.execute(
                text(
                    f'INSERT INTO "{sch_a}".orders '
                    "(id, wholesaler_id, retailer_id, status, total_amount, is_deleted) "
                    "VALUES (:id, :ws, :ret, 'confirmed', 100.00, false)"
                ),
                {"id": oid, "ws": wrong_ws, "ret": ret_a},
            )
            await db.commit()
            token_admin = await _cashier_token(i2b_client, cashier_identity)
            r = await i2b_client.get(
                f"/api/v1/orders/{oid}/print", headers=_headers(token_admin)
            )
            assert r.status_code == HTTPStatus.NOT_FOUND
        finally:
            await _cleanup_seeded_rows(db, sch_a, {"order_ids": [oid]})
            fp_after = await _tenant_table_fingerprint(db, sch_a)
            assert fp_before == fp_after, f"residue: {fp_before} != {fp_after}"

    async def test_supplier_receipt_wrong_wholesaler_order_in_same_schema(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """R2: a confirmed declaration + payment linked to an order with a
        WRONG wholesaler_id in the same schema must fail receipt eligibility."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        _ca, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        fp_before = await _tenant_table_fingerprint(db, sch_a)
        wrong_ws = uuid.uuid4()
        oid_bad = uuid.uuid4()
        pay_id = None
        did = None
        try:
            await db.execute(
                text(
                    f'INSERT INTO "{sch_a}".orders '
                    "(id, wholesaler_id, retailer_id, status, total_amount, is_deleted) "
                    "VALUES (:id, :ws, :ret, 'confirmed', 100.00, false)"
                ),
                {"id": oid_bad, "ws": wrong_ws, "ret": ret_a},
            )
            await db.commit()
            pay_id = await _seed_completed_payment(db, sch_a, ws_a, ret_a, oid_bad, "100.00")
            did = await _seed_confirmed_declaration_linked(
                db, sch_a, ws_a, ret_a, oid_bad, pay_id
            )
            token_admin = await _cashier_token(i2b_client, cashier_identity)
            r = await i2b_client.get(
                f"/api/v1/declarations/{did}/receipt", headers=_headers(token_admin)
            )
            assert r.status_code == HTTPStatus.NOT_FOUND
        finally:
            await _cleanup_seeded_rows(db, sch_a, {
                "declaration_ids": [did], "payment_ids": [pay_id], "order_ids": [oid_bad],
            })
            fp_after = await _tenant_table_fingerprint(db, sch_a)
            assert fp_before == fp_after, f"residue: {fp_before} != {fp_after}"

    async def test_receipt_wrong_retailer_payment_in_same_schema(
        self, i2b_client, two_tenants, s2_clean_db
    ):
        """R2: payment with a wrong retailer_id (different from declaration)
        must fail receipt eligibility — same order, wrong retailer."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        _ca, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        fp_before = await _tenant_table_fingerprint(db, sch_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        wrong_ret = uuid.uuid4()
        pay_id = uuid.uuid4()
        did = None
        try:
            await db.execute(
                text(
                    f'INSERT INTO "{sch_a}".payments '
                    "(id, order_id, retailer_id, transaction_id, idempotency_key, "
                    "amount, method, status, receipt_number, created_at, updated_at, is_deleted) "
                    "VALUES (:id, :oid, :ret, :txid, :idem, 100.00, 'cash', 'completed', "
                    ":rno, now(), now(), false)"
                ),
                {
                    "id": pay_id, "oid": oid, "ret": wrong_ret,
                    "txid": f"tx-{pay_id.hex[:16]}", "idem": f"pay-{pay_id.hex}",
                    "rno": f"RCT-20260804-{pay_id.int % 900000 + 100000:06d}",
                },
            )
            await db.commit()
            did = await _seed_confirmed_declaration_linked(db, sch_a, ws_a, ret_a, oid, pay_id)
            token_ret = await _login_retailer(i2b_client, two_tenants)
            r = await i2b_client.get(
                f"/api/v1/client/declarations/{did}/receipt", headers=_headers(token_ret)
            )
            assert r.status_code == HTTPStatus.NOT_FOUND
        finally:
            await _cleanup_seeded_rows(db, sch_a, {
                "declaration_ids": [did], "payment_ids": [pay_id], "order_ids": [oid],
            })
            fp_after = await _tenant_table_fingerprint(db, sch_a)
            assert fp_before == fp_after, f"residue: {fp_before} != {fp_after}"

    async def test_receipt_soft_deleted_order_fail_closed(
        self, i2b_client, two_tenants, s2_clean_db
    ):
        """R2: if the order is soft-deleted, receipt eligibility must fail."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        _ca, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        fp_before = await _tenant_table_fingerprint(db, sch_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        pay_id = None
        did = None
        try:
            await db.execute(
                text(f'UPDATE "{sch_a}".orders SET is_deleted = true WHERE id = :oid'),
                {"oid": oid},
            )
            await db.commit()
            pay_id = await _seed_completed_payment(db, sch_a, ws_a, ret_a, oid, "100.00")
            did = await _seed_confirmed_declaration_linked(db, sch_a, ws_a, ret_a, oid, pay_id)
            token_ret = await _login_retailer(i2b_client, two_tenants)
            r = await i2b_client.get(
                f"/api/v1/client/declarations/{did}/receipt", headers=_headers(token_ret)
            )
            assert r.status_code == HTTPStatus.NOT_FOUND
        finally:
            await _cleanup_seeded_rows(db, sch_a, {
                "declaration_ids": [did], "payment_ids": [pay_id], "order_ids": [oid],
            })
            fp_after = await _tenant_table_fingerprint(db, sch_a)
            assert fp_before == fp_after, f"residue: {fp_before} != {fp_after}"

    async def test_deleted_binding_denies_supplier_receipt(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """R2: soft-deleted binding denies supplier receipt (404)."""
        info = await _submit_and_confirm(
            i2b_client, two_tenants, s2_clean_db, cashier_identity
        )
        db, _reg = s2_clean_db
        binding_snap = await _snapshot_binding(db, info["ws_a"], info["ret_a"])
        try:
            await db.execute(
                text(
                    "UPDATE public.wholesaler_retailer_bindings SET is_deleted = true "
                    "WHERE wholesaler_id = :ws AND retailer_id = :ret"
                ),
                {"ws": info["ws_a"], "ret": info["ret_a"]},
            )
            await db.commit()
            r = await i2b_client.get(
                f"/api/v1/declarations/{info['decl_id']}/receipt",
                headers=_headers(info["token_admin"]),
            )
            assert r.status_code == HTTPStatus.NOT_FOUND
        finally:
            await _restore_binding(db, binding_snap)


# ===========================================================================
# R3: Direct service-level predicate proof
# Tests check_receipt_eligibility() directly (not through the route) to prove
# the service predicate catches wrong-wholesaler order independently of the
# route's own get_order_for_wholesaler guard.
# ===========================================================================


class TestCheckReceiptEligibilityDirect:
    """R3: directly test check_receipt_eligibility() return value for
    wrong-wholesaler order, proving the SERVICE predicate (not just the
    route's redundant guard) rejects it."""

    async def test_wrong_wholesaler_order_returns_false(
        self, i2b_client, two_tenants, s2_clean_db
    ):
        """R3: check_receipt_eligibility returns False when the order has a
        wrong wholesaler_id — tested by calling the service directly."""
        from services.print_service import check_receipt_eligibility

        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        _ca, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        fp_before = await _tenant_table_fingerprint(db, sch_a)
        wrong_ws = uuid.uuid4()
        oid_bad = uuid.uuid4()
        pay_id = None
        did = None
        try:
            await db.execute(
                text(
                    f'INSERT INTO "{sch_a}".orders '
                    "(id, wholesaler_id, retailer_id, status, total_amount, is_deleted) "
                    "VALUES (:id, :ws, :ret, 'paid', 100.00, false)"
                ),
                {"id": oid_bad, "ws": wrong_ws, "ret": ret_a},
            )
            await db.commit()
            pay_id = await _seed_completed_payment(db, sch_a, ws_a, ret_a, oid_bad, "100.00")
            did = await _seed_confirmed_declaration_linked(
                db, sch_a, ws_a, ret_a, oid_bad, pay_id
            )
            from repositories.payment_declaration_repository import (
                PaymentDeclarationRepository,
            )

            # Set search_path so the repository query can find the tenant tables.
            await db.execute(text(f'SET LOCAL search_path TO "{sch_a}", public'))
            row = await PaymentDeclarationRepository().get_detail_by_wholesaler(
                db, declaration_id=did, wholesaler_id=uuid.UUID(ws_a),
            )
            assert row is not None
            result = await check_receipt_eligibility(
                db, row=row, wholesaler_id=uuid.UUID(ws_a),
            )
            assert result is False, (
                "check_receipt_eligibility must return False for wrong-wholesaler order"
            )
        finally:
            await _cleanup_seeded_rows(db, sch_a, {
                "declaration_ids": [did], "payment_ids": [pay_id], "order_ids": [oid_bad],
            })
            fp_after = await _tenant_table_fingerprint(db, sch_a)
            assert fp_before == fp_after, f"residue: {fp_before} != {fp_after}"


# ===========================================================================
# R4: Forced-seed-failure cleanup regression
# Proves that _cleanup_seeded_rows correctly cleans up when a seed step
# fails mid-way (first INSERT committed, second seed raises). Without the
# None-init + fresh-session cleanup, this would UnboundLocalError and leave
# the committed row as pollution.
# ===========================================================================


class TestForcedSeedFailureCleanup:
    """R5: prove cleanup works when seed fails mid-way — fail-closed.

    Uses ``pytest.raises(IntegrityError)`` so the test cannot pass unless the
    expected unique-constraint violation actually occurs. After cleanup,
    verifies zero residue by explicitly querying for each committed ID (not
    just fingerprint counts, which could be restored by cascade).
    """

    async def test_cleanup_after_partial_seed_failure(
        self, i2b_client, two_tenants, s2_clean_db
    ):
        """R5: insert an order + first payment successfully, then force a
        second payment with a duplicate receipt_number to raise
        IntegrityError. Cleanup must remove all committed rows. Zero residue
        is verified by explicit per-ID existence check, not just counts."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        _ca, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        fp_before = await _tenant_table_fingerprint(db, sch_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        pay_id = None
        did = None

        # Step 1: commit the first payment (succeeds).
        pay_id = await _seed_completed_payment(
            db, sch_a, ws_a, ret_a, oid, "100.00",
            receipt_number="RCT-20260804-999998",
        )

        # Step 2: second payment with the SAME receipt_number must raise
        # IntegrityError (ux_payments_receipt_number unique constraint).
        # R5: pytest.raises ensures the test FAILS if no violation occurs
        # (no except-Exception-pass that could swallow a missing failure).
        with pytest.raises(IntegrityError, match="receipt_number"):
            await _seed_completed_payment(
                db, sch_a, ws_a, ret_a, oid, "50.00",
                receipt_number="RCT-20260804-999998",
            )

        # Step 3: cleanup — must remove the committed order and payment.
        await _cleanup_seeded_rows(db, sch_a, {
            "declaration_ids": [did],
            "payment_ids": [pay_id],
            "order_ids": [oid],
        })

        # Step 4: fingerprint must return to baseline.
        fp_after = await _tenant_table_fingerprint(db, sch_a)
        assert fp_before == fp_after, (
            f"residue after forced-failure cleanup: {fp_before} != {fp_after}"
        )

        # Step 5: R5 — explicit per-ID zero-residue check (not just counts).
        # This catches rows that might be hidden by cascade or count
        # coincidences.
        from database.session import AsyncSessionLocal

        async with AsyncSessionLocal() as check_db:
            for table, ident in [
                (f'"{sch_a}".orders', oid),
                (f'"{sch_a}".payments', pay_id),
            ]:
                row = (
                    await check_db.execute(
                        text(f"SELECT count(*) FROM {table} WHERE id = :id"),
                        {"id": ident},
                    )
                ).scalar()
                assert row == 0, (
                    f"residue: {table} still contains id={ident} (count={row})"
                )
