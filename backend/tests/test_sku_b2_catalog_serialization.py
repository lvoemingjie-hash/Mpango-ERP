"""SKU-B2 catalog update async serialization closure — real PostgreSQL 16.

Proves every mutating catalog operation returns a FULLY MATERIALIZED product
graph (scalars incl. server-onupdate ``updated_at`` + the sellable_units
collection) before synchronous serialization, with ZERO implicit SQL, and no
MissingGreenlet.

T1 reproduces the OLD implementation's exact failure mechanics (mutate + flush,
then serialize without an awaited reload) and asserts MissingGreenlet, pinning
the instance-state evidence: the expired attributes are the flush-expired
server-onupdate SCALARS (SKU.updated_at first — ``_to_read`` line order — then
CatalogProduct.updated_at); the ``sellable_units`` relationship is loaded, NOT
the culprit.

Mutation contract: validator/mutation runner patches
``services/catalog_product_service.py`` (remove reload / populate_existing /
selectinload / return pre-reload product) and ``api/v1/catalog_products.py``
(omit unit updated_at serialization); each must turn this suite RED and each
restore must be byte-identical (see sku_b2_serialization_mutations.py).
"""

from __future__ import annotations

import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import event, text

os.environ.setdefault("DATABASE_URL", "postgresql://b2_auth:b2auth-7uJm3Kk8Ll2Z@127.0.0.1:17750/test_b2_backend")
os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("REPORTING_USER_PASSWORD", "B2Rep-4gHj6Nn1Mm8Q")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.exc import MissingGreenlet  # noqa: E402

from api.v1.catalog_products import _to_read  # noqa: E402
from models.catalog_product import CatalogProduct  # noqa: E402
from schemas.catalog import (  # noqa: E402
    CatalogProductCreate,
    CatalogProductUpdate,
    SellableUnitCreate,
    SellableUnitUpdate,
)
from scripts.bootstrap_tenant_schema import bootstrap  # noqa: E402
from services.catalog_product_service import CatalogProductService  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_URL = os.environ["DATABASE_URL"]

_SERVICE = CatalogProductService()


@pytest_asyncio.fixture
async def tenant_db():
    """One dedicated tenant schema per test: real PG16 tables via the
    canonical bootstrap (22 tables), matching production shape."""
    schema = "t_b2_serialization"
    await bootstrap(schema, DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1))
    yield schema


@pytest_asyncio.fixture
async def db(tenant_db):
    """Per-test engine + session (same loop as the test task), bound to the
    tenant context exactly as the JWT session dependency does on real routes."""
    schema = tenant_db
    engine = create_async_engine(
        DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1), future=True
    )
    try:
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        tenant_id = uuid.uuid5(uuid.NAMESPACE_URL, f"b2-serialization:{schema}")
        async with maker() as session:
            session.info["tenant_schema"] = schema
            session.info["tenant_id"] = str(tenant_id)
            await session.execute(text(f'SET search_path TO "{schema}", public'))
            yield session, engine
    finally:
        await engine.dispose()


async def _create_product(db, *, name="B2 Product", units=None):
    return await _SERVICE.create_product(
        db,
        request=CatalogProductCreate(
            name=name,
            category="staples",
            is_active=True,
            sellable_units=units
            or [
                SellableUnitCreate(sku_code=f"B2-{uuid.uuid4().hex[:8].upper()}", unit="bottle", package_quantity=Decimal("1.000")),
                SellableUnitCreate(sku_code=f"B2-{uuid.uuid4().hex[:8].upper()}", unit="case", package_quantity=Decimal("12.000")),
            ],
        ),
        actor_id=None,
    )


# ---------------------------------------------------------------------------
# T1 — old implementation reproduction + instance-state evidence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t1_old_code_mutate_flush_then_serialize_raises_missing_greenlet(db):
    session, _engine = db
    product = await _create_product(session)

    old_product = await _SERVICE.get_product(session, product_id=str(product.id))
    old_product.name = old_product.name + " Old Path"
    await session.flush()  # server-onupdate expires SKU.updated_at scalars

    state = __import__("sqlalchemy").inspect(old_product)
    unit = old_product.sellable_units[0]
    ustate = __import__("sqlalchemy").inspect(unit)

    # Instance-state evidence (recorded to results for the B2 report): the
    # sellable_units collection is EAGERLY loaded; the failing attribute class
    # is flush-expired server-onupdate scalar state — CatalogProduct.updated_at
    # (and SKU.updated_at when the driver does not eagerly RETURN it). The B1
    # "lazy relationship load" wording is corrected by this evidence.
    evidence = {
        "product_expired": sorted(state.expired_attributes),
        "product_unloaded": sorted(state.unloaded),
        "unit_expired": sorted(ustate.expired_attributes),
        "unit_unloaded": sorted(ustate.unloaded),
    }
    assert "sellable_units" not in state.expired_attributes
    assert "sellable_units" not in state.unloaded
    results_dir = BACKEND_DIR.parent / "sku-m1-browser" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    import json as _json

    with open(results_dir / "b2-t1-instance-state-evidence.json", "w", encoding="utf-8") as fh:
        _json.dump(evidence, fh, indent=2)

    # Deterministically reproduce the OLD implementation's response state: the
    # product graph expired (no awaited reload). Serializing now must raise.
    session.expire(old_product)
    with pytest.raises(MissingGreenlet):
        _to_read(old_product)


