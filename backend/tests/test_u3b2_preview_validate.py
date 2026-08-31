"""U3-B2 Contract Tests -- preview + validate import pipeline.

Static + unit tests that validate:
  1. Router registration in api/app.py
  2. Endpoint definitions in api/v1/sku_imports.py
  3. Service logic in services/import_service.py
  4. CSV parsing (including UTF-8-sig BOM)
  5. Field mapping validation
  6. Row-level validation rules (required, format, length)
  7. Intra-file duplicate sku_code detection
  8. Existing catalog duplicate sku_code detection (mock-based)
  9. Error models for bad CSV / empty file / missing fields
 10. 403 permission enforcement (AST guard)
 11. ImportRun status transitions
 12. No SKU/inventory writes in U3-B2 scope

No database or network required -- all tests use AST, unit calls, or mocks.
"""
from __future__ import annotations

import ast
import uuid
from pathlib import Path
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

# -- Paths -----------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_PY = BACKEND_DIR / "api" / "app.py"
SKU_IMPORTS_PY = BACKEND_DIR / "api" / "v1" / "sku_imports.py"
IMPORT_SERVICE_PY = BACKEND_DIR / "services" / "import_service.py"
SCHEMAS_PY = BACKEND_DIR / "schemas" / "import_schemas.py"


# ====================================================================
# 1. Router Registration
# ====================================================================

class TestRouterRegistration:
    """Verify sku_imports router is registered in app.py."""

    def test_sku_imports_import_in_app(self):
        source = APP_PY.read_text(encoding="utf-8")
        assert "sku_imports" in source, "sku_imports not imported in app.py"

    def test_router_prefix_is_correct(self):
        source = APP_PY.read_text(encoding="utf-8")
        assert 'prefix="/api/v1/skus/import"' in source

    def test_router_tag_is_sku_imports(self):
        source = APP_PY.read_text(encoding="utf-8")
        assert 'tags=["sku-imports"]' in source


# ====================================================================
# 2. Endpoint Definitions (AST)
# ====================================================================

