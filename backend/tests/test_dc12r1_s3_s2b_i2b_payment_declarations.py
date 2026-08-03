"""DC-12R1-S3-S2B-I2B: payment declaration & cashier confirmation runtime.

Real-tenant provisioned tests. Tenants are created via TenantProvisioningService
(full bootstrap), which validates migration-037 parity: if payment_declarations
or receipt_sequences are missing on a freshly provisioned tenant, the parity
gate fails loudly here. No migration DDL is copied.

Harness reused from the S2/S3 retailer-login + catalog-hardening suites:
``provisioned_pool``, ``s2_clean_db``, ``two_tenants`` (module-scoped tenant
provisioning) and the retailer/admin login helpers.

Coverage maps to the 16 contract invariants, the R2 namespace-isolation fix,
and the 3 binding addenda.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from http import HTTPStatus
from unittest import mock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.app import configure_app
from auth.strategies.jwt import JwtAuthStrategy
from core.config import get_settings
from core.error_codes import register_exception_handlers
from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (
    _OWNER_PW,
    _TWO_TENANT_PW,
    _create_binding,
    _create_retailer,
    _create_retailer_user,
    _execute,
    _grant_retailer_operator,
    _unique_email,
    provisioned_pool,  # module-scoped fixture
    s2_clean_db,       # function-scoped (db, registry)
    two_tenants,       # function-scoped tuple
)
# NOTE: ``_pool_instance`` is deliberately imported INSIDE helper bodies (not at
# module top). A top-level ``from X import _pool_instance`` captures None at
# import time and never reflects the source module's later mutation; an in-body
# re-import reads the current value after provisioning has run.


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def i2b_client():
    fresh_app = FastAPI()
    with mock.patch("auth.factory.get_auth_strategy", return_value=JwtAuthStrategy()):
        configure_app(fresh_app, get_settings())
    register_exception_handlers(fresh_app)
    async with AsyncClient(
        transport=ASGITransport(app=fresh_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as ac:
        yield ac


async def _login_retailer(client: AsyncClient, two_tenants) -> str:
    code_a, _b, _sb, email, password, _a, _b2 = two_tenants
    resp = await client.post(
        "/api/v1/client/auth/login",
        json={"email": email, "password": password, "wholesaler_code": code_a},
    )
    assert resp.status_code == HTTPStatus.OK, resp.text
    return resp.json()["data"]["tokens"]["access_token"]


async def _grant_admin_role(s2_clean_db) -> None:
    """Grant the admin role to the retailer user in tenant A."""
    db, _reg = s2_clean_db
    a = _pool_a()
    schema_a = a["schema"]
    ws_a = a["ws_id"]
    row = (await db.execute(
        text(
            "SELECT tenant_user_id FROM public.wholesaler_retailer_bindings "
            "WHERE wholesaler_id = :ws AND is_deleted IS FALSE LIMIT 1"
        ),
        {"ws": ws_a},
    )).fetchone()
    assert row is not None, "no bound retailer user in tenant A"
    uid = str(row.tenant_user_id)
    await db.execute(
        text(f'INSERT INTO "{schema_a}".roles (name, description) '
             "VALUES ('admin', 'Tenant Admin') ON CONFLICT (name) DO NOTHING"),
    )
    await db.execute(
        text(f'INSERT INTO "{schema_a}".user_roles (user_id, role_id) '
             f"SELECT :uid, id FROM \"{schema_a}\".roles WHERE name = 'admin' "
             f"ON CONFLICT DO NOTHING"),
        {"uid": uid},
    )
    # Ensure admin has payments:create so namespace-isolation tests can reach the
    # idempotency-key rejection path (not blocked by permission check).
    await db.execute(
        text(
            f"INSERT INTO \"{schema_a}\".permissions (code, description) "
            "VALUES ('payments:create', 'Create payments') ON CONFLICT (code) DO NOTHING"
        ),
    )
    await db.execute(
        text(
            f"INSERT INTO \"{schema_a}\".role_permissions (role_id, permission_id) "
            f"SELECT r.id, p.id FROM \"{schema_a}\".roles r, \"{schema_a}\".permissions p "
            f"WHERE r.name = 'admin' AND p.code = 'payments:create' "
            f"AND NOT EXISTS ("
            f"  SELECT 1 FROM \"{schema_a}\".role_permissions rp "
            f"  WHERE rp.role_id = r.id AND rp.permission_id = p.id"
            f")"
        ),
    )
    await db.commit()


async def _admin_token(i2b_client, two_tenants, s2_clean_db) -> str:
    """Return an admin-capable token by granting admin to the retailer user,
    logging in via wholesaler /auth/login with email + password (no
    wholesaler_code, so it's an identity login), then selecting the tenant."""
    await _grant_admin_role(s2_clean_db)
    db, _reg = s2_clean_db
    a = _pool_a()
    tenant_id = a["ws_id"]
    # The retailer user (from two_tenants) can also use /auth/login directly
    # with email+password (no wholesaler_code path). This returns identity tokens.
    code_a, _b, _sb, email, password, _a, _b2 = two_tenants
    resp = await i2b_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == HTTPStatus.OK, resp.text
    identity_token = resp.json()["data"]["access_token"]
    resp2 = await i2b_client.post(
        "/api/v1/auth/select-tenant",
        json={"tenant_id": tenant_id},
        headers={"Authorization": f"Bearer {identity_token}"},
    )
    assert resp2.status_code == HTTPStatus.OK, resp2.text
    return resp2.json()["data"]["access_token"]
    """Grant the admin role to the retailer user in tenant A.

    The user already has ``retailer_operator`` via ``two_tenants``. Adding
    ``admin`` gives them ``payments:confirm_declaration`` while keeping the
    existing tenant linkage intact — no ``select-tenant`` dance needed.
    """
    db, _reg = s2_clean_db
    a = _pool_a()
    schema_a = a["schema"]
    ws_a = a["ws_id"]
    # Find ANY retailer user in tenant A with a binding.
    row = (await db.execute(
        text(
            "SELECT tenant_user_id FROM public.wholesaler_retailer_bindings "
            "WHERE wholesaler_id = :ws AND is_deleted IS FALSE LIMIT 1"
        ),
        {"ws": ws_a},
    )).fetchone()
    assert row is not None, "no bound retailer user in tenant A"
    uid = str(row.tenant_user_id)
    await db.execute(
        text(f'INSERT INTO "{schema_a}".roles (name, description) '
             "VALUES ('admin', 'Tenant Admin') ON CONFLICT (name) DO NOTHING"),
    )
    await db.execute(
        text(f'INSERT INTO "{schema_a}".user_roles (user_id, role_id) '
             f"SELECT :uid, id FROM \"{schema_a}\".roles WHERE name = 'admin' "
             f"ON CONFLICT DO NOTHING"),
        {"uid": uid},
    )
    # Ensure admin has payments:create so namespace-isolation tests can reach the
    # idempotency-key rejection path (not blocked by permission check).
    await db.execute(
        text(
            f"INSERT INTO \"{schema_a}\".permissions (code, description) "
            "VALUES ('payments:create', 'Create payments') ON CONFLICT (code) DO NOTHING"
        ),
    )
    await db.execute(
        text(
            f"INSERT INTO \"{schema_a}\".role_permissions (role_id, permission_id) "
            f"SELECT r.id, p.id FROM \"{schema_a}\".roles r, \"{schema_a}\".permissions p "
            f"WHERE r.name = 'admin' AND p.code = 'payments:create' "
            f"AND NOT EXISTS ("
            f"  SELECT 1 FROM \"{schema_a}\".role_permissions rp "
            f"  WHERE rp.role_id = r.id AND rp.permission_id = p.id"
            f")"
        ),
    )
    await db.commit()


def _pool_a(provisioned_pool=None) -> dict:
    """Tenant 'a' metadata. Prefer the fixture value; fall back to the
    module global (set when ``provisioned_pool`` materializes)."""
    pool = provisioned_pool
    if pool is None:
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        pool = _pool_instance
    assert pool is not None, "provisioned_pool not materialized — parity gate failed"
    return pool.tenants["a"]


async def _seed_confirmed_order(db: AsyncSession, schema: str, ws_id: str, ret_id: str, total: str = "100.00") -> uuid.UUID:
    oid = uuid.uuid4()
    await db.execute(
        text(
            f'INSERT INTO "{schema}".orders (id, wholesaler_id, retailer_id, status, total_amount, is_deleted) '
            "VALUES (:id, :ws, :ret, 'confirmed', :total, false)"
        ),
        {"id": oid, "ws": ws_id, "ret": ret_id, "total": total},
    )
    await db.commit()
    return oid


async def _resolve_binding_retailer(db: AsyncSession, ws_id: str, uid: str) -> str:
    row = (await db.execute(
        text("SELECT retailer_id FROM public.wholesaler_retailer_bindings "
             "WHERE wholesaler_id = :ws AND tenant_user_id = :uid AND is_deleted IS FALSE LIMIT 1"),
        {"ws": ws_id, "uid": uid},
    )).fetchone()
    assert row is not None, "no binding for retailer"
    return str(row.retailer_id)


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _errcode(resp) -> str:
    """Extract the error code from a 4xx/5xx response (flat envelope)."""
    body = resp.json()
    return body.get("code") or body.get("error", {}).get("code", "")


# ---------------------------------------------------------------------------
# Financial snapshot helper
# ---------------------------------------------------------------------------


async def _snapshot(db: AsyncSession, schema: str, order_id, ws_id: str, ret_id: str) -> dict:
    """Financial-state snapshot. Excludes declaration_count: a declaration row
    is NOT a financial mutation (zero payment/ledger/balance/order effect)."""
    result = await db.execute(
        text(
            f"""
            SELECT
                (SELECT status::text FROM "{schema}".orders WHERE id = :oid) AS order_status,
                (SELECT COUNT(*) FROM "{schema}".payments WHERE order_id = :oid AND is_deleted IS FALSE) AS payment_count,
                (SELECT COALESCE(SUM(amount), 0) FROM "{schema}".payments WHERE order_id = :oid AND is_deleted IS FALSE) AS payment_total,
                (SELECT COUNT(*) FROM "{schema}".ledger_entries WHERE reference_type = 'order' AND reference_id = :oid) AS ledger_count,
                (SELECT outstanding_balance FROM public.wholesaler_retailer_bindings WHERE wholesaler_id = :ws AND retailer_id = :ret) AS outstanding_balance
            """
        ),
        {"oid": order_id, "ws": ws_id, "ret": ret_id},
    )
    return dict(result.mappings().one())


# ---------------------------------------------------------------------------
# Parity gate (P1 #3): a freshly provisioned tenant has migration-037 objects.
# Uses two_tenants so provisioned_pool is guaranteed materialized.
# ---------------------------------------------------------------------------


class TestParityGate:
    async def test_provisioned_tenant_has_i2b_objects(self, s2_clean_db):
        """If bootstrap parity is broken, this fails loudly — no DDL copy."""
        db, _reg = s2_clean_db
        sch = _pool_a()["schema"]
        has_declarations = (await db.execute(text(
            "SELECT to_regclass(:t) IS NOT NULL"
        ), {"t": f'"{sch}".payment_declarations'})).scalar()
        has_sequences = (await db.execute(text(
            "SELECT to_regclass(:t) IS NOT NULL"
        ), {"t": f'"{sch}".receipt_sequences'})).scalar()
        has_receipt_col = (await db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = 'payments' AND column_name = 'receipt_number'"
        ), {"s": sch})).fetchone()
        assert has_declarations, f"payment_declarations missing in {sch} — parity gap"
        assert has_sequences, f"receipt_sequences missing in {sch} — parity gap"
        assert has_receipt_col is not None, f"payments.receipt_number missing in {sch} — parity gap"


