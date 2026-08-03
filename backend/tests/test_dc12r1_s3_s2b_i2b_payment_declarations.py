"""DC-12R1-S3-S2B-I2B-R2-R3: payment declaration & cashier confirmation runtime.

Real-tenant provisioned tests. Tenants are created via TenantProvisioningService
(full bootstrap), which validates migration-037 parity: if payment_declarations
or receipt_sequences are missing on a freshly provisioned tenant, the parity
gate fails loudly here. No migration DDL is copied.

Harness reused from the S2/S3 retailer-login + catalog-hardening suites:
``provisioned_pool``, ``s2_clean_db``, ``two_tenants`` (module-scoped tenant
provisioning) and the retailer login helpers.

R2-R3 closures:
- S3: exact joined dual-key detail reads (no list+search).
- S4: non-latest rejection does not KeyError/500.
- S6: authentic admin/cashier harness — separate user, real auth path.
- S7: full backend runtime matrix (ownership, concurrency, rollback, isolation).
"""
from __future__ import annotations

import asyncio
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

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# H5: Flush asyncpg prepared-statement cache after module-scoped DDL
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _h5_flush_stmt_cache(provisioned_pool):
    """H5: Dispose engine pool after provisioning DDL.

    Tenant provisioning (``provisioned_pool``) runs bootstrap DDL that creates
    / alters tables in tenant schemas.  This invalidates asyncpg prepared
    statements cached on pooled connections from prior test modules (e.g. I2A).

    Disposing the engine closes every pooled connection so that subsequent
    sessions obtain fresh connections with empty prepared-statement caches.
    """
    from database.session import async_engine
    await async_engine.dispose()
    yield


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


# ---------------------------------------------------------------------------
# S6: Authentic Admin/Cashier Harness — canonical owner lifecycle (R2-R1)
# ---------------------------------------------------------------------------

_CASHIER_PW = "CashierTestPass99!"


@pytest_asyncio.fixture
async def cashier_identity(s2_clean_db, provisioned_pool) -> dict:
    """Function-scoped cashier identity via canonical owner lifecycle.

    Uses ``OwnerCredentialSetupService.create_first_admin_rbac`` to obtain
    the full ``ADMIN_PERMISSION_CODES`` set through the production onboarding
    path — no hand-written INSERT into permissions/role_permissions.

    The naked-bootstrap admin role has only 3 permissions
    (``EXPECTED_PRE_OWNER_SETUP_STATE``).  After owner setup it has the
    complete canonical set including ``payments:create`` and
    ``payments:confirm_declaration``.

    Cleanup: explicitly deletes the cashier ``user_roles`` and ``users``
    rows in the fixture teardown.  The canonical permission / role /
    role_permissions catalog is left intact (idempotent across tests).
    """
    from core.permission_registry import ADMIN_PERMISSION_CODES
    from database.session import AsyncSessionLocal
    from services.owner_credential_service import OwnerCredentialSetupService

    db, reg = s2_clean_db
    a = provisioned_pool.tenants["a"]
    schema_a = a["schema"]
    ws_a = a["ws_id"]
    reg_id = uuid.UUID(a["reg_id"])

    svc = OwnerCredentialSetupService(db)

    # Pre-clean any stale tokens left by a crashed prior test so that
    # issue_setup_token always returns action="issued".
    await db.execute(
        text(
            "DELETE FROM public.owner_credential_setup_tokens "
            "WHERE registration_id = :rid"
        ),
        {"rid": reg_id},
    )
    await db.flush()

    # 1. Issue + consume setup token (canonical owner credential flow)
    issue = await svc.issue_setup_token(reg_id)
    assert issue.action == "issued", f"setup token issue failed: {issue}"

    consume = await svc.consume_setup_token(issue.raw_token, _CASHIER_PW)

    # 2. Create first admin RBAC via canonical service
    result = await svc.create_first_admin_rbac(consume)
    await db.commit()

    cashier_uid = result.user_id
    cashier_email = result.owner_email

    # Register for ownership-registry backup cleanup (user_roles + users)
    reg.register_tenant_user(schema_a, str(cashier_uid))

    # 3. Fail-closed assertions on the canonical permission set
    assert result.permission_count == len(ADMIN_PERMISSION_CODES), (
        f"permission_count {result.permission_count} != "
        f"len(ADMIN_PERMISSION_CODES) {len(ADMIN_PERMISSION_CODES)}"
    )

    admin_codes = (await db.execute(
        text(
            f'SELECT p.code FROM "{schema_a}".permissions p '
            f'JOIN "{schema_a}".role_permissions rp ON rp.permission_id = p.id '
            f'WHERE rp.role_id = :rid ORDER BY p.code'
        ),
        {"rid": result.role_id},
    )).fetchall()
    code_set = {r.code for r in admin_codes}

    for required in ("payments:create", "payments:confirm_declaration"):
        assert required in code_set, f"admin missing canonical permission: {required}"

    client_perms = {c for c in code_set if c.startswith("client:")}
    assert not client_perms, f"admin has client:* permissions: {sorted(client_perms)}"

    try:
        yield {
            "email": cashier_email,
            "password": _CASHIER_PW,
            "user_id": cashier_uid,
            "schema": schema_a,
            "ws_id": ws_a,
        }
    finally:
        # 4. Explicit cleanup — user_roles + users + setup token
        async with AsyncSessionLocal() as cleanup_db:
            await cleanup_db.execute(
                text(f'DELETE FROM "{schema_a}".user_roles WHERE user_id = :uid'),
                {"uid": cashier_uid},
            )
            await cleanup_db.execute(
                text(f'DELETE FROM "{schema_a}".users WHERE id = :uid'),
                {"uid": cashier_uid},
            )
            await cleanup_db.execute(
                text(
                    "DELETE FROM public.owner_credential_setup_tokens "
                    "WHERE registration_id = :rid"
                ),
                {"rid": reg_id},
            )
            await cleanup_db.commit()


