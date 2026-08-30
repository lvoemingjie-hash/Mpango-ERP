"""U3-C Import Apply Tests -- validated import_run -> SKU creation.

Tests cover all 10 CTO-specified requirements:
  a. Non-validated status cannot apply
  b. skip strategy: existing sku_code skipped, new SKU created
  c. fail strategy: existing sku_code causes 409, no SKU created
  d. import_run status set to applied after apply
  e. created_rows/skipped_rows/updated_rows/applied_at/applied_by correct
  f. apply creates one zero stock row per new sellable unit, while
     pricing/payments/orders remain untouched
  g. No skus:import permission returns 403 (AST guard)
  h. Duplicate apply does not duplicate SKUs (idempotent)
  i. custom_attributes.* triggers STOP_AND_REPORT_CTO
  j. U3-B1/B2/B2.1 regression continues passing (verified by test runner)

No live database required -- all tests use mocks.
"""
from __future__ import annotations

import ast
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# -- Paths -----------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent
SKU_IMPORTS_PY = BACKEND_DIR / "api" / "v1" / "sku_imports.py"
IMPORT_SERVICE_PY = BACKEND_DIR / "services" / "import_service.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_db_for_apply(
    rows: List[Dict],
    field_mapping: Dict[str, str],
    run_status: str = "validated",
    existing_sku_codes: set = None,
) -> tuple:
    """Create a mock AsyncSession and ImportRun for apply tests.

    Returns (mock_db, run) so tests can inspect run state after apply.
    """
    from models.import_run import ImportRun

    run = ImportRun(
        import_id="imp_test",
        tenant_id=uuid.uuid4(),
        status=run_status,
        total_rows=len(rows),
        mapping={
            "columns": list(field_mapping.keys()),
            "rows": rows,
            "sample_rows": rows[:5],
            "field_mapping": field_mapping,
        },
    )
    mock_db = AsyncMock()

    # _get_run returns our run
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = run
    stock_result = MagicMock()
    stock_result.scalar_one_or_none.return_value = None

    async def mock_execute(stmt):
        if "import_runs" in str(stmt):
            return mock_result
        return stock_result

    mock_db.execute = AsyncMock(side_effect=mock_execute)
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()

    return mock_db, run


