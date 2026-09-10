"""DC-12R1-MVP-L1-SKU-BC06-R1 — package_quantity vs retailer price validity.

Real PostgreSQL 16, real tenant schemas via the canonical bootstrap, real
concurrent connections with event barriers (no timing sleeps, no mocked SQL).

Contract (CTO-AUTH-DC12R1-MVP-L1-SKU-BC06-R1-RETAILER-PRICE-VALIDITY):

- ``retailer_prices`` rows are current/retired price CONFIGURATION, never
  transaction history. A soft-deleted row is retired configuration: it does
  NOT gate repackaging and must survive byte-identical as an audit record.
- CURRENT_RETAILER_PRICE_CONFIGURED := EXISTS retailer_prices
  WHERE sku_id = :sku_id AND is_deleted IS NOT TRUE (any retailer; no
  validity-window/is_active columns exist).
- ``price > 0`` is guaranteed by ck_retailer_prices_positive_price; a
  non-deleted NULL/non-positive price must fail closed as
  PRICE_DATA_INTEGRITY_RED, never be silently ignored.
- Current price configuration is an independent SKU_PACKAGE_QUANTITY_
  REPRICE_REQUIRED gate (structured 409), NOT the history lock.
- Real transaction history is a separate, stronger gate:
  SKU_PACKAGE_QUANTITY_IMMUTABLE_AFTER_USE. Zero-value inventory_stocks
  placeholder rows are NOT history and never block.
- This round performs NO automatic retailer_prices deletion/retirement/
  migration/recomputation.

Covered paths (both modification entries call the ONE shared guard in
services/package_identity.py, and set_price takes the SAME skus row lock):
- SKUService.update_sku                  (PUT /skus/{sku_code})
- CatalogProductService.update_sellable_unit
                                         (PUT /catalog-products/{id}/sellable-units/{uid})
- pricing_repository.set_price           (PUT /prices)

Sessions are closed defensively (finally) and ORM identity is captured into
plain strings up front: after a rollback every ORM attribute is expired and
touching it from async context raises MissingGreenlet.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio

# Task-private V3 database (throwaway container, URL-safe credential chosen
# for this task only; no percent-encoding semantics involved or claimed).
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://bc06r1:bc06r1-Tx9vQm4pWn7k@127.0.0.1:17755/test_bc06_backend",  # pragma: allowlist secret
)
os.environ.setdefault("MPANGO_ENV", "test")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from models.import_run import ImportRun  # noqa: E402
from models.order import Order, OrderItem, OrderStatus  # noqa: E402
from schemas.catalog import CatalogProductCreate, SellableUnitCreate, SellableUnitUpdate  # noqa: E402
from scripts.bootstrap_tenant_schema import bootstrap  # noqa: E402
from services.catalog_product_service import CatalogProductService  # noqa: E402
from services.import_service import ImportService  # noqa: E402
from services.intake_apply_service import IntakeApplyService  # noqa: E402
from services.package_identity import (  # noqa: E402
    CODE_IMMUTABLE_AFTER_USE,
    CODE_PRICE_DATA_INTEGRITY_RED,
    CODE_REPRICE_REQUIRED,
)
from services.sku_service import SKUService  # noqa: E402

DB_URL = os.environ["DATABASE_URL"]
ASYNC_DB_URL = DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

_SCHEMA = "t_bc06_r1"

_CATALOG = CatalogProductService()
_SKU_SERVICE = SKUService()
_IMPORT = ImportService()
_INTAKE = IntakeApplyService()

# The price-first serialization scenario is repeated: WITH the shared skus
# row lock every iteration must deterministically return REPRICE_REQUIRED;
# removing the lock exposes the pre-commit read window within a few
# iterations (see falsification M5).
PRICE_FIRST_ITERATIONS = 12


@pytest_asyncio.fixture
async def tenant_db():
    """One dedicated tenant schema, RESET per test: real PG16 tables via the
    canonical bootstrap (matching production shape). Teardown terminates any
    backend still holding schema locks (a failed test may leave sessions
    open) so the next test's DROP SCHEMA can never hang."""
    admin_engine = create_async_engine(ASYNC_DB_URL, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            await conn.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid()"
            ))
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE'))
    finally:
        await admin_engine.dispose()
    await bootstrap(_SCHEMA, ASYNC_DB_URL)
    yield _SCHEMA
    try:
        admin_engine = create_async_engine(ASYNC_DB_URL, isolation_level="AUTOCOMMIT")
        async with admin_engine.connect() as conn:
            await conn.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid()"
            ))
    finally:
        await admin_engine.dispose()


@pytest_asyncio.fixture
async def engine(tenant_db):
    eng = create_async_engine(ASYNC_DB_URL, future=True)
    yield eng
    await eng.dispose()


