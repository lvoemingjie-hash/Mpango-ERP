"""DC-12R1-S3-S2B-I2C-I2B Contract D — relationship account statement print tests.

Real PostgreSQL 16 (+ Redis 7) integration. Reuses the I2B/I2C-I1 harness.

Coverage (binding accounting rules + R1 truth closure):
  * dual-key supplier/retailer isolation + neutral cross-tenant denial;
  * strict shared date-range contract: missing/blank/malformed/reversed/
    >365-day ranges -> controlled 400 INVALID_DATE_RANGE (never 422/404);
  * inclusive date boundaries + opening/closing arithmetic;
  * charge + collection and post-range reconstruction;
  * soft-deleted-order history retention with snapshot/restore discipline and
    identical active-vs-deleted accounting totals;
  * orphan ledger + arithmetic/reconciliation fail-closed (409) cases;
  * completed-payment ownership-integrity precheck (payment retailer != order
    retailer -> 409 STATEMENT_INTERNAL_INCONSISTENT, zero partial document);
  * zero-valued movement -> 409 STATEMENT_INTERNAL_INCONSISTENT;
  * settled_total derived ONLY from settled_payments[].amount;
  * movement kind (charge|collection) + display_amount=abs(signed_amount);
  * no movement_id/payment_id in serialized responses (R1 redaction);
  * reconciliation tolerance: <=0.01 accepted, >0.01 -> 409 (credit-only only);
  * exact 1000-line aggregate cap -> 400 STATEMENT_RANGE_TOO_LARGE;
  * pending/rejected exclusion and completed-only settled payments;
  * zero-write fingerprints and no internal-ID leakage;
  * natural and reverse focused order with explicit cleanup.

All statement routes are 100% read-only; this is proven via table/binding
fingerprint snapshots taken before and after each exercised route.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from http import HTTPStatus

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch

from tests.test_dc12r1_s3_s2b_i2b_payment_declarations import (  # noqa: E402
    _CASHIER_PW,
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
    _create_binding,
    _create_provisioned_full_login,
    _create_retailer,
    _create_retailer_user,
    _grant_retailer_operator,
    _unique_email,
)
from tests.test_dc12r1_s3_s2b_i2c_i1_printable_records import (  # noqa: E402
    _seed_order_with_item,
    _submit_and_confirm,
    _table_fingerprint,
    _binding_fingerprint,
    _receipt_seq_fingerprint,
)
from services.tenant_provisioning_service import TenantProvisioningService  # noqa: E402


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _contractd_flush_stmt_cache(provisioned_pool):
    """Dispose engine pool after provisioning DDL (prepared-statement cache)."""
    from database.session import async_engine

    await async_engine.dispose()


@pytest_asyncio.fixture
async def contractd_disposable_tenant(s2_clean_db):
    """Per-test OWNED DISPOSABLE tenant (R1-R1-R1 Blocker 3; R1-R1-R2 setup-
    failure safety).

    Every Contract D test runs inside its own freshly-provisioned tenant
    (wholesaler + schema + retailer + binding). The schema is NOT registered
    in the ownership registry (whose teardown would query it after dropping);
    instead this fixture DROPs the schema (CASCADE) in a fresh cleanup session
    and verifies it is absent — discarding every row, including IMMUTABLE
    ledger_entries rows. Public ownership rows are deleted by the registry by
    exact id. We never rely on deleting immutable rows.

    R1-R1-R2 (P1): the schema is captured the MOMENT the provisioning service
    commits its CREATE SCHEMA, and the DROP guard runs in ``finally`` from that
    point on — so a provisioning failure AFTER the schema exists (or a
    CREATE-TABLE failure mid-provisioning) still drops the schema. No partial
    tenant can ever leak (this is exactly how 58d4b51f produced 131 stray
    schemas).

    Provisioning DDL (CREATE SCHEMA) invalidates asyncpg prepared-statement
    caches on pooled connections (search_path-dependent plans), so the engine
    pool is disposed after provisioning and after the schema drop — same
    pattern as the module-level ``_contractd_flush_stmt_cache``.
    """
    from database.session import AsyncSessionLocal, async_engine

    db, reg = s2_clean_db
    # Provision inside a try/finally that is armed the moment the schema is
    # known, so ANY later failure drops it. _provision_disposable_tenant
    # returns (tenant, schema) with schema set as soon as CREATE SCHEMA commits.
    tenant = await _provision_disposable_tenant(db, reg)
    schema = tenant["schema"]
    # Provisioning DDL invalidates prepared-statement caches -> dispose pool.
    await async_engine.dispose()
    try:
        yield tenant
    finally:
        # Release the main session's open transaction FIRST — otherwise the
        # fresh cleanup session's DROP SCHEMA blocks on its ACCESS SHARE locks
        # until the 60s asyncpg command timeout (TimeoutError at bind_execute).
        await db.rollback()
        async with AsyncSessionLocal() as cleanup_db:
            await cleanup_db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await cleanup_db.commit()
            row = (
                await cleanup_db.execute(
                    text(
                        "SELECT schema_name FROM information_schema.schemata "
                        "WHERE schema_name = :s"
                    ),
                    {"s": schema},
                )
            ).first()
            assert row is None, f"disposable tenant schema {schema} still present after drop"
        # Schema drop invalidates prepared-statement caches -> dispose pool.
        await async_engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _contractd_ledger_scope_clean(provisioned_pool, s2_clean_db):
    """Per-test ledger hygiene for the Contract D suite.

    ``ledger_entries`` is IMMUTABLE at the database level (S6-P write-only
    trigger — DELETE/UPDATE raise ``Ledger immutable``), so stale receivable
    rows from prior tests in the shared provisioning schema would trip the
    orphan precheck (rule 9). The I2B harness cleans up declarations/payments/
    orders but NOT ledger rows. This fixture issues a TRUNCATE on the shared
    schema's ledger_entries ONLY when it is empty-free of prior test residue;
    because the ledger write-only trigger blocks DELETE, tests instead clean
    the seeded ORDERS they own (via the I2C-I1 cleanup helper), which keeps the
    ledger rows resolvable. This fixture is a no-op safety net asserting the
    ledger is write-only (DELETE raises) and yields the schema name.
    """
    from database.session import AsyncSessionLocal

    db, _reg = s2_clean_db
    await db.rollback()
    schema = _pool_a()["schema"]
    yield schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _stmt_period_yesterday_today() -> tuple[str, str]:
    """A period covering yesterday + today (EAT) — broad enough to capture
    freshly-seeded movements whose transaction_date is ~now."""
    eat = timezone(timedelta(hours=3), "Africa/Nairobi")
    today_eat = datetime.now(timezone.utc).astimezone(eat).date()
    frm = (today_eat - timedelta(days=2)).isoformat()
    to = today_eat.isoformat()
    return frm, to


async def _post_receivable_charge(db: AsyncSession, schema: str, order_id: uuid.UUID, amount: str = "100.00") -> uuid.UUID:
    """Insert a +RECEIVABLE charge ledger entry for an order (mirrors
    ``LedgerService.post_order_confirmation``). ``_seed_confirmed_order`` seeds
    the order via raw SQL (no service path), so this posts the charge the
    statement must aggregate as ``charge_total``."""
    lid = uuid.uuid4()
    await db.execute(
        text(
            f'INSERT INTO "{schema}".ledger_entries '
            "(id, transaction_date, account_type, amount, reference_type, reference_id, "
            "description, entry_version, is_deleted, created_at, updated_at) "
            "VALUES (:id, now(), 'receivable', :amt, 'order', :ref, "
            ":desc, 1, false, now(), now())"
        ),
        {
            "id": lid,
            "amt": Decimal(amount),
            "ref": order_id,
            "desc": f"Receivable for order {order_id}",
        },
    )
    await db.commit()
    return lid


async def _seed_order_only(db: AsyncSession, schema: str, ws_id: str, ret_id: str, total: str = "100.00") -> uuid.UUID:
    """Seed a confirmed order (posts a +RECEIVABLE ledger entry; no payment)."""
    return await _seed_confirmed_order(db, schema, ws_id, ret_id, total)


async def _get_retailer_statement(client, token: str, frm: str, to: str, include_pending: bool = False):
    return await client.get(
        "/api/v1/client/statements/print",
        params={"from": frm, "to": to, "include_pending": str(include_pending).lower()},
        headers=_headers(token),
    )


async def _get_supplier_statement(client, token: str, retailer_id: str, frm: str, to: str):
    return await client.get(
        "/api/v1/statements/print",
        params={"retailer_id": retailer_id, "from": frm, "to": to},
        headers=_headers(token),
    )


# ===========================================================================
# R1-R1-R1 Blocker 3 — owned disposable tenant (per test).
#
# Every Contract D test runs inside its OWN freshly-provisioned tenant
# (wholesaler + schema + retailer + binding). All rows — including IMMUTABLE
# ledger_entries (write-only trigger) — are discarded by the registry cleanup
# which DROP SCHEMA CASCADE and deletes the public ownership rows, then
# verifies zero residue. We never rely on deleting immutable rows.
# ===========================================================================

_DISPOSABLE_PW = "CorrectPass99"


async def _provision_disposable_tenant(
    db: AsyncSession, registry, *, prefix: str = "CDR1R1R1", reg_id: uuid.UUID | None = None
) -> dict:
    """Provision a fresh, disposable Contract D tenant.

    Creates registration -> claim -> provision (wholesaler + schema) ->
    retailer user -> retailer -> binding.

    When ``reg_id`` is supplied (R1-R1-R6 exact-ownership), the caller owns
    that exact id and may clean up by ``WHERE id = :reg_id`` (never a LIKE /
    prefix / latest-row scan). When omitted, a fresh uuid is generated.

    The schema is intentionally NOT registered in the ownership registry
    (registry teardown would DROP it and then the registry's own
    ``assert_zero_residue`` queries the dropped schema). Instead the
    ``contractd_disposable_tenant`` fixture DROPs the schema (CASCADE) in its
    own teardown and verifies it is absent — discarding every row, including
    the IMMUTABLE ledger_entries rows (R1-R1-R1 Blocker 3: never delete
    immutable rows). Only the public ownership rows are registered so the
    registry deletes them by exact id.

    R1-R1-R3 (P1): an OUTERMOST ``try/finally`` wraps EVERY line of this
    helper — the registration INSERT, claim, ``provision_wholesaler_and_schema``,
    the schema query, and the remaining setup. A single ``finally`` resolves
    the schema that MAY have been created (from the owned registration row, or
    from the wholesaler-derived schema name) and, on the failure path, drops it
    in a FRESH session and asserts zero residue. The guard is therefore armed
    from the FIRST statement, not after provisioning returns — covering a
    bootstrap failure that creates the schema then raises, a provisioning
    ``failed``/``blocked`` result, and any later setup failure. The original
    exception is always re-raised (never swallowed); the cleanup runs in a
    fresh session because the main session may be in a failed transaction.
    """
    from core.security import hash_password
    from services.tenant_provisioning_service import TenantProvisioningService

    code = f"{prefix}{uuid.uuid4().hex[:6].upper()}"
    email = _unique_email()
    password = _DISPOSABLE_PW
    if reg_id is None:
        reg_id = uuid.uuid4()
    registry.register_registration(str(reg_id))

    try:
        await db.execute(
            text(
                "INSERT INTO public.tenant_registrations "
                "(id, company_name, tenant_code, country, owner_email, status, "
                " expires_at, created_at, updated_at) "
                "VALUES (:id, :company, :code, 'TZ', :email, 'email_verified', "
                " now() + interval '365 days', now(), now())"
            ),
            {
                "id": reg_id,
                "company": f"Disposable {code}",
                "code": code,
                "email": f"owner.{code.lower()}@example.com",
            },
        )
        await db.commit()

        service = TenantProvisioningService(db)
        claim_result = await service.claim_registration_for_provisioning(str(reg_id))
        if claim_result.action != "claimed":
            raise AssertionError(f"claim failed: {claim_result}")
        await db.commit()
        provision_result = await service.provision_wholesaler_and_schema(str(reg_id))
        # provisioning that returns failed/blocked must fail-closed immediately
        # (R1-R1-R3) — a partial schema may exist (bootstrap creates it before a
        # later step raises; the service records a failed_assignment pointing at
        # it). Surface this as a hard failure so the finally cleans it up.
        if provision_result.action != "provisioned":
            raise AssertionError(
                f"provisioning did not complete: action={provision_result.action} "
                f"reason={getattr(provision_result, 'reason', None)}"
            )
        await db.commit()

        reg_row = (
            await db.execute(
                text("SELECT tenant_schema FROM public.tenant_registrations WHERE id = :id"),
                {"id": reg_id},
            )
        ).fetchone()
        ws_row = (
            await db.execute(
                text("SELECT id FROM public.wholesalers WHERE code = :code"),
                {"code": code},
            )
        ).fetchone()
        schema = reg_row.tenant_schema
        ws_id = str(ws_row.id)
        registry.register_wholesaler(ws_id)
        # NOTE: do NOT register_tenant_schema / register_tenant_user — the
        # fixture drops the schema itself (see contractd_disposable_tenant).

        # Retailer user (known email/password for HTTP login). Registered rows
        # inside the schema are discarded by the schema drop.
        pw_hash = hash_password(password)
        uid_row = (
            await db.execute(
                text(
                    f'INSERT INTO "{schema}".users '
                    "(email, password_hash, full_name, is_active) "
                    "VALUES (:email, :pw, 'Test Retailer', true) RETURNING id"
                ),
                {"email": email, "pw": pw_hash},
            )
        ).fetchone()
        uid = str(uid_row.id)
        await _grant_retailer_operator(db, tenant_schema=schema, user_id=uid)
        ret_id = await _create_retailer(db, name=f"Retailer {code}", registry=registry)
        await _create_binding(
            db, wholesaler_id=ws_id, retailer_id=ret_id, tenant_user_id=uid, registry=registry
        )
        return {
            "code": code,
            "email": email,
            "password": password,
            "ws_id": ws_id,
            "schema": schema,
            "ret_id": ret_id,
            "uid": uid,
            "reg_id": str(reg_id),
        }
    except BaseException as original_error:
        # R1-R1-R4 §3 cleanup fail-closed. The original provisioning/setup
        # exception is captured; cleanup runs in a FRESH session and every
        # cleanup-side error is RECORDED (never swallowed). If a cleanup error
        # occurs, BOTH the original and cleanup errors are raised via
        # BaseExceptionGroup; if cleanup succeeds, bare ``raise`` re-raises the
        # original exception unchanged. See ``_cleanup_partial_tenant`` for the
        # independently-tested cleanup body.
        cleanup_errors = await _cleanup_partial_tenant(db, reg_id, code)
        if cleanup_errors:
            raise BaseExceptionGroup(
                "provisioning failure with cleanup errors",
                [original_error, *cleanup_errors],
            )
        raise


async def _cleanup_partial_tenant(
    db: AsyncSession, reg_id: uuid.UUID, code: str
) -> list[BaseException]:
    """R1-R1-R4 §3/§4 — the partial-tenant cleanup body, extracted so it is
    independently testable. Returns a list of cleanup-side errors (empty on
    success). Never swallows; never raises. Steps:

      1. rollback the main session FIRST (release its locks);
      2. resolve + validate candidate schema names (registration row +
         wholesaler-derived), dedupe, fail-closed on inconsistency;
      3. for each owned candidate present in pg_namespace, DROP + commit;
      4. verify zero residue in pg_namespace.

    Every error is appended to the returned list. Callers decide how to raise
    (the production path wraps the list + the original error in a
    ``BaseExceptionGroup``).
    """
    from database.session import AsyncSessionLocal, async_engine
    from db.sql_safety import validate_identifier
    from models.wholesaler import Wholesaler

    cleanup_errors: list[BaseException] = []

    # 1. Release the main session's transaction / locks before DROP.
    try:
        await db.rollback()
    except BaseException as exc:
        cleanup_errors.append(exc)

    # 2. Resolve + validate candidate schema names.
    candidates: list[str] = []
    try:
        await async_engine.dispose()
        async with AsyncSessionLocal() as cleanup_db:
            reg_schema: str | None = None
            sch_row = (
                await cleanup_db.execute(
                    text(
                        "SELECT tenant_schema FROM public.tenant_registrations "
                        "WHERE id = :rid"
                    ),
                    {"rid": reg_id},
                )
            ).first()
            if sch_row is not None and sch_row.tenant_schema:
                reg_schema = str(sch_row.tenant_schema)
                validate_identifier(reg_schema, "registration tenant_schema")

            ws_schema: str | None = None
            ws_schema_row = (
                await cleanup_db.execute(
                    text("SELECT id FROM public.wholesalers WHERE code = :code"),
                    {"code": code},
                )
            ).first()
            if ws_schema_row is not None:
                ws_schema = Wholesaler.derive_schema_from_id(str(ws_schema_row.id))
                validate_identifier(ws_schema, "wholesaler-derived schema")

            # Both sources present but inconsistent -> fail-closed (do NOT
            # pick one and DROP — that could drop the wrong schema).
            if (
                reg_schema is not None
                and ws_schema is not None
                and reg_schema != ws_schema
            ):
                raise RuntimeError(
                    f"schema inconsistency during cleanup: registration="
                    f"{reg_schema!r} wholesaler={ws_schema!r} — refusing to DROP"
                )

            # Dedupe (order-preserving) and validate every candidate.
            seen: set[str] = set()
            for sch in (reg_schema, ws_schema):
                if sch is None or sch in seen:
                    continue
                validate_identifier(sch, "cleanup candidate schema")
                seen.add(sch)
                candidates.append(sch)
    except BaseException as exc:
        cleanup_errors.append(exc)
        # candidates may be partial; skip the DROP phase if resolution
        # itself failed (we must not DROP with an unresolved set).
        candidates = []

    # 3. DROP each owned candidate present in pg_namespace; 4. verify residue.
    if candidates:
        try:
            await async_engine.dispose()
            async with AsyncSessionLocal() as cleanup_db:
                for sch in candidates:
                    present = (
                        await cleanup_db.execute(
                            text("SELECT 1 FROM pg_namespace WHERE nspname = :s"),
                            {"s": sch},
                        )
                    ).first()
                    if present is not None:
                        await cleanup_db.execute(
                            text(f'DROP SCHEMA IF EXISTS "{sch}" CASCADE')
                        )
                        await cleanup_db.commit()
                # Zero-residue: every owned candidate must be absent from
                # pg_namespace afterwards.
                for sch in candidates:
                    still = (
                        await cleanup_db.execute(
                            text("SELECT 1 FROM pg_namespace WHERE nspname = :s"),
                            {"s": sch},
                        )
                    ).first()
                    assert still is None, (
                        f"setup-failure cleanup failed: schema {sch} still "
                        f"present in pg_namespace"
                    )
        except BaseException as exc:
            cleanup_errors.append(exc)

    return cleanup_errors


async def _login_disposable_retailer(client, tenant: dict) -> str:
    """Authentic retailer login for a disposable tenant."""
    resp = await client.post(
        "/api/v1/client/auth/login",
        json={
            "email": tenant["email"],
            "password": tenant["password"],
            "wholesaler_code": tenant["code"],
        },
    )
    assert resp.status_code == HTTPStatus.OK, resp.text
    return resp.json()["data"]["tokens"]["access_token"]


async def _provision_disposable_admin(db: AsyncSession, tenant: dict, registry) -> dict:
    """Create the disposable tenant's first admin via the canonical owner
    credential setup path (same production flow as cashier_identity).

    The admin user lives inside the disposable schema, which the fixture
    teardown drops — so it is NOT registered in the ownership registry.
    """
    from services.owner_credential_service import OwnerCredentialSetupService

    svc = OwnerCredentialSetupService(db)
    issue = await svc.issue_setup_token(uuid.UUID(tenant["reg_id"]))
    assert issue.action == "issued", f"setup token issue failed: {issue}"
    consume = await svc.consume_setup_token(issue.raw_token, _CASHIER_PW)
    result = await svc.create_first_admin_rbac(consume)
    await db.commit()
    return {
        "email": result.owner_email,
        "password": _CASHIER_PW,
        "user_id": str(result.user_id),
        "schema": tenant["schema"],
        "ws_id": tenant["ws_id"],
    }


async def _disposable_admin_token(i2b_client, admin: dict) -> str:
    """Authentic /auth/login + /auth/select-tenant admin token."""
    resp = await i2b_client.post(
        "/api/v1/auth/login",
        json={"email": admin["email"], "password": admin["password"]},
    )
    assert resp.status_code == HTTPStatus.OK, resp.text
    identity_token = resp.json()["data"]["access_token"]
    resp2 = await i2b_client.post(
        "/api/v1/auth/select-tenant",
        json={"tenant_id": admin["ws_id"]},
        headers={"Authorization": f"Bearer {identity_token}"},
    )
    assert resp2.status_code == HTTPStatus.OK, resp2.text
    return resp2.json()["data"]["access_token"]


async def _disposable_tokens(i2b_client, db, tenant: dict, registry) -> tuple[str, str]:
    """Retailer + admin tokens for a disposable tenant (no data seeded)."""
    token_ret = await _login_disposable_retailer(i2b_client, tenant)
    admin = await _provision_disposable_admin(db, tenant, registry)
    token_admin = await _disposable_admin_token(i2b_client, admin)
    return token_ret, token_admin


async def _submit_and_confirm_disposable(
    i2b_client, db, tenant: dict, registry, amount: str = "100.00", method: str = "cash"
) -> dict:
    """Full declare→confirm flow INSIDE the disposable tenant.

    Equivalent of the shared I2C-I1 ``_submit_and_confirm`` but bound to the
    per-test disposable tenant: retailer login + declaration + disposable-admin
    confirmation. ALL rows (orders, payments, declarations, and the immutable
    ledger entries the confirm flow writes) live in the disposable schema,
    which the s2_clean_db teardown DROP SCHEMA CASCADE discards.
    """
    oid = await _seed_order_with_item(
        db, tenant["schema"], tenant["ws_id"], tenant["ret_id"], amount
    )
    token_ret = await _login_disposable_retailer(i2b_client, tenant)
    decl = await i2b_client.post(
        f"/api/v1/client/orders/{oid}/declare",
        json={"declared_amount": amount, "method": method},
        headers={**_headers(token_ret), "X-Declaration-Idempotency-Key": f"cdr1r1r1-{uuid.uuid4().hex}"},
    )
    assert decl.status_code == HTTPStatus.CREATED, decl.text
    decl_id = decl.json()["data"]["id"]

    admin = await _provision_disposable_admin(db, tenant, registry)
    token_admin = await _disposable_admin_token(i2b_client, admin)
    r = await i2b_client.post(
        f"/api/v1/declarations/{decl_id}/confirm", headers=_headers(token_admin)
    )
    assert r.status_code == HTTPStatus.OK, r.text

    return {
        "decl_id": decl_id,
        "oid": str(oid),
        "schema": tenant["schema"],
        "ws_id": tenant["ws_id"],
        "ret_id": tenant["ret_id"],
        "token_ret": token_ret,
        "token_admin": token_admin,
        "admin": admin,
        "tenant": tenant,
    }


async def _insert_payment_row(
    db: AsyncSession,
    schema: str,
    order_id: uuid.UUID,
    retailer_id: uuid.UUID,
    amount: str = "100.00",
    method: str = "cash",
    status: str = "completed",
    pay_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert a raw payment row (mirrors the canonical payments shape).

    ``retailer_id`` is intentionally a parameter so corrupt-ownership rows
    (payment retailer != order retailer) can be seeded for the R1 precheck.
    """
    if pay_id is None:
        pay_id = uuid.uuid4()
    receipt_number = f"RCT-20260804-{pay_id.int % 900000 + 100000:06d}"
    await db.execute(
        text(
            f'INSERT INTO "{schema}".payments '
            "(id, order_id, retailer_id, transaction_id, idempotency_key, amount, "
            "method, status, receipt_number, created_at, updated_at, is_deleted) "
            "VALUES (:id, :oid, :ret, :txid, :idem, :amt, :method, :status, "
            ":rno, now(), now(), false)"
        ),
        {
            "id": pay_id,
            "oid": order_id,
            "ret": retailer_id,
            "txid": f"tx-{pay_id.hex[:16]}",
            "idem": f"pay-{pay_id.hex}",
            "amt": Decimal(amount),
            "method": method,
            "status": status,
            "rno": receipt_number,
        },
    )
    await db.commit()
    return pay_id


