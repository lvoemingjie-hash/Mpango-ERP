"""
P25-ED: Platform System DB Context / Tenant Filter Boundary Fix

Regression tests proving:
  1. Product tenant-scoped ORM query without tenant context still fails closed
     (TenantContextMissingError raised).
  2. Platform allowlisted public/system query (via mark_session_as_system)
     no longer fails with TenantContextMissingError.
  3. Product tenant isolation is preserved: tenant_id filter still applied
     when tenant context is set.
  4. Session-level system scope only affects the marked session, not other
     sessions on the same thread/process.

These are synchronous unit tests using SQLite in-memory databases, mirroring
the pattern in tests/test_global_tenant_filter.py.
"""
import pytest
from sqlalchemy import Column, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session, mapped_column

from db.tenant_filter import (
    TenantContextMissingError,
    mark_session_as_system,
    reset_current_tenant,
    run_as_system,
    set_current_tenant,
)


class _Base(DeclarativeBase):
    pass


class _TenantRow(_Base):
    """Simulates a product model with tenant_id (e.g. Invoice, Customer)."""

    __tablename__ = "tenant_rows"

    id = mapped_column(String, primary_key=True)
    tenant_id = mapped_column(String, nullable=False)
    value = mapped_column(String, nullable=False)


class _WholesalerRow(_Base):
    """Simulates a platform model with wholesaler_id (e.g. PlatformAuditLog)."""

    __tablename__ = "wholesaler_rows"

    id = mapped_column(String, primary_key=True)
    wholesaler_id = mapped_column(String, nullable=False)
    value = mapped_column(String, nullable=False)


def _setup_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.execute(
            _TenantRow.__table__.insert(),
            [
                {"id": "1", "tenant_id": "t1", "value": "a"},
                {"id": "2", "tenant_id": "t2", "value": "b"},
            ],
        )
        session.execute(
            _WholesalerRow.__table__.insert(),
            [
                {
                    "id": "w1",
                    "wholesaler_id": "11111111-1111-1111-1111-111111111111",
                    "value": "x",
                },
                {
                    "id": "w2",
                    "wholesaler_id": "22222222-2222-2222-2222-222222222222",
                    "value": "y",
                },
            ],
        )
        session.commit()

    return engine


# ===============================================================
# Part 1: Product tenant-scoped query fails closed (no regression)
# ===============================================================


def test_product_query_without_tenant_context_fails_closed():
    """Product ORM query on tenant_id model without context must raise."""
    engine = _setup_db()

    with Session(engine) as session:
        with pytest.raises(TenantContextMissingError):
            session.execute(select(_TenantRow))


def test_product_query_without_tenant_id_fails_closed():
    """Product ORM query with schema but no tenant_id must raise."""
    engine = _setup_db()

    with Session(engine) as session:
        session.info["tenant_schema"] = "public"
        with pytest.raises(TenantContextMissingError) as exc:
            session.execute(select(_TenantRow))
        assert "tenant_id required" in str(exc.value)


# ===============================================================
# Part 2: Platform allowlisted system query passes (the fix)
# ===============================================================


def test_platform_query_with_mark_session_as_system_passes():
    """Platform ORM query with mark_session_as_system must NOT raise."""
    engine = _setup_db()

    with Session(engine) as session:
        session.info["tenant_schema"] = "public"
        mark_session_as_system(session, reason="platform_system_query")

        result = session.execute(select(_WholesalerRow)).scalars().all()

    assert {r.id for r in result} == {"w1", "w2"}


def test_platform_query_with_mark_session_as_system_passes_tenant_model():
    """Platform system scope also works for tenant_id models (cross-tenant)."""
    engine = _setup_db()

    with Session(engine) as session:
        session.info["tenant_schema"] = "public"
        mark_session_as_system(session, reason="platform_system_query")

        result = session.execute(select(_TenantRow)).scalars().all()

    assert {r.id for r in result} == {"1", "2"}


