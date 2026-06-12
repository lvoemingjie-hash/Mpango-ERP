"""U3-B1 Contract Foundation Tests.

Validates:
1. skus:import permission exists in ALL seed scripts (static check)
2. 022_import_runs migration structure (AST/static analysis)
3. ImportRun ORM model maps to all columns
4. Pydantic contract schemas serialize/deserialize correctly
5. No import API endpoints in backend/api/v1/skus.py (static source check)
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_migration_source() -> str:
    """Read the 022_import_runs.py migration file as source text."""
    backend_dir = Path(__file__).resolve().parent.parent
    migration_file = backend_dir / "alembic" / "versions" / "022_import_runs.py"
    assert migration_file.exists(), f"Migration file not found: {migration_file}"
    return migration_file.read_text(encoding="utf-8")


def _parse_migration() -> ast.Module:
    """Parse 022_import_runs.py into an AST."""
    return ast.parse(_read_migration_source())


def _get_function_body_lines(module: ast.Module, name: str) -> set[str]:
    """Extract the source lines of a top-level function as a set."""
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            lines: set[str] = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Constant) and isinstance(child.value, str):
                    lines.add(child.value)
                if isinstance(child, ast.Name):
                    lines.add(child.id)
            return lines
    return set()


# ---------------------------------------------------------------------------
# Test 1: Permission exists in ALL seed scripts (static check)
# ---------------------------------------------------------------------------

class TestSkusImportPermission:
    """Verify skus:import is present in all four seed scripts."""

    def test_create_wholesaler_has_skus_import(self):
        """create_wholesaler.py create_permissions() must include skus:import."""
        import scripts.create_wholesaler as cw

        source = inspect.getsource(cw.create_permissions)
        assert "skus:import" in source, (
            "create_wholesaler.py create_permissions() missing 'skus:import'"
        )

    def test_seed_demo_data_has_skus_import(self):
        """seed_demo_data.py PERMISSION_CODES must include skus:import."""
        from scripts.seed_demo_data import PERMISSION_CODES

        codes = {code for code, _desc in PERMISSION_CODES}
        assert "skus:import" in codes, (
            f"PERMISSION_CODES missing 'skus:import'. Found: {sorted(codes)}"
        )

    def test_onboard_tenant_has_skus_import(self):
        """onboard_tenant.py setup_admin() must include skus:import."""
        import scripts.onboard_tenant as ot

        source = inspect.getsource(ot.setup_admin)
        assert "skus:import" in source, (
            "onboard_tenant.py setup_admin() missing 'skus:import'"
        )

    def test_seed_test_tenant_has_skus_import(self):
        """seed_test_tenant.py permission_codes must include skus:import."""
        # seed_test_tenant.py builds permission_codes inside seed() so we
        # check the source file directly (avoiding DB imports).
        backend_dir = Path(__file__).resolve().parent.parent
        source = (backend_dir / "scripts" / "seed_test_tenant.py").read_text(encoding="utf-8")
        assert "skus:import" in source, (
            "seed_test_tenant.py missing 'skus:import' in permission_codes"
        )


# ---------------------------------------------------------------------------
# Test 2: 022_import_runs migration static analysis
# ---------------------------------------------------------------------------

class TestImportRunsMigration:
    """Verify 022_import_runs.py upgrade/downgrade structure, columns, indexes."""

    EXPECTED_COLUMNS = {
        "id", "import_id", "tenant_id", "status",
        "source_filename", "source_encoding", "total_rows",
        "valid_rows", "error_rows", "warning_rows",
        "mapping", "validation_result", "apply_result",
        "created_rows", "skipped_rows", "updated_rows",
        "applied_by", "applied_at", "created_at", "updated_at",
        "is_deleted", "deleted_at",
    }

    EXPECTED_INDEX_NAMES = {
        "ix_import_runs_import_id",
        "ix_import_runs_status",
        "ix_import_runs_tenant_id",
        "ix_import_runs_created_at",
    }

    def test_migration_file_exists(self):
        """Migration file 022_import_runs.py must exist."""
        source = _read_migration_source()
        assert len(source) > 100, "Migration file is unexpectedly short"

    def test_upgrade_and_downgrade_functions_exist(self):
        """AST must contain upgrade() and downgrade() top-level functions."""
        tree = _parse_migration()
        func_names = {
            node.name for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        assert "upgrade" in func_names, "upgrade() function missing from migration"
        assert "downgrade" in func_names, "downgrade() function missing from migration"

    def test_upgrade_creates_import_runs_table(self):
        """upgrade() must call op.create_table('import_runs', ...)."""
        source = _read_migration_source()
        assert "create_table" in source, "upgrade() must call op.create_table"
        assert '"import_runs"' in source, "create_table target must be 'import_runs'"

    def test_upgrade_has_all_columns(self):
        """upgrade() must define all expected columns in create_table call."""
        source = _read_migration_source()
        for col in self.EXPECTED_COLUMNS:
            assert f'"{col}"' in source or f"'{col}'" in source, (
                f"Column '{col}' not found in migration create_table call"
            )

    def test_upgrade_creates_expected_indexes(self):
        """upgrade() must create all 4 indexes with correct names."""
        source = _read_migration_source()
        for idx_name in self.EXPECTED_INDEX_NAMES:
            assert idx_name in source, (
                f"Index '{idx_name}' not found in migration"
            )

    def test_upgrade_tenant_only_guard(self):
        """upgrade() must check search_path for t_* prefix (tenant-only)."""
        source = _read_migration_source()
        assert "t_" in source, "Migration must check for tenant schema (t_*)"
        assert "search_path" in source, "Migration must check search_path"

    def test_upgrade_table_exists_guard(self):
        """upgrade() must check _table_exists before creating."""
        source = _read_migration_source()
        assert "_table_exists" in source, (
            "Migration must use _table_exists helper for idempotency"
        )

    def test_downgrade_drops_import_runs(self):
        """downgrade() must drop the import_runs table."""
        source = _read_migration_source()
        assert "drop_table" in source and "import_runs" in source, (
            "downgrade() must call op.drop_table('import_runs')"
        )

    def test_helper_table_exists_function(self):
        """_table_exists helper must be defined and query information_schema."""
        source = _read_migration_source()
        assert "def _table_exists" in source, "_table_exists helper function missing"
        assert "information_schema.tables" in source, (
            "_table_exists must query information_schema.tables"
        )

    def test_revision_metadata(self):
        """Migration must have correct revision and down_revision."""
        source = _read_migration_source()
        assert 'revision = "022_import_runs"' in source, (
            "revision must be '022_import_runs'"
        )
        assert "021_tenant_payments" in source, (
            "down_revision must reference 021_tenant_payments"
        )


# ---------------------------------------------------------------------------
# Test 3: ImportRun ORM model
# ---------------------------------------------------------------------------

class TestImportRunModel:
    """Verify ImportRun ORM model has all required attributes."""

    EXPECTED_ATTRS = {
        "id", "import_id", "tenant_id", "status",
        "source_filename", "source_encoding", "total_rows",
        "valid_rows", "error_rows", "warning_rows",
        "mapping", "validation_result", "apply_result",
        "created_rows", "skipped_rows", "updated_rows",
        "applied_by", "applied_at", "created_at", "updated_at",
        "is_deleted", "deleted_at",
    }

    def test_import_run_model_attributes(self):
        """ImportRun must define all columns from the contract."""
        from models.import_run import ImportRun

        mapper = ImportRun.__mapper__
        orm_columns = {c.key for c in mapper.columns}

        missing = self.EXPECTED_ATTRS - orm_columns
        assert not missing, (
            f"ImportRun ORM model missing columns: {sorted(missing)}"
        )

    def test_import_run_tablename(self):
        """ImportRun must map to 'import_runs' table."""
        from models.import_run import ImportRun
        assert ImportRun.__tablename__ == "import_runs"

    def test_import_run_repr(self):
        """ImportRun __repr__ must work without error."""
        from models.import_run import ImportRun
        run = ImportRun(import_id="imp_test", status="previewed", total_rows=10)
        repr_str = repr(run)
        assert "imp_test" in repr_str
        assert "previewed" in repr_str

    def test_import_run_exported_from_models_init(self):
        """ImportRun must be importable from models.__init__."""
        from models import ImportRun
        assert ImportRun.__tablename__ == "import_runs"


# ---------------------------------------------------------------------------
# Test 4: Pydantic contract schemas serialize/deserialize
# ---------------------------------------------------------------------------

class TestImportPydanticSchemas:
    """Verify all 3-phase contract schemas work correctly."""

    def test_import_error_detail(self):
        """ImportErrorDetail must serialize/deserialize."""
        from schemas.import_schemas import ImportErrorDetail

        err = ImportErrorDetail(row=5, field="sku_code", message="Missing required field")
        data = err.model_dump()
        assert data["row"] == 5
        assert data["field"] == "sku_code"

        err2 = ImportErrorDetail.model_validate(data)
        assert err2 == err

    def test_import_warning_detail(self):
        """ImportWarningDetail must serialize/deserialize."""
        from schemas.import_schemas import ImportWarningDetail

        warn = ImportWarningDetail(row=12, field="unit", message="Unknown unit: 'carton'")
        data = warn.model_dump()
        assert data["row"] == 12

        warn2 = ImportWarningDetail.model_validate(data)
        assert warn2 == warn

    def test_import_preview_response(self):
        """ImportPreviewResponse must serialize/deserialize."""
        from schemas.import_schemas import ImportPreviewResponse

        resp = ImportPreviewResponse(
            import_id="imp_a1b2c3d4",
            source={"filename": "products.csv", "encoding": "utf-8", "row_count": 150},
            columns_detected=["Product Code", "Product Name", "Category"],
            sample_rows=[
                {"Product Code": "F001", "Product Name": "Maize Flour 2kg", "Category": "Flour"}
            ],
        )
        data = resp.model_dump()
        assert data["import_id"] == "imp_a1b2c3d4"
        assert data["source"]["row_count"] == 150
        assert len(data["columns_detected"]) == 3

        resp2 = ImportPreviewResponse.model_validate(data)
        assert resp2.import_id == resp.import_id

    def test_import_validate_request(self):
        """ImportValidateRequest must accept mapping dict."""
        from schemas.import_schemas import ImportValidateRequest

        req = ImportValidateRequest(
            mapping={
                "Product Code": "sku_code",
                "Product Name": "name",
                "Brand": "custom_attributes.brand",
            }
        )
        data = req.model_dump()
        assert data["mapping"]["Product Code"] == "sku_code"

        req2 = ImportValidateRequest.model_validate(data)
        assert req2.mapping == req.mapping

    def test_import_validate_response(self):
        """ImportValidateResponse must handle both statuses."""
        from schemas.import_schemas import ImportValidateResponse, ImportErrorDetail

        resp = ImportValidateResponse(
            import_id="imp_a1b2c3d4",
            status="needs_review",
            valid_rows=143,
            error_rows=7,
            warning_rows=12,
            errors=[
                ImportErrorDetail(row=5, field="sku_code", message="Missing required field")
            ],
        )
        data = resp.model_dump()
        assert data["status"] == "needs_review"
        assert len(data["errors"]) == 1

        resp_ok = ImportValidateResponse(
            import_id="imp_a1b2c3d4",
            status="validated",
            valid_rows=150,
            error_rows=0,
        )
        assert resp_ok.status == "validated"

    def test_import_apply_request(self):
        """ImportApplyRequest must accept skip and fail conflict strategies."""
        from schemas.import_schemas import ImportApplyRequest
        import pydantic

        for strategy in ("skip", "fail"):
            req = ImportApplyRequest(on_conflict=strategy)
            assert req.on_conflict == strategy

        # 'update' and 'error' must be rejected (CTO directive: not yet approved)
        for bad_strategy in ("update", "error"):
            with pytest.raises(pydantic.ValidationError):
                ImportApplyRequest(on_conflict=bad_strategy)

    def test_import_apply_response(self):
        """ImportApplyResponse must serialize full result."""
        from schemas.import_schemas import ImportApplyResponse
        from datetime import datetime, timezone

        resp = ImportApplyResponse(
            import_id="imp_a1b2c3d4",
            status="completed",
            created=140,
            skipped=3,
            updated=0,
            errors=[],
            audit_run_id="aud_run_x9y0z1",
            applied_at=datetime(2026, 6, 12, 10, 30, 0, tzinfo=timezone.utc),
            applied_by="user-uuid-here",
        )
        data = resp.model_dump()
        assert data["created"] == 140
        assert data["audit_run_id"] == "aud_run_x9y0z1"

        resp2 = ImportApplyResponse.model_validate(data)
        assert resp2.import_id == resp.import_id

    def test_import_apply_response_failed_with_errors(self):
        """ImportApplyResponse must handle failed status (fail-closed contract).

        U3-C removed completed_with_errors -- errors always mean failed.
        """
        from schemas.import_schemas import ImportApplyResponse, ImportErrorDetail

        resp = ImportApplyResponse(
            import_id="imp_a1b2c3d4",
            status="failed",
            created=0,
            skipped=0,
            errors=[
                ImportErrorDetail(row=5, sku_code=None, message="Missing sku_code"),
            ],
        )
        assert resp.status == "failed"
        assert len(resp.errors) == 1


# ---------------------------------------------------------------------------
# Test 5: No import API endpoints in skus.py (static source check)
# ---------------------------------------------------------------------------

class TestNoImportEndpoints:
    """Verify U3-B1 does NOT introduce any import API endpoints in skus.py."""

    def test_skus_router_no_import_routes(self):
        """backend/api/v1/skus.py must NOT contain /import route definitions."""
        backend_dir = Path(__file__).resolve().parent.parent
        skus_file = backend_dir / "api" / "v1" / "skus.py"
        assert skus_file.exists(), f"skus.py not found: {skus_file}"

        source = skus_file.read_text(encoding="utf-8")

        # Static analysis: check no route decorator references "/import"
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for deco in node.decorator_list:
                    deco_src = ast.get_source_segment(source, deco) or ""
                    if "/import" in deco_src:
                        pytest.fail(
                            f"Found /import route in skus.py: "
                            f"@{deco_src} on function '{node.name}'"
                        )