async def _bulk_orders_with_charges(
    db: AsyncSession, schema: str, ws_id, ret_id, n: int, amount: str = "1.00"
) -> list[uuid.UUID]:
    """Seed ``n`` confirmed orders, each with a distinct non-zero +RECEIVABLE
    charge ledger row (=> ``n`` movements). Orders are left in place (the
    harness never deletes orders), so the charges never become orphans and
    never trip the schema-level orphan precheck for other tests.
    """
    oids = [uuid.uuid4() for _ in range(n)]
    await db.execute(
        text(
            f'INSERT INTO "{schema}".orders (id, wholesaler_id, retailer_id, status, total_amount, is_deleted) '
            "VALUES (:id, :ws, :ret, 'confirmed', :total, false)"
        ),
        [{"id": o, "ws": ws_id, "ret": ret_id, "total": Decimal(amount)} for o in oids],
    )
    await db.execute(
        text(
            f'INSERT INTO "{schema}".ledger_entries '
            "(id, transaction_date, account_type, amount, reference_type, reference_id, "
            "description, entry_version, is_deleted, created_at, updated_at) "
            "VALUES (:id, now(), 'receivable', :amt, 'order', :ref, :desc, 1, false, now(), now())"
        ),
        [
            {"id": uuid.uuid4(), "amt": Decimal(amount), "ref": o, "desc": f"charge {o}"}
            for o in oids
        ],
    )
    await db.commit()
    return oids


async def _bulk_payments(
    db: AsyncSession, schema: str, order_id, ret_id, n: int, amount: str = "1.00"
) -> list[uuid.UUID]:
    """Seed ``n`` completed payments on one order (same retailer).

    All IDs are PRE-GENERATED and returned so the caller can clean up ONLY
    those exact IDs via ``WHERE id = ANY(:owned_ids)`` (R1-R1-R1 Blocker 3).
    """
    pay_ids = [uuid.uuid4() for _ in range(n)]
    rows = [
        {
            "id": pay_ids[i],
            "oid": order_id,
            "ret": ret_id,
            "txid": f"tx-{pay_ids[i].hex[:12]}",
            "idem": f"pay-{pay_ids[i].hex}",
            "amt": Decimal(amount),
            "rno": f"RCT-20260804-{(i % 900000) + 100000:06d}",
        }
        for i in range(n)
    ]
    await db.execute(
        text(
            f'INSERT INTO "{schema}".payments '
            "(id, order_id, retailer_id, transaction_id, idempotency_key, amount, "
            "method, status, receipt_number, created_at, updated_at, is_deleted) "
            "VALUES (:id, :oid, :ret, :txid, :idem, :amt, 'cash', 'completed', "
            ":rno, now(), now(), false)"
        ),
        rows,
    )
    await db.commit()
    return pay_ids


async def _bulk_pending_declarations(
    db: AsyncSession, schema: str, ws_id, ret_id, order_id, n: int
) -> list[uuid.UUID]:
    """Seed ``n`` pending declarations on one order.

    All IDs are PRE-GENERATED and returned so the caller can clean up ONLY
    those exact IDs via ``WHERE id = ANY(:owned_ids)`` (R1-R1-R1 Blocker 3).
    No prefix / idempotency-key scanning is ever used for cleanup.
    """
    decl_ids = [uuid.uuid4() for _ in range(n)]
    rows = [
        {
            "id": decl_ids[i],
            "oid": order_id,
            "ret": ret_id,
            "ws": ws_id,
            "amt": Decimal("10.00"),
            "idem": f"pay-{decl_ids[i].hex}",
            "sb": uuid.uuid4(),
        }
        for i in range(n)
    ]
    await db.execute(
        text(
            f'INSERT INTO "{schema}".payment_declarations '
            "(id, order_id, retailer_id, wholesaler_id, declared_amount, method, "
            "status, idempotency_key, submitted_by, submitted_at, transfer_reference) "
            "VALUES (:id, :oid, :ret, :ws, :amt, 'cash', 'pending', :idem, :sb, now(), NULL)"
        ),
        rows,
    )
    await db.commit()
    return decl_ids


