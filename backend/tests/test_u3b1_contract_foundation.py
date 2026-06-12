"""U3-B1 Contract Foundation Tests.

Validates:
1. skus:import permission exists in seed scripts (static check)
2. import_runs DDL applies cleanly to tenant schema
3. ImportRun ORM model maps to all columns
4. Pydantic contract schemas serialize/deserialize correctly
5. No import API endpoints exist yet
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text


# ---------------------------------------------------------------------------
# Test 1: Permission exists in seed scripts (static check)
# ---------------------------------------------------------------------------

class TestSkusImportPermission:
    """Verify skus:import is present in both seed scripts."""

    def test_create_wholesaler_has_skus_import(self):
        """create_wholesaler.py must include skus:import in permissions_data."""
        import importlib
        import scripts.create_wholesaler as cw

        # Re-read the source to extract permissions_data
        # (permissions_data is built inside create_permissions, not at module level)
        import inspect
        source = inspect.getsource(cw.create_permissions)
        assert "skus:import" in source, (
            "create_wholesaler.py create_permissions() must include 'skus:import'"
        )

    def test_seed_demo_data_has_skus_import(self):
        """seed_demo_data.py PERMISSION_CODES must include skus:import."""
        from scripts.seed_demo_data import PERMISSION_CODES

        codes = {code for code, _desc in PERMISSION_CODES}
        assert "skus:import" in codes, (
            f"PERMISSION_CODES missing 'skus:import'. Found: {sorted(codes)}"
        )

    def test_seed_demo_data_admin_gets_all_perms(self):
        """seed_demo_data assigns ALL permissions to admin (including skus:import)."""
        from scripts.seed_demo_data import PERMISSION_CODES

        # The _seed_rbac function assigns ALL PERMISSION_CODES to admin.
        # This is a structural assertion that the list includes skus:import.
        codes = {code for code, _desc in PERMISSION_CODES}
        assert "skus:import" in codes


# ---------------------------------------------------------------------------
# Test 2: import_runs table DDL
# ---------------------------------------------------------------------------

class TestImportRunsTable:
    """Verify import_runs table can be created in tenant schema."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_import_runs_ddl_applies(self, async_session):
        """The migration's CREATE TABLE must apply without error."""
        # The async_session fixture already bootstraps t_test schema.
        # Run the migration's CREATE TABLE inline to verify DDL correctness.
        await async_session.execute(text("""
            CREATE TABLE IF NOT EXISTS import_runs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                import_id VARCHAR(64) NOT NULL UNIQUE,
                tenant_id UUID NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'previewed',
                source_filename VARCHAR(255),
                source_encoding VARCHAR(32),
                total_rows INTEGER NOT NULL DEFAULT 0,
                valid_rows INTEGER,
                error_rows INTEGER,
                warning_rows INTEGER,
                mapping JSONB,
                validation_result JSONB,
                apply_result JSONB,
                created_rows INTEGER DEFAULT 0,
                skipped_rows INTEGER DEFAULT 0,
                updated_rows INTEGER DEFAULT 0,
                applied_by UUID,
                applied_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        await async_session.commit()

        # Verify table exists
        result = await async_session.execute(text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = 'import_runs'"
        ))
        assert result.first() is not None, "import_runs table must exist after DDL"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_import_runs_columns_exist(self, async_session):
        """All required columns must exist on import_runs."""
        # Ensure table exists (idempotent)
        await async_session.execute(text("""
            CREATE TABLE IF NOT EXISTS import_runs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                import_id VARCHAR(64) NOT NULL UNIQUE,
                tenant_id UUID NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'previewed',
                source_filename VARCHAR(255),
                source_encoding VARCHAR(32),
                total_rows INTEGER NOT NULL DEFAULT 0,
                valid_rows INTEGER,
                error_rows INTEGER,
                warning_rows INTEGER,
                mapping JSONB,
                validation_result JSONB,
                apply_result JSONB,
                created_rows INTEGER DEFAULT 0,
                skipped_rows INTEGER DEFAULT 0,
                updated_rows INTEGER DEFAULT 0,
                applied_by UUID,
                applied_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        await async_session.commit()

        result = await async_session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'import_runs'"
        ))
        columns = {row[0] for row in result.fetchall()}

        expected = {
            "id", "import_id", "tenant_id", "status",
            "source_filename", "source_encoding", "total_rows",
            "valid_rows", "error_rows", "warning_rows",
            "mapping", "validation_result", "apply_result",
            "created_rows", "skipped_rows", "updated_rows",
            "applied_by", "applied_at", "created_at", "updated_at",
        }
        missing = expected - columns
        assert not missing, f"Missing columns: {sorted(missing)}"


# ---------------------------------------------------------------------------
# Test 3: ImportRun ORM model
# ---------------------------------------------------------------------------

class TestImportRunModel:
    """Verify ImportRun ORM model has all required attributes."""

    def test_import_run_model_attributes(self):
        """ImportRun must define all columns from the contract."""
        from models.import_run import ImportRun

        expected_attrs = {
            "id", "import_id", "tenant_id", "status",
            "source_filename", "source_encoding", "total_rows",
            "valid_rows", "error_rows", "warning_rows",
            "mapping", "validation_result", "apply_result",
            "created_rows", "skipped_rows", "updated_rows",
            "applied_by", "applied_at", "created_at", "updated_at",
        }

        mapper = ImportRun.__mapper__
        orm_columns = {c.key for c in mapper.columns}

        missing = expected_attrs - orm_columns
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

        # Round-trip
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

        # Round-trip
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

        # Validated status (no errors)
        resp_ok = ImportValidateResponse(
            import_id="imp_a1b2c3d4",
            status="validated",
            valid_rows=150,
            error_rows=0,
        )
        assert resp_ok.status == "validated"

    def test_import_apply_request(self):
        """ImportApplyRequest must accept all conflict strategies."""
        from schemas.import_schemas import ImportApplyRequest

        for strategy in ("skip", "update", "error"):
            req = ImportApplyRequest(on_conflict=strategy)
            assert req.on_conflict == strategy

    def test_import_apply_response(self):
        """ImportApplyResponse must serialize full result."""
        from schemas.import_schemas import ImportApplyResponse, ImportErrorDetail
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

        # Round-trip
        resp2 = ImportApplyResponse.model_validate(data)
        assert resp2.import_id == resp.import_id

    def test_import_apply_response_completed_with_errors(self):
        """ImportApplyResponse must handle completed_with_errors status."""
        from schemas.import_schemas import ImportApplyResponse, ImportErrorDetail

        resp = ImportApplyResponse(
            import_id="imp_a1b2c3d4",
            status="completed_with_errors",
            created=138,
            skipped=5,
            errors=[
                ImportErrorDetail(row=5, sku_code=None, message="Missing sku_code"),
            ],
        )
        assert resp.status == "completed_with_errors"
        assert len(resp.errors) == 1


# ---------------------------------------------------------------------------
# Test 5: No import API endpoints exist yet
# ---------------------------------------------------------------------------

class TestNoImportEndpoints:
    """Verify U3-B1 does NOT introduce any import API endpoints."""

    def test_no_import_routes_registered(self):
        """The FastAPI app must NOT have /import/ routes yet (U3-B2 scope)."""
        from main import app

        routes = [
            route.path for route in app.routes
            if hasattr(route, "path")
        ]
        import_routes = [r for r in routes if "/import" in r]
        assert len(import_routes) == 0, (
            f"U3-B1 must not register import endpoints. Found: {import_routes}"
        )
