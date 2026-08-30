"""U4-I-B2 apply service for staged intake rows -> official SKUs."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.intake import IntakeProductRow, IntakeValidationIssue, IntakeWorkspace
from models.catalog_product import CatalogProduct
from models.sku import SKU
from repositories.inventory_repository import InventoryRepository
from repositories.sku_repository import SKURepository


class IntakeApplyService:
    """Apply validated intake rows atomically within the caller transaction."""

    def __init__(
        self,
        sku_repo: SKURepository | None = None,
        inventory_repo: InventoryRepository | None = None,
    ) -> None:
        self._sku_repo = sku_repo or SKURepository()
        self._inventory_repo = inventory_repo or InventoryRepository()

    async def apply_workspace(
        self,
        db: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        workspace = (
            await db.execute(
                select(IntakeWorkspace)
                .where(
                    IntakeWorkspace.id == workspace_id,
                    IntakeWorkspace.tenant_id == tenant_id,
                    IntakeWorkspace.is_deleted.is_(False),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "WORKSPACE_NOT_FOUND", "message": "Intake workspace not found"},
            )

        if workspace.apply_status == "applied":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "ALREADY_APPLIED", "message": "Intake workspace has already been applied"},
            )
        if workspace.apply_status != "not_applied":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "INVALID_APPLY_STATUS",
                    "message": f"Cannot apply workspace in apply_status '{workspace.apply_status}'",
                },
            )
        if workspace.status != "READY_FOR_EXPORT":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "WORKSPACE_NOT_READY", "message": "Workspace must be READY_FOR_EXPORT before apply"},
            )

        blocking_count = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(IntakeValidationIssue)
                    .where(
                        IntakeValidationIssue.tenant_id == tenant_id,
                        IntakeValidationIssue.workspace_id == workspace.id,
                        IntakeValidationIssue.is_deleted.is_(False),
                        IntakeValidationIssue.is_blocking.is_(True),
                    )
                )
            ).scalar_one()
        )
        if blocking_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "BLOCKING_ISSUES", "message": "Workspace has blocking validation issues"},
            )

        rows = (
            await db.execute(
                select(IntakeProductRow)
                .where(
                    IntakeProductRow.tenant_id == tenant_id,
                    IntakeProductRow.workspace_id == workspace.id,
                    IntakeProductRow.is_deleted.is_(False),
                )
                .order_by(IntakeProductRow.upload_id, IntakeProductRow.row_index)
                .with_for_update()
            )
        ).scalars().all()
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "NO_MAPPED_ROWS", "message": "Workspace has no staged rows to apply"},
            )

        prepared_rows = self._prepare_apply_rows(rows)
        staged_codes = [row["sku_code"] for row in prepared_rows]
        duplicate_codes = sorted({code for code in staged_codes if staged_codes.count(code) > 1})
        if duplicate_codes:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "DUPLICATE_STAGED_SKU_CODE",
                    "message": "Duplicate staged sku_code values found",
                    "sku_codes": duplicate_codes,
                },
            )

        existing_result = await db.execute(
            select(SKU.sku_code).where(SKU.sku_code.in_(staged_codes))
        )
        existing_codes = sorted(existing_result.scalars().all())
        if existing_codes:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "SKU_CODE_EXISTS",
                    "message": "One or more staged sku_code values already exist",
                    "sku_codes": existing_codes,
                },
            )

        created_sku_ids: list[str] = []
        for prepared in prepared_rows:
            product = CatalogProduct(
                name=prepared["name"],
                description=None,
                category=prepared["category"],
                is_active=True,
                created_by=user_id,
                updated_by=user_id,
            )
            db.add(product)
            await db.flush()
            sku = SKU(
                catalog_product_id=product.id,
                sku_code=prepared["sku_code"],
                name=prepared["name"],
                description=None,
                unit=prepared["unit"] or "unit",
                package_quantity=1,
                category=prepared["category"],
                is_active=True,
                created_by=user_id,
                updated_by=user_id,
            )
            sku = await self._sku_repo.create(db, sku=sku)
            await self._inventory_repo.ensure_stock_row(db, sku_id=sku.id)
            prepared["row"].target_sku_id = sku.id
            prepared["row"].apply_status = "applied"
            prepared["row"].apply_error_code = None
            prepared["row"].apply_error_message = None
            prepared["row"].updated_by = user_id
            created_sku_ids.append(str(sku.id))

        now = datetime.now(UTC)
        workspace.apply_status = "applied"
        workspace.applied_at = now
        workspace.applied_by = user_id
        workspace.apply_result = {
            "created_count": len(created_sku_ids),
            "row_count": len(rows),
            "created_sku_ids": created_sku_ids,
            "applied_at": now.isoformat(),
        }
        workspace.updated_by = user_id
        await db.flush()

        return {
            "workspace_id": str(workspace.id),
            "apply_status": workspace.apply_status,
            "created_count": len(created_sku_ids),
            "row_count": len(rows),
            "created_sku_ids": created_sku_ids,
        }

    def _prepare_apply_rows(self, rows: list[IntakeProductRow]) -> list[dict[str, Any]]:
        prepared_rows: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for row in rows:
            sku_code = self._string_or_none(row.sku_code)
            name = self._string_or_none(row.name)
            if not sku_code:
                errors.append({"row_id": str(row.id), "field": "sku_code", "message": "Missing sku_code"})
            if not name:
                errors.append({"row_id": str(row.id), "field": "name", "message": "Missing name"})
            if not sku_code or not name:
                continue
            prepared_rows.append(
                {
                    "row": row,
                    "sku_code": sku_code,
                    "name": name,
                    "unit": self._string_or_none(row.unit),
                    "category": self._string_or_none(row.category),
                }
            )

        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "INCOMPLETE_STAGED_ROWS",
                    "message": "All staged rows must include required SKU fields before apply",
                    "errors": errors,
                },
            )
        return prepared_rows

    def _string_or_none(self, value: Any) -> str | None:
        string_value = str(value or "").strip()
        return string_value if string_value else None