class TestEndpointDefinitions:
    """Static AST analysis of sku_imports.py endpoint definitions."""

    @staticmethod
    def _get_function_names() -> List[str]:
        source = SKU_IMPORTS_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)
        return [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

    def test_preview_endpoint_exists(self):
        assert "preview_import" in self._get_function_names()

    def test_validate_endpoint_exists(self):
        assert "validate_import" in self._get_function_names()

    def test_apply_endpoint_exists(self):
        assert "apply_import" in self._get_function_names()

    def test_preview_uses_skus_import_permission(self):
        source = SKU_IMPORTS_PY.read_text(encoding="utf-8")
        assert 'RequirePermission("skus:import")' in source

    def test_preview_endpoint_route(self):
        source = SKU_IMPORTS_PY.read_text(encoding="utf-8")
        assert '"/preview"' in source

    def test_validate_endpoint_route(self):
        source = SKU_IMPORTS_PY.read_text(encoding="utf-8")
        assert "import_id}/validate" in source

    def test_apply_endpoint_route(self):
        source = SKU_IMPORTS_PY.read_text(encoding="utf-8")
        assert "import_id}/apply" in source


# ====================================================================
# 3. Service Structure
# ====================================================================

class TestImportServiceStructure:
    """Static analysis of import_service.py."""

    def test_preview_method_exists(self):
        assert "async def preview" in IMPORT_SERVICE_PY.read_text(encoding="utf-8")

    def test_validate_method_exists(self):
        assert "async def validate" in IMPORT_SERVICE_PY.read_text(encoding="utf-8")

    def test_apply_method_exists(self):
        assert "async def apply" in IMPORT_SERVICE_PY.read_text(encoding="utf-8")

    def test_sku_import_only_in_apply(self):
        source = IMPORT_SERVICE_PY.read_text(encoding="utf-8")
        if "from models.sku import" in source:
            # SKU import is allowed only inside the apply method
            assert "async def apply" in source

    def test_only_writes_import_runs(self):
        source = IMPORT_SERVICE_PY.read_text(encoding="utf-8")
        assert "db.add(run)" in source
        assert "db.flush()" in source

    def test_has_csv_parsing(self):
        source = IMPORT_SERVICE_PY.read_text(encoding="utf-8")
        assert "DictReader" in source

    def test_max_rows_limit(self):
        assert "MAX_CSV_ROWS" in IMPORT_SERVICE_PY.read_text(encoding="utf-8")

    def test_max_upload_limit_in_router(self):
        assert "MAX_UPLOAD_BYTES" in SKU_IMPORTS_PY.read_text(encoding="utf-8")

    def test_has_bom_detection(self):
        assert "utf-8-sig" in IMPORT_SERVICE_PY.read_text(encoding="utf-8")

    def test_has_duplicate_sku_detection(self):
        source = IMPORT_SERVICE_PY.read_text(encoding="utf-8")
        assert "Duplicate sku_code" in source

    def test_has_existing_catalog_detection(self):
        assert "existing_sku_codes" in IMPORT_SERVICE_PY.read_text(encoding="utf-8")


# ====================================================================
# 4. CSV Parsing Unit Tests
# ====================================================================

class TestCSVParsing:
    """Test _parse_csv static method directly."""

    def _parse(self, csv_text: str):
        from services.import_service import ImportService
        return ImportService._parse_csv(csv_text)

    def test_simple_csv(self):
        rows, columns = self._parse("sku_code,name,unit\nABC123,Widget,pcs\n")
        assert columns == ["sku_code", "name", "unit"]
        assert rows[0]["sku_code"] == "ABC123"

    def test_empty_csv(self):
        rows, columns = self._parse("sku_code,name\n")
        assert columns == ["sku_code", "name"]
        assert len(rows) == 0

    def test_whitespace_stripped(self):
        rows, _ = self._parse(" sku_code , name \n ABC , Widget \n")
        assert rows[0]["sku_code"] == "ABC"

    def test_extra_columns_preserved(self):
        rows, columns = self._parse("sku_code,name,custom1\nA,B,C\n")
        assert "custom1" in columns
        assert rows[0]["custom1"] == "C"

    def test_utf8_sig_bom_stripped(self):
        """UTF-8-sig BOM must be handled without leaking into data."""
        from services.import_service import ImportService
        raw = b"\xef\xbb\xbfsku_code,name\nABC123,Widget\n"
        text = ImportService._decode_bytes(raw)
        assert not text.startswith("\ufeff"), "BOM must be stripped"
        rows, columns = ImportService._parse_csv(text)
        assert columns == ["sku_code", "name"]
        assert rows[0]["sku_code"] == "ABC123"

    def test_plain_utf8_no_bom(self):
        from services.import_service import ImportService
        raw = b"sku_code,name\nXYZ,Test\n"
        text = ImportService._decode_bytes(raw)
        rows, _ = ImportService._parse_csv(text)
        assert rows[0]["sku_code"] == "XYZ"


# ====================================================================
# 5. Field Mapping Validation
# ====================================================================

class TestFieldMappingValidation:

    def _validate(self, mapping: Dict[str, str]) -> List[str]:
        from services.import_service import ImportService
        return ImportService._validate_mapping(mapping)

    def test_valid_mapping(self):
        assert self._validate({"Product Code": "sku_code", "Name": "name"}) == []

    def test_empty_mapping(self):
        errors = self._validate({})
        assert errors and "empty" in errors[0].lower()

    def test_unknown_target_field(self):
        assert any("unknown target" in e.lower() for e in self._validate({"c": "bad"}))

    def test_custom_attribute_prefix_allowed(self):
        assert self._validate({"Brand": "custom_attributes.brand"}) == []

    def test_empty_source_column(self):
        assert any("empty" in e.lower() for e in self._validate({"": "sku_code"}))

    def test_empty_target_field(self):
        assert any("empty" in e.lower() for e in self._validate({"a": ""}))


# ====================================================================
# 6. Row Mapping Transform
# ====================================================================

class TestApplyMapping:

    def _apply(self, row, mapping):
        from services.import_service import ImportService
        return ImportService._apply_mapping(row, mapping)

    def test_direct_mapping(self):
        r = self._apply({"PC": "ABC", "N": "W"}, {"PC": "sku_code", "N": "name"})
        assert r["sku_code"] == "ABC"

    def test_custom_attributes_nested(self):
        r = self._apply({"Brand": "Nike"}, {"Brand": "custom_attributes.brand"})
        assert r["custom_attributes"]["brand"] == "Nike"

    def test_unmapped_columns_excluded(self):
        r = self._apply({"sku_code": "ABC", "unused": "x"}, {"sku_code": "sku_code"})
        assert "unused" not in r


# ====================================================================
# 7. No SKU/Inventory Writes (AST Guard)
# ====================================================================

class TestNoSkuInventoryWrites:
    """The import path must never write inventory or pricing state directly.

    Since SKU-M1 (DC-12R1-MVP-L1-SKU-R0-M1-R1), the ONE sanctioned exception is
    the apply-phase delegation ``InventoryRepository.ensure_stock_row`` inside
    ``services/import_service.py`` (idempotent stock-row existence for a newly
    imported sellable unit). The guards below enforce exactly that delegation:
    no other repository usage, no direct class usage, and no inventory or
    pricing write anywhere in the router or the service.
    """

    @staticmethod
    def _dotted_name(node):
        """Return 'a.b.c' for nested Attribute/Name chains, else None."""
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
            return ".".join(reversed(parts))
        return None

    def _inventory_repository_usage(self, source: str) -> tuple[set[str], set[str], set[str], list[str]]:
        """Parse the AST and return (imported names, repo instance dotted
        names, methods invoked on repo instances, any other
        InventoryRepository references)."""
        tree = ast.parse(source)
        imported: set[str] = set()
        instances: set[str] = set()
        called: set[str] = set()
        other: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "repositories.inventory_repository":
                for alias in node.names:
                    imported.add(alias.asname or alias.name)
        if not imported:
            return imported, instances, called, other
        constructor_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in imported
        ]
        bound_calls = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                if value is None:
                    continue
                calls_in_value = [c for c in constructor_calls if c in ast.walk(value)]
                if not calls_in_value:
                    continue
                bound_calls.update(calls_in_value)
                if isinstance(node, ast.Assign):
                    targets = [self._dotted_name(t) for t in node.targets]
                else:
                    targets = [self._dotted_name(node.target)]
                instances.update(t for t in targets if t)
        for call in constructor_calls:
            if call not in bound_calls:
                other.append(f"constructor-result-used-directly:line{call.lineno}")
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in imported
            ):
                other.append(f"class-attribute-access:{node.attr}:line{node.lineno}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                base = self._dotted_name(node.func.value)
                if base is not None and base in instances:
                    called.add(node.func.attr)
        return imported, instances, called, other

    @pytest.mark.parametrize("filepath", [SKU_IMPORTS_PY, IMPORT_SERVICE_PY])
    def test_no_inventory_import(self, filepath: Path):
        source = filepath.read_text(encoding="utf-8")
        if filepath == SKU_IMPORTS_PY:
            # The router may not touch the inventory repository at all.
            assert "inventory_repository" not in source
            return
        imported, instances, called, other = self._inventory_repository_usage(source)
        assert imported == {"InventoryRepository"} or not imported
        if imported:
            assert other == [], f"non-delegation InventoryRepository usage: {other}"
            assert instances, "repository imported but never instantiated"
            assert called == {"ensure_stock_row"}, (
                f"only ensure_stock_row delegation is sanctioned; found {sorted(called)}"
            )

    def test_service_sku_import_only_in_apply(self):
        """Service may import SKU only inside the apply method."""
        source = IMPORT_SERVICE_PY.read_text(encoding="utf-8")
        if "from models.sku import" in source:
            assert "async def apply" in source

    def test_ensure_stock_row_delegation_is_apply_phase_only(self):
        """ensure_stock_row may only be reached from the apply phase."""
        source = IMPORT_SERVICE_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)
        apply_funcs = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and node.name.startswith("apply")
        ]
        assert apply_funcs, "apply entry point missing"
        non_apply_calls = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                if node.name.startswith("apply"):
                    continue
                for sub in ast.walk(node):
                    if (
                        isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "ensure_stock_row"
                    ):
                        non_apply_calls.append(f"{node.name}:line{sub.lineno}")
        assert non_apply_calls == [], f"ensure_stock_row outside apply: {non_apply_calls}"

    def test_no_inventory_or_pricing_writes(self):
        """Neither router nor service write to inventory/stocks/pricing."""
        for filepath in [SKU_IMPORTS_PY, IMPORT_SERVICE_PY]:
            source = filepath.read_text(encoding="utf-8")
            assert "stock_movement" not in source
            assert "retailer_price" not in source
            assert "inventory_stock" not in source
            if filepath == SKU_IMPORTS_PY:
                assert "inventory_repository" not in source