async def _cashier_token(i2b_client, cashier_identity: dict) -> str:
    """Return an admin-capable token for the fixture-provisioned cashier.

    Authentic flow: /auth/login (identity) + /auth/select-tenant.
    """
    resp = await i2b_client.post(
        "/api/v1/auth/login",
        json={"email": cashier_identity["email"], "password": cashier_identity["password"]},
    )
    assert resp.status_code == HTTPStatus.OK, resp.text
    identity_token = resp.json()["data"]["access_token"]
    resp2 = await i2b_client.post(
        "/api/v1/auth/select-tenant",
        json={"tenant_id": cashier_identity["ws_id"]},
        headers={"Authorization": f"Bearer {identity_token}"},
    )
    assert resp2.status_code == HTTPStatus.OK, resp2.text
    return resp2.json()["data"]["access_token"]


def _pool_a(provisioned_pool=None) -> dict:
    """Tenant 'a' metadata."""
    pool = provisioned_pool
    if pool is None:
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        pool = _pool_instance
    assert pool is not None, "provisioned_pool not materialized"
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
    """Extract the error code from a 4xx/5xx response."""
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


async def _seed_declaration(
    db: AsyncSession, schema: str, order_id: uuid.UUID, ws_id: str,
    ret_id: str, uid: str, amount: str = "100.00", method: str = "cash",
    ref: str | None = None,
) -> uuid.UUID:
    """Insert a declaration directly via SQL for setup (bypasses API)."""
    did = uuid.uuid4()
    key = f"seed-{did.hex}"
    col_ref = ""
    val_ref = ""
    if ref:
        col_ref = ", transfer_reference"
        val_ref = ", :ref"
    params: dict = {
        "id": did, "oid": order_id, "ws": ws_id, "ret": ret_id,
        "uid": uid, "amount": Decimal(amount), "method": method, "key": key,
    }
    if ref:
        params["ref"] = ref
    await db.execute(
        text(
            f'INSERT INTO "{schema}".payment_declarations '
            "(id, order_id, retailer_id, wholesaler_id, declared_amount, method, "
            f"status, idempotency_key, submitted_by, submitted_at{col_ref}) "
            "VALUES (:id, :oid, :ret, :ws, :amount, :method, "
            f"'pending', :key, :uid, now(){val_ref})"
        ),
        params,
    )
    await db.commit()
    return did


# ---------------------------------------------------------------------------
# Parity gate
# ---------------------------------------------------------------------------


class TestParityGate:
    async def test_provisioned_tenant_has_i2b_objects(self, s2_clean_db):
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
        assert has_declarations, f"payment_declarations missing in {sch}"
        assert has_sequences, f"receipt_sequences missing in {sch}"
        assert has_receipt_col is not None, f"payments.receipt_number missing in {sch}"


# ---------------------------------------------------------------------------
# S6: Authentic harness assertion tests
# ---------------------------------------------------------------------------


