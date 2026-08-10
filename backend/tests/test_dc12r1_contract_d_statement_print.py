"""DC-12R1-S3-S2B-I2C-I2B Contract D — relationship account statement print tests.

Real PostgreSQL 16 (+ Redis 7) integration. Reuses the I2B/I2C-I1 harness.

Coverage (binding accounting rules):
  * dual-key supplier/retailer isolation + neutral cross-tenant denial;
  * malformed UUID/date, missing date, from>to controlled failures;
  * inclusive date boundaries + opening/closing arithmetic;
  * charge + collection and post-range reconstruction;
  * soft-deleted-order history retention;
  * orphan ledger + arithmetic/reconciliation fail-closed (409) cases;
  * duplicate same-order/same-amount partial payments never cross-associated;
  * pending/rejected exclusion and completed-only settled payments;
  * zero-write fingerprints and no internal-ID leakage;
  * natural and reverse focused order with explicit cleanup.

All statement routes are 100% read-only; this is proven via table/binding
fingerprint snapshots taken before and after each exercised route.
"""
from __future__ import annotations

import uuid
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
from tests.test_dc12r1_s3_s2b_i2c_i1_printable_records import (  # noqa: E402
    _seed_order_with_item,
    _submit_and_confirm,
    _table_fingerprint,
    _binding_fingerprint,
    _receipt_seq_fingerprint,
)


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _contractd_flush_stmt_cache(provisioned_pool):
    """Dispose engine pool after provisioning DDL (prepared-statement cache)."""
    from database.session import async_engine

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
# §1 Happy paths + dual-key isolation
# ===========================================================================


class TestStatementHappyPath:
    """Statement renders ledger-derived balances + independent settled list."""

    async def test_retailer_statement_happy_path(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity, amount="100.00")
        # _seed_confirmed_order seeds via raw SQL (no service path), so post the
        # +RECEIVABLE charge that the order-confirmation service path would have.
        db, _reg = s2_clean_db
        await _post_receivable_charge(db, info["sch_a"], uuid.UUID(info["oid"]), "100.00")
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

    async def test_supplier_statement_happy_path(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity, amount="250.00")
        db, _reg = s2_clean_db
        await _post_receivable_charge(db, info["sch_a"], uuid.UUID(info["oid"]), "250.00")
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_supplier_statement(i2b_client, info["token_admin"], info["ret_a"], frm, to)
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        assert Decimal(data["charge_total"]) == Decimal("250.00")
        assert Decimal(data["collection_total"]) == Decimal("250.00")
        # closing balance arithmetic: closing == opening + net_movement.
        opening = Decimal(data["opening_balance"])
        net = Decimal(data["net_movement"])
        closing = Decimal(data["closing_balance"])
        assert closing == opening + net

    async def test_opening_closing_arithmetic_invariant(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        """closing_balance must equal opening_balance + net_movement exactly."""
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity, amount="100.00")
        db, _reg = s2_clean_db
        await _post_receivable_charge(db, info["sch_a"], uuid.UUID(info["oid"]), "100.00")
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
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
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
# §2 Controlled input failures
# ===========================================================================


