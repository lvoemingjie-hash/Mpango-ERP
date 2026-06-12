"""U3-B2 Import Service -- preview + validate logic for SKU bulk import.

This service handles the first two phases of the 3-phase import contract:
  Phase 1 (preview):  Parse CSV, detect columns, store raw rows in ImportRun.
  Phase 2 (validate): Apply field mapping, run row-level validation rules.

CRITICAL constraint (CTO directive): only write to import_runs,
never to SKU/inventory tables.  Real persistence is left for U3-C apply.
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
from schemas.import_schemas import (
    ImportErrorDetail,
    ImportPreviewResponse,
    ImportSourceInfo,
    ImportValidateResponse,
    ImportWarningDetail,
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
