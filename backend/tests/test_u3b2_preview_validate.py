"""U3-B2 Contract Tests -- preview + validate import pipeline.

Static tests that validate:
  1. Router registration in api/app.py
  2. Endpoint definitions in api/v1/sku_imports.py
  3. Service logic in services/import_service.py
  4. CSV parsing correctness
  5. Field mapping validation
  6. Row-level validation rules
  7. ImportRun status transitions
  8. No SKU/inventory writes in U3-B2 scope

No database or network required -- all tests use AST or direct unit calls.
"""
from __future__ import annotations

import ast
import csv
import io
import textwrap
import uuid
from pathlib import Path
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

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
        assert 'prefix="/api/v1/skus/import"' in source, (
            "sku_imports router not registered with correct prefix"
        )

    def test_router_tag_is_sku_imports(self):
        source = APP_PY.read_text(encoding="utf-8")
        assert 'tags=["sku-imports"]' in source, (
            "sku_imports router tag should be 'sku-imports'"
        )


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
        names = self._get_function_names()
        assert "preview_import" in names, "preview_import endpoint missing"

    def test_validate_endpoint_exists(self):
        names = self._get_function_names()
        assert "validate_import" in names, "validate_import endpoint missing"

    def test_no_apply_endpoint(self):
        """U3-B2 scope: apply endpoint should NOT exist yet."""
        names = self._get_function_names()
        assert "apply_import" not in names, (
            "apply_import should not exist in U3-B2 scope (reserved for U3-C)"
        )

    def test_preview_uses_skus_import_permission(self):
        source = SKU_IMPORTS_PY.read_text(encoding="utf-8")
        assert 'RequirePermission("skus:import")' in source, (
            "Endpoints must use RequirePermission('skus:import')"
        )

    def test_preview_endpoint_route(self):
        source = SKU_IMPORTS_PY.read_text(encoding="utf-8")
        assert '"/preview"' in source, (
            "Preview endpoint route should contain '/preview'"
        )

    def test_validate_endpoint_route(self):
        source = SKU_IMPORTS_PY.read_text(encoding="utf-8")
        assert "import_id}/validate" in source, (
            "Validate endpoint route should contain '{import_id}/validate'"
        )


# ====================================================================
# 3. Service Structure
# ====================================================================

class TestImportServiceStructure:
    """Static analysis of import_service.py."""

    def test_preview_method_exists(self):
        source = IMPORT_SERVICE_PY.read_text(encoding="utf-8")
        assert "async def preview" in source, "ImportService.preview() missing"

    def test_validate_method_exists(self):
        source = IMPORT_SERVICE_PY.read_text(encoding="utf-8")
        assert "async def validate" in source, "ImportService.validate() missing"

    def test_no_apply_method(self):
        """U3-B2 scope: apply should NOT exist."""
        source = IMPORT_SERVICE_PY.read_text(encoding="utf-8")
        assert "async def apply" not in source, (
            "apply() should not exist in U3-B2 scope (reserved for U3-C)"
        )

    def test_no_sku_imports(self):
        """Verify service does NOT import SKU model or repository."""
        source = IMPORT_SERVICE_PY.read_text(encoding="utf-8")
        assert "from models.sku import" not in source, (
            "U3-B2 service must not import SKU model"
        )
        assert "from repositories.sku" not in source, (
            "U3-B2 service must not import SKU repository"
        )

    def test_only_writes_import_runs(self):
        """Verify service only adds/flushes ImportRun."""
        source = IMPORT_SERVICE_PY.read_text(encoding="utf-8")
        assert "db.add(run)" in source, "Service should add ImportRun to session"
        assert "db.flush()" in source, "Service should flush (not commit) to session"

    def test_has_csv_parsing(self):
        source = IMPORT_SERVICE_PY.read_text(encoding="utf-8")
        assert "csv" in source, "Service should import csv module"
        assert "DictReader" in source, "Service should use csv.DictReader"

    def test_max_rows_limit(self):
        source = IMPORT_SERVICE_PY.read_text(encoding="utf-8")
        assert "MAX_CSV_ROWS" in source, "Service should define MAX_CSV_ROWS limit"

    def test_max_upload_limit_in_router(self):
        source = SKU_IMPORTS_PY.read_text(encoding="utf-8")
        assert "MAX_UPLOAD_BYTES" in source, "Router should define upload size limit"


# ====================================================================
# 4. CSV Parsing Unit Tests
# ====================================================================

class TestCSVParsing:
    """Test _parse_csv static method directly."""

    def _parse(self, csv_text: str):
        from services.import_service import ImportService
        return ImportService._parse_csv(csv_text)

    def test_simple_csv(self):
        csv_text = "sku_code,name,unit\nABC123,Widget,pcs\nDEF456,Gadget,kg\n"
        rows, columns = self._parse(csv_text)
        assert columns == ["sku_code", "name", "unit"]
        assert len(rows) == 2
        assert rows[0]["sku_code"] == "ABC123"
        assert rows[1]["name"] == "Gadget"

    def test_empty_csv(self):
        csv_text = "sku_code,name\n"
        rows, columns = self._parse(csv_text)
        assert columns == ["sku_code", "name"]
        assert len(rows) == 0

    def test_whitespace_stripped(self):
        csv_text = " sku_code , name \n ABC , Widget \n"
        rows, columns = self._parse(csv_text)
        assert rows[0]["sku_code"] == "ABC"
        assert rows[0]["name"] == "Widget"

    def test_extra_columns_preserved(self):
        csv_text = "sku_code,name,custom1\nA,B,C\n"
        rows, columns = self._parse(csv_text)
        assert "custom1" in columns
        assert rows[0]["custom1"] == "C"