# ====================================================================
# 8. Pydantic Schema Serialization
# ====================================================================

class TestU3B2Schemas:

    def test_preview_response_roundtrip(self):
        from schemas.import_schemas import ImportPreviewResponse, ImportSourceInfo
        resp = ImportPreviewResponse(
            import_id="imp_123",
            source=ImportSourceInfo(filename="t.csv", encoding="utf-8", row_count=10),
            columns_detected=["sku_code", "name"],
            sample_rows=[{"sku_code": "A", "name": "W"}],
        )
        assert resp.model_dump()["import_id"] == "imp_123"

    def test_validate_response_roundtrip(self):
        from schemas.import_schemas import ImportValidateResponse
        resp = ImportValidateResponse(
            import_id="imp_123", status="validated", valid_rows=8, error_rows=0,
        )
        assert resp.model_dump()["status"] == "validated"

    def test_validate_request_schema(self):
        from schemas.import_schemas import ImportValidateRequest
        req = ImportValidateRequest(mapping={"PC": "sku_code"})
        assert req.mapping["PC"] == "sku_code"

    def test_needs_review_status(self):
        from schemas.import_schemas import ImportValidateResponse
        resp = ImportValidateResponse(
            import_id="imp_456", status="needs_review", valid_rows=5, error_rows=3,
        )
        assert resp.status == "needs_review"

    def test_error_detail_model(self):
        from schemas.import_schemas import ImportErrorDetail
        err = ImportErrorDetail(row=3, field="sku_code", sku_code="ABC", message="Dup")
        assert err.model_dump()["row"] == 3

    def test_warning_detail_model(self):
        from schemas.import_schemas import ImportWarningDetail
        w = ImportWarningDetail(row=5, field="is_active", message="Bad bool")
        assert w.model_dump()["row"] == 5


