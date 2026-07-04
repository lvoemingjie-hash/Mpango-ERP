"""S6-C staging reset current-head gate contract tests."""

from __future__ import annotations

from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
RESET_SCRIPT = BACKEND_DIR / "scripts" / "reset-staging.sh"

REQUIRED_TABLES = {
    "import_runs",
    "inventory_reservations",
    "intake_workspaces",
    "intake_uploads",
    "intake_product_rows",
    "intake_validation_issues",
}

REQUIRED_COLUMNS = {
    "intake_workspaces.apply_status",
    "intake_workspaces.applied_at",
    "intake_workspaces.applied_by",
    "intake_workspaces.apply_result",
    "intake_product_rows.apply_status",
    "intake_product_rows.target_sku_id",
    "intake_product_rows.apply_error_code",
    "intake_product_rows.apply_error_message",
}


def _reset_script_source() -> str:
    return RESET_SCRIPT.read_text(encoding="utf-8")


def test_reset_staging_upgrades_to_current_alembic_head():
    source = _reset_script_source()

    assert "python -m alembic upgrade head" in source
    assert "006_phase_b6_payments_idempotency_key" not in source


def test_reset_staging_asserts_required_current_mvp_tables_and_columns():
    source = _reset_script_source()

    for table_name in REQUIRED_TABLES:
        assert table_name in source, f"reset-staging must assert table {table_name}"

    for column_ref in REQUIRED_COLUMNS:
        table_name, column_name = column_ref.split(".")
        assert table_name in source, f"reset-staging must reference {table_name}"
        assert column_name in source, f"reset-staging must assert {column_ref}"

    assert "intake_product_rows.applied_at" not in source
    assert "applied_sku_id" not in source
    assert "apply_error\"" not in source


def test_reset_staging_schema_assertions_fail_closed_without_swallowing_errors():
    source = _reset_script_source()
    verification_section = source.split("# Step 4: Verify", 1)[1]

    assert "assert_tenant_table" in verification_section
    assert "assert_tenant_column" in verification_section
    assert "exit 1" in verification_section
    assert "|| true" not in verification_section


def test_reset_staging_does_not_print_reporting_password():
    source = _reset_script_source()

    assert "set -x" not in source
    assert "ReportingPass_staging_2026" not in source
    assert "DemoAdmin2026" not in source
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("echo") or stripped.startswith("printf"):
            assert "REPORTING_USER_PASSWORD" not in stripped
