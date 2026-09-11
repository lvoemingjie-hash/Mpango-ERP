"""SKU-M1 durable catalog identity contract tests."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select, text
from models.catalog_product import CatalogProduct
from models.inventory_stock import InventoryStock
from models.order import Order, OrderItem, OrderStatus
from models.sku import SKU
from schemas.catalog import CatalogProductCreate, CatalogProductUpdate, SellableUnitCreate
from schemas.client import ClientOrderItemRequest as ClientOrderItemCreate
from schemas.order import WholesalerOrderItemCreate
from repositories.inventory_repository import InventoryRepository
from services.catalog_product_service import CatalogProductService
from services.inventory_service import InventoryService
from services.sku_service import SKUService


def test_catalog_create_requires_unique_packaging_codes() -> None:
    with pytest.raises(ValidationError, match="SKU codes must be unique"):
        CatalogProductCreate(
            name="Maize Flour",
            sellable_units=[
                SellableUnitCreate(sku_code="MAIZE-1KG"),
                SellableUnitCreate(sku_code="MAIZE-1KG"),
            ],
        )


@pytest.mark.parametrize("schema", [WholesalerOrderItemCreate, ClientOrderItemCreate])
def test_order_selector_rejects_non_uuid_stable_identity(schema) -> None:
    with pytest.raises(ValidationError, match="must be a UUID"):
        schema(sellable_unit_id="x" * 36, sku_code="MAIZE-1KG", quantity=1)


def test_sellable_unit_update_contract_cannot_change_code() -> None:
    from schemas.catalog import SellableUnitUpdate
    from schemas.sku import SKUUpdateRequest

    assert "sku_code" not in SellableUnitUpdate.model_fields
    assert "sku_code" not in SKUUpdateRequest.model_fields


@pytest.mark.asyncio
async def test_demo_seeder_delegates_to_canonical_bootstrap(monkeypatch) -> None:
    from database import session as session_module
    from scripts import bootstrap_tenant_schema, seed_demo_data

    canonical_bootstrap = AsyncMock()
    monkeypatch.setattr(bootstrap_tenant_schema, "bootstrap", canonical_bootstrap)
    monkeypatch.setattr(
        session_module.settings,
        "DATABASE_URL",
        "postgresql://localhost/sku_m1_test",
    )
    db = AsyncMock()

    await seed_demo_data._bootstrap_tenant_schema(db, "t_demo")

    db.rollback.assert_awaited_once_with()
    canonical_bootstrap.assert_awaited_once_with(
        "t_demo",
        "postgresql://localhost/sku_m1_test",
    )


@pytest.mark.asyncio
async def test_async_fixture_sku_shape_matches_runtime_contract(async_session) -> None:
    schema = async_session.info["tenant_schema"]
    rows = (
        await async_session.execute(
            text(
                "SELECT column_name, data_type, character_maximum_length, column_default "
                "FROM information_schema.columns "
                "WHERE table_schema=:schema AND table_name='skus' "
                "AND column_name IN ('name', 'unit', 'category') "
                "ORDER BY column_name"
            ),
            {"schema": schema},
        )
    ).all()

    assert rows == [
        ("category", "character varying", 64, None),
        ("name", "character varying", 255, None),
        ("unit", "character varying", 32, "'unit'::character varying"),
    ]


@pytest.mark.asyncio
async def test_product_rename_and_deactivation_preserve_history_and_unit_flags(async_session) -> None:
    service = CatalogProductService()
    product = await service.create_product(
        async_session,
        request=CatalogProductCreate(
            name="Original Name",
            sellable_units=[
                SellableUnitCreate(
                    sku_code="HISTORY-CASE-12",
                    unit="case",
                    package_quantity=Decimal("12"),
                    is_active=True,
                ),
                SellableUnitCreate(
                    sku_code="HISTORY-EACH-1",
                    unit="piece",
                    package_quantity=Decimal("1"),
                    is_active=False,
                ),
            ],
        ),
        actor_id=None,
    )
    active_unit = next(unit for unit in product.sellable_units if unit.sku_code == "HISTORY-CASE-12")
    inactive_unit = next(unit for unit in product.sellable_units if unit.sku_code == "HISTORY-EACH-1")
    order = Order(
        wholesaler_id=uuid.uuid4(),
        retailer_id=uuid.uuid4(),
        status=OrderStatus.DRAFT,
        total_amount=Decimal("150.00"),
        items=[
            OrderItem(
                sellable_unit_id=active_unit.id,
                identity_status="stable",
                product_name="Original Name",
                sku_code=active_unit.sku_code,
                unit_snapshot="case",
                quantity=3,
                unit_price=Decimal("50.00"),
                subtotal=Decimal("150.00"),
            )
        ],
    )
    async_session.add(order)
    await async_session.flush()

    await service.update_product(
        async_session,
        product_id=str(product.id),
        request=CatalogProductUpdate(name="Renamed Product", is_active=False),
        actor_id=None,
    )
    persisted_item = (
        await async_session.execute(
            select(OrderItem)
            .where(OrderItem.order_id == order.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()

    assert product.name == "Renamed Product"
    assert product.is_active is False
    assert active_unit.is_active is True
    assert inactive_unit.is_active is False
    assert persisted_item.product_name == "Original Name"
    assert persisted_item.sku_code == "HISTORY-CASE-12"
    assert persisted_item.unit_snapshot == "case"
    assert persisted_item.quantity == 3
    assert persisted_item.unit_price == Decimal("50.00")
    assert persisted_item.subtotal == Decimal("150.00")


@pytest.mark.asyncio
async def test_product_and_packaging_creation_initialize_zero_stock(async_session) -> None:
    service = CatalogProductService()
    product = await service.create_product(
        async_session,
        request=CatalogProductCreate(
            name="Stocked Product",
            sellable_units=[
                SellableUnitCreate(sku_code="STOCK-EACH", unit="piece"),
                SellableUnitCreate(sku_code="STOCK-CASE", unit="case", package_quantity=12),
            ],
        ),
        actor_id=None,
    )
    await service.add_sellable_unit(
        async_session,
        product_id=str(product.id),
        request=SellableUnitCreate(
            sku_code="STOCK-PALLET",
            unit="pallet",
            package_quantity=480,
        ),
        actor_id=None,
    )

    unit_ids = {
        unit.id
        for unit in (
            await service.get_product(async_session, product_id=str(product.id))
        ).sellable_units
    }
    stocks = (
        await async_session.execute(
            select(InventoryStock).where(InventoryStock.sku_id.in_(unit_ids))
        )
    ).scalars().all()
    assert {stock.sku_id for stock in stocks} == unit_ids
    assert all(stock.quantity_on_hand == Decimal("0.00") for stock in stocks)
    assert all(stock.quantity_reserved == Decimal("0.00") for stock in stocks)


@pytest.mark.asyncio
async def test_retired_sku_code_is_not_reusable(async_session) -> None:
    service = CatalogProductService()
    product = await service.create_product(
        async_session,
        request=CatalogProductCreate(
            name="Retired Product",
            sellable_units=[SellableUnitCreate(sku_code="NEVER-REUSE-ME")],
        ),
        actor_id=None,
    )
    product.sellable_units[0].soft_delete()
    await async_session.flush()

    with pytest.raises(HTTPException) as error:
        await service.create_product(
            async_session,
            request=CatalogProductCreate(
                name="Replacement Product",
                sellable_units=[SellableUnitCreate(sku_code="NEVER-REUSE-ME")],
            ),
            actor_id=None,
        )
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "SKU_EXISTS"


@pytest.mark.asyncio
async def test_order_stock_view_fails_closed_for_unmapped_legacy_line() -> None:
    repository = SimpleNamespace(
        list_sellable_identities_for_order=AsyncMock(return_value=[(None, "LEGACY-CODE")])
    )
    service = InventoryService(inventory_repo=repository)

    with pytest.raises(HTTPException) as error:
        await service.stock_view_for_order(AsyncMock(), order_id=str(uuid.uuid4()))
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "ORDER_ITEM_SELLABLE_ID_REQUIRED"


@pytest.mark.asyncio
async def test_fulfillment_without_reservation_still_requires_matching_identity(async_session) -> None:
    product = await CatalogProductService().create_product(
        async_session,
        request=CatalogProductCreate(
            name="Reservation Required",
            sellable_units=[SellableUnitCreate(sku_code="RESERVATION-REQUIRED")],
        ),
        actor_id=None,
    )
    unit = product.sellable_units[0]
    stock = (
        await async_session.execute(
            select(InventoryStock).where(InventoryStock.sku_id == unit.id)
        )
    ).scalar_one()
    stock.quantity_on_hand = Decimal("10.00")
    await async_session.flush()

    with pytest.raises(HTTPException) as error:
        await InventoryService().deduct_on_fulfillment(
            async_session,
            sellable_unit_id=unit.id,
            sku_code="MISMATCHED-CODE",
            quantity=Decimal("1.00"),
            order_id=uuid.uuid4(),
            order_item_id=uuid.uuid4(),
        )
    assert error.value.detail["code"] == "SELLABLE_UNIT_UNAVAILABLE"
    assert stock.quantity_on_hand == Decimal("10.00")


@pytest.mark.asyncio
async def test_reservation_rejects_inactive_product(async_session) -> None:
    service = CatalogProductService()
    product = await service.create_product(
        async_session,
        request=CatalogProductCreate(
            name="Inactive Before Confirm",
            sellable_units=[SellableUnitCreate(sku_code="INACTIVE-BEFORE-CONFIRM")],
        ),
        actor_id=None,
    )
    unit = product.sellable_units[0]
    product.is_active = False
    await async_session.flush()
    order = SimpleNamespace(
        id=uuid.uuid4(),
        items=[SimpleNamespace(
            id=uuid.uuid4(),
            sellable_unit_id=unit.id,
            sku_code=unit.sku_code,
            quantity=1,
        )],
    )

    with pytest.raises(HTTPException) as error:
        await InventoryService().reserve_on_confirm(async_session, order=order)
    assert error.value.detail["code"] == "SELLABLE_UNIT_UNAVAILABLE"


@pytest.mark.asyncio
async def test_deactivation_does_not_strand_existing_inventory_lifecycle(async_session) -> None:
    service = CatalogProductService()
    product = await service.create_product(
        async_session,
        request=CatalogProductCreate(
            name="Existing Order Product",
            sellable_units=[SellableUnitCreate(sku_code="EXISTING-ORDER-UNIT")],
        ),
        actor_id=None,
    )
    unit = product.sellable_units[0]
    stock = (
        await async_session.execute(
            select(InventoryStock).where(InventoryStock.sku_id == unit.id)
        )
    ).scalar_one()
    stock.quantity_on_hand = Decimal("10.00")
    await async_session.flush()
    order = Order(
        wholesaler_id=uuid.uuid4(),
        retailer_id=uuid.uuid4(),
        status=OrderStatus.CONFIRMED,
        total_amount=Decimal("20.00"),
        items=[OrderItem(
            sellable_unit_id=unit.id,
            identity_status="stable",
            product_name=product.name,
            sku_code=unit.sku_code,
            unit_snapshot=unit.unit,
            quantity=2,
            unit_price=Decimal("10.00"),
            subtotal=Decimal("20.00"),
        )],
    )
    async_session.add(order)
    await async_session.flush()
    inventory = InventoryService()

    await inventory.reserve_on_confirm(async_session, order=order)
    product.is_active = False
    unit.is_active = False
    await async_session.flush()

    await inventory.release_on_cancel(async_session, order=order)
    assert stock.quantity_reserved == Decimal("0.00")
    await inventory.deduct_on_fulfillment(
        async_session,
        sellable_unit_id=unit.id,
        sku_code=unit.sku_code,
        quantity=Decimal("2.00"),
        order_id=order.id,
        order_item_id=order.items[0].id,
    )
    assert stock.quantity_on_hand == Decimal("8.00")
    await inventory.restock_on_return(
        async_session,
        sellable_unit_id=unit.id,
        sku_code=unit.sku_code,
        quantity=Decimal("2.00"),
        order_id=order.id,
    )
    assert stock.quantity_on_hand == Decimal("10.00")


@pytest.mark.asyncio
async def test_compat_create_sku_without_catalog_id_links_product_and_zero_stock(async_session) -> None:
    sku = await SKUService().create_sku(
        async_session,
        catalog_product_id=None,
        sku_code="COMPAT-CREATE-SKU-M1",
        name="Compat Create Product",
        description=None,
        unit="piece",
        package_quantity=Decimal("1"),
        category=None,
        is_active=True,
        created_by=None,
    )

    persisted_sku = (
        await async_session.execute(
            select(SKU).where(
                SKU.sku_code == "COMPAT-CREATE-SKU-M1",
                SKU.is_deleted.is_(False),
            )
        )
    ).scalar_one()
    assert persisted_sku.id == sku.id
    assert persisted_sku.catalog_product_id is not None

    linked_product = (
        await async_session.execute(
            select(CatalogProduct).where(
                CatalogProduct.id == persisted_sku.catalog_product_id,
                CatalogProduct.is_deleted.is_(False),
            )
        )
    ).scalar_one()
    assert linked_product.id == persisted_sku.catalog_product_id
    assert linked_product.name == "Compat Create Product"

    stocks = (
        await async_session.execute(
            select(InventoryStock).where(
                InventoryStock.sku_id == persisted_sku.id,
                InventoryStock.is_deleted.is_(False),
            )
        )
    ).scalars().all()
    assert len(stocks) == 1
    assert stocks[0].quantity_on_hand == Decimal("0.00")
    assert stocks[0].quantity_reserved == Decimal("0.00")


@pytest.mark.asyncio
async def test_ensure_stock_row_is_idempotent_per_unit(async_session) -> None:
    service = CatalogProductService()
    product = await service.create_product(
        async_session,
        request=CatalogProductCreate(
            name="Idempotent Stock Product",
            sellable_units=[SellableUnitCreate(sku_code="IDEMPOTENT-STOCK-UNIT")],
        ),
        actor_id=None,
    )
    unit = product.sellable_units[0]
    repository = InventoryRepository()

    first = await repository.ensure_stock_row(async_session, sku_id=unit.id)
    await async_session.flush()
    second = await repository.ensure_stock_row(async_session, sku_id=unit.id)
    await async_session.flush()

    assert first.id == second.id
    assert first.sku_id == unit.id
    assert second.sku_id == unit.id

    stock_count = (
        await async_session.execute(
            select(func.count())
            .select_from(InventoryStock)
            .where(
                InventoryStock.sku_id == unit.id,
                InventoryStock.is_deleted.is_(False),
            )
        )
    ).scalar_one()
    assert stock_count == 1


def test_migration_backfills_only_from_unique_reservation_evidence() -> None:
    migration = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "038_catalog_identity_vertical_slice.py"
    ).read_text(encoding="utf-8")
    reservation_update = migration.split("WITH reservation_proof AS", 1)[1].split(
        "ALTER TABLE {q}.order_items", 1
    )[0]

    assert "HAVING count(DISTINCT sku_id) = 1" in reservation_update
    assert "JOIN {q}.skus s ON s.id = proof.sku_id" in reservation_update
    assert "sku_code" not in reservation_update
    assert "product_name" not in reservation_update
    assert "forward-only" in migration