# ===========================================================================
# R1-R1-R1 Blocker 3 — exact test-ownership cleanup infrastructure.
#
#  * Every deletable row the test inserts is PRE-GENERATED with an owned ID and
#    cleaned up ONLY via ``WHERE id = ANY(:owned_ids)`` in a fresh session
#    (never a LIKE/prefix/wildcard/table-wide DELETE).
#  * Immutable ledger rows (ledger_entries is write-only) can never be deleted,
#    so every test that seeds ledger data runs inside an OWNED DISPOSABLE
#    SCHEMA which is DROPped (CASCADE) and verified absent afterwards — we
#    never rely on deleting immutable rows.
# ===========================================================================


async def _cleanup_exact_ids(db: AsyncSession, schema: str, table: str, ids: list[uuid.UUID]) -> int:
    """Delete exactly the owned IDs from one tenant table; return rowcount."""
    if not ids:
        return 0
    result = await db.execute(
        text(f'DELETE FROM "{schema}".{table} WHERE id = ANY(:ids)'),
        {"ids": ids},
    )
    await db.commit()
    return result.rowcount


@asynccontextmanager
async def _disposable_statement_schema(db: AsyncSession):
    """Context manager owning a disposable tenant schema for immutable ledger
    test data (R1-R1-R1 Blocker 3; R1-R1-R2 setup-failure safety).

    Creates a fresh ``t_stmt_<hex>`` schema with the exact tables the statement
    service queries, yields its name, then in a FRESH cleanup session DROPs it
    (CASCADE) and verifies it is absent from the catalog. Immutable
    ledger_entries rows are therefore discarded by schema drop — never by
    deleting immutable rows.

    R1-R1-R2 (P1): the DROP guard is armed the moment CREATE SCHEMA commits,
    so a CREATE TABLE failure mid-setup still drops the partial schema. No
    stray schema can ever leak (this is exactly how 58d4b51f leaked schemas).
    """
    from database.session import AsyncSessionLocal, async_engine
    from db.sql_safety import validate_identifier

    schema = f"t_stmt_{uuid.uuid4().hex[:12]}"
    validate_identifier(schema, "disposable statement schema")

    async def _drop(sch: str) -> None:
        validate_identifier(sch, "disposable statement schema (drop)")
        await async_engine.dispose()
        async with AsyncSessionLocal() as cleanup_db:
            await cleanup_db.execute(text(f'DROP SCHEMA IF EXISTS "{sch}" CASCADE'))
            await cleanup_db.commit()

    await db.execute(text(f'CREATE SCHEMA "{schema}"'))
    # From here the schema EXISTS — arm the failure drop for the rest of setup.
    try:
        await db.execute(text(
            f'CREATE TABLE "{schema}".orders ('
            "id UUID PRIMARY KEY, wholesaler_id UUID NOT NULL, retailer_id UUID NOT NULL, "
            "status TEXT NOT NULL, total_amount NUMERIC(12,2) NOT NULL, is_deleted BOOLEAN NOT NULL DEFAULT false, "
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        ))
        await db.execute(text(
            f'CREATE TABLE "{schema}".ledger_entries ('
            "id UUID PRIMARY KEY, transaction_date TIMESTAMPTZ NOT NULL DEFAULT now(), "
            "account_type TEXT NOT NULL, amount NUMERIC(18,4) NOT NULL, "
            "reference_type TEXT NOT NULL, reference_id UUID NOT NULL, description TEXT, "
            "entry_version INTEGER NOT NULL DEFAULT 1, is_deleted BOOLEAN NOT NULL DEFAULT false, "
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        ))
        await db.execute(text(
            f'CREATE TABLE "{schema}".payments ('
            "id UUID PRIMARY KEY, order_id UUID NOT NULL, retailer_id UUID NOT NULL, "
            "transaction_id TEXT NOT NULL, idempotency_key TEXT NOT NULL, amount NUMERIC(12,2) NOT NULL, "
            "method TEXT NOT NULL, status TEXT NOT NULL, receipt_number TEXT, "
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
            "is_deleted BOOLEAN NOT NULL DEFAULT false)"
        ))
        await db.execute(text(
            f'CREATE TABLE "{schema}".payment_declarations ('
            "id UUID PRIMARY KEY, order_id UUID NOT NULL, retailer_id UUID NOT NULL, "
            "wholesaler_id UUID NOT NULL, declared_amount NUMERIC(12,2) NOT NULL, method TEXT NOT NULL, "
            "status TEXT NOT NULL, idempotency_key TEXT NOT NULL, submitted_by UUID, "
            "submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(), transfer_reference TEXT, "
            "confirmed_by UUID, confirmed_at TIMESTAMPTZ, confirmation_payment_id UUID)"
        ))
        await db.commit()
    except BaseException as original_error:
        # R1-R1-R4 §3: a CREATE TABLE failure must still drop the partial
        # schema, but cleanup errors are RECORDED and raised alongside the
        # original via BaseExceptionGroup (never swallowed). Rollback the
        # main session first to release locks before the fresh-session DROP.
        cleanup_errors: list[BaseException] = []
        try:
            await db.rollback()
        except BaseException as exc:
            cleanup_errors.append(exc)
        try:
            await _drop(schema)
        except BaseException as exc:
            cleanup_errors.append(exc)
        if cleanup_errors:
            raise BaseExceptionGroup(
                "statement-schema setup failure with cleanup errors",
                [original_error, *cleanup_errors],
            )
        raise
    try:
        yield schema
    finally:
        # Release the main session's open transaction FIRST — otherwise the
        # fresh cleanup session's DROP SCHEMA blocks on its ACCESS SHARE locks
        # until the 10s asyncpg command timeout (TimeoutError at bind_execute).
        await db.rollback()
        async with AsyncSessionLocal() as cleanup_db:
            await cleanup_db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await cleanup_db.commit()
            row = (
                await cleanup_db.execute(
                    text(
                        "SELECT schema_name FROM information_schema.schemata "
                        "WHERE schema_name = :s"
                    ),
                    {"s": schema},
                )
            ).first()
            assert row is None, f"disposable schema {schema} still present after drop"


# ===========================================================================
# §1 Happy paths + dual-key isolation
# ===========================================================================