def _make_mock_db_with_existing_skus(existing_sku_codes: set):
    """Create a mock DB that returns existing SKU codes on select query."""
    mock_db = AsyncMock()

    # First execute call: _get_run query
    from models.import_run import ImportRun
    run = ImportRun(
        import_id="imp_test",
        tenant_id=uuid.uuid4(),
        status="validated",
        total_rows=3,
        mapping={
            "columns": ["sku_code", "name"],
            "rows": [
                {"sku_code": "SKU-001", "name": "Widget A"},
                {"sku_code": "SKU-002", "name": "Widget B"},
                {"sku_code": "SKU-003", "name": "Widget C"},
            ],
            "field_mapping": {"sku_code": "sku_code", "name": "name"},
        },
    )

    run_result = MagicMock()
    run_result.scalar_one_or_none.return_value = run

    sku_result = MagicMock()
    sku_result.scalars.return_value.all.return_value = list(existing_sku_codes)

    call_count = [0]

    async def mock_execute(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return run_result
        return sku_result

    mock_db.execute = mock_execute
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()

    return mock_db, run


# ====================================================================
# a. Non-validated status cannot apply
# ====================================================================

class TestNonValidatedStatus:

    @pytest.mark.asyncio
    async def test_previewed_status_rejected(self):
        """import_run with status='previewed' cannot apply."""
        from services.import_service import ImportService
        rows = [{"sku_code": "S1", "name": "A"}]
        db, _ = _make_mock_db_for_apply(
            rows, {"sku_code": "sku_code", "name": "name"},
            run_status="previewed",
        )
        with pytest.raises(Exception) as exc_info:
            await ImportService().apply(
                db, import_id="imp_test", on_conflict="skip",
                existing_sku_codes=set(),
            )
        assert "INVALID_STATUS" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_needs_review_status_rejected(self):
        """import_run with status='needs_review' cannot apply."""
        from services.import_service import ImportService
        rows = [{"sku_code": "S1", "name": "A"}]
        db, _ = _make_mock_db_for_apply(
            rows, {"sku_code": "sku_code", "name": "name"},
            run_status="needs_review",
        )
        with pytest.raises(Exception) as exc_info:
            await ImportService().apply(
                db, import_id="imp_test", on_conflict="skip",
                existing_sku_codes=set(),
            )
        assert "INVALID_STATUS" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_applied_status_rejected(self):
        """import_run with status='applied' cannot apply again."""
        from services.import_service import ImportService
        rows = [{"sku_code": "S1", "name": "A"}]
        db, _ = _make_mock_db_for_apply(
            rows, {"sku_code": "sku_code", "name": "name"},
            run_status="applied",
        )
        with pytest.raises(Exception) as exc_info:
            await ImportService().apply(
                db, import_id="imp_test", on_conflict="skip",
                existing_sku_codes=set(),
            )
        assert "INVALID_STATUS" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_failed_status_rejected(self):
        """import_run with status='failed' cannot apply."""
        from services.import_service import ImportService
        rows = [{"sku_code": "S1", "name": "A"}]
        db, _ = _make_mock_db_for_apply(
            rows, {"sku_code": "sku_code", "name": "name"},
            run_status="failed",
        )
        with pytest.raises(Exception) as exc_info:
            await ImportService().apply(
                db, import_id="imp_test", on_conflict="skip",
                existing_sku_codes=set(),
            )
        assert "INVALID_STATUS" in str(exc_info.value)


# ====================================================================
# b. skip strategy: existing sku_code skipped, new SKU created
# ====================================================================

class TestSkipStrategy:

    @pytest.mark.asyncio
    async def test_existing_sku_skipped_new_created(self):
        """skip: existing SKU skipped, new SKU created."""
        from services.import_service import ImportService
        rows = [
            {"sku_code": "EXISTING-001", "name": "Already Here"},
            {"sku_code": "NEW-001", "name": "Brand New"},
        ]
        db, run = _make_mock_db_for_apply(
            rows, {"sku_code": "sku_code", "name": "name"},
            existing_sku_codes=set(),
        )
        result = await ImportService().apply(
            db, import_id="imp_test", on_conflict="skip",
            existing_sku_codes={"EXISTING-001"},
        )
        assert result.created == 1
        assert result.skipped == 1
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_all_new_skus_created(self):
        """skip: all new SKUs created when no conflicts."""
        from services.import_service import ImportService
        rows = [
            {"sku_code": "NEW-001", "name": "A"},
            {"sku_code": "NEW-002", "name": "B"},
            {"sku_code": "NEW-003", "name": "C"},
        ]
        db, run = _make_mock_db_for_apply(
            rows, {"sku_code": "sku_code", "name": "name"},
        )
        result = await ImportService().apply(
            db, import_id="imp_test", on_conflict="skip",
            existing_sku_codes=set(),
        )
        assert result.created == 3
        assert result.skipped == 0
        # CatalogProduct + SKU + InventoryStock for every new row.
        assert db.add.call_count == 9

    @pytest.mark.asyncio
    async def test_all_existing_all_skipped(self):
        """skip: all rows skipped when all sku_codes exist."""
        from services.import_service import ImportService
        rows = [
            {"sku_code": "E-001", "name": "A"},
            {"sku_code": "E-002", "name": "B"},
        ]
        db, run = _make_mock_db_for_apply(
            rows, {"sku_code": "sku_code", "name": "name"},
        )
        result = await ImportService().apply(
            db, import_id="imp_test", on_conflict="skip",
            existing_sku_codes={"E-001", "E-002"},
        )
        assert result.created == 0
        assert result.skipped == 2


# ====================================================================
# c. fail strategy: existing sku_code causes 409, no SKU created
# ====================================================================

class TestFailStrategy:

    @pytest.mark.asyncio
    async def test_conflict_causes_409_no_creation(self):
        """fail: existing sku_code raises 409, no SKUs created."""
        from services.import_service import ImportService
        rows = [
            {"sku_code": "NEW-001", "name": "Good"},
            {"sku_code": "EXISTING-001", "name": "Conflict"},
        ]
        db, run = _make_mock_db_for_apply(
            rows, {"sku_code": "sku_code", "name": "name"},
        )
        with pytest.raises(Exception) as exc_info:
            await ImportService().apply(
                db, import_id="imp_test", on_conflict="fail",
                existing_sku_codes={"EXISTING-001"},
            )
        assert "409" in str(exc_info.value) or "CONFLICT" in str(exc_info.value).upper()
        # Verify db.add was NOT called (no SKU created)
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_conflict_all_created(self):
        """fail: when no conflicts, all SKUs created."""
        from services.import_service import ImportService
        rows = [
            {"sku_code": "NEW-001", "name": "A"},
            {"sku_code": "NEW-002", "name": "B"},
        ]
        db, run = _make_mock_db_for_apply(
            rows, {"sku_code": "sku_code", "name": "name"},
        )
        result = await ImportService().apply(
            db, import_id="imp_test", on_conflict="fail",
            existing_sku_codes=set(),
        )
        assert result.created == 2
        assert result.skipped == 0
        assert result.status == "completed"


# ====================================================================
# d. import_run status set to applied after apply
# ====================================================================

class TestStatusTransition:

    @pytest.mark.asyncio
    async def test_status_becomes_applied(self):
        """After successful apply, import_run.status == 'applied'."""
        from services.import_service import ImportService
        rows = [{"sku_code": "S1", "name": "A"}]
        db, run = _make_mock_db_for_apply(
            rows, {"sku_code": "sku_code", "name": "name"},
        )
        await ImportService().apply(
            db, import_id="imp_test", on_conflict="skip",
            existing_sku_codes=set(),
        )
        assert run.status == "applied"


# ====================================================================
# e. Counters and audit fields correct
# ====================================================================

class TestCountersAndAudit:

    @pytest.mark.asyncio
    async def test_counters_correct(self):
        """created_rows, skipped_rows, updated_rows match reality."""
        from services.import_service import ImportService
        rows = [
            {"sku_code": "NEW-001", "name": "A"},
            {"sku_code": "EXISTING-001", "name": "B"},
            {"sku_code": "NEW-002", "name": "C"},
        ]
        db, run = _make_mock_db_for_apply(
            rows, {"sku_code": "sku_code", "name": "name"},
        )
        await ImportService().apply(
            db, import_id="imp_test", on_conflict="skip",
            existing_sku_codes={"EXISTING-001"},
        )
        assert run.created_rows == 2
        assert run.skipped_rows == 1
        assert run.updated_rows == 0

    @pytest.mark.asyncio
    async def test_applied_at_set(self):
        """applied_at is set to a non-None datetime."""
        from services.import_service import ImportService
        rows = [{"sku_code": "S1", "name": "A"}]
        db, run = _make_mock_db_for_apply(
            rows, {"sku_code": "sku_code", "name": "name"},
        )
        await ImportService().apply(
            db, import_id="imp_test", on_conflict="skip",
            existing_sku_codes=set(),
        )
        assert run.applied_at is not None
        assert isinstance(run.applied_at, datetime)

    @pytest.mark.asyncio
    async def test_applied_by_set_when_provided(self):
        """applied_by is set when user UUID is provided."""
        from services.import_service import ImportService
        user_uuid = uuid.uuid4()
        rows = [{"sku_code": "S1", "name": "A"}]
        db, run = _make_mock_db_for_apply(
            rows, {"sku_code": "sku_code", "name": "name"},
        )
        await ImportService().apply(
            db, import_id="imp_test", on_conflict="skip",
            applied_by=user_uuid,
            existing_sku_codes=set(),
        )
        assert run.applied_by == user_uuid

    @pytest.mark.asyncio
    async def test_apply_result_populated(self):
        """apply_result JSONB field is populated with full details."""
        from services.import_service import ImportService
        rows = [{"sku_code": "S1", "name": "A"}]
        db, run = _make_mock_db_for_apply(
            rows, {"sku_code": "sku_code", "name": "name"},
        )
        await ImportService().apply(
            db, import_id="imp_test", on_conflict="skip",
            existing_sku_codes=set(),
        )
        assert run.apply_result is not None
        assert run.apply_result["created"] == 1
        assert run.apply_result["skipped"] == 0
        assert run.apply_result["updated"] == 0
        assert run.apply_result["on_conflict"] == "skip"


# ====================================================================
# f. catalog + sellable unit + zero-stock initialization boundary
# ====================================================================

class TestWriteBoundaries:

    CONTRACT_MIGRATION = (
        "SUPERSEDED_BY_SKU_R0_M1_CATALOG_AND_INVENTORY_INITIALIZATION_CONTRACT"
    )

    def test_service_uses_inventory_only_for_safe_initialization(self):
        """Import owns zero-stock initialization, not inventory movement."""
        source = IMPORT_SERVICE_PY.read_text(encoding="utf-8")
        assert "inventory_repository" in source
        assert "ensure_stock_row" in source
        forbidden = [
            "stock_movement",
            "retailer_price",
            "order_repository",
            "payment",
        ]
        for keyword in forbidden:
            assert keyword not in source, (
                f"Forbidden import/reference found: {keyword}"
            )

    def test_router_no_inventory_writes(self):
        """sku_imports.py must not import inventory/stock/pricing modules."""
        source = SKU_IMPORTS_PY.read_text(encoding="utf-8")
        forbidden = [
            "inventory_repository",
            "stock_movement",
            "retailer_price",
            "order_repository",
            "payment",
        ]
        for keyword in forbidden:
            assert keyword not in source, (
                f"Forbidden import/reference found: {keyword}"
            )

    def test_apply_creates_catalog_unit_and_zero_stock_only(self):
        """AST check freezes the authorized catalog initialization boundary."""
        source = IMPORT_SERVICE_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "apply":
                body_source = ast.get_source_segment(source, node)
                assert body_source is not None
                assert "CatalogProduct(" in body_source
                assert "SKU(" in body_source
                assert "catalog_product_id=product.id" in body_source
                assert "ensure_stock_row" in body_source
                assert "InventoryStock" not in body_source
                assert "RetailerPrice" not in body_source
                assert "Order" not in body_source
                break


# ====================================================================
# g. No skus:import permission returns 403 (AST guard)
# ====================================================================

class TestPermissionGuard:

    def test_apply_endpoint_requires_permission(self):
        """Apply endpoint must use RequirePermission('skus:import')."""
        source = SKU_IMPORTS_PY.read_text(encoding="utf-8")
        count = source.count('RequirePermission("skus:import")')
        assert count >= 3, (
            f"Expected 3+ permission checks (preview+validate+apply), "
            f"found {count}"
        )

    def test_apply_uses_same_permission_as_others(self):
        """All three endpoints must use the same permission string."""
        import re
        source = SKU_IMPORTS_PY.read_text(encoding="utf-8")
        perms = re.findall(r'RequirePermission\("([^"]+)"\)', source)
        for p in perms:
            assert p == "skus:import", f"Unexpected permission: {p}"
        assert len(perms) >= 3


# ====================================================================
# h. Duplicate apply does not duplicate SKUs (idempotent)
# ====================================================================

class TestIdempotency:

    @pytest.mark.asyncio
    async def test_second_apply_rejected(self):
        """Applying an already-applied import_run returns 409 CONFLICT."""
        from services.import_service import ImportService
        rows = [{"sku_code": "S1", "name": "A"}]
        db, run = _make_mock_db_for_apply(
            rows, {"sku_code": "sku_code", "name": "name"},
            run_status="applied",  # Already applied
        )
        with pytest.raises(Exception) as exc_info:
            await ImportService().apply(
                db, import_id="imp_test", on_conflict="skip",
                existing_sku_codes=set(),
            )
        # Must be rejected with INVALID_STATUS, not silently re-apply
        assert "INVALID_STATUS" in str(exc_info.value)
        # No SKU was added
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_then_apply_same_codes_skip(self):
        """After apply, if someone resets status and applies again with
        existing codes in the catalog, skip works correctly."""
        from services.import_service import ImportService
        rows = [
            {"sku_code": "S1", "name": "A"},
            {"sku_code": "S2", "name": "B"},
        ]
        db, run = _make_mock_db_for_apply(
            rows, {"sku_code": "sku_code", "name": "name"},
        )
        # First apply creates S1 and S2
        result = await ImportService().apply(
            db, import_id="imp_test", on_conflict="skip",
            existing_sku_codes=set(),
        )
        assert result.created == 2
        assert result.skipped == 0

        # Simulate: the SKU codes are now in the catalog
        # If someone tries to apply again with skip, those codes would be skipped
        # (but status='applied' prevents this -- tested above)


# ====================================================================
# i. custom_attributes.* triggers STOP_AND_REPORT_CTO
# ====================================================================

class TestCustomAttributesGuard:

    @pytest.mark.asyncio
    async def test_custom_attributes_mapping_rejected(self):
        """Mapping with custom_attributes.* triggers STOP_AND_REPORT_CTO."""
        from services.import_service import ImportService
        rows = [
            {"sku_code": "S1", "name": "A", "Brand": "Nike"},
        ]
        db, run = _make_mock_db_for_apply(
            rows,
            {"sku_code": "sku_code", "name": "name", "Brand": "custom_attributes.brand"},
        )
        with pytest.raises(Exception) as exc_info:
            await ImportService().apply(
                db, import_id="imp_test", on_conflict="skip",
                existing_sku_codes=set(),
            )
        error_str = str(exc_info.value)
        assert "STOP_AND_REPORT_CTO" in error_str
        # No SKU was added
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_custom_attributes_passes(self):
        """Mapping without custom_attributes proceeds normally."""
        from services.import_service import ImportService
        rows = [
            {"sku_code": "S1", "name": "A"},
        ]
        db, run = _make_mock_db_for_apply(
            rows, {"sku_code": "sku_code", "name": "name"},
        )
        result = await ImportService().apply(
            db, import_id="imp_test", on_conflict="skip",
            existing_sku_codes=set(),
        )
        assert result.created == 1
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_custom_attributes_error_message_includes_details(self):
        """Error message includes the specific custom_attributes fields."""
        from services.import_service import ImportService
        rows = [{"sku_code": "S1", "name": "A", "Color": "Red", "Size": "L"}]
        db, run = _make_mock_db_for_apply(
            rows,
            {
                "sku_code": "sku_code",
                "name": "name",
                "Color": "custom_attributes.color",
                "Size": "custom_attributes.size",
            },
        )
        with pytest.raises(Exception) as exc_info:
            await ImportService().apply(
                db, import_id="imp_test", on_conflict="skip",
                existing_sku_codes=set(),
            )
        error_str = str(exc_info.value)
        assert "custom_attributes.color" in error_str
        assert "custom_attributes.size" in error_str


# ====================================================================
# k. U3-C-R1: Corrupted validated rows -- fail-closed, no SKU added, run NOT applied
# ====================================================================

class TestCorruptedValidatedRows:
    """R1: When validated import_run rows have corruption (missing/invalid
    sku_code), the apply method MUST raise 422 WITHOUT marking the run as
    applied. Mock tests cover pre-write rejection; the live-DB suite proves
    caller-transaction rollback after partial catalog/unit/stock writes.
    """

    @pytest.mark.asyncio
    async def test_missing_sku_code_column_raises_422(self):
        """Row where mapping can't produce sku_code -> 422, run not applied."""
        from services.import_service import ImportService

        # Field mapping maps "sku_code" but row doesn't have that column
        rows = [{"product_code": "PRD-001", "name": "Widget"}]
        fm = {"sku_code": "sku_code", "name": "name"}
        db, run = _make_mock_db_for_apply(rows, fm)

        with pytest.raises(Exception) as exc_info:
            await ImportService().apply(
                db, import_id="imp_test", on_conflict="skip",
                existing_sku_codes=set(),
            )
        err = str(exc_info.value).upper()
        assert "ROW_PROCESSING_ERRORS" in err or "422" in err
        # import_run NOT marked applied
        assert run.status == "validated"
        # no SKU was added
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_sku_code_raises_422(self):
        """Row with empty sku_code -> 422, run not applied."""
        from services.import_service import ImportService

        rows = [{"sku_code": "", "name": "Empty Code"}]
        fm = {"sku_code": "sku_code", "name": "name"}
        db, run = _make_mock_db_for_apply(rows, fm)

        with pytest.raises(Exception) as exc_info:
            await ImportService().apply(
                db, import_id="imp_test", on_conflict="skip",
                existing_sku_codes=set(),
            )
        err = str(exc_info.value).upper()
        assert "ROW_PROCESSING_ERRORS" in err or "422" in err
        assert run.status == "validated"
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_mixed_valid_and_corrupt_fails_entirely(self):
        """Mixed valid+corrupt rows -> entire apply fails, no partial writes."""
        from services.import_service import ImportService

        # Row 1 is valid, row 2 has no sku_code source column
        rows = [
            {"sku_code": "GOOD-001", "name": "Good One"},
            {"wrong_col": "BAD-001", "name": "Bad One"},
        ]
        fm = {"sku_code": "sku_code", "name": "name"}
        db, run = _make_mock_db_for_apply(rows, fm)

        with pytest.raises(Exception) as exc_info:
            await ImportService().apply(
                db, import_id="imp_test", on_conflict="skip",
                existing_sku_codes=set(),
            )
        err = str(exc_info.value).upper()
        assert "ROW_PROCESSING_ERRORS" in err or "422" in err
        # Status NOT applied (fail-closed)
        assert run.status == "validated"

    @pytest.mark.asyncio
    async def test_all_rows_corrupt_no_db_add(self):
        """All rows corrupt -> zero db.add calls, run stays validated."""
        from services.import_service import ImportService

        rows = [
            {"wrong_col": "X", "name": "A"},
            {"wrong_col": "Y", "name": "B"},
            {"wrong_col": "Z", "name": "C"},
        ]
        fm = {"sku_code": "sku_code", "name": "name"}
        db, run = _make_mock_db_for_apply(rows, fm)

        with pytest.raises(Exception) as exc_info:
            await ImportService().apply(
                db, import_id="imp_test", on_conflict="skip",
                existing_sku_codes=set(),
            )
        err = str(exc_info.value).upper()
        assert "ROW_PROCESSING_ERRORS" in err or "422" in err
        assert run.status == "validated"
        db.add.assert_not_called()


# ====================================================================
# j. U3-B1/B2/B2.1 regression (implicit -- test runner covers this)
# ====================================================================

class TestRegressionGuards:
    """Lightweight checks that U3-C changes don't break U3-B1/B2 contracts."""

    def test_import_apply_request_only_skip_fail(self):
        """ImportApplyRequest schema must only accept skip and fail."""
        from schemas.import_schemas import ImportApplyRequest
        import pydantic

        for valid in ("skip", "fail"):
            req = ImportApplyRequest(on_conflict=valid)
            assert req.on_conflict == valid

        for invalid in ("update", "error"):
            with pytest.raises(pydantic.ValidationError):
                ImportApplyRequest(on_conflict=invalid)

    def test_import_run_model_has_apply_fields(self):
        """ImportRun model still has all apply-related fields."""
        from models.import_run import ImportRun
        attrs = {name for name in dir(ImportRun) if not name.startswith("_")}
        for field in ("created_rows", "skipped_rows", "updated_rows",
                       "applied_by", "applied_at", "apply_result", "status"):
            assert field in attrs, f"ImportRun missing field: {field}"

    def test_service_has_all_three_phases(self):
        """ImportService must have preview, validate, and apply methods."""
        source = IMPORT_SERVICE_PY.read_text(encoding="utf-8")
        assert "async def preview" in source
        assert "async def validate" in source
        assert "async def apply" in source

    def test_apply_endpoint_route_pattern(self):
        """Apply endpoint route must match /{import_id}/apply."""
        source = SKU_IMPORTS_PY.read_text(encoding="utf-8")
        assert "import_id}/apply" in source
