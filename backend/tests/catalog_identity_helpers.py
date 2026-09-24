"""Shared stable catalog identity builders for database-backed tests."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from models.catalog_product import CatalogProduct
from models.order import OrderItem
from models.sku import SKU


async def create_sku_with_catalog(
    session,
    *,
    sku_code: str,
    name: str,
    unit: str = "piece",
    is_active: bool = True,
) -> SKU:
    product = CatalogProduct(name=name, is_active=is_active)
    session.add(product)
    await session.flush()
    sku = SKU(
        catalog_product_id=product.id,
        sku_code=sku_code,
        name=name,
        unit=unit,
        package_quantity=Decimal("1.000"),
        is_active=is_active,
    )
    session.add(sku)
    await session.flush()
    return sku


async def stable_order_items(
    session,
    items: list[tuple[str, int, Decimal]],
) -> list[OrderItem]:
    codes = [sku_code for sku_code, _, _ in items]
    result = await session.execute(select(SKU).where(SKU.sku_code.in_(codes)))
    units_by_code = {sku.sku_code: sku for sku in result.scalars().all()}
    if set(units_by_code) != set(codes):
        raise AssertionError("stable order-item fixture requires an existing sellable unit")
    return [
        OrderItem(
            sellable_unit_id=units_by_code[sku_code].id,
            identity_status="stable",
            product_name=f"Product {sku_code}",
            sku_code=sku_code,
            unit_snapshot=units_by_code[sku_code].unit,
            quantity=quantity,
            unit_price=unit_price,
            subtotal=Decimal(quantity) * unit_price,
        )
        for sku_code, quantity, unit_price in items
    ]
