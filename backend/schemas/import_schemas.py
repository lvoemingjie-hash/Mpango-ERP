"""U3-B1 Import Contract Schemas -- 3-phase preview/validate/apply.

These Pydantic schemas define the API contract for the agent-operable
SKU import pipeline.  They are contract-only -- no business logic here.

Phase 1 (preview):  Parse input, detect structure, return import_id.
Phase 2 (validate): Apply field mapping, return row-level errors/warnings.
Phase 3 (apply):    Execute the import, return created/skipped/errors.

All schemas use snake_case (consistent with the existing API convention).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared row-level detail types
# ---------------------------------------------------------------------------

class ImportErrorDetail(BaseModel):
    """A single row-level error from validation or apply."""
    row: int = Field(..., description="1-based row number in the source file")
    field: Optional[str] = Field(
        None, description="Field name that caused the error, if applicable"
    )
    sku_code: Optional[str] = Field(
        None, description="sku_code value from the row, if available"
    )
    message: str = Field(..., description="Human-readable error description")


class ImportWarningDetail(BaseModel):
    """A single row-level warning from validation."""
    row: int = Field(..., description="1-based row number in the source file")
    field: Optional[str] = Field(
        None, description="Field name that triggered the warning"
    )
    message: str = Field(..., description="Human-readable warning description")


# ---------------------------------------------------------------------------
# Phase 1: Preview
# ---------------------------------------------------------------------------

class ImportSourceInfo(BaseModel):
    """Metadata about the uploaded source file."""
    filename: str
    encoding: str = "utf-8"
    row_count: int


class ImportPreviewResponse(BaseModel):
    """Response from POST /api/v1/skus/import/preview.

    Returns parsed file structure without any writes.
    """
    import_id: str = Field(
        ..., description="Stable opaque ID for chaining validate/apply phases"
    )
    source: ImportSourceInfo
    columns_detected: List[str] = Field(
        ..., description="Column headers detected in the source file"
    )
    sample_rows: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="First N rows (max 5) for caller inspection",
    )


# ---------------------------------------------------------------------------
# Phase 2: Validate
# ---------------------------------------------------------------------------

class ImportFieldMapping(BaseModel):
    """Maps source columns to Mpango fields.

    Keys are source column names; values are Mpango field names.
    Use 'custom_attributes.<key>' for custom attributes.
    """
    # Use a plain dict -- Pydantic will validate structure at runtime
    mapping: Dict[str, str] = Field(
        ...,
        description=(
            "Column mapping: source column -> Mpango field. "
            "Use 'custom_attributes.<key>' for unmapped columns."
        ),
    )


class ImportValidateRequest(BaseModel):
    """Request body for POST /api/v1/skus/import/{import_id}/validate."""
    mapping: Dict[str, str] = Field(
        ...,
        description=(
            "Column mapping: source column name -> Mpango field name. "
            "Use 'custom_attributes.<key>' for custom attribute fields."
        ),
    )


class ImportValidateResponse(BaseModel):
    """Response from POST /api/v1/skus/import/{import_id}/validate.

    Returns structured row-level errors and warnings. No writes.
    """
    import_id: str
    status: Literal["validated", "needs_review"] = Field(
        ..., description="validated if 0 errors; needs_review if errors > 0"
    )
    valid_rows: int = Field(..., description="Rows that passed all validation rules")
    error_rows: int = Field(..., description="Rows with one or more errors")
    warning_rows: int = Field(
        default=0, description="Rows with warnings (still importable)"
    )
    errors: List[ImportErrorDetail] = Field(default_factory=list)
    warnings: List[ImportWarningDetail] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 3: Apply
# ---------------------------------------------------------------------------

class ImportApplyRequest(BaseModel):
    """Request body for POST /api/v1/skus/import/{import_id}/apply."""
    on_conflict: Literal["skip", "fail"] = Field(
        default="skip",
        description=(
            "Conflict strategy when sku_code already exists in tenant: "
            "skip = skip row, fail = abort entire import"
        ),
    )


class ImportApplyResponse(BaseModel):
    """Response from POST /api/v1/skus/import/{import_id}/apply.

    Returns the result of the import with audit trail reference.
    Only returns 'completed' (zero errors) or 'failed' (exception raised).
    Never returns non-empty errors with a completed status.
    """
    import_id: str
    status: Literal["completed", "failed"] = Field(
        ..., description="Final status of the import run"
    )
    created: int = Field(default=0, description="SKUs successfully created")
    skipped: int = Field(default=0, description="SKUs skipped (duplicate, conflict)")
    updated: int = Field(default=0, description="SKUs updated (on_conflict=update)")
    errors: List[ImportErrorDetail] = Field(
        default_factory=list,
        description="Row-level errors encountered during apply",
    )
    audit_run_id: Optional[str] = Field(
        None, description="ID of the import_runs audit record"
    )
    applied_at: Optional[datetime] = Field(
        None, description="Timestamp when apply was executed"
    )
    applied_by: Optional[str] = Field(
        None, description="User UUID who triggered the apply"
    )
