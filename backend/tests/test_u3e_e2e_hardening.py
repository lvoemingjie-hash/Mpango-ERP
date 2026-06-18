"""U3-E Product Import End-to-End Hardening Tests.

Exercises the full import pipeline (preview -> validate -> apply) with
realistic CSV payloads and a stateful mock DB that chains all three phases.

Coverage (5 CTO-mandated scenarios):
  1. Valid CSV preview -> validate -> apply -> success summary
  2. Invalid CSV shows row-level errors at validate, apply blocked
  3. Duplicate SKU blocked (fail) or reported (skip) at apply
  4. Apply fail-closed: row-level errors => 422, no partial writes
  5. Lifecycle: status transitions previewed -> validated -> applied

No live database required -- all tests use stateful mocks.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Stateful mock DB -- chains preview -> validate -> apply on one ImportRun
# ---------------------------------------------------------------------------

class E2EMockDB:
    """Mock AsyncSession that persists the ImportRun created by preview
    and returns it on subsequent execute() calls.

    Stores all db.add() targets so tests can inspect created SKUs.
    """

    def __init__(self):
        self.run: Optional[Any] = None  # ImportRun created by preview
        self.added_objects: List[Any] = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    def add(self, obj: Any) -> None:
        self.added_objects.append(obj)
        # Capture ImportRun for subsequent _get_run queries
        try:
            from models.import_run import ImportRun
            if isinstance(obj, ImportRun):
                self.run = obj
        except ImportError:
            pass

    async def execute(self, stmt: Any = None) -> MagicMock:
        result = MagicMock()
        result.scalar_one_or_none.return_value = self.run
        result.scalars.return_value.all.return_value = []
        return result

    async def flush(self) -> None:
        self.flush_count += 1

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1

    # -- Convenience accessors -------------------------------------------

    @property
    def skus_added(self) -> List[Any]:
        """Return only SKU objects added to the session."""
        try:
            from models.sku import SKU
            return [o for o in self.added_objects if isinstance(o, SKU)]
        except ImportError:
            return []

    @property
    def sku_codes_created(self) -> List[str]:
        return [s.sku_code for s in self.skus_added]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_csv() -> bytes:
    """5-row valid CSV with standard columns."""
    return (
        "sku_code,name,description,unit,category\n"
        "SKU-001,Widget Alpha,A red widget,piece,Tools\n"
        "SKU-002,Widget Beta,A blue widget,piece,Tools\n"
        "SKU-003,Widget Gamma,A green widget,piece,Tools\n"
        "SKU-004,Gadget Delta,A small gadget,box,Electronics\n"
        "SKU-005,Gadget Epsilon,A large gadget,box,Electronics\n"
    ).encode("utf-8")


def _csv_with_empty_sku() -> bytes:
    """CSV where row 2 has empty sku_code."""
    return (
        "sku_code,name\n"
        "SKU-001,Good Product\n"
        ",Missing Code Product\n"
    ).encode("utf-8")


def _csv_with_missing_name() -> bytes:
    """CSV where row 3 has empty name."""
    return (
        "sku_code,name\n"
        "SKU-001,Has Name\n"
        "SKU-002,Also Named\n"
        "SKU-003,\n"
    ).encode("utf-8")


def _csv_with_intra_file_duplicates() -> bytes:
    """CSV where SKU-001 appears twice."""
    return (
        "sku_code,name\n"
        "SKU-001,First\n"
        "SKU-001,Second Duplicate\n"
        "SKU-002,Unique\n"
    ).encode("utf-8")


TENANT_ID = uuid.uuid4()


# ======================================================================
# Scenario 1: Valid CSV preview -> validate -> apply -> success summary
# ======================================================================

class TestE2EHappyPath:
    """Full pipeline: parse valid CSV, validate, apply, verify success."""

    @pytest.mark.asyncio
    async def test_preview_creates_import_run(self):
        """Preview parses CSV and creates ImportRun with status='previewed'."""
        from services.import_service import ImportService

        db = E2EMockDB()
        svc = ImportService()

        result = await svc.preview(
            db,
            tenant_id=TENANT_ID,
            filename="products.csv",
            file_bytes=_valid_csv(),
        )

        assert result.import_id.startswith("imp_")
        assert result.source.filename == "products.csv"
        assert result.source.row_count == 5
        assert result.source.encoding == "utf-8"
        assert "sku_code" in result.columns_detected
        assert "name" in result.columns_detected
        assert len(result.sample_rows) <= 5

        # ImportRun created and stored
        assert db.run is not None
        assert db.run.status == "previewed"
        assert db.run.total_rows == 5

    @pytest.mark.asyncio
    async def test_validate_transitions_to_validated(self):
        """Validate on clean CSV transitions status to 'validated'."""
        from services.import_service import ImportService

        db = E2EMockDB()
        svc = ImportService()

        preview = await svc.preview(
            db, tenant_id=TENANT_ID, filename="p.csv",
            file_bytes=_valid_csv(),
        )

        mapping = {
            "sku_code": "sku_code",
            "name": "name",
            "description": "description",
            "unit": "unit",
            "category": "category",
        }

        validation = await svc.validate(
            db, import_id=preview.import_id, mapping=mapping,
        )

        assert validation.status == "validated"
        assert validation.valid_rows == 5
        assert validation.error_rows == 0
        assert validation.errors == []
        assert db.run.status == "validated"
        assert db.run.valid_rows == 5
        assert db.run.error_rows == 0

    @pytest.mark.asyncio
    async def test_apply_creates_all_skus_success(self):
        """Apply on validated import creates all 5 SKUs."""
        from services.import_service import ImportService

        db = E2EMockDB()
        svc = ImportService()

        preview = await svc.preview(
            db, tenant_id=TENANT_ID, filename="p.csv",
            file_bytes=_valid_csv(),
        )
        mapping = {
            "sku_code": "sku_code", "name": "name",
            "description": "description", "unit": "unit",
            "category": "category",
        }
        await svc.validate(db, import_id=preview.import_id, mapping=mapping)

        result = await svc.apply(
            db, import_id=preview.import_id, on_conflict="skip",
            existing_sku_codes=set(),
        )

        # -- Response summary --
        assert result.status == "completed"
        assert result.created == 5
        assert result.skipped == 0
        assert result.updated == 0
        assert result.errors == []

        # -- ImportRun final state --
        assert db.run.status == "applied"
        assert db.run.created_rows == 5
        assert db.run.skipped_rows == 0
        assert db.run.applied_at is not None
        assert isinstance(db.run.applied_at, datetime)

        # -- 5 SKU objects added to session --
        assert len(db.sku_codes_created) == 5
        assert "SKU-001" in db.sku_codes_created
        assert "SKU-005" in db.sku_codes_created

    @pytest.mark.asyncio
    async def test_apply_result_jsonb_populated(self):
        """apply_result JSONB contains full summary with on_conflict strategy."""
        from services.import_service import ImportService

        db = E2EMockDB()
        svc = ImportService()

        preview = await svc.preview(
            db, tenant_id=TENANT_ID, filename="p.csv",
            file_bytes=_valid_csv(),
        )
        await svc.validate(
            db, import_id=preview.import_id,
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        await svc.apply(
            db, import_id=preview.import_id, on_conflict="skip",
            existing_sku_codes=set(),
        )

        ar = db.run.apply_result
        assert ar is not None
        assert ar["created"] == 5
        assert ar["skipped"] == 0
        assert ar["updated"] == 0
        assert ar["on_conflict"] == "skip"
        assert ar["errors"] == []
        assert "applied_at" in ar

    @pytest.mark.asyncio
    async def test_full_pipeline_utf8_bom_handled(self):
        """CSV with UTF-8 BOM is parsed correctly through the pipeline."""
        from services.import_service import ImportService

        bom_csv = b"\xef\xbb\xbf" + _valid_csv()
        db = E2EMockDB()
        svc = ImportService()

        preview = await svc.preview(
            db, tenant_id=TENANT_ID, filename="excel_export.csv",
            file_bytes=bom_csv,
        )

        # BOM should not appear in column names
        assert "\ufeff" not in preview.columns_detected[0]
        assert preview.columns_detected[0] == "sku_code"
        assert preview.source.row_count == 5


# ======================================================================
# Scenario 2: Invalid CSV shows row-level errors, apply blocked
# ======================================================================

class TestE2EInvalidCSV:

    @pytest.mark.asyncio
    async def test_empty_sku_code_shows_row_error(self):
        """CSV with empty sku_code in row 2 produces a row-level error."""
        from services.import_service import ImportService

        db = E2EMockDB()
        svc = ImportService()

        preview = await svc.preview(
            db, tenant_id=TENANT_ID, filename="bad.csv",
            file_bytes=_csv_with_empty_sku(),
        )
        validation = await svc.validate(
            db, import_id=preview.import_id,
            mapping={"sku_code": "sku_code", "name": "name"},
        )

        assert validation.status == "needs_review"
        assert validation.error_rows == 1
        assert validation.valid_rows == 1
        assert len(validation.errors) >= 1

        # Error should reference row 2 (the empty code)
        error = validation.errors[0]
        assert error.row == 2
        assert error.field == "sku_code"

        # ImportRun status reflects needs_review
        assert db.run.status == "needs_review"

    @pytest.mark.asyncio
    async def test_empty_name_shows_row_error(self):
        """CSV with empty name in row 3 produces a row-level error."""
        from services.import_service import ImportService

        db = E2EMockDB()
        svc = ImportService()

        preview = await svc.preview(
            db, tenant_id=TENANT_ID, filename="bad.csv",
            file_bytes=_csv_with_missing_name(),
        )
        validation = await svc.validate(
            db, import_id=preview.import_id,
            mapping={"sku_code": "sku_code", "name": "name"},
        )

        assert validation.status == "needs_review"
        assert validation.error_rows >= 1

        # Find the error for row 3
        row3_errors = [e for e in validation.errors if e.row == 3]
        assert len(row3_errors) >= 1
        assert row3_errors[0].field == "name"

    @pytest.mark.asyncio
    async def test_apply_blocked_on_needs_review(self):
        """Cannot apply when import_run status is 'needs_review'."""
        from services.import_service import ImportService

        db = E2EMockDB()
        svc = ImportService()

        preview = await svc.preview(
            db, tenant_id=TENANT_ID, filename="bad.csv",
            file_bytes=_csv_with_empty_sku(),
        )
        await svc.validate(
            db, import_id=preview.import_id,
            mapping={"sku_code": "sku_code", "name": "name"},
        )

        # Status is now 'needs_review' -> apply must reject
        with pytest.raises(Exception) as exc_info:
            await svc.apply(
                db, import_id=preview.import_id, on_conflict="skip",
                existing_sku_codes=set(),
            )
        assert "INVALID_STATUS" in str(exc_info.value)
        # No SKUs created
        assert len(db.skus_added) == 0

    @pytest.mark.asyncio
    async def test_intra_file_duplicates_detected_at_validate(self):
        """Duplicate sku_code within the same CSV file is flagged at validate."""
        from services.import_service import ImportService

        db = E2EMockDB()
        svc = ImportService()

        preview = await svc.preview(
            db, tenant_id=TENANT_ID, filename="dup.csv",
            file_bytes=_csv_with_intra_file_duplicates(),
        )
        validation = await svc.validate(
            db, import_id=preview.import_id,
            mapping={"sku_code": "sku_code", "name": "name"},
        )

        assert validation.status == "needs_review"
        assert validation.error_rows >= 1

        dup_errors = [
            e for e in validation.errors if "Duplicate" in e.message
        ]
        assert len(dup_errors) >= 1
        assert dup_errors[0].sku_code == "SKU-001"


# ======================================================================
# Scenario 3: Duplicate SKU blocked (fail) or reported (skip)
# ======================================================================

class TestE2EDuplicateHandling:

    @pytest.mark.asyncio
    async def test_skip_strategy_skips_existing_creates_new(self):
        """on_conflict='skip': existing SKU skipped, new SKUs created."""
        from services.import_service import ImportService

        db = E2EMockDB()
        svc = ImportService()

        preview = await svc.preview(
            db, tenant_id=TENANT_ID, filename="p.csv",
            file_bytes=_valid_csv(),
        )
        await svc.validate(
            db, import_id=preview.import_id,
            mapping={"sku_code": "sku_code", "name": "name"},
        )

        # SKU-001 and SKU-003 already exist in catalog
        result = await svc.apply(
            db, import_id=preview.import_id, on_conflict="skip",
            existing_sku_codes={"SKU-001", "SKU-003"},
        )

        assert result.status == "completed"
        assert result.created == 3  # SKU-002, 004, 005
        assert result.skipped == 2  # SKU-001, 003

        created = set(db.sku_codes_created)
        assert "SKU-002" in created
        assert "SKU-004" in created
        assert "SKU-005" in created
        assert "SKU-001" not in created
        assert "SKU-003" not in created

    @pytest.mark.asyncio
    async def test_fail_strategy_blocks_all_on_conflict(self):
        """on_conflict='fail': any existing sku_code => 409, nothing created."""
        from services.import_service import ImportService

        db = E2EMockDB()
        svc = ImportService()

        preview = await svc.preview(
            db, tenant_id=TENANT_ID, filename="p.csv",
            file_bytes=_valid_csv(),
        )
        await svc.validate(
            db, import_id=preview.import_id,
            mapping={"sku_code": "sku_code", "name": "name"},
        )

        with pytest.raises(Exception) as exc_info:
            await svc.apply(
                db, import_id=preview.import_id, on_conflict="fail",
                existing_sku_codes={"SKU-002"},
            )

        err = str(exc_info.value).upper()
        assert "CONFLICT" in err or "409" in err

        # No SKUs created -- zero db.add(SKU) calls
        assert len(db.skus_added) == 0
        # Status remains 'validated', NOT 'applied'
        assert db.run.status == "validated"

    @pytest.mark.asyncio
    async def test_validate_warns_about_existing_catalog_codes(self):
        """Validate phase produces warnings for SKU codes already in catalog."""
        from services.import_service import ImportService

        db = E2EMockDB()
        svc = ImportService()

        preview = await svc.preview(
            db, tenant_id=TENANT_ID, filename="p.csv",
            file_bytes=_valid_csv(),
        )
        validation = await svc.validate(
            db, import_id=preview.import_id,
            mapping={"sku_code": "sku_code", "name": "name"},
            existing_sku_codes={"SKU-001"},
        )

        # Still valid (warnings don't block)
        assert validation.status == "validated"
        assert validation.error_rows == 0
        assert validation.warning_rows >= 1

        # Warning mentions SKU-001 already exists
        catalog_warnings = [
            w for w in validation.warnings if "SKU-001" in w.message
        ]
        assert len(catalog_warnings) >= 1

    @pytest.mark.asyncio
    async def test_skip_all_existing_all_skipped(self):
        """skip: all rows exist in catalog => 0 created, all skipped."""
        from services.import_service import ImportService

        db = E2EMockDB()
        svc = ImportService()

        preview = await svc.preview(
            db, tenant_id=TENANT_ID, filename="p.csv",
            file_bytes=_valid_csv(),
        )
        await svc.validate(
            db, import_id=preview.import_id,
            mapping={"sku_code": "sku_code", "name": "name"},
        )

        all_codes = {"SKU-001", "SKU-002", "SKU-003", "SKU-004", "SKU-005"}
        result = await svc.apply(
            db, import_id=preview.import_id, on_conflict="skip",
            existing_sku_codes=all_codes,
        )

        assert result.created == 0
        assert result.skipped == 5
        assert len(db.skus_added) == 0


# ======================================================================
# Scenario 4: Apply fail-closed -- no partial import on row errors
# ======================================================================

class TestE2EFailClosed:
    """Verify that when apply encounters row-level processing errors,
    it raises 422 WITHOUT marking the run as applied.

    Fail-closed guarantee:
      - Service raises 422 before setting run.status='applied'
      - Endpoint handler catches exception and calls db.rollback()
      - Transaction semantics ensure no SKUs are committed

    For ALL-rows-corrupt scenarios, db.add(SKU) is never called.
    For MIXED valid+corrupt scenarios, db.add may be called for valid rows
    before the corrupt row triggers 422, but db.rollback() in the endpoint
    handler discards those adds.  These tests verify the service-level
    invariant (422 raised, run NOT marked applied).
    """

    @pytest.mark.asyncio
    async def test_all_corrupt_rows_zero_db_add(self):
        """When ALL rows are corrupt, no SKU is ever added to the session."""
        from services.import_service import ImportService
        from models.import_run import ImportRun

        run = ImportRun(
            import_id="imp_all_corrupt",
            tenant_id=TENANT_ID,
            status="validated",
            total_rows=2,
            mapping={
                "columns": ["sku_code", "name"],
                "rows": [
                    {"product_code": "X", "name": "A"},  # wrong key
                    {"product_code": "Y", "name": "B"},  # wrong key
                ],
                "field_mapping": {"sku_code": "sku_code", "name": "name"},
            },
        )
        db = E2EMockDB()
        db.run = run
        db.added_objects.append(run)

        svc = ImportService()

        with pytest.raises(Exception) as exc_info:
            await svc.apply(
                db, import_id="imp_all_corrupt", on_conflict="skip",
                existing_sku_codes=set(),
            )

        err = str(exc_info.value).upper()
        assert "ROW_PROCESSING_ERRORS" in err or "422" in err
        assert run.status == "validated"
        assert len(db.skus_added) == 0

    @pytest.mark.asyncio
    async def test_all_empty_sku_codes_zero_db_add(self):
        """All rows with empty sku_code => no SKU added."""
        from services.import_service import ImportService
        from models.import_run import ImportRun

        run = ImportRun(
            import_id="imp_all_empty",
            tenant_id=TENANT_ID,
            status="validated",
            total_rows=2,
            mapping={
                "columns": ["sku_code", "name"],
                "rows": [
                    {"sku_code": "", "name": "A"},
                    {"sku_code": "", "name": "B"},
                ],
                "field_mapping": {"sku_code": "sku_code", "name": "name"},
            },
        )
        db = E2EMockDB()
        db.run = run
        db.added_objects.append(run)

        svc = ImportService()

        with pytest.raises(Exception) as exc_info:
            await svc.apply(
                db, import_id="imp_all_empty", on_conflict="skip",
                existing_sku_codes=set(),
            )

        assert "ROW_PROCESSING_ERRORS" in str(exc_info.value).upper() or \
               "422" in str(exc_info.value)
        assert run.status == "validated"
        assert len(db.skus_added) == 0

    @pytest.mark.asyncio
    async def test_mixed_valid_corrupt_raises_422_not_applied(self):
        """Mixed valid+corrupt rows: 422 raised, run NOT marked applied.

        The valid row may be db.add()'ed before the corrupt row triggers
        the error, but db.rollback() in the endpoint handler discards it.
        Service-level invariant: run.status stays 'validated'.
        """
        from services.import_service import ImportService
        from models.import_run import ImportRun

        run = ImportRun(
            import_id="imp_mixed",
            tenant_id=TENANT_ID,
            status="validated",
            total_rows=2,
            mapping={
                "columns": ["sku_code", "name"],
                "rows": [
                    {"sku_code": "GOOD-001", "name": "Good"},
                    {"wrong_col": "BAD", "name": "Bad"},
                ],
                "field_mapping": {"sku_code": "sku_code", "name": "name"},
            },
        )
        db = E2EMockDB()
        db.run = run
        db.added_objects.append(run)

        svc = ImportService()

        with pytest.raises(Exception) as exc_info:
            await svc.apply(
                db, import_id="imp_mixed", on_conflict="skip",
                existing_sku_codes=set(),
            )

        assert "ROW_PROCESSING_ERRORS" in str(exc_info.value).upper() or \
               "422" in str(exc_info.value)
        # CRITICAL: run is NOT marked applied (transaction will be rolled back)
        assert run.status == "validated"

    @pytest.mark.asyncio
    async def test_custom_attributes_stops_with_no_creation(self):
        """custom_attributes.* mapping triggers STOP_AND_REPORT_CTO, no SKUs."""
        from services.import_service import ImportService
        from models.import_run import ImportRun

        run = ImportRun(
            import_id="imp_custom",
            tenant_id=TENANT_ID,
            status="validated",
            total_rows=1,
            mapping={
                "columns": ["sku_code", "name", "Brand"],
                "rows": [{"sku_code": "S1", "name": "A", "Brand": "Nike"}],
                "field_mapping": {
                    "sku_code": "sku_code",
                    "name": "name",
                    "Brand": "custom_attributes.brand",
                },
            },
        )
        db = E2EMockDB()
        db.run = run
        db.added_objects.append(run)

        svc = ImportService()

        with pytest.raises(Exception) as exc_info:
            await svc.apply(
                db, import_id="imp_custom", on_conflict="skip",
                existing_sku_codes=set(),
            )

        assert "STOP_AND_REPORT_CTO" in str(exc_info.value)
        assert len(db.skus_added) == 0
        assert run.status == "validated"


# ======================================================================
# Scenario 5: Lifecycle status transitions
# ======================================================================

class TestE2ELifecycle:
    """Verify the full ImportRun status lifecycle."""

    @pytest.mark.asyncio
    async def test_status_previewed_to_validated_to_applied(self):
        """Status transitions: previewed -> validated -> applied."""
        from services.import_service import ImportService

        db = E2EMockDB()
        svc = ImportService()

        # After preview: status = previewed
        preview = await svc.preview(
            db, tenant_id=TENANT_ID, filename="p.csv",
            file_bytes=_valid_csv(),
        )
        assert db.run.status == "previewed"

        # After validate: status = validated
        await svc.validate(
            db, import_id=preview.import_id,
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        assert db.run.status == "validated"

        # After apply: status = applied
        await svc.apply(
            db, import_id=preview.import_id, on_conflict="skip",
            existing_sku_codes=set(),
        )
        assert db.run.status == "applied"

    @pytest.mark.asyncio
    async def test_validated_stores_field_mapping(self):
        """After validate, run.mapping contains field_mapping dict."""
        from services.import_service import ImportService

        db = E2EMockDB()
        svc = ImportService()

        preview = await svc.preview(
            db, tenant_id=TENANT_ID, filename="p.csv",
            file_bytes=_valid_csv(),
        )
        mapping = {"sku_code": "sku_code", "name": "name"}
        await svc.validate(
            db, import_id=preview.import_id, mapping=mapping,
        )

        stored_mapping = db.run.mapping.get("field_mapping", {})
        assert stored_mapping == mapping

    @pytest.mark.asyncio
    async def test_applied_sets_audit_fields(self):
        """Apply sets applied_by and applied_at."""
        from services.import_service import ImportService

        db = E2EMockDB()
        svc = ImportService()
        user_uuid = uuid.uuid4()

        preview = await svc.preview(
            db, tenant_id=TENANT_ID, filename="p.csv",
            file_bytes=_valid_csv(),
        )
        await svc.validate(
            db, import_id=preview.import_id,
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        await svc.apply(
            db, import_id=preview.import_id, on_conflict="skip",
            applied_by=user_uuid,
            existing_sku_codes=set(),
        )

        assert db.run.applied_by == user_uuid
        assert db.run.applied_at is not None

    @pytest.mark.asyncio
    async def test_double_apply_rejected(self):
        """Applying an already-applied run is rejected with INVALID_STATUS."""
        from services.import_service import ImportService

        db = E2EMockDB()
        svc = ImportService()

        preview = await svc.preview(
            db, tenant_id=TENANT_ID, filename="p.csv",
            file_bytes=_valid_csv(),
        )
        await svc.validate(
            db, import_id=preview.import_id,
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        await svc.apply(
            db, import_id=preview.import_id, on_conflict="skip",
            existing_sku_codes=set(),
        )
        assert db.run.status == "applied"

        with pytest.raises(Exception) as exc_info:
            await svc.apply(
                db, import_id=preview.import_id, on_conflict="skip",
                existing_sku_codes=set(),
            )
        assert "INVALID_STATUS" in str(exc_info.value)


# ======================================================================
# Contract regression guards
# ======================================================================

class TestE2EContractGuards:
    """Static / structural guards that key invariants are preserved."""

    def test_three_phase_methods_exist(self):
        """ImportService must expose preview, validate, apply."""
        from pathlib import Path
        svc_py = Path(__file__).resolve().parent.parent / "services" / "import_service.py"
        src = svc_py.read_text(encoding="utf-8")
        assert "async def preview" in src
        assert "async def validate" in src
        assert "async def apply" in src

    def test_required_fields_constant(self):
        """REQUIRED_FIELDS must be sku_code + name."""
        from services.import_service import REQUIRED_FIELDS
        assert REQUIRED_FIELDS == {"sku_code", "name"}

    def test_apply_only_adds_sku_objects(self):
        """AST check: apply only calls db.add with SKU(...)."""
        import ast
        from pathlib import Path
        svc_py = Path(__file__).resolve().parent.parent / "services" / "import_service.py"
        src = svc_py.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "apply":
                body = ast.get_source_segment(src, node)
                assert body is not None
                assert "SKU(" in body
                assert "InventoryStock" not in body
                assert "RetailerPrice" not in body
                assert "Order" not in body
                assert "Payment" not in body
                break

    def test_permission_guard_on_all_endpoints(self):
        """All three import endpoints must require skus:import permission."""
        from pathlib import Path
        router_py = Path(__file__).resolve().parent.parent / "api" / "v1" / "sku_imports.py"
        src = router_py.read_text(encoding="utf-8")
        assert src.count('RequirePermission("skus:import")') >= 3

    def test_apply_uses_fail_closed_pattern(self):
        """Apply method must check apply_errors BEFORE marking run as applied."""
        from pathlib import Path
        svc_py = Path(__file__).resolve().parent.parent / "services" / "import_service.py"
        src = svc_py.read_text(encoding="utf-8")
        # The fail-closed check must come before status='applied'
        error_check_pos = src.find("if apply_errors:")
        applied_pos = src.find('run.status = "applied"')
        assert error_check_pos > 0, "apply_errors check not found"
        assert applied_pos > 0, "status = applied not found"
        assert error_check_pos < applied_pos, (
            "Fail-closed check must come before marking run as applied"
        )
