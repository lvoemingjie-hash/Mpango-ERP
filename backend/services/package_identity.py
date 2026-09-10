"""Package-identity guard (DC-12R1-MVP-L1-SKU-BC06-R1).

Single shared decision point for every ``package_quantity`` MODIFICATION
entry: both ``SKUService.update_sku`` (PUT /skus/{sku_code}) and
``CatalogProductService.update_sellable_unit``
(PUT /catalog-products/{id}/sellable-units/{unit_id}) call the same
implementation — never a per-entry copy.

Contract (CTO-AUTH-DC12R1-MVP-L1-SKU-BC06-R1-RETAILER-PRICE-VALIDITY):

- ``retailer_prices`` rows are current/retired price CONFIGURATION, never
  transaction history. A soft-deleted (``is_deleted = true``) row is retired
  configuration: it does not gate repackaging and must be preserved
  byte-for-byte as an audit record.
- ``CURRENT_RETAILER_PRICE_CONFIGURED`` := EXISTS retailer_prices
  WHERE sku_id = :sku_id AND is_deleted IS NOT TRUE. No validity-window
  (``valid_from``/``valid_to``) or ``is_active`` columns exist in the model,
  migration 017, or the live tenant table — none may be assumed.
- ``price > 0`` is enforced by ``ck_retailer_prices_positive_price``. A
  non-deleted row with NULL or non-positive price is unreachable corruption
  (constraint dropped or bypassed): fail closed as PRICE_DATA_INTEGRITY_RED,
  never silently ignore.
- Real TRANSACTION history is a separate, stronger gate returning
  ``SKU_PACKAGE_QUANTITY_IMMUTABLE_AFTER_USE``. Zero-value
  ``inventory_stocks`` placeholder rows created by ``ensure_stock_row`` are
  NOT transaction history and never block repackaging.
- Serialization: every guarded entry point AND ``pricing_repository.set_price``
  acquire the SAME ``skus`` row lock first, so exactly two outcomes exist:
  a price committed before a repackaging attempt makes it return 409
  REPRICE_REQUIRED; a repackaging committed first means a later explicit
  set_price simply applies to the new package definition.

This module performs NO retailer_prices writes: no deletes, no automatic
retirement, no migration, no recomputation (explicitly out of scope this
round; the price retirement/re-confirmation workflow is separately
authorized).
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CODE_REPRICE_REQUIRED = "SKU_PACKAGE_QUANTITY_REPRICE_REQUIRED"
CODE_IMMUTABLE_AFTER_USE = "SKU_PACKAGE_QUANTITY_IMMUTABLE_AFTER_USE"
CODE_PRICE_DATA_INTEGRITY_RED = "PRICE_DATA_INTEGRITY_RED"


def _conflict(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, "message": message},
    )


async def lock_sku_row(db: AsyncSession, *, sku_id) -> None:
    """``SELECT ... FOR UPDATE`` on the skus row — the shared serialization
    point.

    Both package_quantity modification entries and the pricing set_price path
    acquire this SAME row lock before reading or writing price configuration,
    so their relative commit order fully determines the observable outcome
    (no concurrent read of a not-yet-committed price, no lost update).
    """
    await db.execute(
        text("SELECT id FROM skus WHERE id = :sku_id FOR UPDATE"),
        {"sku_id": sku_id},
    )


def package_quantity_changed(current, new) -> bool:
    """True only when the requested package_quantity actually differs from
    the stored one. Numeric Decimal equality (12 == 12.0 == 12.000), so a
    same-value update is never blocked by the gate."""
    if new is None:
        return False
    return Decimal(str(new)) != Decimal(str(current))


async def has_transaction_history(
    db: AsyncSession, *, sku_id, sku_code: str
) -> bool:
    """Real transaction history: any non-soft-deleted ``order_items`` row
    referencing this SKU — by stable/linked identity (``sellable_unit_id``)
    or by legacy ``sku_code`` (SKU codes are never reusable, so a code match
    is the same product identity). Order status does not exempt: a voided
    order is still a transaction that happened."""
    result = await db.execute(
        text(
            "SELECT 1 FROM order_items "
            "WHERE (sellable_unit_id = :sku_id OR sku_code = :sku_code) "
            "AND is_deleted IS NOT TRUE "
            "LIMIT 1"
        ),
        {"sku_id": sku_id, "sku_code": sku_code},
    )
    return result.first() is not None


async def ensure_package_quantity_change_allowed(
    db: AsyncSession,
    *,
    sku,
    new_package_quantity,
) -> None:
    """The single shared package-identity gate.

    MUST be called only after ``lock_sku_row(db, sku_id=sku.id)`` in the SAME
    transaction, and only for an actually-changed value (the change check is
    repeated here defensively so a future caller cannot bypass it).

    Raises, in order:
      1. ``SKU_PACKAGE_QUANTITY_IMMUTABLE_AFTER_USE`` — real transaction
         history exists for the SKU.
      2. ``PRICE_DATA_INTEGRITY_RED`` — a non-deleted price row carries NULL
         or a non-positive price.
      3. ``SKU_PACKAGE_QUANTITY_REPRICE_REQUIRED`` — current retailer price
         configuration exists (an independent gate, NOT the history lock).
    """
    if not package_quantity_changed(sku.package_quantity, new_package_quantity):
        return

    if await has_transaction_history(db, sku_id=sku.id, sku_code=sku.sku_code):
        raise _conflict(
            CODE_IMMUTABLE_AFTER_USE,
            f"SKU '{sku.sku_code}' has real transaction history; "
            "package_quantity is immutable after use",
        )

    price_rows = (
        await db.execute(
            text(
                "SELECT price FROM retailer_prices "
                "WHERE sku_id = :sku_id AND is_deleted IS NOT TRUE"
            ),
            {"sku_id": sku.id},
        )
    ).fetchall()

    for row in price_rows:
        if row.price is None or Decimal(str(row.price)) <= 0:
            raise _conflict(
                CODE_PRICE_DATA_INTEGRITY_RED,
                "retailer_prices contains a non-deleted row with a NULL or "
                f"non-positive price for SKU '{sku.sku_code}' while "
                "ck_retailer_prices_positive_price should guarantee price > 0; "
                "failing closed instead of silently ignoring corrupt price data",
            )

    if price_rows:
        raise _conflict(
            CODE_REPRICE_REQUIRED,
            f"SKU '{sku.sku_code}' has current retailer price configuration "
            f"({len(price_rows)} non-deleted retailer_prices row(s)); "
            "package_quantity changes require the price retirement/"
            "re-confirmation workflow — create a new sellable unit instead",
        )