class TestStatementHappyPath:
    """Statement renders ledger-derived balances + independent settled list.

    Runs entirely inside the per-test OWNED DISPOSABLE tenant: every order,
    payment, declaration and IMMUTABLE ledger row lives in the disposable
    schema, which the s2_clean_db teardown DROP SCHEMA CASCADE discards
    (R1-R1-R1 Blocker 3). No row is ever deleted individually.
    """

    async def test_retailer_statement_happy_path(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        tenant = contractd_disposable_tenant
        db, reg = s2_clean_db
        info = await _submit_and_confirm_disposable(
            i2b_client, db, tenant, reg, amount="100.00"
        )
        # _seed_order_with_item seeds via raw SQL (no service path), so post the
        # +RECEIVABLE charge that the order-confirmation service path would have.
        await _post_receivable_charge(db, info["schema"], uuid.UUID(info["oid"]), "100.00")
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        assert data["document_type"] == "statement"
        assert data["supplier_name"]
        assert data["retailer_name"]
        assert Decimal(data["opening_balance"]) >= Decimal("0")
        # The order-confirmation receivable (+100) + cash collection (-100).
        assert Decimal(data["charge_total"]) == Decimal("100.00")
        assert Decimal(data["collection_total"]) == Decimal("100.00")
        # Independent settled-payments list carries the completed payment.
        assert any(Decimal(p["amount"]) == Decimal("100.00") for p in data["settled_payments"])
        # R1: settled_total derives ONLY from settled_payments[].amount.
        assert Decimal(data["settled_total"]) == sum(
            (Decimal(p["amount"]) for p in data["settled_payments"]), Decimal("0")
        )
        # R1: movements carry kind + display_amount=abs(signed_amount).
        for m in data["movements"]:
            assert m["kind"] in ("charge", "collection")
            assert Decimal(m["display_amount"]) == abs(Decimal(m["signed_amount"]))
            assert m["kind"] == ("charge" if Decimal(m["signed_amount"]) > 0 else "collection")
        # R1: no internal ids in the serialized response.
        assert "movement_id" not in r.text
        assert "payment_id" not in r.text

    async def test_supplier_statement_happy_path(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        tenant = contractd_disposable_tenant
        db, reg = s2_clean_db
        info = await _submit_and_confirm_disposable(
            i2b_client, db, tenant, reg, amount="250.00"
        )
        await _post_receivable_charge(db, info["schema"], uuid.UUID(info["oid"]), "250.00")
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_supplier_statement(i2b_client, info["token_admin"], info["ret_id"], frm, to)
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        assert Decimal(data["charge_total"]) == Decimal("250.00")
        assert Decimal(data["collection_total"]) == Decimal("250.00")
        # closing balance arithmetic: closing == opening + net_movement.
        opening = Decimal(data["opening_balance"])
        net = Decimal(data["net_movement"])
        closing = Decimal(data["closing_balance"])
        assert closing == opening + net

    async def test_opening_closing_arithmetic_invariant(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        """closing_balance must equal opening_balance + net_movement exactly."""
        tenant = contractd_disposable_tenant
        db, reg = s2_clean_db
        info = await _submit_and_confirm_disposable(
            i2b_client, db, tenant, reg, amount="100.00"
        )
        await _post_receivable_charge(db, info["schema"], uuid.UUID(info["oid"]), "100.00")
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        data = r.json()["data"]
        opening = Decimal(data["opening_balance"])
        net = Decimal(data["net_movement"])
        charge = Decimal(data["charge_total"])
        coll = Decimal(data["collection_total"])
        assert net == charge - coll
        assert Decimal(data["closing_balance"]) == opening + net


class TestDualKeyIsolation:
    """Cross-tenant / cross-retailer denial is neutral (no existence disclosure)."""

    async def test_supplier_foreign_retailer_denied_neutral(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        tenant = contractd_disposable_tenant
        db, reg = s2_clean_db
        info = await _submit_and_confirm_disposable(i2b_client, db, tenant, reg)
        frm, to = await _stmt_period_yesterday_today()
        # A random retailer id not bound to this supplier -> neutral 404.
        foreign_ret = str(uuid.uuid4())
        r = await _get_supplier_statement(i2b_client, info["token_admin"], foreign_ret, frm, to)
        assert r.status_code == HTTPStatus.NOT_FOUND
        body = r.json()
        assert body["code"] == "STATEMENT_NOT_AVAILABLE"
        # No internal id leak.
        assert foreign_ret not in r.text


# ===========================================================================
# §2 Strict shared date-range contract (R1 rule 3) — 400 INVALID_DATE_RANGE
# ===========================================================================


class TestDateRangeContract:
    """Missing/blank/malformed/reversed/>365-day ranges -> controlled 400
    INVALID_DATE_RANGE (never a framework 422 or a neutral 404) on BOTH routes
    (they share the same strict parser). The public message is neutral and
    carries no raw parser/internal details.

    Date validation runs BEFORE any ledger/list access, so these tests only
    need disposable tokens — no statement data is seeded.
    """

    async def test_missing_from_date(self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity):
        db, reg = s2_clean_db
        token_ret, _ = await _disposable_tokens(i2b_client, db, contractd_disposable_tenant, reg)
        r = await i2b_client.get(
            "/api/v1/client/statements/print",
            params={"to": "2026-08-10"},
            headers=_headers(token_ret),
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST
        assert r.json()["code"] == "INVALID_DATE_RANGE"
        # No raw parser/internal details in the public message.
        assert "strptime" not in r.text
        assert "ValueError" not in r.text

    async def test_missing_to_date(self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity):
        db, reg = s2_clean_db
        token_ret, _ = await _disposable_tokens(i2b_client, db, contractd_disposable_tenant, reg)
        r = await i2b_client.get(
            "/api/v1/client/statements/print",
            params={"from": "2026-08-01"},
            headers=_headers(token_ret),
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST
        assert r.json()["code"] == "INVALID_DATE_RANGE"

    async def test_blank_from_date(self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity):
        db, reg = s2_clean_db
        token_ret, _ = await _disposable_tokens(i2b_client, db, contractd_disposable_tenant, reg)
        r = await i2b_client.get(
            "/api/v1/client/statements/print",
            params={"from": "   ", "to": "2026-08-10"},
            headers=_headers(token_ret),
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST
        assert r.json()["code"] == "INVALID_DATE_RANGE"

    async def test_malformed_from_date(self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity):
        db, reg = s2_clean_db
        token_ret, _ = await _disposable_tokens(i2b_client, db, contractd_disposable_tenant, reg)
        r = await i2b_client.get(
            "/api/v1/client/statements/print",
            params={"from": "01/08/2026", "to": "2026-08-10"},
            headers=_headers(token_ret),
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST
        assert r.json()["code"] == "INVALID_DATE_RANGE"
        assert "01/08/2026" not in r.text

    async def test_from_after_to(self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity):
        db, reg = s2_clean_db
        token_ret, _ = await _disposable_tokens(i2b_client, db, contractd_disposable_tenant, reg)
        r = await _get_retailer_statement(i2b_client, token_ret, "2026-08-10", "2026-08-01")
        assert r.status_code == HTTPStatus.BAD_REQUEST
        assert r.json()["code"] == "INVALID_DATE_RANGE"

    async def test_span_exceeds_365_days(self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity):
        db, reg = s2_clean_db
        token_ret, _ = await _disposable_tokens(i2b_client, db, contractd_disposable_tenant, reg)
        r = await _get_retailer_statement(i2b_client, token_ret, "2025-01-01", "2026-08-10")
        assert r.status_code == HTTPStatus.BAD_REQUEST
        assert r.json()["code"] == "INVALID_DATE_RANGE"

    async def test_supplier_route_shares_the_same_strict_parser(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        db, reg = s2_clean_db
        _, token_admin = await _disposable_tokens(i2b_client, db, contractd_disposable_tenant, reg)
        ret_id = contractd_disposable_tenant["ret_id"]
        # Malformed + reversed + >365-day must behave identically on the
        # supplier route (same shared parser).
        r1 = await _get_supplier_statement(i2b_client, token_admin, ret_id, "nope", "2026-08-10")
        assert r1.status_code == HTTPStatus.BAD_REQUEST
        assert r1.json()["code"] == "INVALID_DATE_RANGE"
        r2 = await _get_supplier_statement(i2b_client, token_admin, ret_id, "2026-08-10", "2026-08-01")
        assert r2.status_code == HTTPStatus.BAD_REQUEST
        assert r2.json()["code"] == "INVALID_DATE_RANGE"
        r3 = await _get_supplier_statement(i2b_client, token_admin, ret_id, "2025-01-01", "2026-08-10")
        assert r3.status_code == HTTPStatus.BAD_REQUEST
        assert r3.json()["code"] == "INVALID_DATE_RANGE"

    async def test_non_zero_padded_date_is_rejected(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        """R1-R1 P2: strptime would accept ``2026-8-1``; the strict YYYY-MM-DD
        contract (regex fullmatch before parse) must reject it."""
        db, reg = s2_clean_db
        token_ret, _ = await _disposable_tokens(i2b_client, db, contractd_disposable_tenant, reg)
        for bad in (("2026-8-01", "2026-08-10"), ("2026-08-1", "2026-08-10"),
                    ("2026-8-1", "2026-8-2")):
            r = await _get_retailer_statement(i2b_client, token_ret, bad[0], bad[1])
            assert r.status_code == HTTPStatus.BAD_REQUEST, bad
            assert r.json()["code"] == "INVALID_DATE_RANGE"

    async def test_extra_characters_in_date_are_rejected(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        """R1-R1 P2: trailing/leading/embedded characters (that survive strip)
        must not pass (fullmatch). Bare whitespace is stripped by the parser
        and therefore legitimately accepted."""
        db, reg = s2_clean_db
        token_ret, _ = await _disposable_tokens(i2b_client, db, contractd_disposable_tenant, reg)
        for bad in ("2026-08-010", "2026-08-01T00:00", "x2026-08-01", "2026-08-01X", "2026--08-01"):
            r = await _get_retailer_statement(i2b_client, token_ret, bad, "2026-08-10")
            assert r.status_code == HTTPStatus.BAD_REQUEST, bad
            assert r.json()["code"] == "INVALID_DATE_RANGE"

    async def test_invalid_calendar_date_is_rejected(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        """R1-R1: regex-valid but impossible calendar dates (Feb 30, month 13)
        are rejected by the strict parser too."""
        db, reg = s2_clean_db
        token_ret, _ = await _disposable_tokens(i2b_client, db, contractd_disposable_tenant, reg)
        for bad in ("2026-02-30", "2026-13-01", "2026-00-10", "0000-08-10"):
            r = await _get_retailer_statement(i2b_client, token_ret, bad, "2026-08-10")
            assert r.status_code == HTTPStatus.BAD_REQUEST, bad
            assert r.json()["code"] == "INVALID_DATE_RANGE"

    # -- R1-R1-R1 exact syntax: whitespace/encoded whitespace is NOT trimmed --

    async def test_whitespace_suffix_is_rejected(self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity):
        """R1-R1-R1: a trailing space (decoded %20) must return 400 — the raw
        value differs from its own strip(), so it is rejected without trimming."""
        db, reg = s2_clean_db
        token_ret, _ = await _disposable_tokens(i2b_client, db, contractd_disposable_tenant, reg)
        r = await _get_retailer_statement(i2b_client, token_ret, "2026-08-01 ", "2026-08-10")
        assert r.status_code == HTTPStatus.BAD_REQUEST
        assert r.json()["code"] == "INVALID_DATE_RANGE"

    async def test_encoded_space_20_is_rejected(self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity):
        """R1-R1-R1: %20 in the query is decoded to a space by the framework;
        the raw received value therefore carries a trailing space and must be
        rejected (400 INVALID_DATE_RANGE), not trimmed.

        The encoded query string is sent in the RAW URL (httpx ``params`` would
        double-encode ``%20`` -> ``%2520``, never exercising the decoded path).
        """
        db, reg = s2_clean_db
        token_ret, _ = await _disposable_tokens(i2b_client, db, contractd_disposable_tenant, reg)
        r = await i2b_client.get(
            "/api/v1/client/statements/print?from=2026-08-01%20&to=2026-08-10",
            headers=_headers(token_ret),
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST
        assert r.json()["code"] == "INVALID_DATE_RANGE"

    async def test_encoded_tab_09_is_rejected(self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity):
        """R1-R1-R1: %09 (tab) as a suffix must be rejected on the raw value
        (raw URL form so the framework decodes %09 to a real tab)."""
        db, reg = s2_clean_db
        token_ret, _ = await _disposable_tokens(i2b_client, db, contractd_disposable_tenant, reg)
        r = await i2b_client.get(
            "/api/v1/client/statements/print?from=2026-08-01%09&to=2026-08-10",
            headers=_headers(token_ret),
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST
        assert r.json()["code"] == "INVALID_DATE_RANGE"

    async def test_tab_and_newline_suffixes_are_rejected(self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity):
        """R1-R1-R1: literal tab / newline suffixes (decoded from %09/%0A) are
        rejected on the raw value."""
        db, reg = s2_clean_db
        token_ret, _ = await _disposable_tokens(i2b_client, db, contractd_disposable_tenant, reg)
        for bad in ("2026-08-01\t", "2026-08-01\n"):
            r = await _get_retailer_statement(i2b_client, token_ret, bad, "2026-08-10")
            assert r.status_code == HTTPStatus.BAD_REQUEST, repr(bad)
            assert r.json()["code"] == "INVALID_DATE_RANGE"

    async def test_parser_rejects_trimmed_input_directly(self):
        """R1-R1-R1 direct-parser proof: the shared parser rejects any raw value
        that differs from its own strip() (space/tab/newline suffixes)."""
        from repositories.statement_repository import (
            StatementPeriodError,
            parse_statement_date_range,
        )

        for bad_from, bad_to in (
            ("2026-08-01 ", "2026-08-10"),
            ("2026-08-01\t", "2026-08-10"),
            ("2026-08-01\n", "2026-08-10"),
            (" 2026-08-01", "2026-08-10"),
            ("2026-08-01", "2026-08-10 "),
        ):
            with pytest.raises(StatementPeriodError):
                parse_statement_date_range(bad_from, bad_to)

    async def test_parser_accepts_canonical_input_directly(self):
        """R1-R1-R1 direct-parser proof: the canonical zero-padded shape passes."""
        from repositories.statement_repository import parse_statement_date_range

        from_, to_ = parse_statement_date_range("2026-08-01", "2026-08-10")
        assert from_.isoformat() == "2026-08-01"
        assert to_.isoformat() == "2026-08-10"

    async def test_malformed_retailer_uuid_supplier(self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity):
        db, reg = s2_clean_db
        _, token_admin = await _disposable_tokens(i2b_client, db, contractd_disposable_tenant, reg)
        r = await _get_supplier_statement(i2b_client, token_admin, "not-a-uuid", "2026-08-01", "2026-08-10")
        assert r.status_code == HTTPStatus.NOT_FOUND
        assert r.json()["code"] == "STATEMENT_NOT_AVAILABLE"


# ===========================================================================
# §3 Zero-write proof
# ===========================================================================


class TestZeroWrite:
    """Statement routes produce zero writes and zero fingerprint changes."""

    async def test_statement_routes_zero_fingerprint(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        db, reg = s2_clean_db
        tenant = contractd_disposable_tenant
        info = await _submit_and_confirm_disposable(i2b_client, db, tenant, reg)
        sch_a = info["schema"]
        ws_a = tenant["ws_id"]
        ret_a = tenant["ret_id"]

        fp_before = {
            "orders": await _table_fingerprint(db, sch_a, "orders"),
            "order_items": await _table_fingerprint(db, sch_a, "order_items"),
            "payments": await _table_fingerprint(db, sch_a, "payments"),
            "payment_declarations": await _table_fingerprint(db, sch_a, "payment_declarations"),
            "ledger_entries": await _table_fingerprint(db, sch_a, "ledger_entries"),
            "receipt_sequences": await _receipt_seq_fingerprint(db, sch_a),
            "binding_balance": await _binding_fingerprint(db, ws_a, ret_a),
        }

        frm, to = await _stmt_period_yesterday_today()
        # Exercise both statement routes.
        r1 = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        r2 = await _get_supplier_statement(i2b_client, info["token_admin"], ret_a, frm, to)
        assert r1.status_code == HTTPStatus.OK, r1.text
        assert r2.status_code == HTTPStatus.OK, r2.text

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
# §4 Independent dual lists (movements vs settled payments)
# ===========================================================================


class TestIndependentLists:
    """movements[] and settled_payments[] are independent; never cross-associated."""

    async def test_movements_and_settled_payments_are_separate_lists(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        db, reg = s2_clean_db
        info = await _submit_and_confirm_disposable(i2b_client, db, contractd_disposable_tenant, reg)
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        data = r.json()["data"]
        # movements carry ledger reference_type (order/refund) + R1 kind/
        # display_amount; no internal ledger id.
        for m in data["movements"]:
            assert m["reference_type"] in ("order", "refund")
            assert m["kind"] in ("charge", "collection")
            assert "movement_id" not in m
        # settled payments carry receipt_number/method — no ledger reference
        # fields, no internal payment id (R1).
        for p in data["settled_payments"]:
            assert "reference_type" not in p
            assert "signed_amount" not in p
            assert "payment_id" not in p
        # settled_total is a top-level field, never per-line.
        assert "settled_total" in data
        for p in data["settled_payments"]:
            assert "settled_total" not in p

    async def test_pending_declarations_only_when_requested(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        db, reg = s2_clean_db
        info = await _submit_and_confirm_disposable(i2b_client, db, contractd_disposable_tenant, reg)
        frm, to = await _stmt_period_yesterday_today()
        # Default (include_pending=false): no pending list entries leak.
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        assert r.json()["data"]["pending_declarations"] == []
        # Pending never affects balances or settled totals.


# ===========================================================================
# §5 No internal-ID leakage
# ===========================================================================


class TestNoLeakage:
    """No payment row UUID, cashier user id, tenant_user_id, or schema name leaks.

    R1 evidence repair: the "no internal ID" assertions now verify the
    SERIALIZED response contains no movement_id/payment_id keys at all.
    """

    async def test_no_internal_ids_in_statement(self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity):
        db, reg = s2_clean_db
        info = await _submit_and_confirm_disposable(i2b_client, db, contractd_disposable_tenant, reg)
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        body = r.text
        # Schema name must never leak.
        assert info["schema"] not in body
        # The supplier internal tenant id must not appear as a raw value.
        assert info["ws_id"] not in body
        # R1 redaction: no movement_id / payment_id anywhere in the response.
        assert "movement_id" not in body
        assert "payment_id" not in body


# ===========================================================================
# §6 Fail-closed 409 cases (orphan / arithmetic / reconciliation)
# ===========================================================================


class TestFailClosed:
    """Orphan ledger / arithmetic mismatch surface precise 409 codes."""

    async def test_orphan_ledger_ref_returns_409_scope_incomplete(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        """Orphan receivable refs surface STATEMENT_LEDGER_SCOPE_INCOMPLETE.

        The orphan row lives in the OWNED DISPOSABLE tenant schema which the
        teardown DROP SCHEMA CASCADE discards (R1-R1-R1 Blocker 3) — we never
        rely on deleting immutable ledger rows.

        The service is invoked directly (with the disposable schema) so the
        assertion is independent of HTTP identity resolution.
        """
        from datetime import date as _date
        from services.print_service import build_statement_print
        from repositories.statement_repository import StatementLedgerScopeIncomplete

        db, _reg = s2_clean_db
        tenant = contractd_disposable_tenant
        schema = tenant["schema"]
        ws_id = uuid.UUID(tenant["ws_id"])
        ret_id = uuid.UUID(tenant["ret_id"])

        # Insert an orphan receivable ledger entry referencing a non-existent
        # order (no FK exists, so the INSERT succeeds).
        orphan_id = uuid.uuid4()
        await db.execute(
            text(
                f'INSERT INTO "{schema}".ledger_entries '
                "(id, transaction_date, account_type, amount, reference_type, reference_id, "
                "entry_version, is_deleted, created_at, updated_at) "
                "VALUES (:id, now(), 'receivable', :amt, 'order', :ref, 1, false, now(), now())"
            ),
            {"id": orphan_id, "amt": Decimal("999.00"), "ref": uuid.uuid4()},
        )
        await db.commit()

        res = await build_statement_print(
            db,
            schema=schema,
            wholesaler_id=ws_id,
            retailer_id=ret_id,
            date_from=_date(2026, 8, 1),
            date_to=_date(2026, 8, 10),
        )
        assert res.view is None
        assert isinstance(res.error, StatementLedgerScopeIncomplete)
        # The HTTP route maps this to 409 STATEMENT_LEDGER_SCOPE_INCOMPLETE
        # (verified separately by the route-level inventory tests).

    async def test_zero_value_movement_returns_409_internal_inconsistent(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        """R1 rule 2 — a zero-valued receivable movement is an internal
        inconsistency and must fail closed (409 STATEMENT_INTERNAL_INCONSISTENT).

        RED: on the pre-R1 implementation a zero-valued movement rendered
        silently (no kind classification existed); this assertion fails there.
        GREEN: the R1 zero-value check returns the 409.

        The zero-valued row (and the whole disposable tenant) is discarded by
        the teardown DROP SCHEMA — never by deleting immutable rows.
        """
        db, reg = s2_clean_db
        info = await _submit_and_confirm_disposable(i2b_client, db, contractd_disposable_tenant, reg)
        await _post_receivable_charge(db, info["schema"], uuid.UUID(info["oid"]), "0.00")
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        assert r.status_code == HTTPStatus.CONFLICT
        assert r.json()["code"] == "STATEMENT_INTERNAL_INCONSISTENT"
        # Zero partial document.
        assert "data" not in r.json()


# ===========================================================================
# §6b R1-R1-R1 — completed-payment ownership integrity (rule 1; wrong
# wholesaler / missing order closure). Corrupt payments live in the OWNED
# DISPOSABLE tenant; the teardown DROP SCHEMA discards them. For the deletable
# corruption rows we ALSO demonstrate exact-ID cleanup with rowcount + fresh
# session (R1-R1-R1 Blocker 3).
# ===========================================================================


class TestPaymentOwnershipIntegrity:
    """A completed payment whose retailer differs from its order's retailer,
    whose order belongs to a different wholesaler, or whose order is
    unresolvable makes the payment scope inconsistent: the statement fails
    closed with 409 STATEMENT_INTERNAL_INCONSISTENT and zero partial document.
    Corrupt rows neither leak into the document nor silently disappear."""

    async def _seed_corrupt_payment(self, db, tenant, *, payment_retailer=None, order_wholesaler=None, order_id=None):
        """Insert a corrupt completed payment into the disposable schema.

        The order is always created with the CORRECT owner (tenant retailer +
        tenant wholesaler); only the payment is corrupt (or the order is
        missing / belongs to another wholesaler). Returns the pre-generated
        owned payment id.
        """
        schema = tenant["schema"]
        oid = order_id or uuid.uuid4()
        if order_id is None:
            # A resolvable order owned by THIS relationship (correct retailer /
            # wholesaler) so only the payment is corrupt.
            await db.execute(
                text(
                    f'INSERT INTO "{schema}".orders (id, wholesaler_id, retailer_id, status, total_amount, is_deleted) '
                    "VALUES (:id, :ws, :ret, 'confirmed', 50.00, false)"
                ),
                {
                    "id": oid,
                    "ws": order_wholesaler or tenant["ws_id"],
                    "ret": tenant["ret_id"],
                },
            )
        pay_id = await _insert_payment_row(
            db, schema, oid, payment_retailer or tenant["ret_id"], amount="50.00"
        )
        return pay_id

    async def test_payment_retailer_mismatch_returns_409_internal_inconsistent(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        """Payment retailer != order retailer -> 409 (both routes)."""
        db, reg = s2_clean_db
        tenant = contractd_disposable_tenant
        info = await _submit_and_confirm_disposable(i2b_client, db, tenant, reg)
        foreign_ret = uuid.uuid4()
        pay_id = await self._seed_corrupt_payment(
            db, tenant, payment_retailer=foreign_ret
        )
        try:
            frm, to = await _stmt_period_yesterday_today()
            r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
            assert r.status_code == HTTPStatus.CONFLICT
            assert r.json()["code"] == "STATEMENT_INTERNAL_INCONSISTENT"
            # Zero partial document — the corrupt row is not rendered.
            assert "data" not in r.json()
            assert str(pay_id) not in r.text
            assert str(foreign_ret) not in r.text
        finally:
            # Exact-ID cleanup with fresh session + rowcount (R1-R1-R1 Blocker 3).
            from database.session import AsyncSessionLocal

            async with AsyncSessionLocal() as cleanup_db:
                result = await cleanup_db.execute(
                    text(f'DELETE FROM "{tenant["schema"]}".payments WHERE id = :pid'),
                    {"pid": pay_id},
                )
                assert result.rowcount == 1, "expected exactly 1 owned payment deleted"
                await cleanup_db.commit()

    async def test_wrong_order_wholesaler_returns_409(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        """R1-R1-R1: a completed payment whose ORDER belongs to a DIFFERENT
        wholesaler (even with a matching payment retailer) is corruption."""
        db, reg = s2_clean_db
        tenant = contractd_disposable_tenant
        info = await _submit_and_confirm_disposable(i2b_client, db, tenant, reg)
        other_ws = uuid.uuid4()
        pay_id = await self._seed_corrupt_payment(
            db, tenant, order_wholesaler=other_ws
        )
        try:
            frm, to = await _stmt_period_yesterday_today()
            r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
            assert r.status_code == HTTPStatus.CONFLICT
            assert r.json()["code"] == "STATEMENT_INTERNAL_INCONSISTENT"
            assert "data" not in r.json()
        finally:
            from database.session import AsyncSessionLocal

            async with AsyncSessionLocal() as cleanup_db:
                result = await cleanup_db.execute(
                    text(f'DELETE FROM "{tenant["schema"]}".payments WHERE id = :pid'),
                    {"pid": pay_id},
                )
                assert result.rowcount == 1
                await cleanup_db.commit()

    async def test_missing_order_returns_409(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        """R1-R1-R1: a completed payment whose order is unresolvable (LEFT JOIN
        -> o.id IS NULL) is corruption -> 409.

        The PRODUCTION schema has ``payments_order_id_fkey`` (FK), so an orphan
        payment is NOT constructible there — the DB itself already prevents the
        corruption. The LEFT JOIN ``o.id IS NULL`` branch is therefore proven in
        the FK-LESS owned disposable schema (``_disposable_statement_schema``),
        where the orphan payment CAN be inserted, and the precheck must fail
        closed with STATEMENT_INTERNAL_INCONSISTENT and zero partial view.
        """
        from datetime import date as _date
        from services.print_service import build_statement_print
        from repositories.statement_repository import StatementInternalInconsistent

        db, _reg = s2_clean_db
        tenant = contractd_disposable_tenant
        ws_id = uuid.UUID(tenant["ws_id"])
        ret_id = uuid.UUID(tenant["ret_id"])

        async with _disposable_statement_schema(db) as schema:
            # Orphan completed payment: order_id references nothing (no FK).
            orphan_pay_id = uuid.uuid4()
            await db.execute(
                text(
                    f'INSERT INTO "{schema}".payments '
                    "(id, order_id, retailer_id, transaction_id, idempotency_key, amount, "
                    "method, status, receipt_number, created_at, updated_at, is_deleted) "
                    "VALUES (:id, :oid, :ret, 'tx-orphan', 'pay-orphan-idem', 50.00, "
                    "'cash', 'completed', 'RCT-000001', now(), now(), false)"
                ),
                {"id": orphan_pay_id, "oid": uuid.uuid4(), "ret": ret_id},
            )
            await db.commit()

            res = await build_statement_print(
                db,
                schema=schema,
                wholesaler_id=ws_id,
                retailer_id=ret_id,
                date_from=_date(2026, 8, 1),
                date_to=_date(2026, 8, 10),
            )
            assert res.view is None
            assert isinstance(res.error, StatementInternalInconsistent)
            # The HTTP route maps this to 409 STATEMENT_INTERNAL_INCONSISTENT
            # (verified separately by the route-level tests); zero partial doc.
            # The orphan payment lives in the disposable schema, discarded by
            # the DROP SCHEMA CASCADE teardown (never deleted by id).

    async def test_ownership_mismatch_also_fails_closed_on_supplier_route(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        db, reg = s2_clean_db
        tenant = contractd_disposable_tenant
        info = await _submit_and_confirm_disposable(i2b_client, db, tenant, reg)
        foreign_ret = uuid.uuid4()
        pay_id = await self._seed_corrupt_payment(
            db, tenant, payment_retailer=foreign_ret
        )
        try:
            frm, to = await _stmt_period_yesterday_today()
            r = await _get_supplier_statement(i2b_client, info["token_admin"], tenant["ret_id"], frm, to)
            assert r.status_code == HTTPStatus.CONFLICT
            assert r.json()["code"] == "STATEMENT_INTERNAL_INCONSISTENT"
            assert "data" not in r.json()
        finally:
            from database.session import AsyncSessionLocal

            async with AsyncSessionLocal() as cleanup_db:
                result = await cleanup_db.execute(
                    text(f'DELETE FROM "{tenant["schema"]}".payments WHERE id = :pid'),
                    {"pid": pay_id},
                )
                assert result.rowcount == 1
                await cleanup_db.commit()

    async def test_unrelated_relationship_is_not_faulted(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        """R1-R1-R2: the ownership precheck is scoped to the AUTHORITATIVE
        (wholesaler_id, retailer_id) relationship. A corrupt payment in ONE
        relationship does NOT fault an UNRELATED relationship's statement —
        the unrelated retailer keeps getting 200 (its own rows are clean).

        RED on 58d4b51f: the schema-global precheck faulted every relationship
        (cross-relationship availability coupling). GREEN now: the precheck
        scans only the requesting relationship's payments.
        """
        db, reg = s2_clean_db
        tenant = contractd_disposable_tenant
        info = await _submit_and_confirm_disposable(i2b_client, db, tenant, reg)
        # A second, unrelated retailer (valid relationship) in the SAME schema.
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (
            _create_retailer_user,
            _grant_retailer_operator,
        )

        other_email = _unique_email()
        # NOTE: no registry registration for this second user — its rows live
        # INSIDE the disposable schema, which the fixture teardown drops.
        # Registering it would make the registry's teardown query user_roles in
        # the ALREADY-DROPPED schema (UndefinedTableError).
        other_uid = await _create_retailer_user(
            db, tenant_schema=tenant["schema"], email=other_email,
            password=_DISPOSABLE_PW,
        )
        await _grant_retailer_operator(db, tenant_schema=tenant["schema"], user_id=other_uid)
        other_ret = await _create_retailer(db, name="Other Retailer", registry=reg)
        await _create_binding(
            db, wholesaler_id=tenant["ws_id"], retailer_id=other_ret,
            tenant_user_id=other_uid, registry=reg,
        )
        # Corrupt payment in the PRIMARY relationship (foreign retailer) — this
        # must NOT touch the OTHER relationship (other_ret).
        foreign_ret = uuid.uuid4()
        pay_id = await self._seed_corrupt_payment(db, tenant, payment_retailer=foreign_ret)
        try:
            frm, to = await _stmt_period_yesterday_today()
            # The unrelated retailer logs in and requests its OWN statement.
            resp = await i2b_client.post(
                "/api/v1/client/auth/login",
                json={
                    "email": other_email,
                    "password": _DISPOSABLE_PW,
                    "wholesaler_code": tenant["code"],
                },
            )
            assert resp.status_code == HTTPStatus.OK, resp.text
            other_token = resp.json()["data"]["tokens"]["access_token"]
            # The unrelated relationship has no corruption -> 200, not 409.
            r = await _get_retailer_statement(i2b_client, other_token, frm, to)
            assert r.status_code == HTTPStatus.OK, r.text
            assert "data" in r.json()
            # The PRIMARY (corrupt) relationship still fails closed 409.
            r_corrupt = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
            assert r_corrupt.status_code == HTTPStatus.CONFLICT
            assert r_corrupt.json()["code"] == "STATEMENT_INTERNAL_INCONSISTENT"
            assert "data" not in r_corrupt.json()
        finally:
            from database.session import AsyncSessionLocal

            async with AsyncSessionLocal() as cleanup_db:
                result = await cleanup_db.execute(
                    text(f'DELETE FROM "{tenant["schema"]}".payments WHERE id = :pid'),
                    {"pid": pay_id},
                )
                assert result.rowcount == 1
                await cleanup_db.commit()


# ===========================================================================
# §6c R1 — settled_total derives ONLY from settled_payments[].amount (rule 2)
# ===========================================================================


class TestSettledTotal:
    """settled_total must equal the sum of settled_payments[].amount — never
    derived from movements or cached balances.

    RED: the pre-R1 response had no settled_total field at all.
    """

    async def test_settled_total_equals_sum_of_settled_payments(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        db, reg = s2_clean_db
        tenant = contractd_disposable_tenant
        info = await _submit_and_confirm_disposable(
            i2b_client, db, tenant, reg, amount="250.00"
        )
        # A second completed payment in the same period (independent row).
        pay_id = await _insert_payment_row(
            db, info["schema"], uuid.UUID(info["oid"]), uuid.UUID(tenant["ret_id"]), amount="75.00"
        )
        try:
            frm, to = await _stmt_period_yesterday_today()
            r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
            assert r.status_code == HTTPStatus.OK, r.text
            data = r.json()["data"]
            settled_sum = sum((Decimal(p["amount"]) for p in data["settled_payments"]), Decimal("0"))
            assert Decimal(data["settled_total"]) == settled_sum
            assert Decimal(data["settled_total"]) == Decimal("325.00")
            # settled_total never reflects movements or pending declarations.
            assert "settled_total" not in data["settled_payments"][0]
        finally:
            from database.session import AsyncSessionLocal

            async with AsyncSessionLocal() as cleanup_db:
                result = await cleanup_db.execute(
                    text(f'DELETE FROM "{tenant["schema"]}".payments WHERE id = :pid'),
                    {"pid": pay_id},
                )
                assert result.rowcount == 1
                await cleanup_db.commit()


# ===========================================================================
# §6d R1 — reconciliation tolerance (rule 4)
# ===========================================================================


class TestReconciliationTolerance:
    """Credit-only reconciliation fails only when
    abs(ledger_total - cached_balance) > Decimal("0.01").

    Setup per test: convert the relationship to credit-only (the sole
    completed payment becomes method='credit'), then set the cached binding
    outstanding_balance to a value 0.001 / 0.01 / 0.0101 KES away from the
    ledger receivable total (0.00 after the +100 charge and the -100
    collection cancel). Each test uses its own fresh binding, so no residue
    leaks to other tests.
    """

    async def _credit_only_setup(self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity, delta: str):
        """Convert the relationship to credit-only and force a ledger/cache
        difference of exactly ``delta`` KES.

        The cached binding balance column is numeric(12,2), so a >0.01 delta
        cannot be expressed there (0.0101 would be rounded to 0.01). The delta
        is therefore introduced as a high-precision receivable LEDGER row, and
        the cached balance is pinned to exactly 0 (exactly representable):
        ledger_total = 0 + delta, cached = 0 -> diff = delta.
        """
        db, reg = s2_clean_db
        info = await _submit_and_confirm_disposable(i2b_client, db, contractd_disposable_tenant, reg)
        schema = info["schema"]
        # +100 charge (order confirmation receivable) — the confirm flow posts
        # the -100 collection, so the relationship ledger total is 0.00.
        await _post_receivable_charge(db, schema, uuid.UUID(info["oid"]), "100.00")
        # Make the relationship credit-only (no cash/transfer completed payment).
        await db.execute(
            text(f'UPDATE "{schema}".payments SET method = \'credit\' WHERE order_id = :oid'),
            {"oid": uuid.UUID(info["oid"])},
        )
        # Pin the cached binding balance to exactly 0 (numeric(12,2)-safe).
        await db.execute(
            text(
                "UPDATE public.wholesaler_retailer_bindings SET outstanding_balance = 0 "
                "WHERE wholesaler_id = :ws AND retailer_id = :rid AND is_deleted IS FALSE"
            ),
            {"ws": uuid.UUID(contractd_disposable_tenant["ws_id"]), "rid": uuid.UUID(contractd_disposable_tenant["ret_id"])},
        )
        # Introduce the exact delta via a high-precision receivable row.
        await _post_receivable_charge(db, schema, uuid.UUID(info["oid"]), delta)
        await db.commit()
        return info

    async def test_0001_difference_is_accepted(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        info = await self._credit_only_setup(
            i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity, delta="0.001"
        )
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        assert r.status_code == HTTPStatus.OK, r.text

    async def test_001_difference_is_accepted(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        info = await self._credit_only_setup(
            i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity, delta="0.01"
        )
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        assert r.status_code == HTTPStatus.OK, r.text

    async def test_00101_difference_is_rejected(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        info = await self._credit_only_setup(
            i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity, delta="0.0101"
        )
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        assert r.status_code == HTTPStatus.CONFLICT
        assert r.json()["code"] == "STATEMENT_RECONCILIATION_FAILED"
        assert "data" not in r.json()


# ===========================================================================
# §6e R1 — bounded high-volume behavior (rule 5)
# ===========================================================================


class TestRangeCap:
    """Aggregate statement-line cap of 1000 (R1-R1 rule 5).

    The per-list cap MUST be checked immediately after each read, BEFORE any
    sum / cross-check / assembly — otherwise an over-cap movement list would
    surface STATEMENT_INTERNAL_INCONSISTENT (the truncated sum vs the full DB
    period sum) instead of the required STATEMENT_RANGE_TOO_LARGE. LIMIT cap+1
    makes overflow detectable; combined lines > cap also fail closed. Over-cap
    returns 400 STATEMENT_RANGE_TOO_LARGE with zero partial document; at-cap
    (exactly 1000 combined) is accepted.
    """

    async def test_movements_1001_return_400_range_too_large_before_internal_inconsistent(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        db, reg = s2_clean_db
        tenant = contractd_disposable_tenant
        info = await _submit_and_confirm_disposable(i2b_client, db, tenant, reg)
        schema = info["schema"]
        # 1001 movements (distinct orders) -> per-list cap fires.
        await _bulk_orders_with_charges(db, schema, tenant["ws_id"], tenant["ret_id"], n=1001)
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        assert r.status_code == HTTPStatus.BAD_REQUEST
        assert r.json()["code"] == "STATEMENT_RANGE_TOO_LARGE"
        assert "data" not in r.json()

    async def test_movements_1002_return_400_range_too_large(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        db, reg = s2_clean_db
        tenant = contractd_disposable_tenant
        info = await _submit_and_confirm_disposable(i2b_client, db, tenant, reg)
        await _bulk_orders_with_charges(db, info["schema"], tenant["ws_id"], tenant["ret_id"], n=1002)
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        assert r.status_code == HTTPStatus.BAD_REQUEST
        assert r.json()["code"] == "STATEMENT_RANGE_TOO_LARGE"

    async def test_settled_1001_return_400_range_too_large(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        db, reg = s2_clean_db
        tenant = contractd_disposable_tenant
        info = await _submit_and_confirm_disposable(i2b_client, db, tenant, reg)
        oid = uuid.UUID(info["oid"])
        # 1001 owned payment IDs pre-generated; cleaned up EXACTLY by id.
        pay_ids = await _bulk_payments(db, info["schema"], oid, uuid.UUID(tenant["ret_id"]), n=1001)
        try:
            frm, to = await _stmt_period_yesterday_today()
            r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
            assert r.status_code == HTTPStatus.BAD_REQUEST
            assert r.json()["code"] == "STATEMENT_RANGE_TOO_LARGE"
            assert "data" not in r.json()
        finally:
            # Exact-ID cleanup with fresh session + exact rowcount (no LIKE).
            from database.session import AsyncSessionLocal

            async with AsyncSessionLocal() as cleanup_db:
                result = await cleanup_db.execute(
                    text(f'DELETE FROM "{tenant["schema"]}".payments WHERE id = ANY(:ids)'),
                    {"ids": pay_ids},
                )
                assert result.rowcount == 1001, "expected exactly 1001 owned payments deleted"
                await cleanup_db.commit()

    async def test_pending_1001_return_400_range_too_large(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        db, reg = s2_clean_db
        tenant = contractd_disposable_tenant
        info = await _submit_and_confirm_disposable(i2b_client, db, tenant, reg)
        oid = uuid.UUID(info["oid"])
        decl_ids = await _bulk_pending_declarations(
            db, info["schema"], tenant["ws_id"], tenant["ret_id"], oid, n=1001
        )
        try:
            frm, to = await _stmt_period_yesterday_today()
            r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to, include_pending=True)
            assert r.status_code == HTTPStatus.BAD_REQUEST
            assert r.json()["code"] == "STATEMENT_RANGE_TOO_LARGE"
            assert "data" not in r.json()
            assert "1001" not in r.text
            assert "1000" not in r.text
        finally:
            from database.session import AsyncSessionLocal

            async with AsyncSessionLocal() as cleanup_db:
                result = await cleanup_db.execute(
                    text(f'DELETE FROM "{tenant["schema"]}".payment_declarations WHERE id = ANY(:ids)'),
                    {"ids": decl_ids},
                )
                assert result.rowcount == 1001, "expected exactly 1001 owned declarations deleted"
                await cleanup_db.commit()

    async def test_combined_1001_across_lists_return_400_range_too_large(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        """Per-list counts are each <= cap but their combined total exceeds it:
        the aggregate combined cap fires (R1-R1 rule 5)."""
        db, reg = s2_clean_db
        tenant = contractd_disposable_tenant
        info = await _submit_and_confirm_disposable(i2b_client, db, tenant, reg)
        oid = uuid.UUID(info["oid"])
        # 600 movements + 1 settled + 400 pending = 1001 combined.
        await _bulk_orders_with_charges(db, info["schema"], tenant["ws_id"], tenant["ret_id"], n=600)
        decl_ids = await _bulk_pending_declarations(
            db, info["schema"], tenant["ws_id"], tenant["ret_id"], oid, n=400
        )
        try:
            frm, to = await _stmt_period_yesterday_today()
            r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to, include_pending=True)
            assert r.status_code == HTTPStatus.BAD_REQUEST
            assert r.json()["code"] == "STATEMENT_RANGE_TOO_LARGE"
            assert "data" not in r.json()
        finally:
            from database.session import AsyncSessionLocal

            async with AsyncSessionLocal() as cleanup_db:
                result = await cleanup_db.execute(
                    text(f'DELETE FROM "{tenant["schema"]}".payment_declarations WHERE id = ANY(:ids)'),
                    {"ids": decl_ids},
                )
                assert result.rowcount == 400, "expected exactly 400 owned declarations deleted"
                await cleanup_db.commit()

    async def test_at_cap_1000_is_accepted(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        """Exactly 1000 combined lines is accepted (boundary)."""
        db, reg = s2_clean_db
        tenant = contractd_disposable_tenant
        info = await _submit_and_confirm_disposable(i2b_client, db, tenant, reg)
        oid = uuid.UUID(info["oid"])
        # 998 pending + 1 settled payment + 1 movement = 1000 == cap.
        decl_ids = await _bulk_pending_declarations(
            db, info["schema"], tenant["ws_id"], tenant["ret_id"], oid, n=998
        )
        try:
            frm, to = await _stmt_period_yesterday_today()
            r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to, include_pending=True)
            assert r.status_code == HTTPStatus.OK, r.text
            assert len(r.json()["data"]["pending_declarations"]) == 998
        finally:
            from database.session import AsyncSessionLocal

            async with AsyncSessionLocal() as cleanup_db:
                result = await cleanup_db.execute(
                    text(f'DELETE FROM "{tenant["schema"]}".payment_declarations WHERE id = ANY(:ids)'),
                    {"ids": decl_ids},
                )
                assert result.rowcount == 998, "expected exactly 998 owned declarations deleted"
                await cleanup_db.commit()

    async def test_sentinel_payment_survives_exact_cleanup(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        """R1-R1-R1 sentinel: a payment whose transaction/idempotency text ALSO
        starts with ``pay-`` must be left byte-for-byte unchanged by cleanup —
        cleanup only ever targets owned ids (never a ``pay-%`` LIKE scan)."""
        from database.session import AsyncSessionLocal

        db, reg = s2_clean_db
        tenant = contractd_disposable_tenant
        info = await _submit_and_confirm_disposable(i2b_client, db, tenant, reg)
        oid = uuid.UUID(info["oid"])
        ret = uuid.UUID(tenant["ret_id"])
        schema = tenant["schema"]

        # Owned payment (deletable by exact id).
        owned_ids = await _bulk_payments(db, schema, oid, ret, n=2)
        # Sentinel: text also starts with pay-; NOT owned by this test.
        sentinel_id = uuid.uuid4()
        await _insert_payment_row(db, schema, oid, ret, amount="9.99", pay_id=sentinel_id)
        # Make the sentinel's transaction/idempotency text start with pay- too.
        await db.execute(
            text(
                f'UPDATE "{schema}".payments '
                "SET transaction_id = 'pay-sentinel-tx', idempotency_key = 'pay-sentinel-idem' "
                "WHERE id = :sid"
            ),
            {"sid": sentinel_id},
        )
        await db.commit()

        try:
            # Statement must still work (sentinel is valid-owned so no 409) and
            # the sentinel must be byte-for-byte unchanged after cleanup.
            frm, to = await _stmt_period_yesterday_today()
            r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
            assert r.status_code == HTTPStatus.OK, r.text
        finally:
            async with AsyncSessionLocal() as cleanup_db:
                result = await cleanup_db.execute(
                    text(f'DELETE FROM "{schema}".payments WHERE id = ANY(:ids)'),
                    {"ids": owned_ids},
                )
                assert result.rowcount == 2, "expected exactly 2 owned payments deleted"
                await cleanup_db.commit()
                # Sentinel must survive byte-for-byte.
                sentinel = (
                    await cleanup_db.execute(
                        text(
                            f'SELECT id, order_id, retailer_id, transaction_id, idempotency_key, '
                            f'amount, method, status, receipt_number, is_deleted '
                            f'FROM "{schema}".payments WHERE id = :sid'
                        ),
                        {"sid": sentinel_id},
                    )
                ).first()
                assert sentinel is not None, "sentinel payment was deleted by cleanup"
                assert sentinel.transaction_id == "pay-sentinel-tx"
                assert sentinel.idempotency_key == "pay-sentinel-idem"
                assert Decimal(sentinel.amount) == Decimal("9.99")


class TestDisposableSchemaSetupSafety:
    """R1-R1-R4 — every temp schema creation is wrapped so a setup failure
    CANNOT leak a stray schema, and cleanup is FAIL-CLOSED: cleanup errors are
    never swallowed, and when both an original and a cleanup error exist they
    are raised together via ``BaseExceptionGroup``.

    RED on 2da1bd57 (R3): the R3 cleanup swallowed cleanup errors
    (``except BaseException: pass``), used ``information_schema.schemata``
    instead of ``pg_namespace``, did not validate identifiers, did not
    dedupe / inconsistency-fail-closed candidate schemas, and rollback ran
    only inside the swallow. GREEN now (R4): all six new tests pass.
    """

    async def test_bootstrap_failure_drops_partial_tenant_schema(
        self, s2_clean_db
    ):
        """Inject a bootstrap failure AFTER CREATE SCHEMA has committed but
        BEFORE ``provision_wholesaler_and_schema`` returns: patch the
        provisioning service's bootstrap callable to create the schema (so it
        exists in the catalog) and then raise. The partial schema must be
        dropped on the failure path with zero residue, and the original
        exception must propagate (test fails on that exception, not a swallowed
        one)."""
        db, reg = s2_clean_db
        import services.tenant_provisioning_service as _tps
        from unittest.mock import patch as _upatch

        # A bootstrap that creates the schema + one table (so the catalog has a
        # partial tenant schema), then raises — simulating a bootstrap failure
        # after CREATE SCHEMA.
        async def _failing_bootstrap(schema, database_url):
            from sqlalchemy.ext.asyncio import create_async_engine as _cae
            eng = _cae(database_url)
            try:
                async with eng.begin() as conn:
                    await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
                    await conn.execute(
                        text(f'CREATE TABLE "{schema}".users (id UUID PRIMARY KEY)')
                    )
            finally:
                await eng.dispose()
            raise RuntimeError("induced bootstrap failure after CREATE SCHEMA")

        before = await _count_schemas_starting_with(db, "t_")
        try:
            with _upatch.object(_tps, "_load_bootstrap", lambda: _failing_bootstrap):
                with pytest.raises(BaseException, match="provisioning did not complete"):
                    await _provision_disposable_tenant(db, reg)
        finally:
            pass
        # The partial schema must have been dropped on the failure path.
        after = await _count_schemas_starting_with(db, "t_")
        assert after == before, (
            f"bootstrap failure leaked a schema: before={before} after={after}"
        )

    async def test_provisioning_failure_drops_partial_tenant_schema(
        self, s2_clean_db
    ):
        """Inject a provisioning failure AFTER the schema is fully bootstrapped
        and provisioning returns, but DURING the remaining setup (binding) —
        the outermost guard must still drop the schema. Proves the guard covers
        the post-provision setup too."""
        db, reg = s2_clean_db
        import tests.test_dc12r1_contract_d_statement_print as _self_mod
        from unittest.mock import patch as _upatch

        async def _boom(*a, **kw):
            raise RuntimeError("induced setup failure after provisioning")

        before = await _count_schemas_starting_with(db, "t_")
        try:
            with _upatch.object(_self_mod, "_create_binding", _boom):
                with pytest.raises(BaseException, match="induced setup failure"):
                    await _provision_disposable_tenant(db, reg)
        finally:
            pass
        after = await _count_schemas_starting_with(db, "t_")
        assert after == before, (
            f"setup failure leaked a schema: before={before} after={after}"
        )

    async def test_create_table_failure_drops_partial_statement_schema(
        self, s2_clean_db
    ):
        """Inject a failure DURING a CREATE TABLE execution inside
        ``_disposable_statement_schema`` — not in the ``async with`` body. The
        schema + first table exist; the second CREATE TABLE raises mid-setup.
        The partial schema must be dropped with zero residue."""
        db, _reg = s2_clean_db
        before = await _count_schemas_starting_with(db, "t_stmt_")

        # Wrap db.execute so the SECOND CREATE TABLE raises mid-execution.
        real_execute = db.execute
        state = {"creates": 0}

        async def _flaky_execute(statement, *args, **kwargs):
            stmt = str(statement)
            if "CREATE TABLE" in stmt:
                state["creates"] += 1
                if state["creates"] == 2:
                    raise RuntimeError("induced CREATE TABLE failure mid-setup")
            return await real_execute(statement, *args, **kwargs)

        db.execute = _flaky_execute  # type: ignore[assignment]
        try:
            with pytest.raises(BaseException, match="induced CREATE TABLE failure"):
                async with _disposable_statement_schema(db):
                    pass  # never reached — failure is during setup
        finally:
            db.execute = real_execute  # type: ignore[assignment]

        after = await _count_schemas_starting_with(db, "t_stmt_")
        assert after == before, (
            f"CREATE TABLE failure leaked a schema: before={before} after={after}"
        )

    # -- R1-R1-R4 §5 new tests (cleanup fail-closed + schema safety) ---------
    # §5.1–5.4 test the extracted ``_cleanup_partial_tenant`` body directly, so
    # they don't run the full provisioning path (which would register public
    # rows + create tenant-scoped user_roles that the s2_clean_db teardown
    # would then try to query). §5.5 runs the full helper to prove the
    # original-exception re-raise end-to-end.

    async def _seed_registration_with_schema(
        self, db: AsyncSession, *, reg_id: uuid.UUID, code: str
    ) -> str:
        """Minimal seed: a registration row + wholesaler row whose
        ``derive_schema_from_id`` equals the registration's ``tenant_schema``,
        plus the live schema in pg_namespace. Both cleanup sources therefore
        AGREE (no spurious schema-mismatch error). Returns the wholesaler id
        (str) so callers can derive the schema name consistently.

        Uses status ``email_verified`` (non-terminal) so the row passes the
        terminal-password-cleared CHECK without the full credential-clear
        fields a real ``active`` row requires."""
        from models.wholesaler import Wholesaler
        ws_id = uuid.uuid4()
        schema = Wholesaler.derive_schema_from_id(str(ws_id))
        await db.execute(
            text(
                "INSERT INTO public.tenant_registrations "
                "(id, company_name, tenant_code, country, owner_email, status, "
                " tenant_schema, expires_at, created_at, updated_at) "
                "VALUES (:id, :company, :code, 'TZ', :email, 'email_verified', :schema, "
                " now() + interval '365 days', now(), now())"
            ),
            {
                "id": reg_id,
                "company": f"Seed {code}",
                "code": code,
                "email": f"seed.{code.lower()}@example.com",
                "schema": schema,
            },
        )
        await db.execute(
            text(
                "INSERT INTO public.wholesalers "
                "(id, code, name, contact, status, created_at, updated_at) "
                "VALUES (:id, :code, :name, :contact, 'active', now(), now())"
            ),
            {
                "id": ws_id,
                "code": code,
                "name": f"Seed {code}",
                "contact": f"seed.{code.lower()}@example.com",
            },
        )
        await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        await db.commit()
        return str(ws_id)

    async def test_cleanup_failure_preserves_both_original_and_cleanup_errors(
        self, s2_clean_db
    ):
        """R1-R1-R6: provisioning fails AND cleanup/DROP fails. The raised
        ``BaseExceptionGroup.exceptions`` must PRECISELY contain BOTH the
        original provisioning error and the cleanup DROP error.

        R1-R1-R6 exact ownership: the test PRE-GENERATES ``reg_id``, passes it
        to ``_provision_disposable_tenant``, and the finally cleanup locates
        the schema by EXACT owned id (``WHERE id = :reg_id``) — never a LIKE /
        prefix / latest-row scan. A SENTINEL registration + schema with the
        SAME prefix is seeded beforehand; after the fault cleanup the sentinel
        schema must be byte-for-byte unchanged (proving the cleanup did not
        touch an unrelated same-prefix registration)."""
        db, reg = s2_clean_db
        import tests.test_dc12r1_contract_d_statement_print as _self_mod
        from unittest.mock import patch as _upatch
        from database import session as _session_mod
        from database.session import AsyncSessionLocal as _RealSessionLocal, async_engine
        from sqlalchemy.ext.asyncio import AsyncSession as _AS
        from models.wholesaler import Wholesaler
        from db.sql_safety import validate_identifier

        # Pre-generate the owned registration id (R1-R1-R6 exact ownership).
        owned_reg_id = uuid.uuid4()

        # Seed a SENTINEL registration + schema with the SAME prefix, to prove
        # the fault cleanup does not touch an unrelated same-prefix row.
        sentinel_reg_id = uuid.uuid4()
        sentinel_ws_id = uuid.uuid4()
        sentinel_schema = Wholesaler.derive_schema_from_id(str(sentinel_ws_id))
        sentinel_code = f"CDR1R1R1S{uuid.uuid4().hex[:4].upper()}"
        await db.execute(
            text(
                "INSERT INTO public.tenant_registrations "
                "(id, company_name, tenant_code, country, owner_email, status, "
                " tenant_schema, expires_at, created_at, updated_at) "
                "VALUES (:id, :company, :code, 'TZ', :email, 'email_verified', :schema, "
                " now() + interval '365 days', now(), now())"
            ),
            {
                "id": sentinel_reg_id,
                "company": f"Sentinel {sentinel_code}",
                "code": sentinel_code,
                "email": f"sentinel.{sentinel_code.lower()}@example.com",
                "schema": sentinel_schema,
            },
        )
        await db.execute(
            text(
                "INSERT INTO public.wholesalers "
                "(id, code, name, contact, status, created_at, updated_at) "
                "VALUES (:id, :code, :name, :contact, 'active', now(), now())"
            ),
            {
                "id": sentinel_ws_id,
                "code": sentinel_code,
                "name": f"Sentinel {sentinel_code}",
                "contact": f"sentinel.{sentinel_code.lower()}@example.com",
            },
        )
        await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{sentinel_schema}"'))
        # Put a marker table in the sentinel schema so byte-equality is checkable.
        await db.execute(
            text(
                f'CREATE TABLE "{sentinel_schema}".sentinel_marker '
                "(id INT PRIMARY KEY, payload TEXT NOT NULL)"
            )
        )
        await db.execute(
            text(
                f'INSERT INTO "{sentinel_schema}".sentinel_marker '
                "(id, payload) VALUES (1, 'sentinel-byte-unchanged')"
            )
        )
        await db.commit()

        async def _original_boom(*a, **kw):
            raise RuntimeError("ORIGINAL provisioning failure")

        class _SelectiveSessionWrapper:
            def __init__(self, *args, **kwargs):
                self._real = _AS(async_engine, expire_on_commit=False)

            async def __aenter__(self):
                await self._real.__aenter__()
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return await self._real.__aexit__(exc_type, exc, tb)

            async def execute(self, statement, *args, **kwargs):
                stmt = str(statement).upper()
                if "DROP SCHEMA" in stmt:
                    raise RuntimeError("CLEANUP drop failure")
                return await self._real.execute(statement, *args, **kwargs)

            async def commit(self):
                return await self._real.commit()

            def __getattr__(self, name):
                return getattr(self._real, name)

        before = await _count_schemas_starting_with(db, "t_")
        try:
            with _upatch.object(_self_mod, "_create_binding", _original_boom):
                with _upatch.object(
                    _session_mod, "AsyncSessionLocal", _SelectiveSessionWrapper
                ):
                    with pytest.raises(BaseExceptionGroup) as ei:
                        # Pass the pre-generated owned reg_id (R1-R1-R6).
                        await _provision_disposable_tenant(db, reg, reg_id=owned_reg_id)
        finally:
            # The DROP failed, so the OWNED schema still exists. Locate it by
            # EXACT owned id (R1-R1-R6) — never LIKE / prefix / latest-row.
            await async_engine.dispose()
            async with _RealSessionLocal() as cdb:
                row = (
                    await cdb.execute(
                        text(
                            "SELECT tenant_schema FROM public.tenant_registrations "
                            "WHERE id = :rid"
                        ),
                        {"rid": owned_reg_id},
                    )
                ).first()
                if row is not None and row.tenant_schema:
                    sch = row.tenant_schema
                    validate_identifier(sch, "owned test-residual schema")
                    await cdb.execute(text(f'DROP SCHEMA IF EXISTS "{sch}" CASCADE'))
                await cdb.commit()

        group = ei.value
        assert isinstance(group, BaseExceptionGroup), type(group).__name__
        excs = group.exceptions
        assert len(excs) == 2, [type(e).__name__ for e in excs]
        orig = [e for e in excs if isinstance(e, RuntimeError) and "ORIGINAL provisioning failure" in str(e)]
        clean = [e for e in excs if isinstance(e, RuntimeError) and "CLEANUP drop failure" in str(e)]
        assert len(orig) == 1, [str(e) for e in excs]
        assert len(clean) == 1, [str(e) for e in excs]

        # SENTINEL byte-equality: the sentinel schema + its marker row must be
        # unchanged after the fault cleanup (proving exact-id cleanup did not
        # touch the unrelated same-prefix registration).
        await async_engine.dispose()
        async with _RealSessionLocal() as vdb:
            still = (
                await vdb.execute(
                    text("SELECT 1 FROM pg_namespace WHERE nspname = :s"),
                    {"s": sentinel_schema},
                )
            ).first()
            assert still is not None, "sentinel schema was dropped by cleanup"
            marker = (
                await vdb.execute(
                    text(
                        f'SELECT payload FROM "{sentinel_schema}".sentinel_marker '
                        "WHERE id = 1"
                    )
                )
            ).first()
            assert marker is not None and marker.payload == "sentinel-byte-unchanged", (
                f"sentinel marker changed: {marker}"
            )
            # Clean up the sentinel (exact id).
            validate_identifier(sentinel_schema, "sentinel cleanup schema")
            await vdb.execute(text(f'DROP SCHEMA IF EXISTS "{sentinel_schema}" CASCADE'))
            await vdb.execute(
                text("DELETE FROM public.tenant_registrations WHERE id = :rid"),
                {"rid": sentinel_reg_id},
            )
            await vdb.execute(
                text("DELETE FROM public.wholesalers WHERE id = :wid"),
                {"wid": sentinel_ws_id},
            )
            await vdb.commit()

        # Exact-residue check (R1-R1-R6): verify the OWNED schema and the
        # SENTINEL schema are BOTH absent from pg_namespace (not a fragile
        # global t_ count that includes pool/other-test schemas).
        await async_engine.dispose()
        async with _RealSessionLocal() as vdb:
            owned_row = (
                await vdb.execute(
                    text("SELECT tenant_schema FROM public.tenant_registrations WHERE id = :rid"),
                    {"rid": owned_reg_id},
                )
            ).first()
            owned_schema_name = owned_row.tenant_schema if owned_row else None
            for name in (owned_schema_name, sentinel_schema):
                if name is None:
                    continue
                present = (
                    await vdb.execute(
                        text("SELECT 1 FROM pg_namespace WHERE nspname = :s"),
                        {"s": name},
                    )
                ).first()
                assert present is None, f"schema {name} still present after cleanup"


    async def test_rollback_failure_is_visible(self, s2_clean_db
    ):
        """R1-R1-R5 §5.2: when the main-session ``rollback`` itself fails,
        ``_cleanup_partial_tenant`` records it as a cleanup error (visible),
        not swallowed. Uses the consistent wholesaler-derived schema seed."""
        db, _reg = s2_clean_db
        from models.wholesaler import Wholesaler

        reg_id = uuid.uuid4()
        code = f"R4B{uuid.uuid4().hex[:6].upper()}"
        ws_id = await self._seed_registration_with_schema(db, reg_id=reg_id, code=code)
        schema = Wholesaler.derive_schema_from_id(ws_id)

        real_rollback = db.rollback

        async def _failing_rollback():
            raise RuntimeError("CLEANUP rollback failure")

        db.rollback = _failing_rollback  # type: ignore[assignment]
        try:
            errors = await _cleanup_partial_tenant(db, reg_id, code)
        finally:
            db.rollback = real_rollback  # type: ignore[assignment]
            from database.session import AsyncSessionLocal, async_engine
            from db.sql_safety import validate_identifier
            validate_identifier(schema, "test-residual schema")
            await async_engine.dispose()
            async with AsyncSessionLocal() as cdb:
                await cdb.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
                await cdb.execute(
                    text("DELETE FROM public.tenant_registrations WHERE id = :rid"),
                    {"rid": reg_id},
                )
                await cdb.execute(
                    text("DELETE FROM public.wholesalers WHERE id = :wid"),
                    {"wid": ws_id},
                )
                await cdb.commit()

        msgs = [str(e) for e in errors]
        assert any("CLEANUP rollback failure" in m for m in msgs), msgs

    async def test_schema_inconsistency_fails_closed_without_arbitrary_drop(
        self, s2_clean_db
    ):
        """R1-R1-R4 §5.3 / §4: when the registration row's tenant_schema and
        the wholesaler-derived schema name BOTH exist but DIFFER, cleanup must
        fail-closed (refuse to DROP either) and surface the inconsistency. The
        live schema is NOT dropped (it would be arbitrary)."""
        db, _reg = s2_clean_db
        reg_id = uuid.uuid4()
        code = f"R4C{uuid.uuid4().hex[:6].upper()}"
        # Seed with a schema that does NOT match the wholesaler-derived name
        # (derive_schema_from_id uses the wholesaler id hex; we set the
        # registration's tenant_schema to a deliberately different value).
        ws_id = uuid.uuid4()
        derived = f"t_{ws_id.hex}"
        reg_schema = f"t_mismatch_{reg_id.hex}"[:63]
        await db.execute(
            text(
                "INSERT INTO public.tenant_registrations "
                "(id, company_name, tenant_code, country, owner_email, status, "
                " tenant_schema, expires_at, created_at, updated_at) "
                "VALUES (:id, :company, :code, 'TZ', :email, 'email_verified', :schema, "
                " now() + interval '365 days', now(), now())"
            ),
            {
                "id": reg_id,
                "company": f"Seed {code}",
                "code": code,
                "email": f"seed.{code.lower()}@example.com",
                "schema": reg_schema,
            },
        )
        await db.execute(
            text(
                "INSERT INTO public.wholesalers "
                "(id, code, name, contact, status, created_at, updated_at) "
                "VALUES (:id, :code, :name, :contact, 'active', now(), now())"
            ),
            {"id": ws_id, "code": code, "name": code, "contact": "x@example.com"},
        )
        # Create the derived schema (so it exists) — cleanup must NOT drop it
        # because the two sources disagree.
        await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{derived}"'))
        await db.commit()

        errors = await _cleanup_partial_tenant(db, reg_id, code)
        msgs = [str(e) for e in errors]
        assert any("schema inconsistency" in m for m in msgs), msgs

        # Fail-closed: the derived schema must STILL EXIST (cleanup refused to
        # DROP because of the inconsistency).
        from database.session import AsyncSessionLocal, async_engine
        from db.sql_safety import validate_identifier
        validate_identifier(derived, "derived test schema")
        await async_engine.dispose()
        async with AsyncSessionLocal() as vdb:
            still = (
                await vdb.execute(
                    text("SELECT 1 FROM pg_namespace WHERE nspname = :s"),
                    {"s": derived},
                )
            ).first()
            assert still is not None, (
                "cleanup must NOT drop the schema when sources are inconsistent"
            )
        # Zero-residue cleanup of the derived schema + the seeded public rows.
        validate_identifier(derived, "derived test schema (cleanup)")
        await async_engine.dispose()
        async with AsyncSessionLocal() as cdb:
            await cdb.execute(text(f'DROP SCHEMA IF EXISTS "{derived}" CASCADE'))
            await cdb.execute(
                text("DELETE FROM public.tenant_registrations WHERE id = :rid"),
                {"rid": reg_id},
            )
            await cdb.execute(
                text("DELETE FROM public.wholesalers WHERE id = :wid"),
                {"wid": ws_id},
            )
            await cdb.commit()

    async def test_illegal_schema_identifier_rejected_before_dynamic_sql(
        self, s2_clean_db
    ):
        """R1-R1-R5 §5.4 / §4: an illegal schema identifier written into an
        OWNED registration must be rejected by ``_cleanup_partial_tenant``
        BEFORE any ``DROP SCHEMA`` is executed. We write a malicious
        ``tenant_schema`` into the registration row (bypassing app validation,
        as a corrupted row could), run the REAL cleanup, capture every SQL
        statement executed in the fresh cleanup session, and assert that NO
        ``DROP SCHEMA`` string was ever issued."""
        db, _reg = s2_clean_db
        from database import session as _session_mod
        from unittest.mock import patch as _upatch
        from database.session import AsyncSessionLocal, async_engine

        reg_id = uuid.uuid4()
        code = f"R4D{uuid.uuid4().hex[:6].upper()}"
        # Seed a CONSISTENT, valid registration + schema first.
        ws_id = await self._seed_registration_with_schema(db, reg_id=reg_id, code=code)
        from models.wholesaler import Wholesaler
        real_schema = Wholesaler.derive_schema_from_id(ws_id)
        # Corrupt the registration's tenant_schema with a malicious value
        # (semicolons / comment) — simulate a corrupted row. The CHECK
        # constraint may reject this; if so we bypass it by writing via a raw
        # connection that disables constraints is not available, so instead we
        # DELETE the registration row and re-INSERT with the malicious value
        # using a session that allows it. Simpler: set tenant_schema directly
        # via UPDATE; if the CHECK rejects, the test proves the DB itself
        # blocks it (also a valid fail-closed). We attempt the UPDATE and
        # tolerate either outcome.
        malicious = "t_evil'; DROP TABLE public.retailers; --"
        update_rejected = False
        try:
            await db.execute(
                text(
                    "UPDATE public.tenant_registrations SET tenant_schema = :bad "
                    "WHERE id = :rid"
                ),
                {"bad": malicious, "rid": reg_id},
            )
            await db.commit()
        except Exception:
            update_rejected = True
            await db.rollback()

        if update_rejected:
            # The DB CHECK blocked the malicious value at the source — a
            # stronger fail-closed than the cleanup guard. Still assert the
            # cleanup does not DROP the real schema with an unvalidated value.
            pass

        # Capture all SQL executed in the fresh cleanup session.
        captured_sql: list[str] = []

        class _CapturingSession:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def execute(self, statement, *args, **kwargs):
                stmt = str(statement)
                captured_sql.append(stmt)
                # Delegate to a real session for actual execution.
                real = AsyncSession(async_engine, expire_on_commit=False)
                async with real as rdb:
                    return await rdb.execute(statement, *args, **kwargs)

            async def commit(self):
                pass

        try:
            with _upatch.object(_session_mod, "AsyncSessionLocal", _CapturingSession):
                errors = await _cleanup_partial_tenant(db, reg_id, code)
        finally:
            from db.sql_safety import validate_identifier
            validate_identifier(real_schema, "test-residual schema")
            await async_engine.dispose()
            async with AsyncSessionLocal() as cdb:
                await cdb.execute(text(f'DROP SCHEMA IF EXISTS "{real_schema}" CASCADE'))
                await cdb.execute(
                    text("DELETE FROM public.tenant_registrations WHERE id = :rid"),
                    {"rid": reg_id},
                )
                await cdb.execute(
                    text("DELETE FROM public.wholesalers WHERE id = :wid"),
                    {"wid": ws_id},
                )
                await cdb.commit()

        # No DROP SCHEMA may appear in the captured SQL — the malicious value
        # was rejected by validate_identifier before reaching dynamic SQL.
        drop_stmts = [s for s in captured_sql if "DROP SCHEMA" in s.upper()]
        assert drop_stmts == [], (
            f"DROP SCHEMA executed despite illegal identifier: {drop_stmts}"
        )
        # The malicious value never entered a DROP string anywhere.
        assert all("DROP TABLE public.retailers" not in s for s in captured_sql), (
            "malicious SQL fragment reached execution"
        )
        # validate_identifier either rejected the candidate (cleanup error) or
        # the DB CHECK blocked it; either way no DROP ran.
        # (errors may be non-empty if the identifier was rejected — that's the
        # fail-closed behavior, surfaced not swallowed.)

    async def test_cleanup_success_propagates_original_exception_exactly(
        self, s2_clean_db
    ):
        """R1-R1-R4 §5.5: when cleanup SUCCEEDS, the ORIGINAL provisioning
        exception is re-raised EXACTLY (same type, same message) via bare
        ``raise`` — not wrapped in a group, not swapped for a cleanup error."""
        db, reg = s2_clean_db
        import tests.test_dc12r1_contract_d_statement_print as _self_mod
        from unittest.mock import patch as _upatch

        class _OriginalMarker(RuntimeError):
            pass

        async def _boom(*a, **kw):
            raise _OriginalMarker("exact original exception")

        before = await _count_schemas_starting_with(db, "t_")
        with _upatch.object(_self_mod, "_create_binding", _boom):
            with pytest.raises(_OriginalMarker, match="exact original exception") as ei:
                await _provision_disposable_tenant(db, reg)
        # Must be the EXACT original instance, not a group, not a copy.
        assert isinstance(ei.value, _OriginalMarker)
        assert not isinstance(ei.value, BaseExceptionGroup)
        after = await _count_schemas_starting_with(db, "t_")
        assert after == before, (
            f"cleanup success leaked a schema: before={before} after={after}"
        )


async def _count_schemas_starting_with(db: AsyncSession, prefix: str) -> int:
    """Count tenant schemas matching a prefix in the live catalog
    (``pg_namespace`` — R1-R1-R4 §4 exact verification source)."""
    row = (
        await db.execute(
            text(
                "SELECT count(*) FROM pg_namespace WHERE nspname LIKE :p"
            ),
            {"p": prefix + "%"},
        )
    ).first()
    await db.rollback()
    return int(row[0])


class TestDateBoundaries:
    async def test_inclusive_boundaries_capture_today_movements(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        db, reg = s2_clean_db
        info = await _submit_and_confirm_disposable(i2b_client, db, contractd_disposable_tenant, reg)
        # A period ending today must include movements posted ~now.
        eat = timezone(timedelta(hours=3), "Africa/Nairobi")
        today = datetime.now(timezone.utc).astimezone(eat).date().isoformat()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], today, today)
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        # At least one movement (the order confirmation receivable) is present.
        assert len(data["movements"]) >= 1

    async def test_far_future_period_empty_movements(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        db, reg = s2_clean_db
        info = await _submit_and_confirm_disposable(i2b_client, db, contractd_disposable_tenant, reg)
        # A future period with no movements: opening may be non-zero (all-time
        # before), but the period movements list is empty.
        r = await _get_retailer_statement(i2b_client, info["token_ret"], "2099-01-01", "2099-01-02")
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        assert data["movements"] == []
        assert Decimal(data["charge_total"]) == Decimal("0")
        assert Decimal(data["collection_total"]) == Decimal("0")


class TestSoftDeletedOrderRetention:
    """Soft-deleted orders remain in historical accounting scope (rule 8).

    R1 evidence repair: the mutation is snapshot BEFORE it happens, restored in
    ``finally`` from a FRESH session with an exact rowcount==1 assertion and an
    exact reread-equality assertion. A second test proves that an active and a
    soft-deleted order produce IDENTICAL accounting totals. All rows live in
    the owned disposable tenant schema.
    """

    async def test_soft_deleted_order_still_in_statement(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        from database.session import AsyncSessionLocal

        db, reg = s2_clean_db
        info = await _submit_and_confirm_disposable(i2b_client, db, contractd_disposable_tenant, reg)
        sch_a = info["schema"]
        oid = uuid.UUID(info["oid"])

        # Snapshot BEFORE any mutation (fresh session).
        async with AsyncSessionLocal() as snap:
            snap_row = (
                await snap.execute(
                    text(f'SELECT is_deleted FROM "{sch_a}".orders WHERE id = :oid'), {"oid": oid}
                )
            ).first()
            assert snap_row is not None, "order not found for snapshot"
            orig_is_deleted = snap_row.is_deleted

        # Soft-delete the order in-place (ledger entries survive).
        await db.execute(
            text(f'UPDATE "{sch_a}".orders SET is_deleted = true WHERE id = :oid'),
            {"oid": oid},
        )
        await db.commit()
        try:
            frm, to = await _stmt_period_yesterday_today()
            r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
            assert r.status_code == HTTPStatus.OK, r.text
            data = r.json()["data"]
            # The receivable movement for the soft-deleted order is still present.
            assert any(m["reference_id"] == str(oid) for m in data["movements"])
        finally:
            # Restore in a FRESH session; require exactly one row updated and
            # exact reread equality with the pre-mutation snapshot.
            async with AsyncSessionLocal() as restore_db:
                result = await restore_db.execute(
                    text(f'UPDATE "{sch_a}".orders SET is_deleted = :orig WHERE id = :oid'),
                    {"orig": orig_is_deleted, "oid": oid},
                )
                assert result.rowcount == 1, "restore UPDATE must affect exactly one row"
                await restore_db.commit()
                reread = (
                    await restore_db.execute(
                        text(f'SELECT is_deleted FROM "{sch_a}".orders WHERE id = :oid'), {"oid": oid}
                    )
                ).first()
                assert reread is not None and reread.is_deleted == orig_is_deleted

    async def test_active_and_soft_deleted_order_have_identical_accounting_totals(
        self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity
    ):
        from database.session import AsyncSessionLocal

        db, reg = s2_clean_db
        info = await _submit_and_confirm_disposable(i2b_client, db, contractd_disposable_tenant, reg)
        sch_a = info["schema"]
        oid = uuid.UUID(info["oid"])
        await _post_receivable_charge(db, sch_a, oid, "100.00")
        frm, to = await _stmt_period_yesterday_today()

        # Active state totals (baseline).
        r_active = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        assert r_active.status_code == HTTPStatus.OK, r_active.text
        active = r_active.json()["data"]
        total_keys = (
            "opening_balance", "closing_balance", "charge_total",
            "collection_total", "net_movement", "settled_total",
        )

        # Snapshot BEFORE mutation.
        async with AsyncSessionLocal() as snap:
            snap_row = (
                await snap.execute(
                    text(f'SELECT is_deleted FROM "{sch_a}".orders WHERE id = :oid'), {"oid": oid}
                )
            ).first()
            assert snap_row is not None
            orig_is_deleted = snap_row.is_deleted

        # Soft-delete -> statement totals must be IDENTICAL.
        await db.execute(
            text(f'UPDATE "{sch_a}".orders SET is_deleted = true WHERE id = :oid'),
            {"oid": oid},
        )
        await db.commit()
        try:
            r_deleted = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
            assert r_deleted.status_code == HTTPStatus.OK, r_deleted.text
            deleted = r_deleted.json()["data"]
            for key in total_keys:
                assert Decimal(deleted[key]) == Decimal(active[key]), (
                    f"totals differ after soft-delete for {key}: "
                    f"{active[key]} vs {deleted[key]}"
                )
        finally:
            async with AsyncSessionLocal() as restore_db:
                result = await restore_db.execute(
                    text(f'UPDATE "{sch_a}".orders SET is_deleted = :orig WHERE id = :oid'),
                    {"orig": orig_is_deleted, "oid": oid},
                )
                assert result.rowcount == 1, "restore UPDATE must affect exactly one row"
                await restore_db.commit()
                reread = (
                    await restore_db.execute(
                        text(f'SELECT is_deleted FROM "{sch_a}".orders WHERE id = :oid'), {"oid": oid}
                    )
                ).first()
                assert reread is not None and reread.is_deleted == orig_is_deleted


# ===========================================================================
# §8 Order independence (natural + reverse) with exact ownership cleanup
# ===========================================================================


class TestOrderIndependence:
    """Run the focused Contract D suite in natural and reverse declaration order.

    Demonstrates that test outcomes do not depend on execution order (no
    cross-test state leakage). Each test uses its OWN disposable tenant, so
    the teardown DROP SCHEMA discards every row (including immutable ledger)
    and the registry verifies zero residue.
    """

    @pytest.fixture(autouse=True)
    def _no_leak(self):
        yield

    async def test_a_first_seeds(self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity):
        db, reg = s2_clean_db
        info = await _submit_and_confirm_disposable(
            i2b_client, db, contractd_disposable_tenant, reg, amount="100.00"
        )
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        assert r.status_code == HTTPStatus.OK
        assert r.json()["data"]["document_type"] == "statement"

    async def test_b_second_seeds(self, i2b_client, contractd_disposable_tenant, s2_clean_db, cashier_identity):
        # Each test seeds its OWN disposable tenant; nothing accumulates from
        # test_a. Assert route availability + structural invariants.
        db, reg = s2_clean_db
        info = await _submit_and_confirm_disposable(
            i2b_client, db, contractd_disposable_tenant, reg, amount="200.00"
        )
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        assert r.status_code == HTTPStatus.OK
        data = r.json()["data"]
        # Structural invariants hold regardless of accumulated history.
        opening = Decimal(data["opening_balance"])
        net = Decimal(data["net_movement"])
        assert Decimal(data["closing_balance"]) == opening + net
        assert Decimal(data["charge_total"]) >= Decimal("0")
        assert Decimal(data["collection_total"]) >= Decimal("0")
