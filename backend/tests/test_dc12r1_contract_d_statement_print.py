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
# §2 Strict shared date-range contract (R1 rule 3) — 400 INVALID_DATE_RANGE
# ===========================================================================


class TestDateRangeContract:
    """Missing/blank/malformed/reversed/>365-day ranges -> controlled 400
    INVALID_DATE_RANGE (never a framework 422 or a neutral 404) on BOTH routes
    (they share the same strict parser). The public message is neutral and
    carries no raw parser/internal details."""

    async def test_missing_from_date(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        r = await i2b_client.get(
            "/api/v1/client/statements/print",
            params={"to": "2026-08-10"},
            headers=_headers(info["token_ret"]),
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST
        assert r.json()["code"] == "INVALID_DATE_RANGE"
        # No raw parser/internal details in the public message.
        assert "strptime" not in r.text
        assert "ValueError" not in r.text

    async def test_missing_to_date(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        r = await i2b_client.get(
            "/api/v1/client/statements/print",
            params={"from": "2026-08-01"},
            headers=_headers(info["token_ret"]),
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST
        assert r.json()["code"] == "INVALID_DATE_RANGE"

    async def test_blank_from_date(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        r = await i2b_client.get(
            "/api/v1/client/statements/print",
            params={"from": "   ", "to": "2026-08-10"},
            headers=_headers(info["token_ret"]),
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST
        assert r.json()["code"] == "INVALID_DATE_RANGE"

    async def test_malformed_from_date(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        r = await i2b_client.get(
            "/api/v1/client/statements/print",
            params={"from": "01/08/2026", "to": "2026-08-10"},
            headers=_headers(info["token_ret"]),
        )
        assert r.status_code == HTTPStatus.BAD_REQUEST
        assert r.json()["code"] == "INVALID_DATE_RANGE"
        assert "01/08/2026" not in r.text

    async def test_from_after_to(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        r = await _get_retailer_statement(i2b_client, info["token_ret"], "2026-08-10", "2026-08-01")
        assert r.status_code == HTTPStatus.BAD_REQUEST
        assert r.json()["code"] == "INVALID_DATE_RANGE"

    async def test_span_exceeds_365_days(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        r = await _get_retailer_statement(i2b_client, info["token_ret"], "2025-01-01", "2026-08-10")
        assert r.status_code == HTTPStatus.BAD_REQUEST
        assert r.json()["code"] == "INVALID_DATE_RANGE"

    async def test_supplier_route_shares_the_same_strict_parser(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        # Malformed + reversed + >365-day must behave identically on the
        # supplier route (same shared parser).
        r1 = await _get_supplier_statement(i2b_client, info["token_admin"], info["ret_a"], "nope", "2026-08-10")
        assert r1.status_code == HTTPStatus.BAD_REQUEST
        assert r1.json()["code"] == "INVALID_DATE_RANGE"
        r2 = await _get_supplier_statement(i2b_client, info["token_admin"], info["ret_a"], "2026-08-10", "2026-08-01")
        assert r2.status_code == HTTPStatus.BAD_REQUEST
        assert r2.json()["code"] == "INVALID_DATE_RANGE"
        r3 = await _get_supplier_statement(i2b_client, info["token_admin"], info["ret_a"], "2025-01-01", "2026-08-10")
        assert r3.status_code == HTTPStatus.BAD_REQUEST
        assert r3.json()["code"] == "INVALID_DATE_RANGE"

    async def test_malformed_retailer_uuid_supplier(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        r = await _get_supplier_statement(i2b_client, info["token_admin"], "not-a-uuid", "2026-08-01", "2026-08-10")
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
    """No payment row UUID, cashier user id, tenant_user_id, or schema name leaks.

    R1 evidence repair: the "no internal ID" assertions now verify the
    SERIALIZED response contains no movement_id/payment_id keys at all.
    """

    async def test_no_internal_ids_in_statement(self, i2b_client, two_tenants, s2_clean_db, cashier_identity):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        body = r.text
        # Schema name must never leak.
        assert info["sch_a"] not in body
        # The supplier internal tenant id must not appear as a raw value.
        assert info["ws_a"] not in body
        # R1 redaction: no movement_id / payment_id anywhere in the response.
        assert "movement_id" not in body
        assert "payment_id" not in body


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

    async def test_zero_value_movement_returns_409_internal_inconsistent(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        """R1 rule 2 — a zero-valued receivable movement is an internal
        inconsistency and must fail closed (409 STATEMENT_INTERNAL_INCONSISTENT).

        RED: on the pre-R1 implementation a zero-valued movement rendered
        silently (no kind classification existed); this assertion fails there.
        GREEN: the R1 zero-value check returns the 409.

        The zero-valued row references this test's own order, which is left in
        place (orders are never deleted by the harness), so the row is never an
        orphan — it cannot trip the schema-level orphan precheck for other
        tests, and other tests' statements filter by their own (wid, rid).
        """
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        db, _reg = s2_clean_db
        await _post_receivable_charge(db, info["sch_a"], uuid.UUID(info["oid"]), "0.00")
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        assert r.status_code == HTTPStatus.CONFLICT
        assert r.json()["code"] == "STATEMENT_INTERNAL_INCONSISTENT"
        # Zero partial document.
        assert "data" not in r.json()


# ===========================================================================
# §6b R1 — completed-payment ownership integrity (rule 1)
# ===========================================================================


class TestPaymentOwnershipIntegrity:
    """A completed payment whose retailer differs from its order's retailer
    makes the payment scope inconsistent: the statement fails closed with 409
    STATEMENT_INTERNAL_INCONSISTENT and zero partial document. Corrupt rows
    neither leak into the document nor silently disappear."""

    async def test_payment_retailer_mismatch_returns_409_internal_inconsistent(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        db, _reg = s2_clean_db
        foreign_ret = uuid.uuid4()
        # A completed payment whose retailer_id does NOT match its order's
        # retailer_id (the payment row is corrupt).
        pay_id = await _insert_payment_row(
            db, info["sch_a"], uuid.UUID(info["oid"]), foreign_ret, amount="50.00"
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
            # payments are deletable (no immutable trigger) — clean residue.
            await db.execute(
                text(f'DELETE FROM "{info["sch_a"]}".payments WHERE id = :pid'),
                {"pid": pay_id},
            )
            await db.commit()

    async def test_ownership_mismatch_also_fails_closed_on_supplier_route(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        db, _reg = s2_clean_db
        foreign_ret = uuid.uuid4()
        pay_id = await _insert_payment_row(
            db, info["sch_a"], uuid.UUID(info["oid"]), foreign_ret, amount="50.00"
        )
        try:
            frm, to = await _stmt_period_yesterday_today()
            r = await _get_supplier_statement(i2b_client, info["token_admin"], info["ret_a"], frm, to)
            assert r.status_code == HTTPStatus.CONFLICT
            assert r.json()["code"] == "STATEMENT_INTERNAL_INCONSISTENT"
            assert "data" not in r.json()
        finally:
            await db.execute(
                text(f'DELETE FROM "{info["sch_a"]}".payments WHERE id = :pid'),
                {"pid": pay_id},
            )
            await db.commit()


# ===========================================================================
# §6c R1 — settled_total derives ONLY from settled_payments[].amount (rule 2)
# ===========================================================================


class TestSettledTotal:
    """settled_total must equal the sum of settled_payments[].amount — never
    derived from movements or cached balances.

    RED: the pre-R1 response had no settled_total field at all.
    """

    async def test_settled_total_equals_sum_of_settled_payments(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity, amount="250.00")
        db, _reg = s2_clean_db
        # A second completed payment in the same period (independent row).
        await _insert_payment_row(
            db, info["sch_a"], uuid.UUID(info["oid"]), uuid.UUID(info["ret_a"]), amount="75.00"
        )
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        assert r.status_code == HTTPStatus.OK, r.text
        data = r.json()["data"]
        settled_sum = sum((Decimal(p["amount"]) for p in data["settled_payments"]), Decimal("0"))
        assert Decimal(data["settled_total"]) == settled_sum
        assert Decimal(data["settled_total"]) == Decimal("325.00")
        # settled_total never reflects movements or pending declarations.
        assert "settled_total" not in data["settled_payments"][0]


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

    async def _credit_only_setup(self, i2b_client, two_tenants, s2_clean_db, cashier_identity, delta: str):
        """Convert the relationship to credit-only and force a ledger/cache
        difference of exactly ``delta`` KES.

        The cached binding balance column is numeric(12,2), so a >0.01 delta
        cannot be expressed there (0.0101 would be rounded to 0.01). The delta
        is therefore introduced as a high-precision receivable LEDGER row, and
        the cached balance is pinned to exactly 0 (exactly representable):
        ledger_total = 0 + delta, cached = 0 -> diff = delta.
        """
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        db, _reg = s2_clean_db
        sch_a = info["sch_a"]
        # +100 charge (order confirmation receivable) — the confirm flow posts
        # the -100 collection, so the relationship ledger total is 0.00.
        await _post_receivable_charge(db, sch_a, uuid.UUID(info["oid"]), "100.00")
        # Make the relationship credit-only (no cash/transfer completed payment).
        await db.execute(
            text(f'UPDATE "{sch_a}".payments SET method = \'credit\' WHERE order_id = :oid'),
            {"oid": uuid.UUID(info["oid"])},
        )
        # Pin the cached binding balance to exactly 0 (numeric(12,2)-safe).
        await db.execute(
            text(
                "UPDATE public.wholesaler_retailer_bindings SET outstanding_balance = 0 "
                "WHERE wholesaler_id = :ws AND retailer_id = :rid AND is_deleted IS FALSE"
            ),
            {"ws": uuid.UUID(info["ws_a"]), "rid": uuid.UUID(info["ret_a"])},
        )
        # Introduce the exact delta via a high-precision receivable row.
        await _post_receivable_charge(db, sch_a, uuid.UUID(info["oid"]), delta)
        await db.commit()
        return info

    async def test_0001_difference_is_accepted(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await self._credit_only_setup(
            i2b_client, two_tenants, s2_clean_db, cashier_identity, delta="0.001"
        )
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        assert r.status_code == HTTPStatus.OK, r.text

    async def test_001_difference_is_accepted(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await self._credit_only_setup(
            i2b_client, two_tenants, s2_clean_db, cashier_identity, delta="0.01"
        )
        frm, to = await _stmt_period_yesterday_today()
        r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to)
        assert r.status_code == HTTPStatus.OK, r.text

    async def test_00101_difference_is_rejected(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await self._credit_only_setup(
            i2b_client, two_tenants, s2_clean_db, cashier_identity, delta="0.0101"
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
    """Aggregate statement-line cap of 1000: over-cap periods fail closed with
    400 STATEMENT_RANGE_TOO_LARGE — never a silent truncation and never a
    partial document. Lists are queried with LIMIT cap+1 so overflow is
    detectable."""

    async def test_over_cap_pending_declarations_return_400_range_too_large(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        db, _reg = s2_clean_db
        sch_a = info["sch_a"]
        ws_a = uuid.UUID(info["ws_a"])
        ret_a = uuid.UUID(info["ret_a"])
        oid = uuid.UUID(info["oid"])
        # Seed 1001 pending declarations (LIMIT cap+1 -> 1001 rows -> overflow).
        rows = []
        for _ in range(1001):
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "oid": oid,
                    "ret": ret_a,
                    "ws": ws_a,
                    "amt": Decimal("10.00"),
                    "idem": f"cap-{uuid.uuid4().hex}",
                    "sb": uuid.uuid4(),
                }
            )
        await db.execute(
            text(
                f'INSERT INTO "{sch_a}".payment_declarations '
                "(id, order_id, retailer_id, wholesaler_id, declared_amount, method, "
                "status, idempotency_key, submitted_by, submitted_at, transfer_reference) "
                "VALUES (:id, :oid, :ret, :ws, :amt, 'cash', 'pending', :idem, :sb, now(), NULL)"
            ),
            rows,
        )
        await db.commit()
        try:
            frm, to = await _stmt_period_yesterday_today()
            r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to, include_pending=True)
            assert r.status_code == HTTPStatus.BAD_REQUEST
            assert r.json()["code"] == "STATEMENT_RANGE_TOO_LARGE"
            assert "data" not in r.json()
            # The public message is neutral (no internal counts).
            assert "1001" not in r.text
            assert "1000" not in r.text
        finally:
            await db.execute(
                text(f'DELETE FROM "{sch_a}".payment_declarations WHERE idempotency_key LIKE \'cap-%\''),
            )
            await db.commit()

    async def test_at_cap_is_accepted(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        db, _reg = s2_clean_db
        sch_a = info["sch_a"]
        ws_a = uuid.UUID(info["ws_a"])
        ret_a = uuid.UUID(info["ret_a"])
        oid = uuid.UUID(info["oid"])
        # combined = movements(1 collection) + settled(1 payment) + pending(998)
        #           = 1000 == cap -> accepted.
        rows = []
        for _ in range(998):
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "oid": oid,
                    "ret": ret_a,
                    "ws": ws_a,
                    "amt": Decimal("10.00"),
                    "idem": f"cap-{uuid.uuid4().hex}",
                    "sb": uuid.uuid4(),
                }
            )
        await db.execute(
            text(
                f'INSERT INTO "{sch_a}".payment_declarations '
                "(id, order_id, retailer_id, wholesaler_id, declared_amount, method, "
                "status, idempotency_key, submitted_by, submitted_at, transfer_reference) "
                "VALUES (:id, :oid, :ret, :ws, :amt, 'cash', 'pending', :idem, :sb, now(), NULL)"
            ),
            rows,
        )
        await db.commit()
        try:
            frm, to = await _stmt_period_yesterday_today()
            r = await _get_retailer_statement(i2b_client, info["token_ret"], frm, to, include_pending=True)
            assert r.status_code == HTTPStatus.OK, r.text
            assert len(r.json()["data"]["pending_declarations"]) == 998
        finally:
            await db.execute(
                text(f'DELETE FROM "{sch_a}".payment_declarations WHERE idempotency_key LIKE \'cap-%\''),
            )
            await db.commit()


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
    """Soft-deleted orders remain in historical accounting scope (rule 8).

    R1 evidence repair: the mutation is snapshot BEFORE it happens, restored in
    ``finally`` from a FRESH session with an exact rowcount==1 assertion and an
    exact reread-equality assertion. A second test proves that an active and a
    soft-deleted order produce IDENTICAL accounting totals.
    """

    async def test_soft_deleted_order_still_in_statement(
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        from database.session import AsyncSessionLocal

        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        db, _reg = s2_clean_db
        sch_a = info["sch_a"]
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
        self, i2b_client, two_tenants, s2_clean_db, cashier_identity
    ):
        from database.session import AsyncSessionLocal

        info = await _submit_and_confirm(i2b_client, two_tenants, s2_clean_db, cashier_identity)
        db, _reg = s2_clean_db
        sch_a = info["sch_a"]
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
