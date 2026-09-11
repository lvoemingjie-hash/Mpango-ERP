"""Package-identity guard (DC-12R1-MVP-L1-SKU-BC06-R1 + R2 amendment).

Single shared decision point for every ``package_quantity`` MODIFICATION
entry: both ``SKUService.update_sku`` (PUT /skus/{sku_code}) and
``CatalogProductService.update_sellable_unit``
(PUT /catalog-products/{id}/sellable-units/{unit_id}) call the same
implementation — never a per-entry copy.

Contract (CTO-AUTH-DC12R1-MVP-L1-SKU-BC06-R1-RETAILER-PRICE-VALIDITY, as
amended by CTO-AUTH-DC12R1-MVP-L1-SKU-BC06-R2-HISTORY-LOCK-ORM-FRESHNESS):

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
- Real IDENTITY-USE history is a separate, stronger gate returning
  ``SKU_PACKAGE_QUANTITY_IMMUTABLE_AFTER_USE`` (R2: orders INCLUDING
  soft-deleted items, ANY retained inventory_movements row, any NON-ZERO
  inventory_stocks on-hand or reserved, ANY retained inventory_reservations
  row). Only the automatic all-zero inventory_stocks placeholder row created
  by ``ensure_stock_row`` is NOT history. No consumed/released reservation
  exception exists: any retained reservation row blocks (fail-closed,
  exceeding the R2 minimum).
- Serialization + freshness: ``lock_sku_row`` acquires the SAME ``skus`` row
  lock for both modification entries AND ``pricing_repository.set_price``
  and returns the LOCKED, FRESHEST committed SKU row (``FOR UPDATE`` with
  ``populate_existing``) — callers MUST make their change decision and their
  write from that returned instance, never from a pre-lock loaded object.

This module performs NO retailer_prices writes: no deletes, no automatic
retirement, no migration, no recomputation (explicitly out of scope this
round; the price retirement/re-confirmation workflow is separately
authorized).
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.sku import SKU

CODE_REPRICE_REQUIRED = "SKU_PACKAGE_QUANTITY_REPRICE_REQUIRED"
CODE_IMMUTABLE_AFTER_USE = "SKU_PACKAGE_QUANTITY_IMMUTABLE_AFTER_USE"
CODE_PRICE_DATA_INTEGRITY_RED = "PRICE_DATA_INTEGRITY_RED"


def _conflict(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, "message": message},
    )


async def lock_sku_row(db: AsyncSession, *, sku_id) -> SKU | None:
    """Acquire the shared ``skus`` row lock and return the FRESHEST row.

    ``SELECT ... FOR UPDATE`` with ``populate_existing``: the row lock makes
    this transaction the serialization point for both package_quantity
    modification entries and the pricing set_price path, and
    ``populate_existing`` refreshes the caller's identity-map instance with
    the committed state as of lock acquisition — a stale pre-lock object is
    overwritten here, so the change decision and the write always act on the
    locked-fresh ``package_quantity``. Returns ``None`` only when the row
    does not exist (concurrent soft-delete between precheck and lock).
    """
    result = await db.execute(
        select(SKU)
        .where(SKU.id == sku_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    return result.scalar_one_or_none()


def package_quantity_changed(current, new) -> bool:
    """True only when the requested package_quantity actually differs from
    the stored one. Numeric Decimal equality (12 == 12.0 == 12.000), so a
    same-value update is never blocked by the gate."""
    if new is None:
        return False
    return Decimal(str(new)) != Decimal(str(current))


async def has_identity_use_history(
    db: AsyncSession, *, sku_id, sku_code: str
) -> bool:
    """True when the SKU's package identity has been USED anywhere.

    R2 semantics — deliberately fail-closed:
    - ``order_items``: ANY row referencing the SKU by stable/linked identity
      (``sellable_unit_id``) or legacy ``sku_code`` (codes are never
      reusable), INCLUDING soft-deleted rows — a deleted line item does not
      un-happen the order.
    - ``inventory_movements``: ANY retained row — movements are a journal of
      real stock events; soft-delete does not erase the event.
    - ``inventory_stocks``: any row with ``quantity_on_hand <> 0`` OR
      ``quantity_reserved <> 0`` (only the automatic all-zero placeholder
      row created by ``ensure_stock_row`` passes; checked regardless of
      ``is_deleted``).
    - ``inventory_reservations``: ANY retained row in ANY status
      (``reserved``/``consumed``/``released``) — no consumed/released
      exception is granted this round (directive: must not default to
      modifiable).
    """
    # Raw statements (tenant-schema tables via search_path); the ORM-level
    # tenant filter injects criteria only for mapped entities, so each
    # history probe is explicit and audit-visible.
    order_item = (
        await db.execute(
            text(
                "SELECT 1 FROM order_items "
                "WHERE (sellable_unit_id = :sku_id OR sku_code = :sku_code) "
                "LIMIT 1"
            ),
            {"sku_id": sku_id, "sku_code": sku_code},
        )
    ).first()
    if order_item is not None:
        return True

    movement = (
        await db.execute(
            text("SELECT 1 FROM inventory_movements WHERE sku_id = :sku_id LIMIT 1"),
            {"sku_id": sku_id},
        )
    ).first()
    if movement is not None:
        return True

    stock = (
        await db.execute(
            text(
                "SELECT 1 FROM inventory_stocks "
                "WHERE sku_id = :sku_id "
                "AND (quantity_on_hand <> 0 OR quantity_reserved <> 0) "
                "LIMIT 1"
            ),
            {"sku_id": sku_id},
        )
    ).first()
    if stock is not None:
        return True

    reservation = (
        await db.execute(
            text("SELECT 1 FROM inventory_reservations WHERE sku_id = :sku_id LIMIT 1"),
            {"sku_id": sku_id},
        )
    ).first()
    return reservation is not None


async def ensure_package_quantity_change_allowed(
    db: AsyncSession,
    *,
    sku,
    new_package_quantity,
) -> None:
    """The single shared package-identity gate.

    MUST be called only after ``lock_sku_row`` returned a fresh instance in
    the SAME transaction (``sku`` must be that locked-fresh object — the
    change check is repeated here defensively so a future caller cannot
    bypass it), and only for an actually-changed value.

    Raises, in order:
      1. ``SKU_PACKAGE_QUANTITY_IMMUTABLE_AFTER_USE`` — identity-use history
         exists for the SKU (R2 definition).
      2. ``PRICE_DATA_INTEGRITY_RED`` — a non-deleted price row carries NULL
         or a non-positive price.
      3. ``SKU_PACKAGE_QUANTITY_REPRICE_REQUIRED`` — current retailer price
         configuration exists (an independent gate, NOT the history lock).
    """
    if not package_quantity_changed(sku.package_quantity, new_package_quantity):
        return

    if await has_identity_use_history(db, sku_id=sku.id, sku_code=sku.sku_code):
        raise _conflict(
            CODE_IMMUTABLE_AFTER_USE,
            f"SKU '{sku.sku_code}' has identity-use history (orders, inventory "
            "movements, non-zero stock/reserved, or reservations); "
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