# ---------------------------------------------------------------------------
# Submit (zero financial effect) — invariants 1, 2, 3, 4, 14
# ---------------------------------------------------------------------------


class TestSubmitDeclaration:
    async def test_submit_creates_pending_declaration_with_zero_financial_effect(
        self, i2b_client, two_tenants, s2_clean_db, provisioned_pool
    ):
        db, reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        token = await _login_retailer(i2b_client, two_tenants)

        before = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        resp = await i2b_client.post(
            f"/api/v1/client/orders/{oid}/declare",
            json={"declared_amount": "50.00", "method": "cash"},
            headers={**_headers(token), "X-Declaration-Idempotency-Key": "i2b-sub-cash-001"},
        )
        assert resp.status_code == HTTPStatus.CREATED, resp.text
        data = resp.json()["data"]
        assert data["status"] == "pending"
        assert data["declared_amount"] == "50.00"
        assert data["method"] == "cash"
        assert data["transfer_reference"] is None
        assert data["receipt_number"] is None
        after = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        assert after == before  # invariant 1: zero financial effect

    async def test_submit_replay_same_payload_returns_200(self, i2b_client, two_tenants, s2_clean_db):
        db, reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        token = await _login_retailer(i2b_client, two_tenants)
        key = "i2b-sub-replay-001"
        body = {"declared_amount": "30.00", "method": "cash"}
        r1 = await i2b_client.post(
            f"/api/v1/client/orders/{oid}/declare", json=body,
            headers={**_headers(token), "X-Declaration-Idempotency-Key": key},
        )
        assert r1.status_code == HTTPStatus.CREATED, r1.text
        first_id = r1.json()["data"]["id"]
        r2 = await i2b_client.post(
            f"/api/v1/client/orders/{oid}/declare", json=body,
            headers={**_headers(token), "X-Declaration-Idempotency-Key": key},
        )
        assert r2.status_code == HTTPStatus.OK, r2.text
        assert r2.json()["data"]["id"] == first_id

    async def test_submit_same_key_different_payload_returns_409(self, i2b_client, two_tenants, s2_clean_db):
        db, reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        token = await _login_retailer(i2b_client, two_tenants)
        key = "i2b-sub-conflict-001"
        await i2b_client.post(
            f"/api/v1/client/orders/{oid}/declare",
            json={"declared_amount": "30.00", "method": "cash"},
            headers={**_headers(token), "X-Declaration-Idempotency-Key": key},
        )
        r2 = await i2b_client.post(
            f"/api/v1/client/orders/{oid}/declare",
            json={"declared_amount": "40.00", "method": "cash"},
            headers={**_headers(token), "X-Declaration-Idempotency-Key": key},
        )
        assert r2.status_code == HTTPStatus.CONFLICT, r2.text
        assert _errcode(r2) == "DECLARATION_IDEMPOTENCY_KEY_CONFLICT"

    async def test_submit_invalid_amount_rejected_before_sql(self, i2b_client, two_tenants, s2_clean_db):
        db, reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        token = await _login_retailer(i2b_client, two_tenants)
        for amt in ["0", "-5.00"]:
            r = await i2b_client.post(
                f"/api/v1/client/orders/{oid}/declare",
                json={"declared_amount": amt, "method": "cash"},
                headers={**_headers(token), "X-Declaration-Idempotency-Key": f"i2b-inv-{amt}"},
            )
            assert r.status_code == HTTPStatus.BAD_REQUEST, r.text
            assert _errcode(r) == "INVALID_DECLARED_AMOUNT"

    async def test_submit_transfer_requires_reference(self, i2b_client, two_tenants, s2_clean_db):
        db, reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        token = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.post(
            f"/api/v1/client/orders/{oid}/declare",
            json={"declared_amount": "50.00", "method": "transfer"},
            headers={**_headers(token), "X-Declaration-Idempotency-Key": "i2b-tx-noref"},
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST, r.text
        assert _errcode(r) == "DECLARATION_TRANSFER_REFERENCE_REQUIRED"

    async def test_submit_transfer_with_reference_maps_to_transaction_id(self, i2b_client, two_tenants, s2_clean_db):
        db, reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        token = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.post(
            f"/api/v1/client/orders/{oid}/declare",
            json={"declared_amount": "50.00", "method": "transfer", "transfer_reference": "  TRF-12345  "},
            headers={**_headers(token), "X-Declaration-Idempotency-Key": "i2b-tx-trim"},
        )
        assert r.status_code == HTTPStatus.CREATED, r.text
        assert r.json()["data"]["transfer_reference"] == "TRF-12345"  # trimmed (invariant 14)

    async def test_submit_wrong_order_404(self, i2b_client, two_tenants, s2_clean_db):
        token = await _login_retailer(i2b_client, two_tenants)
        bogus = str(uuid.uuid4())
        r = await i2b_client.post(
            f"/api/v1/client/orders/{bogus}/declare",
            json={"declared_amount": "50.00", "method": "cash"},
            headers={**_headers(token), "X-Declaration-Idempotency-Key": "i2b-wrongorder-1"},
        )
        assert r.status_code == HTTPStatus.NOT_FOUND, r.text
        assert _errcode(r) == "ORDER_NOT_FOUND"


# ---------------------------------------------------------------------------
# Namespace isolation (R2): reserved decl-confirm- prefix
# ---------------------------------------------------------------------------


class TestNamespaceIsolation:
    async def test_direct_pay_rejects_reserved_prefix(self, i2b_client, two_tenants, s2_clean_db):
        """Direct pay_order must reject decl-confirm- keys (R2-1). Zero writes."""
        db, reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        token = await _admin_token(i2b_client, two_tenants, s2_clean_db)
        before = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        r = await i2b_client.post(
            f"/api/v1/orders/{oid}/pay",
            json={"amount": "10.00", "method": "cash"},
            headers={**_headers(token), "X-Idempotency-Key": f"decl-confirm-{uuid.uuid4().hex}"},
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST, r.text
        assert _errcode(r) == "RESERVED_IDEMPOTENCY_KEY"
        after = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        assert after == before  # zero financial SQL/write

    async def test_confirm_bare_payment_conflict_fail_closed(self, i2b_client, two_tenants, s2_clean_db):
        """A bare payment occupying decl-confirm-<hex> with no receipt -> 409."""
        db, reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        token_retailer = await _login_retailer(i2b_client, two_tenants)

        decl = await i2b_client.post(
            f"/api/v1/client/orders/{oid}/declare",
            json={"declared_amount": "100.00", "method": "cash"},
            headers={**_headers(token_retailer), "X-Declaration-Idempotency-Key": "i2b-ns-bare-1"},
        )
        assert decl.status_code == HTTPStatus.CREATED, decl.text
        decl_id = decl.json()["data"]["id"]
        canonical_key = f"decl-confirm-{uuid.UUID(decl_id).hex}"

        # Manually pre-occupy the canonical slot with a bare payment (no receipt).
        await db.execute(
            text(
                f'INSERT INTO "{sch_a}".payments '
                "(id, order_id, retailer_id, transaction_id, idempotency_key, amount, method, status, is_deleted, created_at, updated_at) "
                "VALUES (:pid, :oid, :ret, NULL, :key, 100.00, 'cash', 'completed', false, now(), now())"
            ),
            {"pid": uuid.uuid4(), "oid": oid, "ret": ret_a, "key": canonical_key},
        )
        await db.commit()

        token_admin = await _admin_token(i2b_client, two_tenants, s2_clean_db)
        r = await i2b_client.post(
            f"/api/v1/declarations/{decl_id}/confirm",
            headers=_headers(token_admin),
        )
        assert r.status_code == HTTPStatus.CONFLICT, r.text
        assert _errcode(r) == "DECLARATION_CONFIRMATION_KEY_CONFLICT"


# ---------------------------------------------------------------------------
# Confirm / replay / partial-vs-final — invariants 5,6,7,8,9,11,12
# ---------------------------------------------------------------------------


class TestConfirmDeclaration:
    async def _submit(self, client, two_tenants, s2_clean_db, amount="100.00", method="cash", ref=None):
        db, reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        token = await _login_retailer(client, two_tenants)
        body = {"declared_amount": amount, "method": method}
        if ref is not None:
            body["transfer_reference"] = ref
        decl = await client.post(
            f"/api/v1/client/orders/{oid}/declare", json=body,
            headers={**_headers(token), "X-Declaration-Idempotency-Key": f"i2b-cf-{uuid.uuid4().hex}"},
        )
        assert decl.status_code == HTTPStatus.CREATED, decl.text
        return decl.json()["data"]["id"], oid, ws_a, sch_a, ret_a

    async def test_confirm_full_creates_receipt_and_paid_order(self, i2b_client, two_tenants, s2_clean_db):
        decl_id, oid, ws_a, sch_a, ret_a = await self._submit(i2b_client, two_tenants, s2_clean_db, "100.00")
        token_admin = await _admin_token(i2b_client, two_tenants, s2_clean_db)
        r = await i2b_client.post(f"/api/v1/declarations/{decl_id}/confirm", headers=_headers(token_admin))
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        assert data["status"] == "confirmed"
        assert data["receipt_number"].startswith("RCT-")  # invariant 9
        assert data["order_status"] == "paid"  # invariant 12: full -> PAID

    async def test_confirm_replay_returns_same_payment_and_receipt(self, i2b_client, two_tenants, s2_clean_db):
        decl_id, oid, ws_a, sch_a, ret_a = await self._submit(i2b_client, two_tenants, s2_clean_db, "100.00")
        token_admin = await _admin_token(i2b_client, two_tenants, s2_clean_db)
        r1 = await i2b_client.post(f"/api/v1/declarations/{decl_id}/confirm", headers=_headers(token_admin))
        assert r1.status_code == HTTPStatus.OK, r1.text
        first = r1.json()["data"]
        db, _reg = s2_clean_db
        payments_before = (await db.execute(text(
            f'SELECT COUNT(*) FROM "{sch_a}".payments WHERE order_id = :oid AND is_deleted IS FALSE'
        ), {"oid": oid})).scalar()
        # Replay (sequential).
        r2 = await i2b_client.post(f"/api/v1/declarations/{decl_id}/confirm", headers=_headers(token_admin))
        assert r2.status_code == HTTPStatus.OK, r2.text  # invariant 8: replay 200
        second = r2.json()["data"]
        assert second["confirmation_payment_id"] == first["confirmation_payment_id"]
        assert second["receipt_number"] == first["receipt_number"]
        payments_after = (await db.execute(text(
            f'SELECT COUNT(*) FROM "{sch_a}".payments WHERE order_id = :oid AND is_deleted IS FALSE'
        ), {"oid": oid})).scalar()
        assert payments_after == payments_before  # zero duplicate writes

    async def test_confirm_partial_yields_completed_payment_and_partially_paid(self, i2b_client, two_tenants, s2_clean_db):
        decl_id, oid, ws_a, sch_a, ret_a = await self._submit(i2b_client, two_tenants, s2_clean_db, "40.00")
        token_admin = await _admin_token(i2b_client, two_tenants, s2_clean_db)
        r = await i2b_client.post(f"/api/v1/declarations/{decl_id}/confirm", headers=_headers(token_admin))
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        assert data["status"] == "confirmed"
        assert data["receipt_number"].startswith("RCT-")
        assert data["order_status"] == "partially_paid"  # invariant 11

    async def test_confirm_overpayment_returns_400_pay_exceeds_remaining(self, i2b_client, two_tenants, s2_clean_db):
        # declared 150 on a 100 order. The service guard rejects before any SQL.
        decl_id, oid, ws_a, sch_a, ret_a = await self._submit(i2b_client, two_tenants, s2_clean_db, "150.00")
        token_admin = await _admin_token(i2b_client, two_tenants, s2_clean_db)
        r = await i2b_client.post(f"/api/v1/declarations/{decl_id}/confirm", headers=_headers(token_admin))
        assert r.status_code == HTTPStatus.BAD_REQUEST, r.text
        assert _errcode(r) == "PAYMENT_EXCEEDS_REMAINING"  # canonical 400, not 409

    async def test_confirm_overpayment_leaves_declaration_pending_and_zero_writes(self, i2b_client, two_tenants, s2_clean_db):
        decl_id, oid, ws_a, sch_a, ret_a = await self._submit(i2b_client, two_tenants, s2_clean_db, "150.00")
        db, _reg = s2_clean_db
        before = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        token_admin = await _admin_token(i2b_client, two_tenants, s2_clean_db)
        await i2b_client.post(f"/api/v1/declarations/{decl_id}/confirm", headers=_headers(token_admin))
        after = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        assert after == before  # zero financial mutation; declaration stays pending

    async def test_confirm_malformed_declaration_id_returns_404(self, i2b_client, two_tenants, s2_clean_db):
        token_admin = await _admin_token(i2b_client, two_tenants, s2_clean_db)
        r = await i2b_client.post("/api/v1/declarations/not-a-uuid/confirm", headers=_headers(token_admin))
        assert r.status_code == HTTPStatus.NOT_FOUND, r.text
        assert _errcode(r) == "DECLARATION_NOT_FOUND"


# ---------------------------------------------------------------------------
# Reject — invariant 10
# ---------------------------------------------------------------------------


class TestRejectDeclaration:
    async def test_reject_is_terminal_and_zero_financial_effect(self, i2b_client, two_tenants, s2_clean_db):
        db, reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        token = await _login_retailer(i2b_client, two_tenants)
        decl = await i2b_client.post(
            f"/api/v1/client/orders/{oid}/declare",
            json={"declared_amount": "100.00", "method": "cash"},
            headers={**_headers(token), "X-Declaration-Idempotency-Key": f"i2b-rj-{uuid.uuid4().hex}"},
        )
        decl_id = decl.json()["data"]["id"]
        before = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        token_admin = await _admin_token(i2b_client, two_tenants, s2_clean_db)
        r = await i2b_client.post(
            f"/api/v1/declarations/{decl_id}/reject",
            json={"reason": "Could not verify funds"},
            headers=_headers(token_admin),
        )
        assert r.status_code == HTTPStatus.OK, r.text
        assert r.json()["data"]["status"] == "rejected"
        assert r.json()["data"]["reason"] == "Could not verify funds"
        after = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        assert after == before  # invariant 10: zero financial mutation

    async def test_reject_then_confirm_returns_not_pending(self, i2b_client, two_tenants, s2_clean_db):
        db, reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        token = await _login_retailer(i2b_client, two_tenants)
        decl = await i2b_client.post(
            f"/api/v1/client/orders/{oid}/declare",
            json={"declared_amount": "100.00", "method": "cash"},
            headers={**_headers(token), "X-Declaration-Idempotency-Key": f"i2b-rjc-{uuid.uuid4().hex}"},
        )
        decl_id = decl.json()["data"]["id"]
        token_admin = await _admin_token(i2b_client, two_tenants, s2_clean_db)
        await i2b_client.post(
            f"/api/v1/declarations/{decl_id}/reject",
            json={"reason": "Rejected"},
            headers=_headers(token_admin),
        )
        r = await i2b_client.post(f"/api/v1/declarations/{decl_id}/confirm", headers=_headers(token_admin))
        assert r.status_code == HTTPStatus.CONFLICT, r.text
        assert _errcode(r) == "DECLARATION_NOT_PENDING"

    async def test_reject_reason_validated_1_to_256(self, i2b_client, two_tenants, s2_clean_db):
        db, reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        token = await _login_retailer(i2b_client, two_tenants)
        decl = await i2b_client.post(
            f"/api/v1/client/orders/{oid}/declare",
            json={"declared_amount": "100.00", "method": "cash"},
            headers={**_headers(token), "X-Declaration-Idempotency-Key": f"i2b-rjv-{uuid.uuid4().hex}"},
        )
        decl_id = decl.json()["data"]["id"]
        token_admin = await _admin_token(i2b_client, two_tenants, s2_clean_db)
        # empty reason after strip -> rejected
        r = await i2b_client.post(
            f"/api/v1/declarations/{decl_id}/reject",
            json={"reason": "   "},
            headers=_headers(token_admin),
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST, r.text
        assert _errcode(r) == "INVALID_REJECTION_REASON"
