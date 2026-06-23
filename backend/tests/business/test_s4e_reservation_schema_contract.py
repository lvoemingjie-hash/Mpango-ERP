"""S4-E3 inventory reservation schema ownership contract."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from core.config import get_settings
from database.session import AsyncSessionLocal
from scripts.bootstrap_tenant_schema import bootstrap


REQUIRED_COLUMNS = {
    "id",
    "order_id",
    "order_item_id",
    "sku_id",
    "sku_code",
    "quantity",
    "status",
    "reserved_at",
    "consumed_at",
    "released_at",
    "reference_type",
    "reference_id",
    "created_at",
    "updated_at",
    "is_deleted",
    "deleted_at",
    "created_by",
    "updated_by",
}

REQUIRED_INDEXES = {
    "ix_inventory_reservations_order_id",
    "ix_inventory_reservations_sku_id",
    "ix_inventory_reservations_status",
    "ux_inventory_reservations_active_order_item",
}


async def _columns_for_schema(session, schema: str) -> set[str]:
    result = await session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = 'inventory_reservations'"
        ),
        {"schema": schema},
    )
    return {row.column_name for row in result.fetchall()}


async def _indexes_for_schema(session, schema: str) -> set[str]:
    result = await session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = :schema AND tablename = 'inventory_reservations'"
        ),
        {"schema": schema},
    )
    return {row.indexname for row in result.fetchall()}


@pytest.mark.asyncio
async def test_inventory_reservation_model_is_exported():
    from models import InventoryReservation

    assert InventoryReservation.__tablename__ == "inventory_reservations"


@pytest.mark.asyncio
async def test_inventory_reservations_table_contract_exists_in_test_schema(async_session):
    schema = async_session.info["tenant_schema"]

    columns = await _columns_for_schema(async_session, schema)
    indexes = await _indexes_for_schema(async_session, schema)

    assert REQUIRED_COLUMNS.issubset(columns)
    assert REQUIRED_INDEXES.issubset(indexes)

    constraints = await async_session.execute(
        text(
            "SELECT conname FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_namespace n ON n.oid = t.relnamespace "
            "WHERE n.nspname = :schema AND t.relname = 'inventory_reservations'"
        ),
        {"schema": schema},
    )
    constraint_names = {row.conname for row in constraints.fetchall()}
    assert "ck_inventory_reservations_quantity_positive" in constraint_names
    assert "ck_inventory_reservations_status" in constraint_names


@pytest.mark.asyncio
async def test_fresh_tenant_bootstrap_creates_inventory_reservations_contract():
    schema = f"t_s4e3_contract_{uuid.uuid4().hex[:12]}"
    settings = get_settings()

    try:
        await bootstrap(schema, settings.DATABASE_URL)
        async with AsyncSessionLocal() as session:
            columns = await _columns_for_schema(session, schema)
            indexes = await _indexes_for_schema(session, schema)

            assert REQUIRED_COLUMNS.issubset(columns)
            assert REQUIRED_INDEXES.issubset(indexes)
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await session.commit()
