import pytest
from sqlalchemy import Column, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session, mapped_column

from db.tenant_filter import (
    TenantContextMissingError,
    reset_current_tenant,
    run_as_system,
    set_current_tenant,
)


class _Base(DeclarativeBase):
    pass


class _Row(_Base):
    __tablename__ = "rows"

    id = mapped_column(String, primary_key=True)
    tenant_id = mapped_column(String, nullable=False)
    value = mapped_column(String, nullable=False)


class _OrderRow(_Base):
    __tablename__ = "orders"

    id = mapped_column(String, primary_key=True)
    wholesaler_id = mapped_column(String, nullable=False)
    value = mapped_column(String, nullable=False)


def _setup_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.execute(
            _Row.__table__.insert(),
            [
                {"id": "1", "tenant_id": "t1", "value": "a"},
                {"id": "2", "tenant_id": "t2", "value": "b"},
            ],
        )
        session.execute(
            _OrderRow.__table__.insert(),
            [
                {
                    "id": "o1",
                    "wholesaler_id": "11111111-1111-1111-1111-111111111111",
                    "value": "a",
                },
                {
                    "id": "o2",
                    "wholesaler_id": "22222222-2222-2222-2222-222222222222",
                    "value": "b",
                },
            ],
        )
        session.commit()

    return engine


def test_b6_requires_tenant_context_for_orm_select():
    engine = _setup_db()

    with Session(engine) as session:
        with pytest.raises(TenantContextMissingError) as exc:
            session.execute(select(_Row))

        assert str(exc.value) == "Tenant context required"


def test_b6_orders_query_without_tenant_id_raises_tenant_context_missing_error():
    engine = _setup_db()

    with Session(engine) as session:
        session.info["tenant_schema"] = "t_schema"

        with pytest.raises(TenantContextMissingError) as exc:
            session.execute(select(_OrderRow))

        assert str(exc.value) == "Tenant context missing: tenant_id required for tenant-scoped query"


def test_b6_ignore_tenant_escape_hatch_skips_enforcement():
    engine = _setup_db()

    with Session(engine) as session:
        result = session.execute(select(_Row).execution_options(ignore_tenant=True)).scalars().all()

    assert {r.id for r in result} == {"1", "2"}


def test_b6_run_as_system_bypass_skips_enforcement():
    engine = _setup_db()

    with Session(engine) as session:
        with run_as_system(reason="unit_test_public_scope"):
            result = session.execute(select(_Row)).scalars().all()

    assert {r.id for r in result} == {"1", "2"}


def test_b6_applies_tenant_id_filter_when_model_has_tenant_id_column():
    engine = _setup_db()

    tokens = set_current_tenant(tenant_id="t1", tenant_schema="t_schema")
    try:
        with Session(engine) as session:
            result = session.execute(select(_Row)).scalars().all()
    finally:
        reset_current_tenant(*tokens)

    assert [r.id for r in result] == ["1"]


def test_b6_ignore_tenant_skips_tenant_id_filtering():
    engine = _setup_db()

    tokens = set_current_tenant(tenant_id="t1", tenant_schema="t_schema")
    try:
        with Session(engine) as session:
            result = session.execute(select(_Row).execution_options(ignore_tenant=True)).scalars().all()
    finally:
        reset_current_tenant(*tokens)

    assert {r.id for r in result} == {"1", "2"}