def _session_maker(eng):
    return async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


async def _bind_tenant_session(maker, schema: str) -> AsyncSession:
    """A session bound to the tenant schema exactly as the JWT request
    dependency prepares it (search_path scoped)."""
    session = maker()
    session.info["tenant_schema"] = schema
    session.info["tenant_id"] = str(_tenant_uuid(schema))
    await session.execute(text(f'SET search_path TO "{schema}", public'))
    return session


def _product_create(code: str, *, name: str = "BC06 Juice") -> CatalogProductCreate:
    return CatalogProductCreate(
        name=name,
        category="staples",
        is_active=True,
        sellable_units=[
            SellableUnitCreate(sku_code=code, unit="bottle", package_quantity=Decimal("1.000")),
        ],
    )


def _code(prefix: str) -> str:
    return f"BC06-{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _tenant_uuid(schema: str) -> uuid.UUID:
    """The tenant identity bound to every session AND written on tenant-scoped
    rows (import_runs, intake_*): the global tenant filter injects
    ``tenant_id == session.info['tenant_id']`` into ORM selects, so rows must
    carry the SAME uuid the session is bound to."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"bc06:{schema}")


async def _create_baseline_unit(session: AsyncSession, code: str) -> tuple[str, str, str]:
    """One product + one unit (package_quantity 1.000), committed. Returns
    plain (product_id, unit_id, sku_code) — safe to use after rollbacks."""
    product = await _CATALOG.create_product(session, request=_product_create(code), actor_id=None)
    await session.commit()
    return str(product.id), str(product.sellable_units[0].id), product.sellable_units[0].sku_code


async def _scalar(session: AsyncSession, sql: str, params=None):
    return (await session.execute(text(sql), params or {})).scalar_one()


async def _sku_row_tuple(session: AsyncSession, schema: str, unit_id: str) -> tuple:
    """Full skus row for before/after byte-comparison."""
    row = (
        await session.execute(
            text(
                f'SELECT id, catalog_product_id, sku_code, name, description, unit, '
                f'package_quantity, category, is_active, created_at, updated_at, '
                f'is_deleted, deleted_at, created_by, updated_by '
                f'FROM "{schema}".skus WHERE id = :sid'
            ),
            {"sid": unit_id},
        )
    ).fetchone()
    assert row is not None
    return tuple(row)


async def _stock_row_tuple(session: AsyncSession, schema: str, unit_id: str) -> tuple:
    row = (
        await session.execute(
            text(
                f'SELECT id, sku_id, quantity_on_hand, quantity_reserved, created_at, '
                f'updated_at, is_deleted, deleted_at, created_by, updated_by '
                f'FROM "{schema}".inventory_stocks WHERE sku_id = :sid'
            ),
            {"sid": unit_id},
        )
    ).fetchone()
    return tuple(row) if row else None


async def _price_rows(session: AsyncSession, schema: str, unit_id: str) -> list[tuple]:
    rows = (
        await session.execute(
            text(
                f'SELECT id, retailer_id, sku_id, price, created_at, updated_at, '
                f'is_deleted, deleted_at, created_by, updated_by '
                f'FROM "{schema}".retailer_prices WHERE sku_id = :sid '
                f'ORDER BY retailer_id'
            ),
            {"sid": unit_id},
        )
    ).fetchall()
    return [tuple(r) for r in rows]


async def _set_live_price(session: AsyncSession, unit_id: str, retailer_id, price) -> None:
    """The production write path (PUT /prices → set_price), committed."""
    from repositories.pricing_repository import set_price

    await set_price(
        db=session,
        retailer_id=retailer_id,
        sku_id=unit_id,
        price=Decimal(price),
        updated_by=None,
    )
    await session.commit()


async def _soft_delete_prices(session: AsyncSession, schema: str, unit_id: str) -> None:
    """Retire the SKU's price rows. Production has no retailer_prices delete
    path, so the retired state is fabricated directly at the SQL level."""
    await session.execute(
        text(
            f'UPDATE "{schema}".retailer_prices '
            f'SET is_deleted = TRUE, deleted_at = now() WHERE sku_id = :sid'
        ),
        {"sid": unit_id},
    )
    await session.commit()


def _assert_conflict(exc: HTTPException, entry: str, code: str) -> None:
    assert exc.status_code == 409, (
        f"{entry}: expected structured 409, got {exc.status_code}: {exc.detail}"
    )
    assert isinstance(exc.detail, dict), f"{entry}: detail must be a structured dict"
    assert exc.detail.get("code") == code, (
        f"{entry}: expected {code}, got {exc.detail.get('code')}"
    )


async def _update_qty_via_sku_entry(session: AsyncSession, sku_code: str, new_qty: Decimal):
    """The SKU-code modification entry (PUT /skus/{sku_code})."""
    return await _SKU_SERVICE.update_sku(
        session,
        sku_code=sku_code,
        name=None,
        description=None,
        unit=None,
        package_quantity=new_qty,
        category=None,
        is_active=None,
        updated_by=None,
    )


async def _update_qty_via_unit_entry(
    session: AsyncSession, product_id: str, unit_id: str, new_qty: Decimal | None
):
    """The sellable-unit modification entry
    (PUT /catalog-products/{id}/sellable-units/{uid})."""
    return await _CATALOG.update_sellable_unit(
        session,
        product_id=product_id,
        sellable_unit_id=unit_id,
        request=SellableUnitUpdate(package_quantity=new_qty),
        actor_id=None,
    )


# ---------------------------------------------------------------------------
# T1 — no SKU creation entry auto-creates retailer_prices rows; the automatic
#       zero-value inventory_stocks placeholder is NOT "SKU used"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_sku_creation_entries_create_zero_retailer_price_rows(engine, tenant_db):
    """create_sku / create_product / add_sellable_unit / import apply /
    intake apply must all leave retailer_prices untouched (COUNT == 0)."""
    maker = _session_maker(engine)
    session = await _bind_tenant_session(maker, tenant_db)
    try:
        # 1. SKUService.create_sku (implicit product creation)
        await _SKU_SERVICE.create_sku(
            session,
            catalog_product_id=None,
            sku_code=_code("CREATESKU"),
            name="BC06 Create SKU",
            description=None,
            unit="bottle",
            package_quantity=Decimal("1.000"),
            category=None,
            is_active=True,
            created_by=None,
        )
        # 2. CatalogProductService.create_product
        await _CATALOG.create_product(
            session, request=_product_create(_code("CPROD")), actor_id=None
        )
        # 3. CatalogProductService.add_sellable_unit
        base = await _CATALOG.create_product(
            session, request=_product_create(_code("CBASE"), name="BC06 Add Base"), actor_id=None
        )
        await _CATALOG.add_sellable_unit(
            session,
            product_id=str(base.id),
            request=SellableUnitCreate(
                sku_code=_code("CADD"), unit="case", package_quantity=Decimal("12.000")
            ),
            actor_id=None,
        )
        # 4. ImportService.apply (bulk SKU creation from a validated run)
        import_code = _code("CIMPORT")
        run = ImportRun(
            import_id=f"bc06-{uuid.uuid4().hex[:12]}",
            tenant_id=_tenant_uuid(tenant_db),
            status="validated",
            total_rows=1,
            mapping={
                "rows": [{"col_code": import_code, "col_name": "BC06 Imported"}],
                "field_mapping": {"col_code": "sku_code", "col_name": "name"},
            },
        )
        session.add(run)
        await session.flush()
        await _IMPORT.apply(session, import_id=run.import_id, on_conflict="skip")
        # 5. IntakeApplyService.apply_workspace (staged rows → official SKUs)
        workspace_id = uuid.uuid4()
        tenant_uuid = _tenant_uuid(tenant_db)
        upload_id = uuid.uuid4()
        intake_code = _code("CINTAKE")
        await session.execute(
            text(
                f'INSERT INTO "{tenant_db}".intake_workspaces '
                "(id, tenant_id, name, source_type, status, apply_status) "
                "VALUES (:id, :tid, 'BC06 workspace', 'CATALOG_REFRESH', "
                "'READY_FOR_EXPORT', 'not_applied')"
            ),
            {"id": workspace_id, "tid": tenant_uuid},
        )
        await session.execute(
            text(
                f'INSERT INTO "{tenant_db}".intake_uploads '
                "(id, tenant_id, workspace_id, filename, file_ext, file_size_bytes, sha256, "
                "status, row_count, column_count, headers_raw, headers_normalized) "
                "VALUES (:id, :tid, :wid, 'bc06.csv', 'csv', 12, :sha, 'PARSED', 1, 4, "
                "'[\"sku_code\",\"name\",\"unit\",\"category\"]'::jsonb, "
                "'{\"sku_code\":\"sku_code\",\"name\":\"name\",\"unit\":\"unit\","
                "\"category\":\"category\"}'::jsonb)"
            ),
            {"id": upload_id, "tid": tenant_uuid, "wid": workspace_id, "sha": "0" * 64},
        )
        await session.execute(
            text(
                f'INSERT INTO "{tenant_db}".intake_product_rows '
                "(id, tenant_id, workspace_id, upload_id, source_row_number, row_index, "
                "raw_values, normalized_values, mapping_version, sku_code, name, unit, "
                "category, review_status) "
                "VALUES (:id, :tid, :wid, :uid, 2, 0, '{}'::jsonb, '{}'::jsonb, 2, "
                ":code, 'BC06 Intake', 'bottle', 'staples', 'VALID')"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_uuid,
                "wid": workspace_id,
                "uid": upload_id,
                "code": intake_code,
            },
        )
        await _INTAKE.apply_workspace(
            session, tenant_id=tenant_uuid, workspace_id=workspace_id, user_id=None
        )
        await session.commit()

        price_count = await _scalar(
            session, f'SELECT COUNT(*) FROM "{tenant_db}".retailer_prices'
        )
        assert price_count == 0, (
            f"no SKU creation entry may auto-create retailer_prices rows; found {price_count}"
        )
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_zero_value_stock_placeholder_is_not_use_and_does_not_block(engine, tenant_db):
    """The automatic inventory_stocks placeholder row (zero quantities, created
    by ensure_stock_row) is NOT transaction history: repackaging a SKU that
    only has that placeholder row must succeed."""
    maker = _session_maker(engine)
    session = await _bind_tenant_session(maker, tenant_db)
    try:
        product_id, unit_id, sku_code = await _create_baseline_unit(
            session, _code("PLACEHOLDER")
        )

        stock = await _stock_row_tuple(session, tenant_db, unit_id)
        assert stock is not None, "ensure_stock_row must have created the placeholder row"
        assert Decimal(str(stock[2])) == 0 and Decimal(str(stock[3])) == 0, (
            f"placeholder stock must be zero-value, got {stock}"
        )

        await _update_qty_via_sku_entry(session, sku_code, Decimal("24.000"))
        await session.commit()

        row = await _sku_row_tuple(session, tenant_db, unit_id)
        assert Decimal(str(row[6])) == Decimal("24.000")
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# T2 — no history, no current price: repackage succeeds via BOTH entries;
#       same-value updates are never blocked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repackage_without_history_or_price_succeeds_via_both_entries(engine, tenant_db):
    maker = _session_maker(engine)
    session = await _bind_tenant_session(maker, tenant_db)
    try:
        product_id, unit_id, sku_code = await _create_baseline_unit(session, _code("CLEAN"))

        await _update_qty_via_sku_entry(session, sku_code, Decimal("12.000"))
        await session.commit()
        await _update_qty_via_unit_entry(session, product_id, unit_id, Decimal("24.000"))
        await session.commit()

        row = await _sku_row_tuple(session, tenant_db, unit_id)
        assert Decimal(str(row[6])) == Decimal("24.000")
        assert await _price_rows(session, tenant_db, unit_id) == []
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_same_value_repackage_is_never_blocked_even_with_live_price(engine, tenant_db):
    """The gate runs only on an ACTUAL package_quantity change: a same-value
    update must succeed even while current price configuration exists."""
    maker = _session_maker(engine)
    session = await _bind_tenant_session(maker, tenant_db)
    try:
        product_id, unit_id, sku_code = await _create_baseline_unit(session, _code("SAMEQTY"))
        await _set_live_price(session, unit_id, uuid.uuid4(), "100.00")

        await _update_qty_via_sku_entry(session, sku_code, Decimal("1.000"))  # same value
        await session.commit()
        await _update_qty_via_unit_entry(session, product_id, unit_id, Decimal("1.000"))
        await session.commit()

        row = await _sku_row_tuple(session, tenant_db, unit_id)
        assert Decimal(str(row[6])) == Decimal("1.000")
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# T3 + T8 — live price: BOTH entries return the structured 409 and the
#            blocked transactions leave ZERO data changes / no half-commit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_price_blocks_both_entries_with_zero_data_change(engine, tenant_db):
    maker = _session_maker(engine)
    session = await _bind_tenant_session(maker, tenant_db)
    try:
        product_id, unit_id, sku_code = await _create_baseline_unit(session, _code("LIVEPRICE"))
        await _set_live_price(session, unit_id, uuid.uuid4(), "123.45")

        check = await _bind_tenant_session(maker, tenant_db)
        sku_before = await _sku_row_tuple(check, tenant_db, unit_id)
        stock_before = await _stock_row_tuple(check, tenant_db, unit_id)
        prices_before = await _price_rows(check, tenant_db, unit_id)
        assert len(prices_before) == 1
        await check.close()

        # Entry 1: PUT /skus/{sku_code}
        with pytest.raises(HTTPException) as exc1:
            await _update_qty_via_sku_entry(session, sku_code, Decimal("12.000"))
        _assert_conflict(exc1.value, "update_sku entry", CODE_REPRICE_REQUIRED)
        await session.rollback()

        # Entry 2: PUT /catalog-products/{id}/sellable-units/{uid}
        with pytest.raises(HTTPException) as exc2:
            await _update_qty_via_unit_entry(session, product_id, unit_id, Decimal("12.000"))
        _assert_conflict(exc2.value, "update_sellable_unit entry", CODE_REPRICE_REQUIRED)
        await session.rollback()

        # Zero data change: sku row, stock row and price row are byte-identical.
        check = await _bind_tenant_session(maker, tenant_db)
        assert await _sku_row_tuple(check, tenant_db, unit_id) == sku_before
        assert await _stock_row_tuple(check, tenant_db, unit_id) == stock_before
        assert await _price_rows(check, tenant_db, unit_id) == prices_before
        await check.close()

        # The blocked session is immediately reusable: an unrelated write
        # commits cleanly (no half-commit, no poisoned transaction).
        await _CATALOG.add_sellable_unit(
            session,
            product_id=product_id,
            request=SellableUnitCreate(
                sku_code=_code("AFTER409"), unit="case", package_quantity=Decimal("6.000")
            ),
            actor_id=None,
        )
        await session.commit()
        check = await _bind_tenant_session(maker, tenant_db)
        persisted = (
            await check.execute(
                text(f'SELECT COUNT(*) FROM "{tenant_db}".skus WHERE sku_code LIKE :p'),
                {"p": "BC06-AFTER409-%"},
            )
        ).scalar_one()
        assert persisted == 1, "session reuse after the 409 must commit cleanly"
        await check.close()
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# T4 — only soft-deleted price rows: no price gate; audit row byte-identical
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_soft_deleted_price_rows_do_not_gate_and_stay_byte_identical(engine, tenant_db):
    maker = _session_maker(engine)
    session = await _bind_tenant_session(maker, tenant_db)
    try:
        product_id, unit_id, sku_code = await _create_baseline_unit(session, _code("RETIRED"))
        await _set_live_price(session, unit_id, uuid.uuid4(), "99.99")
        await _soft_delete_prices(session, tenant_db, unit_id)

        check = await _bind_tenant_session(maker, tenant_db)
        prices_before = await _price_rows(check, tenant_db, unit_id)
        await check.close()
        assert len(prices_before) == 1 and prices_before[0][6] is True, (
            "setup must produce exactly one soft-deleted (retired) price row"
        )

        await _update_qty_via_sku_entry(session, sku_code, Decimal("12.000"))
        await session.commit()
        await _update_qty_via_unit_entry(session, product_id, unit_id, Decimal("24.000"))
        await session.commit()

        check = await _bind_tenant_session(maker, tenant_db)
        prices_after = await _price_rows(check, tenant_db, unit_id)
        row = await _sku_row_tuple(check, tenant_db, unit_id)
        await check.close()
        assert prices_after == prices_before, (
            "the retired price audit row must survive byte-identical "
            "(no automatic deletion, retirement or recomputation)"
        )
        assert Decimal(str(row[6])) == Decimal("24.000")
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# T5 — multiple retailers: ANY non-deleted price row blocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_any_live_price_among_multiple_retailers_blocks(engine, tenant_db):
    maker = _session_maker(engine)
    session = await _bind_tenant_session(maker, tenant_db)
    try:
        product_id, unit_id, sku_code = await _create_baseline_unit(session, _code("MULTIRET"))
        await _set_live_price(session, unit_id, uuid.uuid4(), "10.00")
        await _set_live_price(session, unit_id, uuid.uuid4(), "20.00")
        await _soft_delete_prices(session, tenant_db, unit_id)
        # retailer 3: live; retailers 1-2: retired — one live row must block.
        await _set_live_price(session, unit_id, uuid.uuid4(), "30.00")

        with pytest.raises(HTTPException) as exc1:
            await _update_qty_via_sku_entry(session, sku_code, Decimal("12.000"))
        _assert_conflict(exc1.value, "update_sku entry", CODE_REPRICE_REQUIRED)
        await session.rollback()

        with pytest.raises(HTTPException) as exc2:
            await _update_qty_via_unit_entry(session, product_id, unit_id, Decimal("12.000"))
        _assert_conflict(exc2.value, "update_sellable_unit entry", CODE_REPRICE_REQUIRED)
        await session.rollback()

        check = await _bind_tenant_session(maker, tenant_db)
        row = await _sku_row_tuple(check, tenant_db, unit_id)
        await check.close()
        assert Decimal(str(row[6])) == Decimal("1.000"), "blocked repackage must not persist"
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# T6 — corrupt non-deleted price data must fail closed (PRICE_DATA_INTEGRITY_RED)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_corrupt_nonpositive_live_price_fails_closed_red(engine, tenant_db):
    """price > 0 is guaranteed by ck_retailer_prices_positive_price; a
    non-deleted non-positive row is therefore reachable only through dropped
    constraints or bypassed writes — exactly the corruption this gate must
    fail closed on instead of silently ignoring. (A NULL price is impossible
    under the live schema: retailer_prices.price is NOT NULL — verified
    below; the guard keeps a defensive NULL check regardless.)"""
    maker = _session_maker(engine)
    session = await _bind_tenant_session(maker, tenant_db)
    try:
        product_id, unit_id, sku_code = await _create_baseline_unit(session, _code("CORRUPT"))

        check = await _bind_tenant_session(maker, tenant_db)
        nullable = (
            await check.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema = :s AND table_name = 'retailer_prices' "
                    "AND column_name = 'price'"
                ),
                {"s": tenant_db},
            )
        ).scalar_one()
        await check.close()
        assert nullable == "NO", "live schema must keep retailer_prices.price NOT NULL"

        # Simulate the corruption: remove the guarantee, insert bad live rows.
        await session.execute(
            text(
                f'ALTER TABLE "{tenant_db}".retailer_prices '
                f"DROP CONSTRAINT ck_retailer_prices_positive_price"
            )
        )
        await session.execute(
            text(
                f'INSERT INTO "{tenant_db}".retailer_prices (retailer_id, sku_id, price) '
                f"VALUES (:r1, :sid, 0)"
            ),
            {"r1": str(uuid.uuid4()), "sid": unit_id},
        )
        await session.execute(
            text(
                f'INSERT INTO "{tenant_db}".retailer_prices (retailer_id, sku_id, price) '
                f"VALUES (:r2, :sid, -5.00)"
            ),
            {"r2": str(uuid.uuid4()), "sid": unit_id},
        )
        await session.commit()
        # Restore the contract constraint for future writes. NOT VALID is
        # required here: the deliberately corrupt rows must remain (they ARE
        # the simulated corruption), and a validating ADD CONSTRAINT would
        # (correctly) reject them.
        await session.execute(
            text(
                f'ALTER TABLE "{tenant_db}".retailer_prices '
                f"ADD CONSTRAINT ck_retailer_prices_positive_price "
                f"CHECK (price > 0) NOT VALID"
            )
        )
        await session.commit()

        for entry, runner in (
            ("update_sku entry", lambda: _update_qty_via_sku_entry(session, sku_code, Decimal("12.000"))),
            (
                "update_sellable_unit entry",
                lambda: _update_qty_via_unit_entry(session, product_id, unit_id, Decimal("12.000")),
            ),
        ):
            with pytest.raises(HTTPException) as exc:
                await runner()
            _assert_conflict(exc.value, entry, CODE_PRICE_DATA_INTEGRITY_RED)
            await session.rollback()

        check = await _bind_tenant_session(maker, tenant_db)
        row = await _sku_row_tuple(check, tenant_db, unit_id)
        await check.close()
        assert Decimal(str(row[6])) == Decimal("1.000"), "RED must leave the package unchanged"
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# T7 — real two-connection concurrency: set_price vs repackage, event barriers,
#      no sleeps, no mocked SQL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_price_first_then_repackage_returns_reprice_required(
    engine, tenant_db
):
    """A price flushed-then-committed BEFORE the repackaging attempt's shared
    lock acquisition must deterministically make BOTH modification entries
    return SKU_PACKAGE_QUANTITY_REPRICE_REQUIRED — the repackaging
    transaction cannot observe the pre-commit state."""
    maker = _session_maker(engine)
    retailer_id = uuid.uuid4()

    async def price_first_leg(
        entry: str, product_id: str, unit_id: str, sku_code: str
    ) -> str:
        """Two REAL concurrent connections, event-barrier synchronized:
        A flushes the price INSERT while holding the shared skus row lock;
        B enters its modification attempt only after that flush.

        A then keeps its transaction OPEN across B's entire scheduling window
        by yielding the event loop (asyncio.sleep(0): zero-duration
        cooperative yields, NOT wall-clock timing sleeps). With the shared
        skus row lock, B physically cannot pass its FOR UPDATE until A's
        commit releases it, so the gate decision always observes the
        committed price. Without the lock (falsification M5), B runs its
        whole gate decision against the still-uncommitted state and the
        mutation is exposed."""
        session_a = await _bind_tenant_session(maker, tenant_db)
        session_b = await _bind_tenant_session(maker, tenant_db)
        a_flushed = asyncio.Event()
        outcome: dict[str, str] = {}

        async def writer() -> None:
            from repositories.pricing_repository import set_price

            await set_price(
                db=session_a,
                retailer_id=retailer_id,
                sku_id=unit_id,
                price=Decimal("77.00"),
                updated_by=None,
            )
            # set_price flushed inside session_a: the price INSERT and the
            # skus row lock are HELD, uncommitted. Release connection B, then
            # hold the transaction open across B's ENTIRE gate decision by
            # pumping REAL round trips (re-reading our own uncommitted row —
            # never a wall-clock sleep). Each pump gives the event loop a
            # full IO cycle, so B's statements are serviced while the price
            # is provably still uncommitted.
            a_flushed.set()
            for _ in range(20):
                visible = await session_a.execute(
                    text(
                        "SELECT COUNT(*) FROM retailer_prices "
                        "WHERE sku_id = :sid AND is_deleted IS NOT TRUE"
                    ),
                    {"sid": unit_id},
                )
                assert visible.scalar_one() == 1, (
                    "writer must still observe its own uncommitted price INSERT"
                )
            await session_a.commit()  # releases the shared skus row lock

        async def repackager() -> None:
            await a_flushed.wait()
            try:
                if entry == "sku":
                    await _update_qty_via_sku_entry(session_b, sku_code, Decimal("12.000"))
                else:
                    await _update_qty_via_unit_entry(
                        session_b, product_id, unit_id, Decimal("12.000")
                    )
                await session_b.commit()
                outcome["result"] = "success"
            except HTTPException as exc:
                await session_b.rollback()
                _assert_conflict(exc, f"{entry} (iteration)", CODE_REPRICE_REQUIRED)
                outcome["result"] = "reprice_required_409"

        try:
            await asyncio.gather(
                asyncio.create_task(writer()), asyncio.create_task(repackager())
            )
        finally:
            await session_a.close()
            await session_b.close()
        return outcome["result"]

    for iteration in range(PRICE_FIRST_ITERATIONS):
        # A FRESH SKU per iteration: every leg is a true price-first race
        # (no committed price row from an earlier leg may pre-satisfy the
        # gate). Entries alternate so BOTH modification paths are exercised.
        session_i = await _bind_tenant_session(maker, tenant_db)
        try:
            product_id, unit_id, sku_code = await _create_baseline_unit(
                session_i, _code(f"CC{iteration}")
            )
        finally:
            await session_i.close()
        entry = "sku" if iteration % 2 == 0 else "unit"
        result = await price_first_leg(entry, product_id, unit_id, sku_code)
        assert result == "reprice_required_409", (
            f"iteration {iteration} ({entry}): price-first must gate the "
            f"repackage, got {result}"
        )

    # Final state: no package moved; each SKU carries exactly one live price
    # row at 77.00 written by the production set_price path.
    check = await _bind_tenant_session(maker, tenant_db)
    try:
        moved = (
            await check.execute(
                text(
                    f'SELECT COUNT(*) FROM "{tenant_db}".skus '
                    f"WHERE sku_code LIKE 'BC06-CC%' AND package_quantity <> 1"
                )
            )
        ).scalar_one()
        assert moved == 0, (
            "no iteration may persist a package_quantity change under price-first"
        )
        prices = (
            await check.execute(
                text(
                    f'SELECT COUNT(*) FROM "{tenant_db}".retailer_prices rp '
                    f'JOIN "{tenant_db}".skus s ON s.id = rp.sku_id '
                    f"WHERE s.sku_code LIKE 'BC06-CC%' "
                    f"AND rp.is_deleted IS NOT TRUE AND rp.price = 77.00"
                )
            )
        ).scalar_one()
        assert prices == PRICE_FIRST_ITERATIONS, (
            f"expected exactly one live 77.00 price per raced SKU, got {prices}"
        )
    finally:
        await check.close()


@pytest.mark.asyncio
async def test_concurrent_repackage_first_then_set_price_targets_new_definition(
    engine, tenant_db
):
    """Repackaging committed first (no price rows existed at its gate) is
    legal; the subsequent explicit set_price must succeed and apply to the
    NEW package definition — no automatic retirement/deletion of prices."""
    maker = _session_maker(engine)
    session_setup = await _bind_tenant_session(maker, tenant_db)
    try:
        product_id, unit_id, sku_code = await _create_baseline_unit(session_setup, _code("CCPKG"))
    finally:
        await session_setup.close()

    session_b = await _bind_tenant_session(maker, tenant_db)
    session_a = await _bind_tenant_session(maker, tenant_db)
    b_committed = asyncio.Event()

    async def repackager() -> None:
        try:
            await _update_qty_via_sku_entry(session_b, sku_code, Decimal("12.000"))
            await session_b.commit()
        finally:
            b_committed.set()

    async def price_writer() -> None:
        from repositories.pricing_repository import set_price

        await b_committed.wait()
        try:
            await set_price(
                db=session_a,
                retailer_id=uuid.uuid4(),
                sku_id=unit_id,
                price=Decimal("55.00"),
                updated_by=None,
            )
            await session_a.commit()
        except HTTPException as exc:
            await session_a.rollback()
            raise AssertionError(f"set_price after committed repackage must succeed: {exc.detail}")

    try:
        await asyncio.gather(
            asyncio.create_task(repackager()), asyncio.create_task(price_writer())
        )

        check = await _bind_tenant_session(maker, tenant_db)
        row = await _sku_row_tuple(check, tenant_db, unit_id)
        prices = await _price_rows(check, tenant_db, unit_id)
        await check.close()
        assert Decimal(str(row[6])) == Decimal("12.000"), "committed repackage must persist"
        assert (
            len(prices) == 1
            and prices[0][6] is False
            and prices[0][3] == Decimal("55.00")
        ), "the later explicit price must exist unchanged against the new package definition"
    finally:
        await session_a.close()
        await session_b.close()


# ---------------------------------------------------------------------------
# Transaction-history gate (independent category, contract item 10)
# ---------------------------------------------------------------------------


async def _insert_order_history(
    session: AsyncSession,
    *,
    unit_id: str,
    sku_code: str,
    unit: str,
    identity_status: str,
    order_status: OrderStatus = OrderStatus.VOIDED,
) -> None:
    """Fabricate a real transaction record. 'voided' is deliberate: a voided
    order is still a transaction that happened and must lock the package
    identity. Stable/linked rows reference sellable_unit_id; legacy rows
    reference the (never-reusable) sku_code."""
    order = Order(
        wholesaler_id=uuid.uuid4(),
        retailer_id=uuid.uuid4(),
        status=order_status,
        total_amount=Decimal("15.00"),
    )
    session.add(order)
    await session.flush()
    item = OrderItem(
        order_id=order.id,
        sellable_unit_id=None if identity_status == "legacy" else unit_id,
        identity_status=identity_status,
        product_name="BC06 Juice",
        sku_code=sku_code,
        unit_snapshot=None if identity_status == "legacy" else unit,
        quantity=3,
        unit_price=Decimal("5.00"),
        subtotal=Decimal("15.00"),
    )
    session.add(item)
    await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("identity_status", ["stable", "linked_legacy", "legacy"])
async def test_transaction_history_locks_repackage_immutable_after_use(
    engine, tenant_db, identity_status
):
    maker = _session_maker(engine)
    session = await _bind_tenant_session(maker, tenant_db)
    try:
        product_id, unit_id, sku_code = await _create_baseline_unit(session, _code("HIST"))
        unit_row = await _sku_row_tuple(session, tenant_db, unit_id)
        await _insert_order_history(
            session,
            unit_id=unit_id,
            sku_code=sku_code,
            unit=str(unit_row[5]),
            identity_status=identity_status,
        )

        with pytest.raises(HTTPException) as exc1:
            await _update_qty_via_sku_entry(session, sku_code, Decimal("12.000"))
        _assert_conflict(exc1.value, "update_sku entry", CODE_IMMUTABLE_AFTER_USE)
        await session.rollback()

        with pytest.raises(HTTPException) as exc2:
            await _update_qty_via_unit_entry(session, product_id, unit_id, Decimal("12.000"))
        _assert_conflict(exc2.value, "update_sellable_unit entry", CODE_IMMUTABLE_AFTER_USE)
        await session.rollback()

        check = await _bind_tenant_session(maker, tenant_db)
        row = await _sku_row_tuple(check, tenant_db, unit_id)
        await check.close()
        assert Decimal(str(row[6])) == Decimal("1.000")
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_history_lock_dominates_the_price_gate(engine, tenant_db):
    """History and current price configuration are independent gates; real
    transaction history is the stronger category and must be reported."""
    maker = _session_maker(engine)
    session = await _bind_tenant_session(maker, tenant_db)
    try:
        product_id, unit_id, sku_code = await _create_baseline_unit(session, _code("HISTPRICE"))
        unit_row = await _sku_row_tuple(session, tenant_db, unit_id)
        await _set_live_price(session, unit_id, uuid.uuid4(), "42.00")
        await _insert_order_history(
            session,
            unit_id=unit_id,
            sku_code=sku_code,
            unit=str(unit_row[5]),
            identity_status="stable",
        )

        with pytest.raises(HTTPException) as exc:
            await _update_qty_via_sku_entry(session, sku_code, Decimal("12.000"))
        _assert_conflict(exc.value, "update_sku entry", CODE_IMMUTABLE_AFTER_USE)
        await session.rollback()
    finally:
        await session.close()
