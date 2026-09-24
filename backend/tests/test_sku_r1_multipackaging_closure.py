"""DC-12R1-MVP-L1-SKU-R0-M1-R1-R1 — product-level multipackaging closure.

Real PostgreSQL 16, real tenant schemas via the canonical bootstrap.

Part 1 — concurrent duplicate SKU-code race (the 409 defect):
  Two synchronized sessions (two connections = two concurrent requests) insert
  the SAME tenant-local SKU code through the SAME public service path used by
  POST /catalog-products. The friendly precheck passes for both; correctness
  comes from the named unique index ux_skus_sku_code at flush:
    - exactly ONE success, exactly ONE SKU_EXISTS / 409
    - ZERO IntegrityError leaks (never a 500)
    - exactly ONE persisted SKU row per race (the loser's transaction rolled
      back whole, including its parent catalog product)
    - the loser session is usable immediately afterward
  The race is repeated (both session orders, multiple iterations) to
  demonstrate deterministic behavior.

Part 1b — unrelated integrity violations are NOT mislabeled:
  A check-constraint violation (ck_skus_package_quantity_positive) flowing
  through the SAME guarded flush propagates UNCHANGED — never SKU_EXISTS/409 —
  while the classifier is True for a real unique-code violation.

Part 2 — product-level catalog contract:
  - one product container per CatalogProduct; active units nested in
    deterministic (package_quantity, sku_code) order; products in
    deterministic (name, id) order
  - product-level stock/can_order aggregation
"""

from __future__ import annotations

import asyncio
import os
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://r1_auth:r1auth-4uJm7Kk8Ll2Z@127.0.0.1:17751/test_r1_multipack_backend",
)
os.environ.setdefault("MPANGO_ENV", "test")
# R5-F2 P2-02: no REPORTING_USER_PASSWORD literal here — pytest's canonical
# conftest.py resolves that test-only environment before test-module import.

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from models.catalog_product import CatalogProduct  # noqa: E402
from models.sku import SKU  # noqa: E402
from schemas.catalog import CatalogProductCreate, SellableUnitCreate  # noqa: E402
from schemas.client import StockLevel  # noqa: E402
from scripts.bootstrap_tenant_schema import bootstrap  # noqa: E402
from services.catalog_product_service import CatalogProductService  # noqa: E402
from services.sku_integrity import (  # noqa: E402
    SKU_CODE_UNIQUE_CONSTRAINTS,
    flush_skus_or_409,
    is_sku_code_unique_violation,
)

DB_URL = os.environ["DATABASE_URL"]
ASYNC_DB_URL = DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

_SERVICE = CatalogProductService()

RACE_ITERATIONS = 6  # both session orders, repeated — outcome must be invariant