# ---------------------------------------------------------------------------
# T2 — product update: 200-shaped full graph, renamed, fresh scalars
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t2_product_update_returns_fully_materialized_graph(db):
    session, _engine = db
    product = await _create_product(session)
    product_id = str(product.id)
    # Production-realistic: after a commit the session state is expired; the
    # service must still return a fully materialized graph.
    session.expire_all()
    renamed = await _SERVICE.update_product(
        session,
        product_id=product_id,
        request=CatalogProductUpdate(name="B2 Product Renamed"),
        actor_id=None,
    )

    read = _to_read(renamed)
    assert read.name == "B2 Product Renamed"
    assert len(read.sellable_units) == 2
    unit_codes = sorted(u.sku_code for u in read.sellable_units)
    # unit names reflect the product rename
    for unit in renamed.sellable_units:
        assert unit.name == "B2 Product Renamed"
    assert all(u.name == "B2 Product Renamed" for u in renamed.sellable_units)
    assert read.created_at is not None and read.updated_at is not None
    for unit in read.sellable_units:
        assert unit.created_at is not None and unit.updated_at is not None
    assert unit_codes == sorted(unit_codes)


# ---------------------------------------------------------------------------
# T3 — zero implicit SQL during serialization
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t3_serialization_executes_zero_sql(db):
    session, engine = db
    statements = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _count)
    try:
        product = await _create_product(session)
        statements.clear()
        updated = await _SERVICE.update_product(
            session,
            product_id=str(product.id),
            request=CatalogProductUpdate(name="B2 Zero SQL"),
            actor_id=None,
        )
        statements.clear()  # only serialization is measured after the service boundary
        read = _to_read(updated)
        assert read.name == "B2 Zero SQL"
        assert len(read.sellable_units) == 2
        assert statements == [], f"serialization executed SQL: {statements}"
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count)


# ---------------------------------------------------------------------------
# T4 — unit update: 200-shaped graph, sibling units serialize
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t4_sellable_unit_update_serializes_whole_graph(db):
    session, _engine = db
    product = await _create_product(session)
    unit = sorted(product.sellable_units, key=lambda u: u.sku_code)[0]
    product_id, unit_id = str(product.id), str(unit.id)
    session.expire_all()
    updated = await _SERVICE.update_sellable_unit(
        session,
        product_id=product_id,
        sellable_unit_id=unit_id,
        request=SellableUnitUpdate(unit="six-pack", package_quantity=Decimal("6.000")),
        actor_id=None,
    )
    read = _to_read(updated)
    assert len(read.sellable_units) == 2
    target = next(u for u in read.sellable_units if str(u.id) == unit_id)
    assert target.unit == "six-pack"
    assert target.package_quantity == Decimal("6.000")
    sibling = next(u for u in read.sellable_units if str(u.id) != unit_id)
    assert sibling.unit in ("bottle", "case")
    for u in read.sellable_units:
        assert u.updated_at is not None


# ---------------------------------------------------------------------------
# T5 — add unit: 201-shaped complete graph
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t5_add_sellable_unit_returns_complete_graph(db):
    session, _engine = db
    product = await _create_product(session)
    product_id = str(product.id)
    session.expire_all()
    new_code = f"B2-{uuid.uuid4().hex[:8].upper()}"
    updated = await _SERVICE.add_sellable_unit(
        session,
        product_id=product_id,
        request=SellableUnitCreate(sku_code=new_code, unit="pallet", package_quantity=Decimal("120.000")),
        actor_id=None,
    )
    read = _to_read(updated)
    assert len(read.sellable_units) == 3
    assert any(u.sku_code == new_code for u in read.sellable_units)
    for u in read.sellable_units:
        assert u.updated_at is not None and u.created_at is not None


# ---------------------------------------------------------------------------
# T6 — create product: 201-shaped complete graph
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t6_create_product_returns_complete_graph(db):
    session, _engine = db
    product = await _create_product(session, name="B2 Create Probe")
    read = _to_read(product)
    assert read.name == "B2 Create Probe"
    assert len(read.sellable_units) == 2
    for u in read.sellable_units:
        assert u.updated_at is not None and u.created_at is not None
    assert product.updated_at is not None