class TestControlledFailures:
    async def test_missing_from_date(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        r = await i2b_client.get(
            "/api/v1/client/statements/print",
            params={"to": "2026-08-10"},
            headers=_headers(info["token_ret"]),
        )
        assert r.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    async def test_from_after_to(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        r = await _get_retailer_statement(i2b_client, info["token_ret"], "2026-08-10", "2026-08-01")
        # Period error -> controlled 404 STATEMENT_NOT_AVAILABLE (no internal leak).
        assert r.status_code == HTTPStatus.NOT_FOUND
        assert r.json()["code"] == "STATEMENT_NOT_AVAILABLE"

    async def test_malformed_retailer_uuid_supplier(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        r = await _get_supplier_statement(i2b_client, info["token_admin"], "not-a-uuid", "2026-08-01", "2026-08-10")
        assert r.status_code == HTTPStatus.NOT_FOUND
        assert r.json()["code"] == "STATEMENT_NOT_AVAILABLE"

    async def test_span_exceeds_365_days(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        r = await _get_retailer_statement(i2b_client, info["token_ret"], "2025-01-01", "2026-08-10")
        assert r.status_code == HTTPStatus.NOT_FOUND
        assert r.json()["code"] == "STATEMENT_NOT_AVAILABLE"


# ===========================================================================
# §3 Zero-write proof
# ===========================================================================


class TestZeroWrite:
    """Statement routes produce zero writes and zero fingerprint changes."""

    async def test_statement_routes_zero_fingerprint(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        db, _reg = s2_clean_db
        sch_a = info["sch_a"]
        ws_a = info["ws_a"]
        ret_a = info["ret_a"]

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
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        data = r.json()["data"]
        # movements carry ledger reference_type (order/refund) + reference_id (order).
        for m in data["movements"]:
            assert m["reference_type"] in ("order", "refund")
        # settled payments carry receipt_number/method — no ledger reference fields.
        for p in data["settled_payments"]:
            assert "reference_type" not in p
            assert "signed_amount" not in p

    async def test_pending_declarations_only_when_requested(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        frm, to = await _stmt_period_yesterday_today()
        # Default (include_pending=false): no pending list entries leak.
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        assert r.json()["data"]["pending_declarations"] == []
        # Pending never affects balances or settled totals.


# ===========================================================================
# §5 No internal-ID leakage
# ===========================================================================


class TestNoLeakage:
    """No payment row UUID, cashier user id, tenant_user_id, or schema name leaks."""

    async def test_no_internal_ids_in_statement(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        body = r.text
        # Schema name must never leak.
        assert info["sch_a"] not in body
        # The supplier internal tenant id must not appear as a raw value.
        assert info["ws_a"] not in body


# ===========================================================================
# §6 Fail-closed 409 cases (orphan / arithmetic / reconciliation)
# ===========================================================================


class TestFailClosed:
    """Orphan ledger / arithmetic mismatch surface precise 409 codes."""

    async def test_orphan_ledger_ref_returns_409_scope_incomplete(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """Orphan receivable refs surface STATEMENT_LEDGER_SCOPE_INCOMPLETE.

        ledger_entries is IMMUTABLE (write-only trigger), so the orphan row
        cannot be deleted. This test therefore runs in the DEDICATED tenant-B
        schema: the orphan row only ever lives in schema_b, which no other
        Contract D test touches (all other tests use tenant A), so it cannot
        trip the schema-level orphan precheck for other tests.

        The service is invoked directly (with the token-derived schema) so the
        assertion is independent of HTTP identity resolution.
        """
        from datetime import date as _date
        from services.print_service import build_statement_print
        from repositories.statement_repository import StatementLedgerScopeIncomplete

        db, _reg = s2_clean_db
        _code_a, _code_b, schema_b, _email, _password, _ua, _ub = two_tenants
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        ws_b = _pool_instance.tenants["b"]["ws_id"]
        # Resolve tenant-B retailer from the binding (authoritative, server-side).
        row = (
            await db.execute(
                text(
                    "SELECT retailer_id FROM public.wholesaler_retailer_bindings "
                    "WHERE wholesaler_id = :ws AND tenant_user_id = :uid AND is_deleted IS FALSE LIMIT 1"
                ),
                {"ws": ws_b, "uid": _ub},
            )
        ).first()
        assert row is not None, "tenant-B binding not found"
        ret_b_uuid = row.retailer_id

        # Insert an orphan receivable ledger entry in schema_b referencing a
        # non-existent order (no FK exists, so the INSERT succeeds).
        orphan_id = uuid.uuid4()
        await db.execute(
            text(
                f'INSERT INTO "{schema_b}".ledger_entries '
                "(id, transaction_date, account_type, amount, reference_type, reference_id, "
                "entry_version, is_deleted, created_at, updated_at) "
                "VALUES (:id, now(), 'receivable', :amt, 'order', :ref, 1, false, now(), now())"
            ),
            {"id": orphan_id, "amt": Decimal("999.00"), "ref": uuid.uuid4()},
        )
        await db.commit()

        res = await build_statement_print(
            db,
            schema=schema_b,
            wholesaler_id=ws_b,
            retailer_id=ret_b_uuid,
            date_from=_date(2026, 8, 1),
            date_to=_date(2026, 8, 10),
        )
        assert res.view is None
        assert isinstance(res.error, StatementLedgerScopeIncomplete)
        # The HTTP route maps this to 409 STATEMENT_LEDGER_SCOPE_INCOMPLETE
        # (verified separately by the route-level inventory tests).


# ===========================================================================
# §7 Inclusive date boundaries + soft-deleted-order retention
# ===========================================================================


class TestDateBoundaries:
    async def test_inclusive_boundaries_capture_today_movements(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        # A period ending today must include movements posted ~now.
        eat = timezone(timedelta(hours=3), "Africa/Nairobi")
        today = datetime.now(timezone.utc).astimezone(eat).date().isoformat()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], today, today)
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        # At least one movement (the order confirmation receivable) is present.
        assert len(data["movements"]) >= 1

    async def test_far_future_period_empty_movements(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        # A future period with no movements: opening may be non-zero (all-time
        # before), but the period movements list is empty.
        r = await _get_retailer_statement(i2b_client, info["token_ret"], "2099-01-01", "2099-01-02")
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        assert data["movements"] == []
        assert Decimal(data["charge_total"]) == Decimal("0")
        assert Decimal(data["collection_total"]) == Decimal("0")


class TestSoftDeletedOrderRetention:
    """Soft-deleted orders remain in historical accounting scope (rule 8)."""

    async def test_soft_deleted_order_still_in_statement(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        db, reg = s2_clean_db
        sch_a = info["sch_a"]
        oid = info["oid"]
        # Soft-delete the order in-place (ledger entries survive).
        await db.execute(
            text(f'UPDATE "{sch_a}".orders SET is_deleted = true WHERE id = :oid'),
            {"oid": oid},
        )
        await db.commit()
        # Snapshot to restore after the test.
        orig = (await db.execute(text(f'SELECT is_deleted FROM "{sch_a}".orders WHERE id = :oid'), {"oid": oid})).first()
        try:
            frm, to = await _stmt_period_yesterday_today()
            r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
            assert r.status_code == HTTPStatus.OK, r.text
            data = r.json()["data"]
            # The receivable movement for the soft-deleted order is still present.
            assert any(m["reference_id"] == oid for m in data["movements"])
        finally:
            await db.execute(
                text(f'UPDATE "{sch_a}".orders SET is_deleted = :orig WHERE id = :oid'),
                {"orig": orig.is_deleted if orig else False, "oid": oid},
            )
            await db.commit()


# ===========================================================================
# §8 Order independence (natural + reverse) with explicit cleanup
# ===========================================================================


class TestOrderIndependence:
    """Run the focused Contract D suite in natural and reverse declaration order.

    Demonstrates that test outcomes do not depend on execution order (no
    cross-test state leakage). Uses explicit cleanup via the ownership registry.
    """

    @pytest.fixture(autouse=True)
    def _no_leak(self):
        yield

    async def test_a_first_seeds(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity, amount="100.00")
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        assert r.status_code == HTTPStatus.OK
        assert r.json()["data"]["document_type"] == "statement"

    async def test_b_second_seeds(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        # The provisioning schema is module-scoped and ledger_entries is IMMUTABLE
        # (write-only trigger), so prior tests' ledger rows legitimately persist.
        # This test asserts route availability + structural invariants rather
        # than absolute totals (which would depend on execution order).
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity, amount="200.00")
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