@pytest_asyncio.fixture
async def tenant_db():
    """One dedicated tenant schema, RESET per test: real PG16 tables via the
    canonical bootstrap (matching production shape). Residue from earlier
    runs must never influence exact-count assertions."""
    schema = "t_r1_multipack"
    admin_engine = create_async_engine(ASYNC_DB_URL, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    finally:
        await admin_engine.dispose()
    await bootstrap(schema, ASYNC_DB_URL)
    yield schema


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
    session.info["tenant_id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"r1:{schema}"))
    await session.execute(text(f'SET search_path TO "{schema}", public'))
    return session


def _product_create(code: str, *, name: str = "R1 Race Juice") -> CatalogProductCreate:
    return CatalogProductCreate(
        name=name,
        category="staples",
        is_active=True,
        sellable_units=[
            SellableUnitCreate(sku_code=code, unit="bottle", package_quantity=Decimal("1.000")),
        ],
    )


# ---------------------------------------------------------------------------
# Part 1 — concurrent duplicate SKU-code race
# ---------------------------------------------------------------------------


async def _one_race(schema: str, eng) -> tuple[str, str]:
    """One synchronized two-session race on one SKU code.

    Both sessions run create_product concurrently (precheck passes for both);
    correctness is decided by ux_skus_sku_code at flush. Returns the outcome
    pair ('success' | 'sku_exists_409') in session order.
    """
    code = f"R1RACE-{uuid.uuid4().hex[:8].upper()}"
    maker = _session_maker(eng)
    session_a = await _bind_tenant_session(maker, schema)
    session_b = await _bind_tenant_session(maker, schema)

    start = asyncio.Event()
    outcomes: dict[str, str] = {}

    async def attempt(label: str, session: AsyncSession) -> None:
        await start.wait()
        try:
            await _SERVICE.create_product(session, request=_product_create(code), actor_id=None)
            await session.commit()
            outcomes[label] = "success"
        except HTTPException as exc:
            await session.rollback()
            assert exc.status_code == 409, (
                f"{label}: expected 409 SKU_EXISTS, got {exc.status_code}: {exc.detail}"
            )
            assert isinstance(exc.detail, dict) and exc.detail.get("code") == "SKU_EXISTS", (
                f"{label}: expected SKU_EXISTS detail, got {exc.detail}"
            )
            assert "already exists" in exc.detail.get("message", ""), (
                f"{label}: unexpected message {exc.detail}"
            )
            outcomes[label] = "sku_exists_409"

    task_a = asyncio.create_task(attempt("a", session_a))
    task_b = asyncio.create_task(attempt("b", session_b))
    await asyncio.sleep(0.05)  # both tasks park on the start gate
    start.set()
    await asyncio.gather(task_a, task_b)

    await session_a.close()
    await session_b.close()
    return outcomes["a"], outcomes["b"]


@pytest.mark.asyncio
async def test_concurrent_duplicate_sku_code_races_deterministically(engine, tenant_db):
    """Repeated synchronized two-session race: ALWAYS exactly one success and
    exactly one SKU_EXISTS/409 — never 500, never double-insert."""
    for iteration in range(RACE_ITERATIONS):
        a_outcome, b_outcome = await _one_race(tenant_db, engine)
        assert sorted((a_outcome, b_outcome)) == ["sku_exists_409", "success"], (
            f"iteration {iteration}: outcomes {(a_outcome, b_outcome)} — "
            f"expected exactly one success and one SKU_EXISTS/409"
        )

    # Exactly ONE persisted SKU row per race (6 races -> 6 rows).
    async with _session_maker(engine)() as session:
        total = (
            await session.execute(
                text(f"SELECT COUNT(*) FROM \"{tenant_db}\".skus WHERE sku_code LIKE 'R1RACE-%'")
            )
        ).scalar_one()
    assert total == RACE_ITERATIONS, (
        f"expected exactly {RACE_ITERATIONS} persisted SKU rows (one per race), got {total}"
    )

    # The loser's whole transaction rolled back: exactly one parent product per race.
    async with _session_maker(engine)() as session:
        products = (
            await session.execute(
                text(
                    f"SELECT COUNT(*) FROM \"{tenant_db}\".catalog_products "
                    "WHERE name = 'R1 Race Juice'"
                )
            )
        ).scalar_one()
    assert products == RACE_ITERATIONS, (
        f"expected exactly {RACE_ITERATIONS} parent products (one per race), got {products}"
    )


@pytest.mark.asyncio
async def test_race_loser_session_is_immediately_usable_and_parent_row_rolled_back(engine, tenant_db):
    """After the 409 the loser session works again; its rolled-back transaction
    left no parent product behind."""
    code = f"R1USABLE-{uuid.uuid4().hex[:8].upper()}"
    maker = _session_maker(engine)
    session_a = await _bind_tenant_session(maker, tenant_db)
    session_b = await _bind_tenant_session(maker, tenant_db)

    start = asyncio.Event()
    outcomes: dict[str, str] = {}

    async def attempt(label: str, session: AsyncSession) -> None:
        await start.wait()
        try:
            await _SERVICE.create_product(
                session, request=_product_create(code, name="R1 Usable Juice"), actor_id=None
            )
            await session.commit()
            outcomes[label] = "success"
        except HTTPException as exc:
            await session.rollback()
            assert exc.status_code == 409 and exc.detail.get("code") == "SKU_EXISTS"
            outcomes[label] = "sku_exists_409"

    task_a = asyncio.create_task(attempt("a", session_a))
    task_b = asyncio.create_task(attempt("b", session_b))
    await asyncio.sleep(0.05)
    start.set()
    await asyncio.gather(task_a, task_b)

    assert sorted(outcomes.values()) == ["sku_exists_409", "success"]

    # The loser session is immediately usable: a fresh product persists.
    loser_session = session_a if outcomes["a"] == "sku_exists_409" else session_b
    survivor_code = f"R1AFTER-{uuid.uuid4().hex[:8].upper()}"
    survivor_product = await _SERVICE.create_product(
        loser_session, request=_product_create(survivor_code, name="R1 After Juice"), actor_id=None
    )
    await loser_session.commit()

    # Exactly ONE persisted SKU row for the raced code. The survivor product
    # written through the reused loser session must be durably persisted --
    # verified by id through an independent session.
    async with _session_maker(engine)() as check:
        raced_rows = (
            await check.execute(
                text(f"SELECT COUNT(*) FROM \"{tenant_db}\".skus WHERE sku_code = :c"),
                {"c": code},
            )
        ).scalar_one()
        survivor_rows = (
            await check.execute(
                text(
                    f"SELECT COUNT(*) FROM \"{tenant_db}\".catalog_products "
                    "WHERE id = :pid"
                ),
                {"pid": str(survivor_product.id)},
            )
        ).scalar_one()
        usable_products = (
            await check.execute(
                text(
                    f"SELECT COUNT(*) FROM \"{tenant_db}\".catalog_products "
                    "WHERE name = 'R1 Usable Juice'"
                )
            )
        ).scalar_one()
    assert raced_rows == 1, f"expected exactly 1 persisted SKU row for the raced code, got {raced_rows}"
    assert usable_products == 1, (
        f"loser's parent product must be rolled back; expected 1 product, got {usable_products}"
    )
    assert survivor_rows == 1, (
        "the product written through the reused loser session must be durably persisted; "
        f"got {survivor_rows}"
    )

    await session_a.close()
    await session_b.close()


@pytest.mark.asyncio
async def test_concurrent_add_sellable_unit_race_maps_to_409(engine, tenant_db):
    """The add-unit path (POST /catalog-products/{id}/sellable-units) is also
    race-safe: exactly one success + one SKU_EXISTS/409, never a 500."""
    code = f"R1ADD-{uuid.uuid4().hex[:8].upper()}"
    maker = _session_maker(engine)
    session_setup = await _bind_tenant_session(maker, tenant_db)
    product = await _SERVICE.create_product(
        session_setup,
        request=_product_create(f"R1ADDBASE-{uuid.uuid4().hex[:6].upper()}", name="R1 Add Juice"),
        actor_id=None,
    )
    await session_setup.commit()
    await session_setup.close()

    session_a = await _bind_tenant_session(maker, tenant_db)
    session_b = await _bind_tenant_session(maker, tenant_db)
    start = asyncio.Event()
    outcomes: list[str] = []

    async def add_unit(session: AsyncSession) -> None:
        await start.wait()
        try:
            await _SERVICE.add_sellable_unit(
                session,
                product_id=str(product.id),
                request=SellableUnitCreate(
                    sku_code=code, unit="case", package_quantity=Decimal("12.000")
                ),
                actor_id=None,
            )
            await session.commit()
            outcomes.append("success")
        except HTTPException as exc:
            await session.rollback()
            assert exc.status_code == 409 and exc.detail.get("code") == "SKU_EXISTS"
            outcomes.append("sku_exists_409")

    task_a = asyncio.create_task(add_unit(session_a))
    task_b = asyncio.create_task(add_unit(session_b))
    await asyncio.sleep(0.05)
    start.set()
    await asyncio.gather(task_a, task_b)
    await session_a.close()
    await session_b.close()

    assert sorted(outcomes) == ["sku_exists_409", "success"], f"unexpected outcomes: {outcomes}"


# ---------------------------------------------------------------------------
# Part 1b — unrelated IntegrityError is NOT mislabeled as SKU_EXISTS / 409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unrelated_integrity_violation_is_not_mapped_to_409(engine, tenant_db):
    """A check-constraint violation routed through the SAME guarded flush
    propagates as the original IntegrityError — never HTTPException/409 —
    and the classifier distinguishes it from a real unique-code violation."""
    maker = _session_maker(engine)
    session = await _bind_tenant_session(maker, tenant_db)

    product = await _SERVICE.create_product(
        session,
        request=_product_create(f"R1NEGBASE-{uuid.uuid4().hex[:6].upper()}", name="R1 Negative Juice"),
        actor_id=None,
    )
    await session.commit()
    # Capture identity BEFORE any rollback (rollback expires ORM state; a
    # lazy refresh in async context would raise MissingGreenlet).
    product_id = product.id
    base_code = product.sellable_units[0].sku_code

    # (a) REAL unique-code violation through the guarded flush → 409 mapped.
    duplicate = SKU(
        catalog_product_id=product_id,
        sku_code=base_code,  # existing code
        name="R1 Negative Juice",
        unit="case",
        package_quantity=Decimal("12.000"),
        is_active=True,
    )
    session.add(duplicate)
    with pytest.raises(HTTPException) as http_exc:
        await flush_skus_or_409(session, sku_code=duplicate.sku_code)
    assert http_exc.value.status_code == 409
    assert http_exc.value.detail.get("code") == "SKU_EXISTS"
    await session.rollback()

    # (b) UNRELATED check-constraint violation through the SAME guarded flush
    #     → original IntegrityError, NOT an HTTPException, NOT 409.
    bad_unit = SKU(
        catalog_product_id=product_id,
        sku_code=f"R1NEG-{uuid.uuid4().hex[:6].upper()}",
        name="R1 Negative Juice",
        unit="bottle",
        package_quantity=Decimal("0"),  # violates ck_skus_package_quantity_positive
        is_active=True,
    )
    session.add(bad_unit)
    with pytest.raises(IntegrityError) as integrity_exc:
        await flush_skus_or_409(session, sku_code=bad_unit.sku_code)
    await session.rollback()
    assert not isinstance(integrity_exc.value, HTTPException), (
        "unrelated IntegrityError must never be converted to a 409 HTTPException"
    )
    assert is_sku_code_unique_violation(integrity_exc.value) is False, (
        "a check-constraint violation must never classify as a SKU-code unique violation"
    )

    # (c) The classifier is bound to the exact constraint names: the runtime
    #     tenant-schema name AND the legacy alembic public-schema name — the
    #     same SKU-code uniqueness contract, nothing else.
    assert SKU_CODE_UNIQUE_CONSTRAINTS == ("skus_sku_code_key", "ux_skus_sku_code")
    await session.close()


# ---------------------------------------------------------------------------
# Part 2 — product-level catalog contract (route grouping/ordering/aggregation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_product_listing_groups_units_and_orders_deterministically(engine, tenant_db):
    """One container per CatalogProduct; units ordered by (package_quantity,
    sku_code); products ordered by (name, id); product-level aggregation."""
    maker = _session_maker(engine)
    session = await _bind_tenant_session(maker, tenant_db)

    suffix = uuid.uuid4().hex[:6].upper()
    await _SERVICE.create_product(
        session,
        request=CatalogProductCreate(
            name=f"R1 Beta {suffix}",
            category="staples",
            is_active=True,
            sellable_units=[
                SellableUnitCreate(sku_code=f"R1{suffix}-B-12", unit="case", package_quantity=Decimal("12.000")),
                SellableUnitCreate(sku_code=f"R1{suffix}-B-01", unit="bottle", package_quantity=Decimal("1.000")),
            ],
        ),
        actor_id=None,
    )
    await _SERVICE.create_product(
        session,
        request=CatalogProductCreate(
            name=f"R1 Alpha {suffix}",
            category="staples",
            is_active=True,
            sellable_units=[
                SellableUnitCreate(sku_code=f"R1{suffix}-A-01", unit="bottle", package_quantity=Decimal("1.000")),
            ],
        ),
        actor_id=None,
    )
    await session.commit()

    from api.v1.client.products import list_products

    class _FakeClient:
        retailer_id = uuid.uuid5(uuid.NAMESPACE_URL, f"r1-retailer:{tenant_db}")

    response = await list_products(
        page=1,
        size=50,
        category=None,
        search=None,
        client=_FakeClient(),  # type: ignore[arg-type]
        _perm=None,  # type: ignore[arg-type]
        db=session,  # type: ignore[arg-type]
    )
    payload = response.data
    r1_items = [item for item in payload["items"] if item["name"].startswith("R1 ")]
    assert len(r1_items) == 2, "exactly one container per CatalogProduct"
    # deterministic product order: 'R1 Alpha <suffix>' precedes 'R1 Beta <suffix>'
    assert [item["name"] for item in r1_items] == [
        f"R1 Alpha {suffix}",
        f"R1 Beta {suffix}",
    ], "products must be ordered by (name ASC, id ASC)"

    beta = next(item for item in r1_items if item["name"] == f"R1 Beta {suffix}")
    assert beta["unit_count"] == 2
    assert [u["sku_code"] for u in beta["units"]] == [
        f"R1{suffix}-B-01",
        f"R1{suffix}-B-12",
    ], "units must be ordered by (package_quantity, sku_code)"
    assert beta["id"], "product container id must be the CatalogProduct id"
    assert all(u["sellable_unit_id"] for u in beta["units"])

    alpha = next(item for item in r1_items if item["name"] == f"R1 Alpha {suffix}")
    assert alpha["stock_level"] == StockLevel.OUT_OF_STOCK  # the service creates an idempotent zero-quantity stock row
    assert alpha["in_stock"] is False and alpha["can_order"] is False

    await session.rollback()
    await session.close()


# ---------------------------------------------------------------------------
# P2-02 — secret hygiene: no direct REPORTING_USER_PASSWORD default
# ---------------------------------------------------------------------------


def test_module_sets_no_reporting_user_password_default():
    """R5-F2 P2-02: this module must never introduce an os.environ
    setdefault/assignment for the reporting password.

    Pytest's canonical conftest.py resolves that test-only environment before
    test-module import, so a module-level default is both redundant and a
    secret-hygiene defect. The inspected key is constructed here instead of
    embedding a second direct assignment."""
    import ast
    from pathlib import Path

    key = "_".join(("REPORTING", "USER", "PASSWORD"))
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    offenders: list[int] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "setdefault"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == key
        ):
            offenders.append(node.lineno)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value == key
                ):
                    offenders.append(node.lineno)
    assert not offenders, (
        f"direct REPORTING_USER_PASSWORD environ default/assignment must stay out of "
        f"this module (conftest.py owns it); found at lines {offenders}"
    )