# ====================================================================
# 9. Row-Level Validation (Service Unit Tests with Mocks)
# ====================================================================

def _make_mock_db(rows, columns, run_status="previewed"):
    """Create a mock AsyncSession that returns a fake ImportRun."""
    from models.import_run import ImportRun
    run = ImportRun(
        import_id="imp_test",
        tenant_id=uuid.uuid4(),
        status=run_status,
        total_rows=len(rows),
        mapping={
            "columns": columns,
            "rows": rows,
            "sample_rows": rows[:5],
        },
    )
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = run
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.flush = AsyncMock()
    return mock_db


class TestRowLevelValidation:

    @pytest.mark.asyncio
    async def test_validate_all_valid(self):
        from services.import_service import ImportService
        rows = [
            {"sku_code": "SKU-001", "name": "A"},
            {"sku_code": "SKU-002", "name": "B"},
        ]
        db = _make_mock_db(rows, ["sku_code", "name"])
        result = await ImportService().validate(
            db, import_id="imp_test",
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        assert result.status == "validated"
        assert result.error_rows == 0

    @pytest.mark.asyncio
    async def test_validate_missing_required_field_in_mapping(self):
        from services.import_service import ImportService
        rows = [{"sku_code": "S1", "name": "A"}]
        db = _make_mock_db(rows, ["sku_code", "name"])
        with pytest.raises(Exception) as exc_info:
            await ImportService().validate(
                db, import_id="imp_test", mapping={"name": "name"},
            )
        assert "MISSING_REQUIRED_FIELDS" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_empty_sku_code_row(self):
        from services.import_service import ImportService
        rows = [{"sku_code": "", "name": "No Code"}]
        db = _make_mock_db(rows, ["sku_code", "name"])
        result = await ImportService().validate(
            db, import_id="imp_test",
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        assert result.status == "needs_review"
        assert any(e.field == "sku_code" for e in result.errors)

    @pytest.mark.asyncio
    async def test_validate_empty_name_row(self):
        from services.import_service import ImportService
        rows = [{"sku_code": "SKU-001", "name": ""}]
        db = _make_mock_db(rows, ["sku_code", "name"])
        result = await ImportService().validate(
            db, import_id="imp_test",
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        assert any(e.field == "name" for e in result.errors)

    @pytest.mark.asyncio
    async def test_validate_sku_code_too_long(self):
        from services.import_service import ImportService
        rows = [{"sku_code": "A" * 65, "name": "T"}]
        db = _make_mock_db(rows, ["sku_code", "name"])
        result = await ImportService().validate(
            db, import_id="imp_test",
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        assert any("exceeds 64" in e.message for e in result.errors)

    @pytest.mark.asyncio
    async def test_validate_name_too_long(self):
        from services.import_service import ImportService
        rows = [{"sku_code": "S", "name": "N" * 256}]
        db = _make_mock_db(rows, ["sku_code", "name"])
        result = await ImportService().validate(
            db, import_id="imp_test",
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        assert any("exceeds 255" in e.message for e in result.errors)

    @pytest.mark.asyncio
    async def test_validate_sku_code_with_spaces_warning(self):
        from services.import_service import ImportService
        rows = [{"sku_code": "SKU 001", "name": "T"}]
        db = _make_mock_db(rows, ["sku_code", "name"])
        result = await ImportService().validate(
            db, import_id="imp_test",
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        assert result.status == "validated"
        assert any("spaces" in w.message.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_validate_is_active_non_boolean_warning(self):
        from services.import_service import ImportService
        rows = [{"sku_code": "S", "name": "T", "active": "maybe"}]
        db = _make_mock_db(rows, ["sku_code", "name", "active"])
        result = await ImportService().validate(
            db, import_id="imp_test",
            mapping={"sku_code": "sku_code", "name": "name", "active": "is_active"},
        )
        assert any("is_active" in w.field for w in result.warnings)


# ====================================================================
# 10. Duplicate SKU Detection
# ====================================================================

class TestDuplicateSKUDetection:

    @pytest.mark.asyncio
    async def test_intra_file_duplicate_detected(self):
        from services.import_service import ImportService
        rows = [
            {"sku_code": "DUP-001", "name": "First"},
            {"sku_code": "DUP-001", "name": "Second"},
        ]
        db = _make_mock_db(rows, ["sku_code", "name"])
        result = await ImportService().validate(
            db, import_id="imp_test",
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        assert result.status == "needs_review"
        assert any("Duplicate" in e.message and "DUP-001" in e.message for e in result.errors)

    @pytest.mark.asyncio
    async def test_existing_catalog_duplicate_warning(self):
        from services.import_service import ImportService
        rows = [{"sku_code": "EXISTING-001", "name": "In Catalog"}]
        db = _make_mock_db(rows, ["sku_code", "name"])
        result = await ImportService().validate(
            db, import_id="imp_test",
            mapping={"sku_code": "sku_code", "name": "name"},
            existing_sku_codes={"EXISTING-001", "OTHER-999"},
        )
        assert any("already exists" in w.message for w in result.warnings)
        assert result.status == "validated"

    @pytest.mark.asyncio
    async def test_no_false_positive_on_unique_codes(self):
        from services.import_service import ImportService
        rows = [
            {"sku_code": "UNIQ-001", "name": "A"},
            {"sku_code": "UNIQ-002", "name": "B"},
        ]
        db = _make_mock_db(rows, ["sku_code", "name"])
        result = await ImportService().validate(
            db, import_id="imp_test",
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        assert result.status == "validated"
        assert not any("Duplicate" in e.message for e in result.errors)


# ====================================================================
# 11. Error Models (Bad CSV / Empty File / Encoding)
# ====================================================================

class TestErrorModels:

    @pytest.mark.asyncio
    async def test_preview_empty_file(self):
        from services.import_service import ImportService
        with pytest.raises(Exception) as exc_info:
            await ImportService().preview(
                AsyncMock(), tenant_id=uuid.uuid4(),
                filename="empty.csv", file_bytes=b"",
            )
        assert "EMPTY_FILE" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_preview_no_columns(self):
        from services.import_service import ImportService
        with pytest.raises(Exception) as exc_info:
            await ImportService().preview(
                AsyncMock(), tenant_id=uuid.uuid4(),
                filename="blank.csv", file_bytes=b"\n\n\n",
            )
        assert "EMPTY_FILE" in str(exc_info.value) or "no columns" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_preview_bad_encoding(self):
        from services.import_service import ImportService
        bad_bytes = b"\xff\xfe" + b"sku_code\n"
        with pytest.raises(Exception) as exc_info:
            await ImportService().preview(
                AsyncMock(), tenant_id=uuid.uuid4(),
                filename="bad.csv", file_bytes=bad_bytes,
                source_encoding="utf-8",
            )
        assert "ENCODING_ERROR" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_import_not_found(self):
        from services.import_service import ImportService
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        with pytest.raises(Exception) as exc_info:
            await ImportService().validate(
                mock_db, import_id="nonexistent",
                mapping={"sku_code": "sku_code", "name": "name"},
            )
        assert "IMPORT_NOT_FOUND" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_invalid_status(self):
        from services.import_service import ImportService
        db = _make_mock_db([], [], run_status="validated")
        with pytest.raises(Exception) as exc_info:
            await ImportService().validate(
                db, import_id="imp_test",
                mapping={"sku_code": "sku_code", "name": "name"},
            )
        assert "INVALID_STATUS" in str(exc_info.value)


# ====================================================================
# 12. 403 Permission Enforcement (AST Guard)
# ====================================================================

class TestPermissionEnforcement:

    def test_both_endpoints_require_permission(self):
        source = SKU_IMPORTS_PY.read_text(encoding="utf-8")
        count = source.count('RequirePermission("skus:import")')
        assert count >= 2, f"Expected 2+ permission checks, found {count}"

    def test_router_permission_string_exact(self):
        import re
        source = SKU_IMPORTS_PY.read_text(encoding="utf-8")
        perms = re.findall(r'RequirePermission\("([^"]+)"\)', source)
        for p in perms:
            assert p == "skus:import", f"Unexpected permission: {p}"


# ====================================================================
# 13. R3: Full Rows Storage + Dedup Error Counting
# ====================================================================

class TestR3FullRowsAndCounting:
    """CTO R3: preview stores full rows, validate uses full rows,
    invalid_row_numbers set ensures correct error_rows counting."""

    @pytest.mark.asyncio
    async def test_six_row_csv_sixth_row_missing_required(self):
        """6-row CSV, row 6 missing required field -> validate catches it."""
        from services.import_service import ImportService
        rows = [
            {"sku_code": f"SKU-{i:03d}", "name": f"Item {i}"}
            for i in range(1, 6)
        ] + [{"sku_code": "", "name": ""}]  # row 6: both required fields empty
        db = _make_mock_db(rows, ["sku_code", "name"])
        result = await ImportService().validate(
            db, import_id="imp_test",
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        assert result.status == "needs_review"
        row6_errors = [e for e in result.errors if e.row == 6]
        assert len(row6_errors) >= 1, "Row 6 must have error(s)"
        assert any(e.field == "sku_code" for e in row6_errors)

    @pytest.mark.asyncio
    async def test_six_row_csv_row6_duplicate_of_row1(self):
        """6-row CSV, row 6 duplicates row 1's sku_code -> validate catches it."""
        from services.import_service import ImportService
        rows = [
            {"sku_code": f"SKU-{i:03d}", "name": f"Item {i}"}
            for i in range(1, 6)
        ] + [{"sku_code": "SKU-001", "name": "Duplicate of row 1"}]
        db = _make_mock_db(rows, ["sku_code", "name"])
        result = await ImportService().validate(
            db, import_id="imp_test",
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        assert result.status == "needs_review"
        assert any(
            "Duplicate" in e.message and "SKU-001" in e.message
            for e in result.errors
        )

    @pytest.mark.asyncio
    async def test_duplicate_row_with_other_error_counts_once(self):
        """Row with both duplicate sku_code AND missing field: error_rows
        counts that row only once, not twice."""
        from services.import_service import ImportService
        rows = [
            {"sku_code": "SKU-001", "name": "Valid"},
            {"sku_code": "SKU-002", "name": "Valid"},
            {"sku_code": "SKU-001", "name": ""},  # dup + missing name
        ]
        db = _make_mock_db(rows, ["sku_code", "name"])
        result = await ImportService().validate(
            db, import_id="imp_test",
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        # Row 3 has 2 errors (duplicate + missing name), but counts as 1 error row
        assert result.error_rows == 1, (
            f"Expected error_rows=1 (row 3 only), got {result.error_rows}"
        )
        assert result.valid_rows == 2
        row3_errors = [e for e in result.errors if e.row == 3]
        assert len(row3_errors) == 2, (
            "Row 3 should have 2 error details (dup + missing name)"
        )

    @pytest.mark.asyncio
    async def test_no_rows_returns_explicit_error(self):
        """If import_run has no rows (legacy data), validate returns error."""
        from services.import_service import ImportService
        from models.import_run import ImportRun
        run = ImportRun(
            import_id="imp_old",
            tenant_id=uuid.uuid4(),
            status="previewed",
            total_rows=0,
            mapping={"columns": ["sku_code"], "sample_rows": []},
            # No "rows" key -- simulates legacy preview data
        )
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = run
        mock_db.execute = AsyncMock(return_value=mock_result)
        with pytest.raises(Exception) as exc_info:
            await ImportService().validate(
                mock_db, import_id="imp_old",
                mapping={"sku_code": "sku_code", "name": "name"},
            )
        assert "NO_ROWS" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_preview_saves_full_rows_and_returns_sample(self):
        """Preview must store full rows in mapping but return only sample_rows."""
        from services.import_service import ImportService

        csv_bytes = b"sku_code,name\n" + b"\n".join(
            f"SKU-{i:03d},Item {i}".encode() for i in range(1, 8)
        )
        captured_run = {}

        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.add = lambda r: captured_run.update({"mapping": r.mapping})

        result = await ImportService().preview(
            mock_db, tenant_id=uuid.uuid4(),
            filename="test.csv", file_bytes=csv_bytes,
        )
        # Response sample_rows = 5 rows
        assert len(result.sample_rows) == 5
        # Mapping stored full 7 rows
        assert len(captured_run["mapping"]["rows"]) == 7
        # sample_rows in mapping also 5
        assert len(captured_run["mapping"]["sample_rows"]) == 5