def test_platform_query_with_run_as_system_context_manager_passes():
    """The existing run_as_system pattern also still works."""
    engine = _setup_db()

    with Session(engine) as session:
        session.info["tenant_schema"] = "public"
        with run_as_system(reason="platform_system_query"):
            result = session.execute(select(_WholesalerRow)).scalars().all()

    assert {r.id for r in result} == {"w1", "w2"}


def test_mark_session_as_system_requires_reason():
    """mark_session_as_system must reject empty reason."""
    engine = _setup_db()

    with Session(engine) as session:
        with pytest.raises(ValueError):
            mark_session_as_system(session, reason="")


# ===============================================================
# Part 3: Product tenant isolation preserved (no weakening)
# ===============================================================


def test_tenant_filter_still_applies_when_context_set():
    """Tenant_id filter still narrows results when tenant context is active."""
    engine = _setup_db()

    tokens = set_current_tenant(tenant_id="t1", tenant_schema="t_schema")
    try:
        with Session(engine) as session:
            session.info["tenant_schema"] = "t_schema"
            result = session.execute(select(_TenantRow)).scalars().all()
    finally:
        reset_current_tenant(*tokens)

    assert [r.id for r in result] == ["1"]


def test_other_tenant_rows_excluded_when_filtered():
    """Rows from other tenants must be excluded."""
    engine = _setup_db()

    tokens = set_current_tenant(tenant_id="t2", tenant_schema="t_schema")
    try:
        with Session(engine) as session:
            session.info["tenant_schema"] = "t_schema"
            result = session.execute(select(_TenantRow)).scalars().all()
    finally:
        reset_current_tenant(*tokens)

    assert [r.id for r in result] == ["2"]


# ===============================================================
# Part 4: Session scope isolation (no cross-session leak)
# ===============================================================


def test_session_system_scope_does_not_leak_to_other_sessions():
    """A system-scoped session must not affect a separate normal session."""
    engine = _setup_db()

    with Session(engine) as system_session:
        system_session.info["tenant_schema"] = "public"
        mark_session_as_system(system_session, reason="platform_system_query")

        with Session(engine) as normal_session:
            normal_session.info["tenant_schema"] = "public"
            # normal_session is NOT system-scoped, must still fail closed
            with pytest.raises(TenantContextMissingError):
                normal_session.execute(select(_TenantRow))


# ===============================================================
# Part 5: Route smoke equivalent - get_platform_db wiring
# ===============================================================


def test_get_platform_db_marks_session_as_system():
    """Verify get_platform_db sets the system scope reason on the session.

    This is the route-smoke equivalent: it proves that platform routes which
    depend on get_platform_db will receive a system-scoped session, which in
    turn bypasses TenantContextMissingError for public-schema ORM queries on
    models with tenant_id / wholesaler_id columns.

    Before P25-ED, platform routes used get_db which set tenant_schema="public"
    but NO system scope, so TenantContextMissingError was raised (HTTP 500).
    After P25-ED, platform routes use get_platform_db which sets system scope,
    so the filter is bypassed and the route returns HTTP 200.
    """
    import asyncio
    import types

    captured_info: dict = {}

    class _FakeSession:
        def __init__(self):
            self.info = {}

        async def __aenter__(self):
            captured_info.update(self.info)
            return self

        async def __aexit__(self, *args):
            return False

        async def commit(self):
            pass

        async def rollback(self):
            pass

        async def close(self):
            pass

    fake_session = _FakeSession()

    # Patch AsyncSessionLocal inside database.session to return our fake
    import database.session as session_mod

    original_local = session_mod.AsyncSessionLocal
    session_mod.AsyncSessionLocal = lambda: fake_session
    try:
        gen = session_mod.get_platform_db()
        asyncio.get_event_loop().run_until_complete(gen.__anext__())

        # After the first yield, the session.info must contain:
        # 1. tenant_schema = "public"
        # 2. system scope reason = "platform_system_query"
        assert fake_session.info.get("tenant_schema") == "public"
        assert (
            fake_session.info.get("mpango_system_scope_reason")
            == "platform_system_query"
        )
    finally:
        session_mod.AsyncSessionLocal = original_local
