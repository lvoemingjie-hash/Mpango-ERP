"""Schema-contract guard for tenant payments and retailer_prices tables.

Validates that the table definitions in bootstrap_tenant_schema.py
and the running tenant schema (if available) satisfy the minimum contract
required by their respective repositories.

Contract requirements - payments:
  - Column: retailer_id  (UUID, NOT NULL)
  - Column: transaction_id (VARCHAR, nullable)
  - Index: ix_payments_order_id
  - Index: uq_payments_transaction_id  (partial unique, WHERE transaction_id IS NOT NULL)

Contract requirements - retailer_prices (mirrors migration 017):
  - Column: retailer_id  (UUID, NOT NULL)
  - Column: sku_id       (UUID, NOT NULL)
  - Column: price        (NUMERIC(12,2), NOT NULL)
  - Constraint: uq_retailer_prices_retailer_sku  UNIQUE (retailer_id, sku_id)
  - Constraint: ck_retailer_prices_positive_price CHECK (price > 0)
  - Index: ix_retailer_prices_retailer_id
  - Index: ix_retailer_prices_sku_id
  - Audit: created_at, updated_at, is_deleted all NOT NULL

Run:
    poetry run pytest tests/test_payments_schema_contract.py -q --tb=short
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.async_test_utils import run_coroutine


LIVE_TENANT_SCHEMA = os.environ.get(
    "PAYMENTS_SCHEMA_LIVE_TENANT_SCHEMA",
    os.environ.get("TEST_TENANT_SCHEMA", "t_test"),
)
LIVE_SCHEMA_GATE_ENABLED = os.environ.get("PAYMENTS_SCHEMA_REQUIRE_LIVE") == "1"


# ---------------------------------------------------------------------------
# 1. Static DDL analysis — always runs, no DB needed
# ---------------------------------------------------------------------------

BOOTSTRAP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_tenant_schema.py"


@pytest.fixture()
def bootstrap_source() -> str:
    return BOOTSTRAP_PATH.read_text(encoding="utf-8")


def _extract_payments_block(source: str) -> str:
    """Extract the payments CREATE TABLE DDL block from bootstrap source.

    Identifies the closing line by detecting ')' immediately followed by
    a Python string close quote — distinguishing the SQL paren close from
    function-call parens like gen_random_uuid().

    In the bootstrap source, a closing line looks like:
        "created_by UUID, updated_by UUID)",
    Where ')' is the SQL paren close, '"' is the Python string close,
    and ',' is the Python list separator.
    A *non-closing* line like gen_random_uuid()," ends with ',"' not ')"'.
    """
    lines = source.splitlines()
    start = None
    for i, line in enumerate(lines):
        if '"{ts}".payments' in line and "CREATE TABLE" in line:
            start = i
            break

    assert start is not None, "payments CREATE TABLE not found in bootstrap_tenant_schema.py"

    block_lines = []
    for line in lines[start:]:
        block_lines.append(line)
        stripped = line.rstrip()
        # SQL ')' immediately followed by Python string close quote
        if (stripped.endswith(')",') or stripped.endswith(')"')
                or stripped.endswith(")',") or stripped.endswith(")'")):
            break

    return "\n".join(block_lines)


def _extract_uq_transaction_id_block(source: str) -> str:
    """Extract the uq_payments_transaction_id index DDL from bootstrap source.

    The index DDL is a multi-line Python implicit string concatenation:
        f'CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_transaction_id '
        f'ON "{ts}".payments (transaction_id) '
        f"WHERE transaction_id IS NOT NULL",
    """
    lines = source.splitlines()
    start = None
    for i, line in enumerate(lines):
        if "uq_payments_transaction_id" in line and "CREATE" in line:
            start = i
            break

    assert start is not None, "uq_payments_transaction_id index DDL not found in bootstrap source"

    block_lines = []
    for line in lines[start:]:
        block_lines.append(line)
        stripped = line.rstrip()
        # Python implicit concatenation ends at line with trailing comma after quote
        if stripped.endswith('",') or stripped.endswith("',"):
            break

    return "\n".join(block_lines)


class TestBootstrapDDLContract:
    """Verify bootstrap_tenant_schema.py DDL contains required columns and indexes."""

    def test_payments_has_retailer_id(self, bootstrap_source: str) -> None:
        block = _extract_payments_block(bootstrap_source)
        assert "retailer_id" in block, (
            "bootstrap_tenant_schema.py payments DDL missing 'retailer_id' column"
        )

    def test_payments_has_transaction_id(self, bootstrap_source: str) -> None:
        block = _extract_payments_block(bootstrap_source)
        assert "transaction_id" in block, (
            "bootstrap_tenant_schema.py payments DDL missing 'transaction_id' column"
        )

    def test_payments_retailer_id_is_not_null(self, bootstrap_source: str) -> None:
        block = _extract_payments_block(bootstrap_source)
        for line in block.splitlines():
            stripped = line.strip().strip('",').strip("'").strip(",")
            if "retailer_id" in stripped:
                assert "NOT NULL" in stripped.upper(), (
                    f"retailer_id should be NOT NULL, got: {stripped}"
                )
                break
        else:
            pytest.fail("retailer_id line not found in payments block")

    def test_payments_transaction_id_is_nullable(self, bootstrap_source: str) -> None:
        block = _extract_payments_block(bootstrap_source)
        for line in block.splitlines():
            stripped = line.strip().strip('",').strip("'").strip(",")
            if "transaction_id" in stripped:
                assert "NOT NULL" not in stripped.upper(), (
                    f"transaction_id should be nullable, got: {stripped}"
                )
                break
        else:
            pytest.fail("transaction_id line not found in payments block")

    def test_payments_preserves_reference_number(self, bootstrap_source: str) -> None:
        block = _extract_payments_block(bootstrap_source)
        assert "reference_number" in block, (
            "reference_number column was removed — additive alignment only"
        )

    def test_payments_has_order_id_index(self, bootstrap_source: str) -> None:
        assert "ix_payments_order_id" in bootstrap_source, (
            "bootstrap_tenant_schema.py missing exact index name 'ix_payments_order_id'"
        )

    def test_payments_has_transaction_id_partial_unique_index(self, bootstrap_source: str) -> None:
        block = _extract_uq_transaction_id_block(bootstrap_source)
        assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_transaction_id" in block, (
            "uq_payments_transaction_id DDL missing 'CREATE UNIQUE INDEX IF NOT EXISTS' statement"
        )
        assert 'ON "{ts}".payments (transaction_id)' in block, (
            "uq_payments_transaction_id DDL must target payments (transaction_id)"
        )
        assert "WHERE transaction_id IS NOT NULL" in block, (
            "uq_payments_transaction_id DDL must have partial condition: WHERE transaction_id IS NOT NULL"
        )

    def test_index_names_match_migration_021(self, bootstrap_source: str) -> None:
        """Ensure bootstrap index names are exactly aligned with migration 021."""
        payments_block = _extract_payments_block(bootstrap_source)
        uq_block = _extract_uq_transaction_id_block(bootstrap_source)
        # ix_payments_order_id — single-line DDL, exact name check
        assert "ix_payments_order_id" in bootstrap_source, (
            "bootstrap uses non-standard order_id index name — must be ix_payments_order_id"
        )
        # uq_payments_transaction_id must live in index DDL, not in CREATE TABLE block
        assert "uq_payments_transaction_id" not in payments_block, (
            "uq_payments_transaction_id should be in index DDL, not in CREATE TABLE block"
        )
        assert "uq_payments_transaction_id" in uq_block, (
            "bootstrap uses non-standard transaction_id index name — must be uq_payments_transaction_id"
        )


# ---------------------------------------------------------------------------
# 2. Live schema verification — runs against Docker t_dev if available
# ---------------------------------------------------------------------------

def _get_db_urls() -> list[str]:
    """Use only the explicitly authorized test database."""
    test_url = os.environ.get("TEST_DATABASE_URL", "")
    return [test_url] if test_url else []


def _to_async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _require_live_table(table_name: str) -> None:
    """Fail closed when an explicitly requested live contract is unavailable."""
    urls = _get_db_urls()
    if not urls:
        pytest.fail("live schema gate requires TEST_DATABASE_URL")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(_to_async_url(urls[0]), pool_pre_ping=True)

    async def _check() -> bool:
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema=:schema AND table_name=:table LIMIT 1"
                    ),
                    {"schema": LIVE_TENANT_SCHEMA, "table": table_name},
                )
                return result.first() is not None
        finally:
            await engine.dispose()

    try:
        present = run_coroutine(_check())
    except Exception as exc:
        pytest.fail(f"live schema gate database is unavailable ({type(exc).__name__})")
    if not present:
        pytest.fail(
            f"{LIVE_TENANT_SCHEMA}.{table_name} is missing; "
            "live schema gates never bootstrap or repair the validation target"
        )


@pytest.fixture(scope="module")
def live_payments_table() -> str:
    _require_live_table("payments")
    return LIVE_TENANT_SCHEMA


@pytest.fixture(scope="module")
def live_retailer_prices_table() -> str:
    _require_live_table("retailer_prices")
    return LIVE_TENANT_SCHEMA


@pytest.mark.skipif(
    not LIVE_SCHEMA_GATE_ENABLED,
    reason="set PAYMENTS_SCHEMA_REQUIRE_LIVE=1 for prepared-schema verification",
)
@pytest.mark.usefixtures("live_payments_table")
class TestLiveSchemaContract:
    """Verify the configured live tenant payments table satisfies the contract."""

    @pytest.fixture()
    async def payment_columns(self):
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        url = _to_async_url(_get_db_urls()[0])
        engine = create_async_engine(url)

        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT column_name, is_nullable, data_type "
                "FROM information_schema.columns "
                "WHERE table_schema=:schema AND table_name='payments' "
                "ORDER BY ordinal_position"
            ), {"schema": LIVE_TENANT_SCHEMA})
            cols = {row[0]: {"nullable": row[1], "type": row[2]} for row in result}
        await engine.dispose()
        return cols

    @pytest.fixture()
    async def payment_indexes(self):
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        url = _to_async_url(_get_db_urls()[0])
        engine = create_async_engine(url)

        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE schemaname=:schema AND tablename='payments'"
            ), {"schema": LIVE_TENANT_SCHEMA})
            idxs = {row[0]: row[1] for row in result}
        await engine.dispose()
        return idxs

    def test_live_has_retailer_id(self, payment_columns):
        assert "retailer_id" in payment_columns, "t_dev.payments missing retailer_id"

    def test_live_retailer_id_not_null(self, payment_columns):
        assert payment_columns.get("retailer_id", {}).get("nullable") == "NO", (
            "t_dev.payments.retailer_id must be NOT NULL"
        )

    def test_live_has_transaction_id(self, payment_columns):
        assert "transaction_id" in payment_columns, "t_dev.payments missing transaction_id"

    def test_live_transaction_id_nullable(self, payment_columns):
        assert payment_columns.get("transaction_id", {}).get("nullable") == "YES", (
            "t_dev.payments.transaction_id must be nullable"
        )

    def test_live_has_order_id_index(self, payment_indexes):
        assert "ix_payments_order_id" in payment_indexes, (
            "t_dev.payments missing ix_payments_order_id index"
        )

    def test_live_has_transaction_id_partial_unique(self, payment_indexes):
        assert "uq_payments_transaction_id" in payment_indexes, (
            "t_dev.payments missing uq_payments_transaction_id index"
        )
        idxdef = payment_indexes["uq_payments_transaction_id"]
        assert "IS NOT NULL" in idxdef, (
            "uq_payments_transaction_id must be partial unique (WHERE transaction_id IS NOT NULL)"
        )


# ---------------------------------------------------------------------------
# 3. retailer_prices - static DDL analysis (mirrors migration 017 contract)
# ---------------------------------------------------------------------------


def _extract_retailer_prices_block(source: str) -> str:
    """Extract the retailer_prices CREATE TABLE DDL block from bootstrap source."""
    lines = source.splitlines()
    start = None
    for i, line in enumerate(lines):
        if '"{ts}".retailer_prices' in line and "CREATE TABLE" in line:
            start = i
            break

    assert start is not None, "retailer_prices CREATE TABLE not found in bootstrap_tenant_schema.py"

    block_lines = []
    for line in lines[start:]:
        block_lines.append(line)
        stripped = line.rstrip()
        if (stripped.endswith(')",') or stripped.endswith(')"')
                or stripped.endswith(")',") or stripped.endswith(")'")):
            break

    return "\n".join(block_lines)


class TestRetailerPricesDDLContract:
    """Verify bootstrap_tenant_schema.py retailer_prices DDL matches migration 017."""

    def test_retailer_prices_has_retailer_id(self, bootstrap_source: str) -> None:
        block = _extract_retailer_prices_block(bootstrap_source)
        assert "retailer_id" in block, (
            "bootstrap_tenant_schema.py retailer_prices DDL missing 'retailer_id' column"
        )

    def test_retailer_prices_has_sku_id(self, bootstrap_source: str) -> None:
        block = _extract_retailer_prices_block(bootstrap_source)
        assert "sku_id" in block, (
            "bootstrap_tenant_schema.py retailer_prices DDL missing 'sku_id' column"
        )

    def test_retailer_prices_has_price(self, bootstrap_source: str) -> None:
        block = _extract_retailer_prices_block(bootstrap_source)
        assert "price" in block, (
            "bootstrap_tenant_schema.py retailer_prices DDL missing 'price' column"
        )

    def test_retailer_id_is_not_null(self, bootstrap_source: str) -> None:
        block = _extract_retailer_prices_block(bootstrap_source)
        for line in block.splitlines():
            stripped = line.strip().strip('",').strip("'").strip(",")
            if "retailer_id" in stripped:
                assert "NOT NULL" in stripped.upper(), (
                    f"retailer_id should be NOT NULL, got: {stripped}"
                )
                break
        else:
            pytest.fail("retailer_id line not found in retailer_prices block")

    def test_sku_id_is_not_null(self, bootstrap_source: str) -> None:
        block = _extract_retailer_prices_block(bootstrap_source)
        for line in block.splitlines():
            stripped = line.strip().strip('",').strip("'").strip(",")
            if "sku_id" in stripped:
                assert "NOT NULL" in stripped.upper(), (
                    f"sku_id should be NOT NULL, got: {stripped}"
                )
                break
        else:
            pytest.fail("sku_id line not found in retailer_prices block")

    def test_price_is_not_null(self, bootstrap_source: str) -> None:
        block = _extract_retailer_prices_block(bootstrap_source)
        for line in block.splitlines():
            stripped = line.strip().strip('",').strip("'").strip(",")
            if "price" in stripped and "retailer" not in stripped.lower():
                assert "NOT NULL" in stripped.upper(), (
                    f"price should be NOT NULL, got: {stripped}"
                )
                break
        else:
            pytest.fail("price line not found in retailer_prices block")

    def test_has_unique_constraint(self, bootstrap_source: str) -> None:
        assert "uq_retailer_prices_retailer_sku" in bootstrap_source, (
            "bootstrap_tenant_schema.py missing named unique constraint "
            "'uq_retailer_prices_retailer_sku'"
        )

    def test_has_check_constraint(self, bootstrap_source: str) -> None:
        assert "ck_retailer_prices_positive_price" in bootstrap_source, (
            "bootstrap_tenant_schema.py missing named check constraint "
            "'ck_retailer_prices_positive_price'"
        )

    def test_has_retailer_id_index(self, bootstrap_source: str) -> None:
        assert "ix_retailer_prices_retailer_id" in bootstrap_source, (
            "bootstrap_tenant_schema.py missing index 'ix_retailer_prices_retailer_id'"
        )

    def test_has_sku_id_index(self, bootstrap_source: str) -> None:
        assert "ix_retailer_prices_sku_id" in bootstrap_source, (
            "bootstrap_tenant_schema.py missing index 'ix_retailer_prices_sku_id'"
        )

    def test_created_at_is_not_null(self, bootstrap_source: str) -> None:
        block = _extract_retailer_prices_block(bootstrap_source)
        for line in block.splitlines():
            stripped = line.strip().strip('",').strip("'").strip(",")
            if "created_at" in stripped:
                assert "NOT NULL" in stripped.upper(), (
                    f"created_at should be NOT NULL (matching migration 017), got: {stripped}"
                )
                break
        else:
            pytest.fail("created_at line not found in retailer_prices block")

    def test_is_deleted_is_not_null(self, bootstrap_source: str) -> None:
        block = _extract_retailer_prices_block(bootstrap_source)
        for line in block.splitlines():
            stripped = line.strip().strip('",').strip("'").strip(",")
            if "is_deleted" in stripped:
                assert "NOT NULL" in stripped.upper(), (
                    f"is_deleted should be NOT NULL (matching migration 017), got: {stripped}"
                )
                break
        else:
            pytest.fail("is_deleted line not found in retailer_prices block")

    def test_price_is_numeric_12_2(self, bootstrap_source: str) -> None:
        block = _extract_retailer_prices_block(bootstrap_source)
        assert "NUMERIC(12,2)" in block or "numeric(12,2)" in block.lower(), (
            "retailer_prices.price must be NUMERIC(12,2) matching migration 017"
        )


# ---------------------------------------------------------------------------
# 4. Explicit read-only retailer_prices contract guard
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    not LIVE_SCHEMA_GATE_ENABLED,
    reason="set PAYMENTS_SCHEMA_REQUIRE_LIVE=1 for prepared-schema verification",
)
@pytest.mark.usefixtures("live_retailer_prices_table")
class TestLiveRetailerPricesContract:
    """Verify the configured live tenant retailer_prices migration contract."""

    @pytest.fixture()
    async def rp_columns(self):
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        url = _to_async_url(_get_db_urls()[0])
        engine = create_async_engine(url)

        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT column_name, is_nullable, data_type "
                "FROM information_schema.columns "
                "WHERE table_schema=:schema AND table_name='retailer_prices' "
                "ORDER BY ordinal_position"
            ), {"schema": LIVE_TENANT_SCHEMA})
            cols = {row[0]: {"nullable": row[1], "type": row[2]} for row in result}
        await engine.dispose()
        return cols

    @pytest.fixture()
    async def rp_indexes(self):
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        url = _to_async_url(_get_db_urls()[0])
        engine = create_async_engine(url)

        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE schemaname=:schema AND tablename='retailer_prices'"
            ), {"schema": LIVE_TENANT_SCHEMA})
            idxs = {row[0]: row[1] for row in result}
        await engine.dispose()
        return idxs

    @pytest.fixture()
    async def rp_constraints(self):
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        url = _to_async_url(_get_db_urls()[0])
        engine = create_async_engine(url)

        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT conname, contype FROM pg_constraint "
                "WHERE connamespace = (SELECT oid FROM pg_namespace WHERE nspname = :schema) "
                "AND conrelid = to_regclass(:qualified_table)"
            ), {
                "schema": LIVE_TENANT_SCHEMA,
                "qualified_table": f"{LIVE_TENANT_SCHEMA}.retailer_prices",
            })
            constraints = {row[0]: row[1] for row in result}
        await engine.dispose()
        return constraints

    # --- column existence + nullability ---

    def test_live_has_retailer_id(self, rp_columns):
        assert "retailer_id" in rp_columns, "t_dev.retailer_prices missing retailer_id"

    def test_live_retailer_id_not_null(self, rp_columns):
        assert rp_columns.get("retailer_id", {}).get("nullable") == "NO", (
            "t_dev.retailer_prices.retailer_id must be NOT NULL"
        )

    def test_live_has_sku_id(self, rp_columns):
        assert "sku_id" in rp_columns, "t_dev.retailer_prices missing sku_id"

    def test_live_sku_id_not_null(self, rp_columns):
        assert rp_columns.get("sku_id", {}).get("nullable") == "NO", (
            "t_dev.retailer_prices.sku_id must be NOT NULL"
        )

    def test_live_has_price(self, rp_columns):
        assert "price" in rp_columns, "t_dev.retailer_prices missing price"

    def test_live_price_not_null(self, rp_columns):
        assert rp_columns.get("price", {}).get("nullable") == "NO", (
            "t_dev.retailer_prices.price must be NOT NULL"
        )

    def test_live_created_at_not_null(self, rp_columns):
        assert rp_columns.get("created_at", {}).get("nullable") == "NO", (
            "t_dev.retailer_prices.created_at must be NOT NULL"
        )

    def test_live_updated_at_not_null(self, rp_columns):
        assert rp_columns.get("updated_at", {}).get("nullable") == "NO", (
            "t_dev.retailer_prices.updated_at must be NOT NULL"
        )

    def test_live_is_deleted_not_null(self, rp_columns):
        assert rp_columns.get("is_deleted", {}).get("nullable") == "NO", (
            "t_dev.retailer_prices.is_deleted must be NOT NULL"
        )

    # --- constraints ---

    def test_live_has_unique_constraint(self, rp_constraints):
        assert "uq_retailer_prices_retailer_sku" in rp_constraints, (
            "t_dev.retailer_prices missing unique constraint "
            "'uq_retailer_prices_retailer_sku'"
        )

    def test_live_has_check_constraint(self, rp_constraints):
        assert "ck_retailer_prices_positive_price" in rp_constraints, (
            "t_dev.retailer_prices missing check constraint "
            "'ck_retailer_prices_positive_price'"
        )

    # --- indexes ---

    def test_live_has_retailer_id_index(self, rp_indexes):
        assert "ix_retailer_prices_retailer_id" in rp_indexes, (
            "t_dev.retailer_prices missing ix_retailer_prices_retailer_id index"
        )

    def test_live_has_sku_id_index(self, rp_indexes):
        assert "ix_retailer_prices_sku_id" in rp_indexes, (
            "t_dev.retailer_prices missing ix_retailer_prices_sku_id index"
        )
