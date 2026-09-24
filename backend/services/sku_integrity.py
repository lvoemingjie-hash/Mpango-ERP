"""SKU-code uniqueness integrity guard (DC-12R1-MVP-L1-SKU-R0-M1-R1-R1).

Concurrent duplicate SKU-code insertion previously raced past the friendly
check-then-insert precheck and surfaced as a raw IntegrityError → HTTP 500.
The prechecks are retained for UX, but correctness now comes from catching the
PostgreSQL unique violation raised by the exact SKU-code unique index
(``ux_skus_sku_code``) at flush time, rolling back the failed transaction, and
mapping ONLY that named violation to SKU_EXISTS / 409.

Every SKU insertion path routes its flush through :func:`flush_skus_or_409`:

- ``CatalogProductService.create_product`` (initial product unit creation)
- ``CatalogProductService.add_sellable_unit``
- ``SKUService.create_sku``
- ``ImportService`` apply (bulk SKU creation)
- ``IntakeApplyService.apply_workspace`` (staged intake rows → official SKUs;
  the friendly ``SKU_CODE_EXISTS`` precheck is UX only, a flush-time race
  rolls the losing transaction back whole and surfaces as exactly one
  ``SKU_EXISTS`` / 409)

Unrelated IntegrityErrors (check constraints, FKs, other unique indexes) are
explicitly NOT classified as SKU_EXISTS; they propagate unchanged so they can
never be mislabeled as a 409.
"""
from __future__ import annotations

import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

# The exact named unique constraints backing the SKU-code uniqueness contract.
# The tenant-local skus table (created by the canonical bootstrap used by
# production provisioning AND the browser harness) declares
# ``sku_code VARCHAR(64) NOT NULL UNIQUE`` → PG names it ``skus_sku_code_key``.
# The legacy public-schema table created by alembic migration 004 names the
# same contract ``ux_skus_sku_code``. Both names denote exactly this contract;
# nothing else is ever classified as a SKU-code conflict.
SKU_CODE_UNIQUE_CONSTRAINTS = ("skus_sku_code_key", "ux_skus_sku_code")


def is_sku_code_unique_violation(exc: IntegrityError) -> bool:
    """Return True only for a unique violation of the SKU-code unique constraint.

    Uses the driver-reported constraint name when available (asyncpg exposes
    ``constraint_name`` on the original DBAPI error) and falls back to the
    rendered PG message. Any other constraint/index — or any other IntegrityError
    class — is False by construction.
    """
    orig = getattr(exc, "orig", None)
    name = getattr(orig, "constraint_name", None)
    if not name:
        diag = getattr(exc, "diag", None)
        name = getattr(diag, "constraint_name", None)
    if name:
        return name in SKU_CODE_UNIQUE_CONSTRAINTS
    return any(f'"{constraint}"' in str(orig or "") for constraint in SKU_CODE_UNIQUE_CONSTRAINTS)


def sku_conflict_exception(code: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "SKU_EXISTS",
            "message": f"SKU code '{code}' already exists",
        },
    )


def _conflicting_code(exc: IntegrityError, fallback: str) -> str:
    """Best-effort conflicting value from the PG detail line
    ``Key (sku_code)=(<value>) already exists.`` — falls back to the requested
    code when the driver omits the detail."""
    orig = getattr(exc, "orig", None)
    detail = str(getattr(orig, "detail", "") or "")
    match = re.search(r"Key \(sku_code\)=\((.*)\) already exists", detail)
    return match.group(1) if match else fallback


async def flush_skus_or_409(db: AsyncSession, *, sku_code: str) -> None:
    """Flush the current transaction, mapping ONLY a concurrent duplicate
    SKU-code insert to a rolled-back SKU_EXISTS / 409.

    The rollback is mandatory: after a failed INSERT the transaction is aborted
    and the session must be reset before the request boundary can finalize.
    On rollback every row of the failed transaction (including any parent
    catalog product inserted in the same transaction) is discarded atomically.
    Unrelated IntegrityErrors propagate unchanged (never a 409).
    """
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if is_sku_code_unique_violation(exc):
            raise sku_conflict_exception(_conflicting_code(exc, sku_code)) from exc
        raise
