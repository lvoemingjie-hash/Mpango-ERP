"""Schema-contract guard for tenant payments table.

Validates that the payments table definition in bootstrap_tenant_schema.py
and the running tenant schema (if available) satisfy the minimum contract
required by PaymentRepository.

Contract requirements:
  - Column: retailer_id  (UUID, NOT NULL)
  - Column: transaction_id (VARCHAR, nullable)
  - Index: ix_payments_order_id
  - Index: uq_payments_transaction_id  (partial unique, WHERE transaction_id IS NOT NULL)

Run:
    poetry run pytest tests/test_payments_schema_contract.py -q --tb=short
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


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
    """Get candidate database URLs from env and defaults."""
    candidates: list[str] = []
    env_url = os.environ.get("DATABASE_URL", "")
    if env_url:
        candidates.append(env_url)
    candidates.append("postgresql://mpango:mpango@127.0.0.1:5432/mpango_erp")
    return candidates


def _to_async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _can_connect_t_dev() -> bool:
    """Check if we can reach the t_dev schema in the Docker DB."""
    for url in _get_db_urls():
        async_url = _to_async_url(url)
        try:
            import asyncio
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine

            engine = create_async_engine(async_url, pool_pre_ping=True)

            async def _check():
                async with engine.connect() as conn:
                    await conn.execute(text(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema='t_dev' AND table_name='payments' LIMIT 1"
                    ))
                return True

            result = asyncio.run(_check())
            return result
        except Exception:
            continue
    return False


@pytest.mark.skipif(
    not _can_connect_t_dev(),
    reason="t_dev not reachable — run with Docker DB for live verification",
)
class TestLiveSchemaContract:
    """Verify running t_dev.payments satisfies the contract."""

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
                "WHERE table_schema='t_dev' AND table_name='payments' "
                "ORDER BY ordinal_position"
            ))
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
                "WHERE schemaname='t_dev' AND tablename='payments'"
            ))
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
