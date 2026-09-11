"""U3-B2/B3 Import Service -- preview + validate + apply logic for SKU bulk import.

This service handles the three phases of the import contract:
  Phase 1 (preview):  Parse CSV, detect columns, store raw rows in ImportRun.
  Phase 2 (validate): Apply field mapping, run row-level validation rules.
  Phase 3 (apply):    Write validated rows to SKU table.

Phases 1-2 only write to import_runs.  Phase 3 writes to the SKU table
within a single transaction.
"""
from __future__ import annotations

import csv
import io
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.import_run import ImportRun
from repositories.inventory_repository import InventoryRepository
from services.sku_integrity import flush_skus_or_409
from schemas.import_schemas import (
    ImportErrorDetail,
    ImportPreviewResponse,
    ImportSourceInfo,
    ImportValidateResponse,
    ImportWarningDetail,
    ImportApplyResponse,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Known Mpango SKU fields for validation
# ------------------------------------------------------------------
REQUIRED_FIELDS = {"sku_code", "name"}
OPTIONAL_FIELDS = {"description", "unit", "category", "is_active"}
ALL_VALID_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS
CUSTOM_ATTR_PREFIX = "custom_attributes."

# Max rows to return in preview sample
PREVIEW_SAMPLE_SIZE = 5

# Max CSV row limit to prevent OOM
MAX_CSV_ROWS = 50_000


class ImportService:
    """Stateless service; instantiate per request."""

    def __init__(self, inventory_repo: InventoryRepository | None = None) -> None:
        self._inventory_repo = inventory_repo or InventoryRepository()

    # ----------------------------------------------------------
    # Phase 1: Preview
    # ----------------------------------------------------------
    async def preview(
        self,
        db: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        filename: str,
        file_bytes: bytes,
        source_encoding: str = "utf-8",
    ) -> ImportPreviewResponse:
        """Parse CSV bytes, create ImportRun row, return preview metadata.

        Does NOT write to any table other than import_runs.
        """
        # -- Parse CSV --
        text = self._decode_bytes(file_bytes, source_encoding)

        rows, columns = self._parse_csv(text)

        if not columns:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "EMPTY_FILE",
                    "message": "CSV file has no columns or is empty",
                },
            )

        if len(rows) > MAX_CSV_ROWS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "FILE_TOO_LARGE",
                    "message": (
                        f"CSV has {len(rows)} rows, exceeds limit of {MAX_CSV_ROWS}"
                    ),
                },
            )

        # -- Persist ImportRun --
        import_id = f"imp_{uuid.uuid4().hex[:20]}"
        run = ImportRun(
            import_id=import_id,
            tenant_id=tenant_id,
            status="previewed",
            source_filename=filename,
            source_encoding=source_encoding,
            total_rows=len(rows),
            mapping={
                "columns": columns,
                "rows": rows,
                "sample_rows": rows[:PREVIEW_SAMPLE_SIZE],
            },
        )
        db.add(run)
        await db.flush()

        logger.info(
            "import_preview_created",
            extra={
                "action": "import_preview",
                "import_id": import_id,
                "total_rows": len(rows),
                "columns_detected": columns,
            },
        )

        return ImportPreviewResponse(
            import_id=import_id,
            source=ImportSourceInfo(
                filename=filename,
                encoding=source_encoding,
                row_count=len(rows),
            ),
            columns_detected=columns,
            sample_rows=rows[:PREVIEW_SAMPLE_SIZE],
        )

    # ----------------------------------------------------------
    # Phase 2: Validate
    # ----------------------------------------------------------
    async def validate(
        self,
        db: AsyncSession,
        *,
        import_id: str,
        mapping: Dict[str, str],
        existing_sku_codes: Optional[set] = None,
    ) -> ImportValidateResponse:
        """Apply field mapping, validate rows, update ImportRun status.

        Does NOT write to SKU/inventory tables.

        Args:
            existing_sku_codes: Optional set of sku_code values that already
                exist in the tenant catalog.  Used for duplicate detection.
                In production this would be queried from DB; for testability
                it is injected.
        """
        # -- Load ImportRun --
        run = await self._get_run(db, import_id)

        if run.status not in ("previewed", "needs_review"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "INVALID_STATUS",
                    "message": (
                        f"Import run '{import_id}' is in status '{run.status}', "
                        "expected 'previewed' or 'needs_review'"
                    ),
                },
            )

        # -- Validate mapping keys --
        mapping_errors = self._validate_mapping(mapping)
        if mapping_errors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_MAPPING",
                    "message": "; ".join(mapping_errors),
                },
            )

        # -- Retrieve stored rows --
        mapping_data = run.mapping or {}
        columns: List[str] = mapping_data.get("columns", [])
        rows: List[Dict] = mapping_data.get("rows", [])

        if not rows:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "NO_ROWS",
                    "message": (
                        f"Import run '{import_id}' has no row data stored.  "
                        "Re-run preview to upload the CSV again."
                    ),
                },
            )

        # -- Map + validate each row --
        errors: List[ImportErrorDetail] = []
        warnings: List[ImportWarningDetail] = []
        invalid_row_numbers: set = set()

        required_target_fields = REQUIRED_FIELDS
        mapped_targets = set(mapping.values())
        missing_required = required_target_fields - mapped_targets

        if missing_required:
            # Global error: required fields not mapped at all
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "MISSING_REQUIRED_FIELDS",
                    "message": (
                        f"Mapping does not cover required fields: "
                        f"{', '.join(sorted(missing_required))}"
                    ),
                },
            )

        for idx, row in enumerate(rows, start=1):
            row_errors: List[ImportErrorDetail] = []
            row_warnings: List[ImportWarningDetail] = []

            mapped_row = self._apply_mapping(row, mapping)

            # -- Required field check --
            for req_field in required_target_fields:
                val = mapped_row.get(req_field)
                if val is None or (isinstance(val, str) and val.strip() == ""):
                    row_errors.append(
                        ImportErrorDetail(
                            row=idx,
                            field=req_field,
                            sku_code=mapped_row.get("sku_code"),
                            message=f"Required field '{req_field}' is empty",
                        )
                    )

            # -- sku_code format check --
            sku_code = mapped_row.get("sku_code")
            if sku_code and isinstance(sku_code, str):
                stripped = sku_code.strip()
                if len(stripped) > 64:
                    row_errors.append(
                        ImportErrorDetail(
                            row=idx,
                            field="sku_code",
                            sku_code=sku_code,
                            message="sku_code exceeds 64 characters",
                        )
                    )
                if " " in stripped:
                    row_warnings.append(
                        ImportWarningDetail(
                            row=idx,
                            field="sku_code",
                            message=f"sku_code '{stripped}' contains spaces",
                        )
                    )

            # -- name length check --
            name_val = mapped_row.get("name")
            if name_val and isinstance(name_val, str) and len(name_val) > 255:
                row_errors.append(
                    ImportErrorDetail(
                        row=idx,
                        field="name",
                        sku_code=mapped_row.get("sku_code"),
                        message="name exceeds 255 characters",
                    )
                )

            # -- is_active format check --
            is_active_val = mapped_row.get("is_active")
            if is_active_val is not None and isinstance(is_active_val, str):
                if is_active_val.lower() not in ("true", "false", "1", "0", "yes", "no"):
                    row_warnings.append(
                        ImportWarningDetail(
                            row=idx,
                            field="is_active",
                            message=(
                                f"is_active value '{is_active_val}' is not a "
                                "standard boolean (true/false)"
                            ),
                        )
                    )

            # -- Unmapped columns warning --
            for col in columns:
                if col not in mapping and col not in mapped_targets:
                    row_warnings.append(
                        ImportWarningDetail(
                            row=idx,
                            field=col,
                            message=f"Column '{col}' is not mapped",
                        )
                    )

            errors.extend(row_errors)
            warnings.extend(row_warnings)

            if row_errors:
                invalid_row_numbers.add(idx)

        # -- Intra-file duplicate sku_code detection --
        seen_sku_codes: Dict[str, int] = {}
        for idx, row in enumerate(rows, start=1):
            mapped_row = self._apply_mapping(row, mapping)
            sku_code = mapped_row.get("sku_code")
            if not sku_code or not isinstance(sku_code, str):
                continue
            code = sku_code.strip()
            if not code:
                continue
            if code in seen_sku_codes:
                errors.append(
                    ImportErrorDetail(
                        row=idx,
                        field="sku_code",
                        sku_code=code,
                        message=(
                            f"Duplicate sku_code '{code}' in file "
                            f"(first seen at row {seen_sku_codes[code]})"
                        ),
                    )
                )
                invalid_row_numbers.add(idx)
            else:
                seen_sku_codes[code] = idx

        # -- Existing catalog duplicate detection --
        if existing_sku_codes:
            for idx, row in enumerate(rows, start=1):
                mapped_row = self._apply_mapping(row, mapping)
                sku_code = mapped_row.get("sku_code")
                if not sku_code or not isinstance(sku_code, str):
                    continue
                code = sku_code.strip()
                if code and code in existing_sku_codes:
                    warnings.append(
                        ImportWarningDetail(
                            row=idx,
                            field="sku_code",
                            message=(
                                f"sku_code '{code}' already exists in catalog; "
                                "apply with on_conflict='skip' or 'update' to handle"
                            ),
                        )
                    )

        error_count = len(invalid_row_numbers)
        valid_count = len(rows) - error_count

        # -- Determine status --
        new_status = "validated" if error_count == 0 else "needs_review"

        # -- Update ImportRun --
        run.status = new_status
        run.mapping = {**(run.mapping or {}), "field_mapping": mapping}
        run.valid_rows = valid_count
        run.error_rows = error_count
        run.warning_rows = len(warnings)
        run.validation_result = {
            "errors": [e.model_dump() for e in errors],
            "warnings": [w.model_dump() for w in warnings],
        }
        await db.flush()

        logger.info(
            "import_validate_completed",
            extra={
                "action": "import_validate",
                "import_id": import_id,
                "status": new_status,
                "valid_rows": valid_count,
                "error_rows": error_count,
                "warning_rows": len(warnings),
            },
        )

        return ImportValidateResponse(
            import_id=import_id,
            status=new_status,  # type: ignore[arg-type]
            valid_rows=valid_count,
            error_rows=error_count,
            warning_rows=len(warnings),
            errors=errors,
            warnings=warnings,
        )

    # ----------------------------------------------------------
    # Phase 3: Apply
    # ----------------------------------------------------------
    async def apply(
        self,
        db: AsyncSession,
        *,
        import_id: str,
        on_conflict: str,
        applied_by: Optional[uuid.UUID] = None,
        existing_sku_codes: Optional[set] = None,
    ) -> ImportApplyResponse:
        """Write validated rows to the SKU table.

        Only processes import_runs with status='validated'.
        All writes happen within the caller's transaction.

        Args:
            on_conflict: 'skip' (skip duplicates) or 'fail' (abort on any duplicate).
            applied_by: UUID of the user who triggered apply.
            existing_sku_codes: Optional pre-queried set of existing SKU codes.
                If None, will query from DB.

        Raises:
            HTTPException on precondition failures.
        """
        from datetime import datetime, timezone
        from models.catalog_product import CatalogProduct
        from models.sku import SKU

        # -- Load ImportRun --
        run = await self._get_run(db, import_id)

        if run.status != "validated":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "INVALID_STATUS",
                    "message": (
                        f"Import run '{import_id}' is in status '{run.status}', "
                        "expected 'validated'"
                    ),
                },
            )

        # -- Retrieve stored rows and field_mapping --
        mapping_data = run.mapping or {}
        rows: List[Dict] = mapping_data.get("rows", [])
        field_mapping: Dict[str, str] = mapping_data.get("field_mapping", {})

        if not rows:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "NO_ROWS",
                    "message": (
                        f"Import run '{import_id}' has no row data stored.  "
                        "Re-run preview to upload the CSV again."
                    ),
                },
            )

        # -- STOP_AND_REPORT_CTO: check for custom_attributes in mapping --
        custom_attr_mappings = {
            k: v for k, v in field_mapping.items()
            if v.startswith(CUSTOM_ATTR_PREFIX)
        }
        if custom_attr_mappings:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "STOP_AND_REPORT_CTO",
                    "message": (
                        f"Field mapping contains custom_attributes entries: "
                        f"{list(custom_attr_mappings.values())}. "
                        f"The SKU model has no 'custom_attributes' column. "
                        f"CTO must approve either adding the column or removing "
                        f"these mappings before apply can proceed."
                    ),
                },
            )

        # -- Query existing SKU codes if not provided --
        if existing_sku_codes is None:
            code_result = await db.execute(
                select(SKU.sku_code)
            )
            existing_sku_codes = set(code_result.scalars().all())

        # -- Pre-scan for conflicts when on_conflict='fail' --
        if on_conflict == "fail":
            conflict_errors: List[ImportErrorDetail] = []
            for idx, row in enumerate(rows, start=1):
                mapped_row = self._apply_mapping(row, field_mapping)
                sku_code = mapped_row.get("sku_code")
                if not sku_code or not isinstance(sku_code, str):
                    continue
                sku_code = sku_code.strip()
                if sku_code in existing_sku_codes:
                    conflict_errors.append(
                        ImportErrorDetail(
                            row=idx,
                            field="sku_code",
                            sku_code=sku_code,
                            message=(
                                f"sku_code '{sku_code}' already exists in catalog "
                                f"and on_conflict='fail' was specified"
                            ),
                        )
                    )
            if conflict_errors:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "CONFLICT_DETECTED",
                        "message": (
                            f"Found {len(conflict_errors)} conflicting sku_code(s) "
                            f"and on_conflict='fail'. No SKUs were created."
                        ),
                        "conflicts": [e.model_dump() for e in conflict_errors],
                    },
                )

        # -- Process rows --
        created_count = 0
        skipped_count = 0
        apply_errors: List[ImportErrorDetail] = []

        for idx, row in enumerate(rows, start=1):
            mapped_row = self._apply_mapping(row, field_mapping)

            sku_code = mapped_row.get("sku_code")
            if not sku_code or not isinstance(sku_code, str):
                apply_errors.append(
                    ImportErrorDetail(
                        row=idx,
                        field="sku_code",
                        message="Missing or invalid sku_code in mapped row",
                    )
                )
                continue

            sku_code = sku_code.strip()

            if sku_code in existing_sku_codes:
                # skip strategy (fail already handled in pre-scan)
                skipped_count += 1
                continue

            # -- Create SKU --
            is_active_val = mapped_row.get("is_active")
            if isinstance(is_active_val, str):
                is_active_val = is_active_val.lower() in ("true", "1", "yes")

            product = CatalogProduct(
                name=mapped_row.get("name", ""),
                description=mapped_row.get("description"),
                category=mapped_row.get("category"),
                is_active=is_active_val if is_active_val is not None else True,
            )
            db.add(product)
            await db.flush()
            sku = SKU(
                catalog_product_id=product.id,
                sku_code=sku_code,
                name=mapped_row.get("name", ""),
                description=mapped_row.get("description"),
                unit=mapped_row.get("unit", "unit"),
                package_quantity=1,
                category=mapped_row.get("category"),
                is_active=is_active_val if is_active_val is not None else True,
            )
            db.add(sku)
            # R1: concurrent duplicate-code race surfaces at flush — mapped to
            # SKU_EXISTS/409 by the named-constraint guard (never a 500).
            await flush_skus_or_409(db, sku_code=sku_code)
            await self._inventory_repo.ensure_stock_row(db, sku_id=sku.id)
            existing_sku_codes.add(sku_code)
            created_count += 1

        # -- Fail-closed: if any row-level errors exist, abort BEFORE marking applied --
        if apply_errors:
            logger.error(
                "import_apply_row_errors",
                extra={
                    "action": "import_apply",
                    "import_id": import_id,
                    "on_conflict": on_conflict,
                    "error_count": len(apply_errors),
                },
            )

            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "ROW_PROCESSING_ERRORS",
                    "message": (
                        f"Apply aborted: {len(apply_errors)} row-level error(s) "
                        f"detected during processing. No SKUs were created and "
                        f"import_run was NOT marked as applied. Fix the data and "
                        f"re-validate before applying again."
                    ),
                    "errors": [e.model_dump() for e in apply_errors],
                },
            )

        # -- Update ImportRun (only on success, no errors) --
        now = datetime.now(timezone.utc)
        run.status = "applied"
        run.created_rows = created_count
        run.skipped_rows = skipped_count
        run.updated_rows = 0
        run.applied_by = applied_by
        run.applied_at = now
        run.apply_result = {
            "on_conflict": on_conflict,
            "created": created_count,
            "skipped": skipped_count,
            "updated": 0,
            "errors": [],
            "applied_at": now.isoformat(),
        }
        await db.flush()

        logger.info(
            "import_apply_completed",
            extra={
                "action": "import_apply",
                "import_id": import_id,
                "on_conflict": on_conflict,
                "created_count": created_count,
                "skipped": skipped_count,
                "updated": 0,
            },
        )

        return ImportApplyResponse(
            import_id=import_id,
            status="completed",
            created=created_count,
            skipped=skipped_count,
            updated=0,
            errors=[],
            audit_run_id=import_id,
            applied_at=now,
            applied_by=str(applied_by) if applied_by else None,
        )

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------
    @staticmethod
    def _decode_bytes(file_bytes: bytes, source_encoding: str = "utf-8") -> str:
        """Decode file bytes to text, auto-detecting UTF-8 BOM (UTF-8-sig).

        If bytes start with the UTF-8 BOM (\\xef\\xbb\\xbf), force UTF-8-sig
        decoding regardless of the source_encoding parameter.  This ensures
        Excel-exported CSVs with BOM are parsed correctly.
        """
        if file_bytes[:3] == b"\xef\xbb\xbf":
            return file_bytes.decode("utf-8-sig")
        try:
            return file_bytes.decode(source_encoding)
        except (UnicodeDecodeError, LookupError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "ENCODING_ERROR",
                    "message": (
                        f"Cannot decode file with encoding '{source_encoding}': {exc}"
                    ),
                },
            )

    @staticmethod
    def _parse_csv(text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Parse CSV text into list-of-dicts + column names.

        Returns (rows, columns).  All values are strings.
        """
        reader = csv.DictReader(io.StringIO(text))
        columns = list(reader.fieldnames or [])
        rows: List[Dict[str, Any]] = []
        for row in reader:
            # Strip whitespace from keys and values
            rows.append({k.strip(): (v.strip() if v else v) for k, v in row.items() if k})
        return rows, columns

    @staticmethod
    def _validate_mapping(mapping: Dict[str, str]) -> List[str]:
        """Return list of error messages if mapping is invalid."""
        errors: List[str] = []
        if not mapping:
            errors.append("Mapping cannot be empty")
            return errors

        for source_col, target_field in mapping.items():
            if not source_col.strip():
                errors.append("Source column name cannot be empty")
            if not target_field.strip():
                errors.append(f"Target field for '{source_col}' cannot be empty")
            if (
                not target_field.startswith(CUSTOM_ATTR_PREFIX)
                and target_field not in ALL_VALID_FIELDS
            ):
                errors.append(
                    f"Unknown target field '{target_field}'. "
                    f"Valid fields: {sorted(ALL_VALID_FIELDS)}. "
                    f"Use '{CUSTOM_ATTR_PREFIX}<key>' for custom attributes."
                )
        return errors

    @staticmethod
    def _apply_mapping(
        row: Dict[str, Any],
        mapping: Dict[str, str],
    ) -> Dict[str, Any]:
        """Transform a raw CSV row into Mpango field dict using mapping."""
        result: Dict[str, Any] = {}
        for source_col, target_field in mapping.items():
            value = row.get(source_col)
            if target_field.startswith(CUSTOM_ATTR_PREFIX):
                # Nest under custom_attributes
                attr_key = target_field[len(CUSTOM_ATTR_PREFIX) :]
                result.setdefault("custom_attributes", {})[attr_key] = value
            else:
                result[target_field] = value
        return result

    @staticmethod
    async def _get_run(db: AsyncSession, import_id: str) -> ImportRun:
        """Load ImportRun by import_id or raise 404."""
        stmt = select(ImportRun).where(ImportRun.import_id == import_id)
        result = await db.execute(stmt)
        run = result.scalar_one_or_none()
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "IMPORT_NOT_FOUND",
                    "message": f"Import run '{import_id}' not found",
                },
            )
        return run
