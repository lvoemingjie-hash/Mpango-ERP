"""C910 R4R1 frozen directed controls: R4's seven assertions preserved verbatim,
plus three new named cases for the two-point closeout.

The SAME bytes run against BASE (c910 + the audited R4 patch) and the
candidate (c910 + R4 + the R4R1 narrow differ). They drive the real ASGI
router through HTTP and assert on actual JSON wire; data dependencies are
replaced via FastAPI dependency_overrides with a recording fake async
session; no PG/Redis/service process is started.

BASE expectation (c910 + R4): exactly 7 PASSED (the R4 set) and exactly 3
named semantic REDs — (a) "public" not refused, (b) syntactically valid but
non-tenant schema not refused, (c) the original service call chain is not
exercised. Candidate expectation: 10 passed / 0 failed / 0 errors / 0 skipped.

New-case semantics (two-point closeout):
  * the repository must refuse a missing or non-tenant schema read from
    db.info["tenant_schema"] — generic identifier validity is NOT enough;
  * both refusals must happen BEFORE a single payment query is sent;
  * the original API -> service -> repository chain must run, observed by a
    transparent pass-through spy (never a replacement).
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, Request

import api.middleware.rbac as rbac_module
from api.dependencies import get_tenant_db_session
from api.v1.payments import router


# tenant-format schema: t_ + 32 lowercase hex (matches ^t_[0-9a-f]{32}$)
VALID_SCHEMA = "t_a1b2c3d4e5f60718293a4b5c6d7e8f90"


class _FakeResult:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows if rows is not None else []
        self._scalar = scalar

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar


class FakeTenantSession:
    """Records every executed statement; returns canned rows."""

    def __init__(self, info, page_rows, total):
        self.info = dict(info)
        self.page_rows = page_rows
        self.total = total
        self.executed: list[tuple[str, dict]] = []

    async def execute(self, stmt, params=None):
        self.executed.append((str(stmt), dict(params or {})))
        sql = str(stmt)
        if sql.lstrip().upper().startswith("SELECT COUNT"):
            return _FakeResult(scalar=self.total)
        return _FakeResult(rows=self.page_rows)

    async def commit(self):
        return None

    async def rollback(self):
        return None

    async def close(self):
        return None


def _row(**over):
    row = {
        "id": "11111111-1111-4111-8111-111111111111",
        "order_id": "22222222-2222-4222-8222-222222222222",
        "retailer_id": "33333333-3333-4333-8333-333333333333",
        "transaction_id": None,
        "idempotency_key": None,
        "amount": Decimal("100.50"),
        "method": "cash",
        "status": "completed",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "currency_snapshot": None,
    }
    row.update(over)
    return row


BASE_FIELDS = {
    "id", "order_id", "retailer_id", "transaction_id", "amount",
    "method", "status", "created_at", "updated_at",
}


def _make_client(monkeypatch: pytest.MonkeyPatch, session: FakeTenantSession):
    app = FastAPI()
    app.include_router(router, prefix="/payments")

    async def _fake_call(self, request: Request) -> SimpleNamespace:
        return SimpleNamespace()

    monkeypatch.setattr(rbac_module.RequirePermission, "__call__", _fake_call)
    app.dependency_overrides[get_tenant_db_session] = lambda: session
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


# ------------------------- R4's seven assertions (preserved) -------------------------


async def test_list_wire_adds_only_currency_fields_and_preserves_contract(monkeypatch):
    session = FakeTenantSession(
        {"tenant_schema": VALID_SCHEMA},
        [_row(currency_snapshot="KES"), _row(currency_snapshot="UGX"),
         _row(currency_snapshot=None, amount=Decimal("7"))],
        total=3,
    )
    async with _make_client(monkeypatch, session) as client:
        resp = await client.get("/payments")

    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    # currency disclosure semantics: snapshot values, KNOWN / LEGACY statuses
    assert [i["currency"] for i in items] == ["KES", "UGX", None]
    assert [i["currency_status"] for i in items] == ["KNOWN", "KNOWN", "LEGACY_CURRENCY_UNVERIFIED"]
    # wire contract: exactly the original fields plus the two new ones
    assert set(items[0]) == BASE_FIELDS | {"currency", "currency_status"}
    # amount passes through the original serialization path untouched:
    # BASE and candidate both wire the Decimal as its exact string form
    # (empirically identical on both sides, incl. trailing "0")
    assert items[0]["amount"] == "100.50"
    assert items[2]["amount"] == "7"
    # original fields intact
    assert items[0]["method"] == "cash" and items[0]["status"] == "completed"
    assert resp.json()["data"]["pagination"] == {
        "page": 1, "size": 20, "total": 3, "pages": 1,
    }


async def test_list_sql_explicitly_bound_to_authenticated_tenant_schema(monkeypatch):
    session = FakeTenantSession({"tenant_schema": VALID_SCHEMA}, [_row()], total=1)
    async with _make_client(monkeypatch, session) as client:
        resp = await client.get("/payments")

    assert resp.status_code == 200
    assert len(session.executed) == 2  # count + page, nothing else
    count_sql, page_sql = session.executed[0][0], session.executed[1][0]
    for sql in (count_sql, page_sql):
        # explicit same-tenant binding of the payments relation in both queries
        assert f'"{VALID_SCHEMA}".payments' in sql
        assert "search_path" not in sql.lower()
    # the currency authority is the order snapshot from the same schema
    assert f'"{VALID_SCHEMA}".orders' in page_sql
    assert "LEFT JOIN" in page_sql and "INNER JOIN" not in page_sql
    assert "o.currency_snapshot" in page_sql
    # no unqualified (search_path-dependent) relation remains
    assert "FROM payments" not in page_sql and "FROM payments" not in count_sql


async def test_missing_tenant_schema_rejected_before_any_query(monkeypatch):
    session = FakeTenantSession({}, [_row()], total=1)
    async with _make_client(monkeypatch, session) as client:
        resp = await client.get("/payments")

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "TENANT_CONTEXT_MISSING"
    # refused before touching the database: no query was sent at all
    assert session.executed == []


async def test_unsafe_schema_rejected_before_any_query(monkeypatch):
    session = FakeTenantSession(
        {"tenant_schema": "t_x; DROP TABLE payments"}, [_row()], total=1,
    )
    async with _make_client(monkeypatch, session) as client:
        resp = await client.get("/payments")

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "INVALID_TENANT_SCHEMA"
    assert session.executed == []


async def test_pagination_and_filter_params_forwarded_unchanged(monkeypatch):
    session = FakeTenantSession({"tenant_schema": VALID_SCHEMA}, [], total=0)
    oid = "22222222-2222-4222-8222-222222222222"
    async with _make_client(monkeypatch, session) as client:
        resp = await client.get(
            "/payments", params={
                "page": 3, "size": 10, "order_id": oid,
                "method": "cash", "status": "completed",
            },
        )

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["items"] == []
    assert body["pagination"] == {"page": 3, "size": 10, "total": 0, "pages": 0}
    assert len(session.executed) == 2
    for _sql, params in session.executed:
        assert params["method"] == "cash"
        assert params["pstatus"] == "completed"
        assert params["order_id"] == uuid.UUID(oid)
    _sql, page_params = session.executed[1]
    assert page_params["limit"] == 10 and page_params["offset"] == 20


async def test_detail_wire_has_no_currency_fields(monkeypatch):
    # protection: detail GET shares the repository but must keep its contract
    from services.payment_service import PaymentService

    row = _row(currency_snapshot="KES")

    async def fake_get(self, *, tenant_db, payment_id):
        return row

    monkeypatch.setattr(PaymentService, "get_payment_by_id", fake_get)
    session = FakeTenantSession({"tenant_schema": VALID_SCHEMA}, [], total=0)
    async with _make_client(monkeypatch, session) as client:
        resp = await client.get("/payments/11111111-1111-4111-8111-111111111111")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data) == BASE_FIELDS
    assert "currency" not in data and "currency_status" not in data


async def test_post_payments_still_retired_409(monkeypatch):
    # protection: the retired write path must stay exactly as it is
    session = FakeTenantSession({"tenant_schema": VALID_SCHEMA}, [], total=0)
    async with _make_client(monkeypatch, session) as client:
        resp = await client.post("/payments", json={
            "order_id": "22222222-2222-4222-8222-222222222222",
            "amount": "10", "method": "cash",
        })

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "PAYMENT_WRITE_PATH_DISABLED"
    assert session.executed == []


# ------------------------- R4R1's three new named cases -------------------------


async def test_public_schema_refused_before_any_query(monkeypatch):
    session = FakeTenantSession({"tenant_schema": "public"}, [_row()], total=1)
    async with _make_client(monkeypatch, session) as client:
        resp = await client.get("/payments")

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "INVALID_TENANT_SCHEMA"
    # refused before touching the database: no payment query was sent
    assert session.executed == []


async def test_syntactically_valid_non_tenant_schema_refused_before_any_query(monkeypatch):
    # a generic identifier check would accept this; the tenant check must not
    session = FakeTenantSession({"tenant_schema": "my_backup_schema"}, [_row()], total=1)
    async with _make_client(monkeypatch, session) as client:
        resp = await client.get("/payments")

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "INVALID_TENANT_SCHEMA"
    assert session.executed == []


async def test_route_runs_through_real_service_and_repository_with_order_filter(monkeypatch):
    from services.payment_service import PaymentService

    oid = "22222222-2222-4222-8222-222222222222"
    session = FakeTenantSession(
        {"tenant_schema": VALID_SCHEMA},
        [_row(order_id=oid, currency_snapshot="KES", amount=Decimal("100.50"))],
        total=1,
    )
    calls = []
    original = PaymentService.list_payments

    async def spy(self, **kwargs):
        # transparent observation only: the original implementation runs
        calls.append(dict(kwargs))
        return await original(self, **kwargs)

    monkeypatch.setattr(PaymentService, "list_payments", spy)
    async with _make_client(monkeypatch, session) as client:
        resp = await client.get("/payments", params={"order_id": oid})

    assert resp.status_code == 200
    # the real service method was exercised through the real router
    assert calls and calls[0].get("order_id") == oid
    items = resp.json()["data"]["items"]
    assert [i["order_id"] for i in items] == [oid]
    assert items[0]["amount"] == "100.50"
    assert items[0]["currency"] == "KES" and items[0]["currency_status"] == "KNOWN"
    # the order filter reached the real repository SQL (count + page)
    assert len(session.executed) == 2
    for _sql, params in session.executed:
        assert params["order_id"] == uuid.UUID(oid)


# ------------------------- R4R2 strict-schema controls -------------------------


async def test_trailing_whitespace_binding_refused_before_any_query(monkeypatch):
    # strict contract: the raw binding is used as-is — trailing whitespace is
    # never trimmed and must be refused before any payment query
    session = FakeTenantSession(
        {"tenant_schema": VALID_SCHEMA + "  \t"}, [_row()], total=1,
    )
    async with _make_client(monkeypatch, session) as client:
        resp = await client.get("/payments")

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "INVALID_TENANT_SCHEMA"
    assert session.executed == []


async def test_non_string_binding_refused_before_any_query(monkeypatch):
    # strict contract: no str() coercion — a non-string binding (int) is
    # refused by type before any payment query
    session = FakeTenantSession({"tenant_schema": 12345}, [_row()], total=1)
    async with _make_client(monkeypatch, session) as client:
        resp = await client.get("/payments")

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "INVALID_TENANT_SCHEMA"
    assert session.executed == []


async def test_canonical_binding_enters_existing_read_path(monkeypatch):
    # a canonical tenant-format binding passes strict validation and flows
    # through the existing read path unchanged (count + page, schema-qualified)
    session = FakeTenantSession(
        {"tenant_schema": VALID_SCHEMA},
        [_row(currency_snapshot="KES", amount=Decimal("100.50"))],
        total=1,
    )
    async with _make_client(monkeypatch, session) as client:
        resp = await client.get("/payments")

    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert items[0]["currency"] == "KES" and items[0]["currency_status"] == "KNOWN"
    assert items[0]["amount"] == "100.50"
    assert len(session.executed) == 2
    for sql, _params in session.executed:
        assert f'"{VALID_SCHEMA}".payments' in sql