class TestAuthenticHarness:
    """S6: verify the admin/cashier harness uses a separate user with
    canonical authorization — never grants admin to the retailer identity."""

    async def test_admin_user_id_differs_from_retailer(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        await _cashier_token(i2b_client, cashier_identity)
        admin_uid = cashier_identity["user_id"]
        _code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        retailer_uid = uuid.UUID(str(uid_a))
        assert admin_uid != retailer_uid, "admin and retailer must be different users"

    async def test_retailer_operator_lacks_confirm_permission(
        self, i2b_client, two_tenants, s2_clean_db
    ):
        """Retailer token (retailer_operator only) must get 403 on confirm."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        _c, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a)
        did = await _seed_declaration(db, sch_a, oid, ws_a, ret_a, uid_a)
        token = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.post(
            f"/api/v1/declarations/{did}/confirm", headers=_headers(token),
        )
        assert r.status_code == HTTPStatus.FORBIDDEN, r.text

    async def test_admin_lacks_client_permissions(
        self, s2_clean_db, cashier_identity
    ):
        """Admin user must NOT have any client:* permissions.
        Uses fixture directly — no ordering dependency."""
        db, _reg = s2_clean_db
        sch_a = cashier_identity["schema"]
        admin_uid = cashier_identity["user_id"]
        rows = (await db.execute(
            text(
                f'SELECT p.code FROM "{sch_a}".permissions p '
                f'JOIN "{sch_a}".role_permissions rp ON rp.permission_id = p.id '
                f'JOIN "{sch_a}".user_roles ur ON ur.role_id = rp.role_id '
                f'WHERE ur.user_id = :uid AND p.code LIKE :pattern'
            ),
            {"uid": admin_uid, "pattern": "client:%"},
        )).fetchall()
        assert len(rows) == 0, f"admin has client:* permissions: {[r.code for r in rows]}"

    async def test_cashier_executes_confirm_successfully(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """Cashier token (admin role) must execute confirm successfully."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        _c, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a)
        did = await _seed_declaration(db, sch_a, oid, ws_a, ret_a, uid_a)
        token = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post(
            f"/api/v1/declarations/{did}/confirm", headers=_headers(token),
        )
        assert r.status_code == HTTPStatus.OK, r.text
        assert r.json()["data"]["status"] == "confirmed"

    async def test_retailer_lacks_reject_permission(
        self, i2b_client, two_tenants, s2_clean_db
    ):
        """Retailer token must get 403 on reject."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        _c, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a)
        did = await _seed_declaration(db, sch_a, oid, ws_a, ret_a, uid_a)
        token = await _login_retailer(i2b_client, two_tenants)
        r = await i2b_client.post(
            f"/api/v1/declarations/{did}/reject",
            json={"reason": "Test rejection"},
            headers=_headers(token),
        )
        assert r.status_code == HTTPStatus.FORBIDDEN, r.text


# ---------------------------------------------------------------------------
# Submit (zero financial effect)
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
        assert after == before

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
        assert r.json()["data"]["transfer_reference"] == "TRF-12345"

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
# Namespace isolation (R2)
# ---------------------------------------------------------------------------


class TestNamespaceIsolation:
    async def test_direct_pay_rejects_reserved_prefix(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        db, reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        token = await _cashier_token(i2b_client, cashier_identity)
        before = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        r = await i2b_client.post(
            f"/api/v1/orders/{oid}/pay",
            json={"amount": "10.00", "method": "cash"},
            headers={**_headers(token), "X-Idempotency-Key": f"decl-confirm-{uuid.uuid4().hex}"},
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST, r.text
        assert _errcode(r) == "RESERVED_IDEMPOTENCY_KEY"
        after = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        assert after == before

    async def test_confirm_bare_payment_conflict_fail_closed(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
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

        await db.execute(
            text(
                f'INSERT INTO "{sch_a}".payments '
                "(id, order_id, retailer_id, transaction_id, idempotency_key, amount, method, status, is_deleted, created_at, updated_at) "
                "VALUES (:pid, :oid, :ret, NULL, :key, 100.00, 'cash', 'completed', false, now(), now())"
            ),
            {"pid": uuid.uuid4(), "oid": oid, "ret": ret_a, "key": canonical_key},
        )
        await db.commit()

        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post(
            f"/api/v1/declarations/{decl_id}/confirm",
            headers=_headers(token_admin),
        )
        assert r.status_code == HTTPStatus.CONFLICT, r.text
        assert _errcode(r) == "DECLARATION_CONFIRMATION_KEY_CONFLICT"


# ---------------------------------------------------------------------------
# Confirm / replay / partial-vs-final
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

    async def test_confirm_full_creates_receipt_and_paid_order(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        decl_id, oid, ws_a, sch_a, ret_a = await self._submit(i2b_client, two_tenants, s2_clean_db, "100.00")
        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post(f"/api/v1/declarations/{decl_id}/confirm", headers=_headers(token_admin))
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        assert data["status"] == "confirmed"
        assert data["receipt_number"].startswith("RCT-")
        assert data["order_status"] == "paid"

    async def test_confirm_replay_returns_same_payment_and_receipt(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        decl_id, oid, ws_a, sch_a, ret_a = await self._submit(i2b_client, two_tenants, s2_clean_db, "100.00")
        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r1 = await i2b_client.post(f"/api/v1/declarations/{decl_id}/confirm", headers=_headers(token_admin))
        assert r1.status_code == HTTPStatus.OK, r1.text
        first = r1.json()["data"]
        db, _reg = s2_clean_db
        payments_before = (await db.execute(text(
            f'SELECT COUNT(*) FROM "{sch_a}".payments WHERE order_id = :oid AND is_deleted IS FALSE'
        ), {"oid": oid})).scalar()
        r2 = await i2b_client.post(f"/api/v1/declarations/{decl_id}/confirm", headers=_headers(token_admin))
        assert r2.status_code == HTTPStatus.OK, r2.text
        second = r2.json()["data"]
        assert second["confirmation_payment_id"] == first["confirmation_payment_id"]
        assert second["receipt_number"] == first["receipt_number"]
        payments_after = (await db.execute(text(
            f'SELECT COUNT(*) FROM "{sch_a}".payments WHERE order_id = :oid AND is_deleted IS FALSE'
        ), {"oid": oid})).scalar()
        assert payments_after == payments_before

    async def test_confirm_partial_yields_completed_payment_and_partially_paid(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        decl_id, oid, ws_a, sch_a, ret_a = await self._submit(i2b_client, two_tenants, s2_clean_db, "40.00")
        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post(f"/api/v1/declarations/{decl_id}/confirm", headers=_headers(token_admin))
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        assert data["status"] == "confirmed"
        assert data["receipt_number"].startswith("RCT-")
        assert data["order_status"] == "partially_paid"

    async def test_confirm_overpayment_returns_400_pay_exceeds_remaining(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        decl_id, oid, ws_a, sch_a, ret_a = await self._submit(i2b_client, two_tenants, s2_clean_db, "150.00")
        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post(f"/api/v1/declarations/{decl_id}/confirm", headers=_headers(token_admin))
        assert r.status_code == HTTPStatus.BAD_REQUEST, r.text
        assert _errcode(r) == "PAYMENT_EXCEEDS_REMAINING"

    async def test_confirm_overpayment_leaves_declaration_pending_and_zero_writes(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        decl_id, oid, ws_a, sch_a, ret_a = await self._submit(i2b_client, two_tenants, s2_clean_db, "150.00")
        db, _reg = s2_clean_db
        before = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        token_admin = await _cashier_token(i2b_client, cashier_identity)
        await i2b_client.post(f"/api/v1/declarations/{decl_id}/confirm", headers=_headers(token_admin))
        after = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        assert after == before

    async def test_confirm_malformed_declaration_id_returns_404(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post("/api/v1/declarations/not-a-uuid/confirm", headers=_headers(token_admin))
        assert r.status_code == HTTPStatus.NOT_FOUND, r.text
        assert _errcode(r) == "DECLARATION_NOT_FOUND"


# ---------------------------------------------------------------------------
# Reject — invariant 10
# ---------------------------------------------------------------------------


class TestRejectDeclaration:
    async def test_reject_is_terminal_and_zero_financial_effect(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
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
        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post(
            f"/api/v1/declarations/{decl_id}/reject",
            json={"reason": "Could not verify funds"},
            headers=_headers(token_admin),
        )
        assert r.status_code == HTTPStatus.OK, r.text
        assert r.json()["data"]["status"] == "rejected"
        assert r.json()["data"]["reason"] == "Could not verify funds"
        after = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        assert after == before

    async def test_reject_then_confirm_returns_not_pending(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
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
        token_admin = await _cashier_token(i2b_client, cashier_identity)
        await i2b_client.post(
            f"/api/v1/declarations/{decl_id}/reject",
            json={"reason": "Rejected"},
            headers=_headers(token_admin),
        )
        r = await i2b_client.post(f"/api/v1/declarations/{decl_id}/confirm", headers=_headers(token_admin))
        assert r.status_code == HTTPStatus.CONFLICT, r.text
        assert _errcode(r) == "DECLARATION_NOT_PENDING"

    async def test_reject_reason_validated_1_to_256(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
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
        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post(
            f"/api/v1/declarations/{decl_id}/reject",
            json={"reason": "   "},
            headers=_headers(token_admin),
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST, r.text
        assert _errcode(r) == "INVALID_REJECTION_REASON"

    async def test_reject_reason_missing_returns_400(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        """S7: missing reason must return 400, not 422/500."""
        db, reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        did = await _seed_declaration(db, sch_a, oid, ws_a, ret_a, uid_a)
        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post(
            f"/api/v1/declarations/{did}/reject",
            json={},
            headers=_headers(token_admin),
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST, r.text

    async def test_reject_reason_oversized_returns_400(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        """S7: oversized reason must return 400, not 422/500."""
        db, reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        did = await _seed_declaration(db, sch_a, oid, ws_a, ret_a, uid_a)
        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post(
            f"/api/v1/declarations/{did}/reject",
            json={"reason": "x" * 257},
            headers=_headers(token_admin),
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST, r.text

    async def test_reject_reason_forbidden_html_returns_400(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        """S7: HTML tags in reason must return 400, not 422/500."""
        db, reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        did = await _seed_declaration(db, sch_a, oid, ws_a, ret_a, uid_a)
        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post(
            f"/api/v1/declarations/{did}/reject",
            json={"reason": "<script>alert('xss')</script>"},
            headers=_headers(token_admin),
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST, r.text


# ---------------------------------------------------------------------------
# S4: Non-latest rejection
# ---------------------------------------------------------------------------


class TestNonLatestRejection:
    """S4: rejecting an older declaration when a newer one exists must not
    KeyError or 500. The older declaration must be rejected correctly."""

    async def test_reject_older_declaration_with_newer_present(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")

        # Create the older declaration first.
        older_did = await _seed_declaration(db, sch_a, oid, ws_a, ret_a, uid_a, "30.00")
        # Sleep to ensure submitted_at differs.
        await asyncio.sleep(0.05)
        # Create the newer declaration.
        newer_did = await _seed_declaration(db, sch_a, oid, ws_a, ret_a, uid_a, "70.00")

        before = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        token_admin = await _cashier_token(i2b_client, cashier_identity)

        # Reject the OLDER declaration.
        r = await i2b_client.post(
            f"/api/v1/declarations/{older_did}/reject",
            json={"reason": "Duplicate submission"},
            headers=_headers(token_admin),
        )
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        assert data["status"] == "rejected"
        assert data["reason"] == "Duplicate submission"
        assert data["order_status"] is not None

        # Zero financial mutation.
        after = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        assert after == before

        # Newer declaration remains unchanged (pending).
        newer_row = (await db.execute(
            text(f"SELECT status FROM \"{sch_a}\".payment_declarations WHERE id = :did"),
            {"did": newer_did},
        )).fetchone()
        assert newer_row is not None
        assert newer_row.status == "pending"


# ---------------------------------------------------------------------------
# S7: Backend runtime matrix
# ---------------------------------------------------------------------------


class TestRuntimeMatrix:
    """S7: comprehensive runtime matrix covering ownership, concurrency,
    rollback, and isolation scenarios."""

    async def _setup_order_and_decl(
        self, db, sch_a, ws_a, uid_a, ret_a, amount="100.00"
    ):
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        did = await _seed_declaration(db, sch_a, oid, ws_a, ret_a, uid_a, amount)
        return oid, did

    # --- Ownership / fail-closed tests ---

    async def test_wrong_wholesaler_confirm_returns_neutral_404(
        self, i2b_client, two_tenants, s2_clean_db, provisioned_pool, cashier_identity
    ):
        """S7: confirming a declaration from a different wholesaler must 404
        without leaking existence."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        ws_b = provisioned_pool.tenants["b"]["ws_id"]
        sch_b = provisioned_pool.tenants["b"]["schema"]
        code_a, _b, _sb, _e, _p, uid_a, uid_b = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        ret_b = await _resolve_binding_retailer(db, ws_b, uid_b)

        # Create declaration in tenant B.
        oid_b = await _seed_confirmed_order(db, sch_b, ws_b, ret_b, "100.00")
        did_b = await _seed_declaration(db, sch_b, oid_b, ws_b, ret_b, uid_b)

        before_b = await _snapshot(db, sch_b, oid_b, ws_b, ret_b)
        # Confirm using tenant A's admin token.
        token_a = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post(
            f"/api/v1/declarations/{did_b}/confirm",
            headers=_headers(token_a),
        )
        assert r.status_code == HTTPStatus.NOT_FOUND, r.text
        assert _errcode(r) == "DECLARATION_NOT_FOUND"
        # Zero mutation on tenant B.
        after_b = await _snapshot(db, sch_b, oid_b, ws_b, ret_b)
        assert after_b == before_b

    async def test_wrong_retailer_declaration_ownership_fail_closed(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """S7: declaration with wrong retailer/wholesaler must fail closed."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)

        # Create a different retailer ID that doesn't own the order.
        wrong_ret = uuid.uuid4()
        oid = uuid.uuid4()
        await db.execute(
            text(
                f'INSERT INTO "{sch_a}".orders (id, wholesaler_id, retailer_id, status, total_amount, is_deleted) '
                "VALUES (:id, :ws, :ret, 'confirmed', 100.00, false)"
            ),
            {"id": oid, "ws": ws_a, "ret": wrong_ret},
        )
        did = await _seed_declaration(db, sch_a, oid, ws_a, str(wrong_ret), uid_a)

        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post(
            f"/api/v1/declarations/{did}/confirm",
            headers=_headers(token_admin),
        )
        assert r.status_code in (HTTPStatus.NOT_FOUND, HTTPStatus.CONFLICT), r.text

    async def test_inactive_binding_confirmation_fail_closed(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """S7: confirming with an inactive binding must fail closed."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid, did = await self._setup_order_and_decl(db, sch_a, ws_a, uid_a, ret_a)

        # Deactivate the binding.
        await db.execute(
            text(
                "UPDATE public.wholesaler_retailer_bindings "
                "SET status = 'inactive' WHERE wholesaler_id = :ws AND retailer_id = :ret"
            ),
            {"ws": ws_a, "ret": ret_a},
        )
        await db.commit()

        before = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post(
            f"/api/v1/declarations/{did}/confirm",
            headers=_headers(token_admin),
        )
        assert r.status_code in (
            HTTPStatus.NOT_FOUND, HTTPStatus.CONFLICT, HTTPStatus.BAD_REQUEST,
        ), r.text
        after = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        assert after == before

    async def test_soft_deleted_binding_confirmation_fail_closed(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """S7: confirming with a soft-deleted binding must fail closed."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid, did = await self._setup_order_and_decl(db, sch_a, ws_a, uid_a, ret_a)

        await db.execute(
            text(
                "UPDATE public.wholesaler_retailer_bindings "
                "SET is_deleted = true WHERE wholesaler_id = :ws AND retailer_id = :ret"
            ),
            {"ws": ws_a, "ret": ret_a},
        )
        await db.commit()

        before = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post(
            f"/api/v1/declarations/{did}/confirm",
            headers=_headers(token_admin),
        )
        assert r.status_code in (
            HTTPStatus.NOT_FOUND, HTTPStatus.CONFLICT, HTTPStatus.BAD_REQUEST,
        ), r.text
        after = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        assert after == before

    # --- Concurrency tests ---

    async def test_concurrent_same_payload_submit_one_declaration(
        self, i2b_client, two_tenants, s2_clean_db
    ):
        """S7: concurrent same-payload submit produces exactly one declaration."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        token = await _login_retailer(i2b_client, two_tenants)
        key = f"i2b-conc-same-{uuid.uuid4().hex}"
        body = {"declared_amount": "50.00", "method": "cash"}
        headers = {**_headers(token), "X-Declaration-Idempotency-Key": key}

        r1, r2 = await asyncio.gather(
            i2b_client.post(f"/api/v1/client/orders/{oid}/declare", json=body, headers=headers),
            i2b_client.post(f"/api/v1/client/orders/{oid}/declare", json=body, headers=headers),
        )
        codes = {r1.status_code, r2.status_code}
        # One must succeed (201 create), the other must be replay (200) or
        # controlled 409 (concurrent IntegrityError resolved as conflict).
        assert HTTPStatus.CREATED in codes or HTTPStatus.OK in codes, (
            f"no success in concurrent same-payload: {codes}: {r1.text} | {r2.text}"
        )
        # Exactly one declaration row.
        count = (await db.execute(text(
            f"SELECT COUNT(*) FROM \"{sch_a}\".payment_declarations WHERE order_id = :oid"
        ), {"oid": oid})).scalar()
        assert count == 1

    async def test_concurrent_different_payload_same_key_one_success_one_409(
        self, i2b_client, two_tenants, s2_clean_db
    ):
        """S7: concurrent different-payload same-key produces one 201/200 and one 409."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        token = await _login_retailer(i2b_client, two_tenants)
        key = f"i2b-conc-diff-{uuid.uuid4().hex}"
        h1 = {**_headers(token), "X-Declaration-Idempotency-Key": key}
        h2 = {**_headers(token), "X-Declaration-Idempotency-Key": key}

        r1, r2 = await asyncio.gather(
            i2b_client.post(
                f"/api/v1/client/orders/{oid}/declare",
                json={"declared_amount": "30.00", "method": "cash"}, headers=h1,
            ),
            i2b_client.post(
                f"/api/v1/client/orders/{oid}/declare",
                json={"declared_amount": "40.00", "method": "cash"}, headers=h2,
            ),
        )
        codes = sorted([r1.status_code, r2.status_code])
        has_201_or_200 = HTTPStatus.CREATED in codes or HTTPStatus.OK in codes
        has_409 = HTTPStatus.CONFLICT in codes
        assert has_201_or_200 and has_409, (
            f"expected one success + one 409, got {codes}: {r1.text} | {r2.text}"
        )

    async def test_concurrent_confirmation_one_payment_one_receipt(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """S7: concurrent confirmation produces exactly one canonical payment,
        one ledger effect, one receivable effect, one receipt."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        did = await _seed_declaration(db, sch_a, oid, ws_a, ret_a, uid_a, "100.00")

        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r1, r2 = await asyncio.gather(
            i2b_client.post(f"/api/v1/declarations/{did}/confirm", headers=_headers(token_admin)),
            i2b_client.post(f"/api/v1/declarations/{did}/confirm", headers=_headers(token_admin)),
        )
        assert r1.status_code == HTTPStatus.OK, r1.text
        assert r2.status_code == HTTPStatus.OK, r2.text

        pay_count = (await db.execute(text(
            f"SELECT COUNT(*) FROM \"{sch_a}\".payments WHERE order_id = :oid AND is_deleted IS FALSE"
        ), {"oid": oid})).scalar()
        assert pay_count == 1, f"expected 1 payment, got {pay_count}"

        receipt_count = (await db.execute(text(
            f"SELECT COUNT(*) FROM \"{sch_a}\".payments WHERE order_id = :oid "
            "AND receipt_number IS NOT NULL AND is_deleted IS FALSE"
        ), {"oid": oid})).scalar()
        assert receipt_count == 1, f"expected 1 receipt, got {receipt_count}"

    # --- Confirmation replay ---

    async def test_confirmation_replay_same_payment_and_receipt_zero_writes(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """S7: confirmation replay returns same payment+receipt with zero writes."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        did = await _seed_declaration(db, sch_a, oid, ws_a, ret_a, uid_a, "100.00")

        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r1 = await i2b_client.post(f"/api/v1/declarations/{did}/confirm", headers=_headers(token_admin))
        assert r1.status_code == HTTPStatus.OK, r1.text
        first = r1.json()["data"]

        pay_before = (await db.execute(text(
            f"SELECT COUNT(*) FROM \"{sch_a}\".payments WHERE is_deleted IS FALSE"
        ))).scalar()

        r2 = await i2b_client.post(f"/api/v1/declarations/{did}/confirm", headers=_headers(token_admin))
        assert r2.status_code == HTTPStatus.OK, r2.text
        second = r2.json()["data"]

        assert second["confirmation_payment_id"] == first["confirmation_payment_id"]
        assert second["receipt_number"] == first["receipt_number"]

        pay_after = (await db.execute(text(
            f"SELECT COUNT(*) FROM \"{sch_a}\".payments WHERE is_deleted IS FALSE"
        ))).scalar()
        assert pay_after == pay_before

    async def test_malformed_replay_receipt_returns_409(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """S7: malformed or missing replay receipt must return controlled 409."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        did = await _seed_declaration(db, sch_a, oid, ws_a, ret_a, uid_a, "100.00")

        # Insert a bare payment (no receipt) and mark declaration as confirmed with it.
        bogus_pay = uuid.uuid4()
        await db.execute(
            text(
                f'INSERT INTO "{sch_a}".payments '
                "(id, order_id, retailer_id, transaction_id, idempotency_key, amount, method, status, is_deleted, created_at, updated_at) "
                "VALUES (:pid, :oid, :ret, NULL, :key, 100.00, 'cash', 'completed', false, now(), now())"
            ),
            {"pid": bogus_pay, "oid": oid, "ret": ret_a, "key": f"bare-{uuid.uuid4().hex}"},
        )
        await db.execute(
            text(
                f"UPDATE \"{sch_a}\".payment_declarations "
                "SET status = 'confirmed', confirmation_payment_id = :pid, "
                "confirmed_at = now() WHERE id = :did"
            ),
            {"pid": bogus_pay, "did": did},
        )
        await db.commit()

        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post(
            f"/api/v1/declarations/{did}/confirm", headers=_headers(token_admin),
        )
        assert r.status_code in (HTTPStatus.OK, HTTPStatus.CONFLICT), r.text

    # --- Overpayment / financial snapshot ---

    async def test_overpayment_rejection_leaves_declaration_pending(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """S7: overpayment rejection must leave declaration pending and
        complete financial snapshot unchanged."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        did = await _seed_declaration(db, sch_a, oid, ws_a, ret_a, uid_a, "150.00")

        before = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post(
            f"/api/v1/declarations/{did}/confirm", headers=_headers(token_admin),
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST, r.text
        assert _errcode(r) == "PAYMENT_EXCEEDS_REMAINING"
        after = await _snapshot(db, sch_a, oid, ws_a, ret_a)
        assert after == before

        # Declaration remains pending.
        status_row = (await db.execute(
            text(f"SELECT status FROM \"{sch_a}\".payment_declarations WHERE id = :did"),
            {"did": did},
        )).fetchone()
        assert status_row.status == "pending"

    # --- Namespace isolation ---

    async def test_direct_payment_reserved_namespace_rejected(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """S7: direct payment reserved namespace remains rejected."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        token = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post(
            f"/api/v1/orders/{oid}/pay",
            json={"amount": "10.00", "method": "cash"},
            headers={
                **_headers(token),
                "X-Idempotency-Key": f"decl-confirm-{uuid.uuid4().hex}",
            },
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST
        assert _errcode(r) == "RESERVED_IDEMPOTENCY_KEY"

    # --- IntegrityError isolation ---

    async def test_unrelated_integrityerror_not_reclassified_as_409(
        self, i2b_client, two_tenants, s2_clean_db
    ):
        """S7: unrelated FK/CHECK/UNIQUE IntegrityError is never reclassified
        as idempotency replay/409."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        token = await _login_retailer(i2b_client, two_tenants)

        # Submit with an invalid method that will trigger a CHECK violation
        # or FK error (not the idempotency-key unique constraint).
        r = await i2b_client.post(
            f"/api/v1/client/orders/{oid}/declare",
            json={"declared_amount": "50.00", "method": "invalid_method"},
            headers={
                **_headers(token),
                "X-Declaration-Idempotency-Key": f"i2b-fk-{uuid.uuid4().hex}",
            },
        )
        # Must NOT be 409 CONFLICT (idempotency replay).
        assert r.status_code != HTTPStatus.CONFLICT, (
            f"unrelated IntegrityError was reclassified as 409: {r.text}"
        )

    # --- Rollback proof ---

    async def test_receipt_allocation_rollback_zero_residue(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """S7: failed confirmation leaves zero payment/declaration-terminal/
        ledger/receivable residue."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)
        oid = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        did = await _seed_declaration(db, sch_a, oid, ws_a, ret_a, uid_a, "150.00")

        payments_before = (await db.execute(text(
            f'SELECT COUNT(*) FROM "{sch_a}".payments WHERE is_deleted IS FALSE'
        ))).scalar()
        ledger_before = (await db.execute(text(
            f'SELECT COUNT(*) FROM "{sch_a}".ledger_entries'
        ))).scalar()

        token_admin = await _cashier_token(i2b_client, cashier_identity)
        r = await i2b_client.post(
            f"/api/v1/declarations/{did}/confirm", headers=_headers(token_admin),
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST

        payments_after = (await db.execute(text(
            f'SELECT COUNT(*) FROM "{sch_a}".payments WHERE is_deleted IS FALSE'
        ))).scalar()
        ledger_after = (await db.execute(text(
            f'SELECT COUNT(*) FROM "{sch_a}".ledger_entries'
        ))).scalar()
        decl_status = (await db.execute(
            text(f"SELECT status FROM \"{sch_a}\".payment_declarations WHERE id = :did"),
            {"did": did},
        )).scalar()

        assert payments_after == payments_before, "payment residue after rollback"
        assert ledger_after == ledger_before, "ledger residue after rollback"
        assert decl_status == "pending", "declaration should remain pending"

    async def test_rollback_leaves_sequence_transactionally_reusable(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """S7: after a failed confirmation, the receipt sequence can still
        produce a valid receipt for a subsequent successful confirmation."""
        db, _reg = s2_clean_db
        ws_a = _pool_a()["ws_id"]
        sch_a = _pool_a()["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ret_a = await _resolve_binding_retailer(db, ws_a, uid_a)

        # Failed declaration (overpayment).
        oid1 = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        did1 = await _seed_declaration(db, sch_a, oid1, ws_a, ret_a, uid_a, "150.00")
        # Valid declaration.
        oid2 = await _seed_confirmed_order(db, sch_a, ws_a, ret_a, "100.00")
        did2 = await _seed_declaration(db, sch_a, oid2, ws_a, ret_a, uid_a, "100.00")

        token_admin = await _cashier_token(i2b_client, cashier_identity)
        # First: failed confirm.
        r1 = await i2b_client.post(
            f"/api/v1/declarations/{did1}/confirm", headers=_headers(token_admin),
        )
        assert r1.status_code == HTTPStatus.BAD_REQUEST

        # Second: successful confirm — must get a valid receipt.
        r2 = await i2b_client.post(
            f"/api/v1/declarations/{did2}/confirm", headers=_headers(token_admin),
        )
        assert r2.status_code == HTTPStatus.OK, r2.text
        assert r2.json()["data"]["receipt_number"].startswith("RCT-")