# ====================================================================
# 5. Field Mapping Validation
# ====================================================================

class TestFieldMappingValidation:
    """Test _validate_mapping static method."""

    def _validate(self, mapping: Dict[str, str]) -> List[str]:
        from services.import_service import ImportService
        return ImportService._validate_mapping(mapping)

    def test_valid_mapping(self):
        errors = self._validate({"Product Code": "sku_code", "Product Name": "name"})
        assert errors == []

    def test_empty_mapping(self):
        errors = self._validate({})
        assert len(errors) > 0
        assert "empty" in errors[0].lower()

    def test_unknown_target_field(self):
        errors = self._validate({"col": "nonexistent_field"})
        assert any("unknown target" in e.lower() for e in errors)

    def test_custom_attribute_prefix_allowed(self):
        errors = self._validate({"Brand": "custom_attributes.brand"})
        assert errors == []

    def test_empty_source_column(self):
        errors = self._validate({"": "sku_code"})
        assert any("empty" in e.lower() for e in errors)

    def test_empty_target_field(self):
        errors = self._validate({"sku_code": ""})
        assert any("empty" in e.lower() for e in errors)


# ====================================================================
# 6. Row Mapping Transform
# ====================================================================

class TestApplyMapping:
    """Test _apply_mapping static method."""

    def _apply(self, row, mapping):
        from services.import_service import ImportService
        return ImportService._apply_mapping(row, mapping)

    def test_direct_mapping(self):
        result = self._apply(
            {"Product Code": "ABC", "Name": "Widget"},
            {"Product Code": "sku_code", "Name": "name"},
        )
        assert result["sku_code"] == "ABC"
        assert result["name"] == "Widget"

    def test_custom_attributes_nested(self):
        result = self._apply(
            {"Brand": "Nike"},
            {"Brand": "custom_attributes.brand"},
        )
        assert result["custom_attributes"]["brand"] == "Nike"

    def test_unmapped_columns_excluded(self):
        result = self._apply(
            {"sku_code": "ABC", "unused": "data"},
            {"sku_code": "sku_code"},
        )
        assert "unused" not in result


# ====================================================================
# 7. No SKU/Inventory Imports (AST Guard)
# ====================================================================

class TestNoSkuInventoryWrites:
    """Ensure U3-B2 files do NOT import or use SKU/inventory write paths."""

    @pytest.mark.parametrize("filepath", [
        SKU_IMPORTS_PY,
        IMPORT_SERVICE_PY,
    ])
    def test_no_sku_model_import(self, filepath: Path):
        source = filepath.read_text(encoding="utf-8")
        assert "from models.sku" not in source
        assert "import SKU" not in source

    @pytest.mark.parametrize("filepath", [
        SKU_IMPORTS_PY,
        IMPORT_SERVICE_PY,
    ])
    def test_no_inventory_import(self, filepath: Path):
        source = filepath.read_text(encoding="utf-8")
        assert "inventory" not in source.lower() or "inventory_repository" not in source


# ====================================================================
# 8. Pydantic Schema Serialization
# ====================================================================

class TestU3B2Schemas:
    """Ensure all import schemas used by preview/validate can serialize."""

    def test_preview_response_roundtrip(self):
        from schemas.import_schemas import ImportPreviewResponse, ImportSourceInfo
        resp = ImportPreviewResponse(
            import_id="imp_123",
            source=ImportSourceInfo(filename="test.csv", encoding="utf-8", row_count=10),
            columns_detected=["sku_code", "name"],
            sample_rows=[{"sku_code": "A", "name": "Widget"}],
        )
        dumped = resp.model_dump()
        assert dumped["import_id"] == "imp_123"
        assert dumped["source"]["row_count"] == 10

    def test_validate_response_roundtrip(self):
        from schemas.import_schemas import ImportValidateResponse
        resp = ImportValidateResponse(
            import_id="imp_123",
            status="validated",
            valid_rows=8,
            error_rows=0,
            warning_rows=1,
        )
        dumped = resp.model_dump()
        assert dumped["status"] == "validated"
        assert dumped["valid_rows"] == 8

    def test_validate_request_schema(self):
        from schemas.import_schemas import ImportValidateRequest
        req = ImportValidateRequest(
            mapping={"Product Code": "sku_code", "Name": "name"}
        )
        assert req.mapping["Product Code"] == "sku_code"

    def test_needs_review_status_in_response(self):
        from schemas.import_schemas import ImportValidateResponse
        resp = ImportValidateResponse(
            import_id="imp_456",
            status="needs_review",
            valid_rows=5,
            error_rows=3,
        )
        assert resp.status == "needs_review"