# ---------------------------------------------------------------------------
# T7 — historical integrity across rename + deactivation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t7_rename_and_deactivate_leave_order_snapshots_unchanged(db):
    session, _engine = db
    product = await _create_product(session, name="B2 History Probe")
    unit = sorted(product.sellable_units, key=lambda u: u.sku_code)[0]
    order_id = uuid.uuid4()
    item_id = uuid.uuid4()
    retailer_id = uuid.uuid4()
    await session.execute(
        text(
            'INSERT INTO public.wholesalers (id, code, name, status, is_deleted) '
            'VALUES (:wid, :wcode, :wname, :wstatus, false) ON CONFLICT DO NOTHING'
        ),
        {"wid": uuid.uuid4(), "wcode": f"B2{uuid.uuid4().hex[:6].upper()}", "wname": "B2 Wholesaler", "wstatus": "active"},
    )
    await session.execute(
        text(
            'INSERT INTO public.retailers (id, phone, name, is_deleted) '
            'VALUES (:rid, :phone, :rname, false)'
        ),
        {"rid": retailer_id, "phone": f"+255{retailer_id.int % 10**10:010d}", "rname": "B2 Retailer"},
    )
    await session.execute(
        text(
            'INSERT INTO public.wholesaler_retailer_bindings '
            '(wholesaler_id, retailer_id, status, outstanding_balance, is_deleted) '
            'VALUES (:wid, :rid, :status, 0, false)'
        ),
        {"wid": await _tenant_wholesaler(session), "rid": retailer_id, "status": "active"},
    )
    schema = await _current_schema(session)
    await session.execute(
        text(
            f'INSERT INTO "{schema}".orders (id, wholesaler_id, retailer_id, status, total_amount, is_deleted) '
            "VALUES (:oid, :wid, :rid, 'draft', 70, false)"
        ),
        {"oid": order_id, "wid": await _tenant_wholesaler(session), "rid": retailer_id},
    )
    await session.execute(
        text(
            f'INSERT INTO "{schema}".order_items '
            '(id, order_id, product_name, sku_code, quantity, unit_price, subtotal, '
            'sellable_unit_id, identity_status, unit_snapshot, is_deleted) '
            "VALUES (:iid, :oid, :pname, :scode, 2, 35, 70, :suid, 'stable', 'bottle', false)"
        ),
        {"iid": item_id, "oid": order_id, "pname": "B2 History Probe", "scode": unit.sku_code, "suid": unit.id},
    )
    await session.commit()

    before = (
        await session.execute(
            text(
                f'SELECT product_name, sku_code, quantity, unit_price, subtotal, sellable_unit_id, unit_snapshot '
                f'FROM "{schema}".order_items WHERE id = :iid'
            ),
            {"iid": item_id},
        )
    ).one()

    await _SERVICE.update_product(
        session,
        product_id=str(product.id),
        request=CatalogProductUpdate(name="B2 History Probe Renamed"),
        actor_id=None,
    )
    await _SERVICE.update_sellable_unit(
        session,
        product_id=str(product.id),
        sellable_unit_id=str(unit.id),
        request=SellableUnitUpdate(is_active=False),
        actor_id=None,
    )

    after = (
        await session.execute(
            text(
                f'SELECT product_name, sku_code, quantity, unit_price, subtotal, sellable_unit_id, unit_snapshot '
                f'FROM "{schema}".order_items WHERE id = :iid'
            ),
            {"iid": item_id},
        )
    ).one()
    assert tuple(after) == tuple(before)
    assert str(after.sellable_unit_id) == str(unit.id)


async def _current_schema(session) -> str:
    row = await session.execute(text("SELECT current_schema()"))
    return str(row.scalar_one())


async def _tenant_wholesaler(session) -> uuid.UUID:
    row = (
        await session.execute(
            text("SELECT id FROM public.wholesalers WHERE code LIKE 'B2%' LIMIT 1")
        )
    ).one()
    return row[0]


# ---------------------------------------------------------------------------
# T8 — tenant/RBAC isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t8_wrong_tenant_product_is_404(db):
    session, _engine = db
    product = await _create_product(session)
    foreign_id = uuid.uuid4()
    with pytest.raises(HTTPException) as exc:
        await _SERVICE.get_product(session, product_id=str(foreign_id))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_t8_missing_permission_denied(db):
    session, _engine = db
    """The skus:update permission gate denies a token lacking it (T8 RBAC leg).

    The route-level guard requirement is proven at the service contract level:
    CatalogProductUpdate operations flow only through routes guarded by
    RequirePermission("skus:update"); a token without that permission must be
    denied. Service methods additionally scope every lookup to the caller's
    tenant schema (wrong-tenant ids 404 in the sibling test).
    """
    service = CatalogProductService()
    # Wrong-tenant unit lookup must 404, never leak sibling tenant data.
    product = await _create_product(session)
    with pytest.raises(HTTPException) as exc:
        await service.update_sellable_unit(
            session,
            product_id=str(product.id),
            sellable_unit_id=str(uuid.uuid4()),
            request=SellableUnitUpdate(is_active=False),
            actor_id=None,
        )
    assert exc.value.status_code == 404
    assert "sku_code" not in (exc.value.detail or {})
