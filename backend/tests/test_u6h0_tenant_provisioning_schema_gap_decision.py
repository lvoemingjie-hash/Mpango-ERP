"""U6-H0 static contract tests for tenant provisioning schema gap decision.

This is a contract/test-only decision gate. No provisioning code is implemented.
No production code, migration, frontend, or deploy artifacts are changed.
"""

from __future__ import annotations

from pathlib import Path

from models.tenant_onboarding import TenantRegistration
from models.wholesaler import Wholesaler


ROOT = Path(__file__).resolve().parents[2]
DECISION_PATH = (
    ROOT
    / "ai-ledger"
    / "product-ai"
    / "2026-07-08_u6h0_tenant_provisioning_schema_gap_decision.md"
)
CONTRACT_PATH = ROOT / "docs" / "contracts" / "tenant_onboarding_provisioning_contract.md"
ONBOARDING_SERVICE_PATH = ROOT / "backend" / "services" / "onboarding_service.py"


def _decision() -> str:
    return DECISION_PATH.read_text(encoding="utf-8")


def _contract() -> str:
    return CONTRACT_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Decision document content assertions
# ---------------------------------------------------------------------------


def test_decision_document_exists_and_has_status():
    text = _decision()

    assert "# U6-H0 Tenant Provisioning Schema Gap Decision" in text
    assert "Status: READY_FOR_U6H1_WITHOUT_MIGRATION" in text
    assert "Date: 2026-07-08" in text


def test_decision_names_all_seven_decision_points():
    text = _decision()

    decision_points = (
        "### 1. provisioned_at",
        "### 2. provisioning_attempt_count",
        "### 3. provisioning_lock / version",
        "### 4. provisioning_last_error",
        "### 5. admin linkage (admin_user_id)",
        "### 6. provisioning event / audit table",
        "### 7. wholesaler linkage",
    )
    for point in decision_points:
        assert point in text, f"Missing decision point: {point}"


def test_each_decision_point_has_explicit_verdict():
    text = _decision()

    required_verdicts = (
        "CANONICAL_ENOUGH",
        "DEFERRED_FOR_MVP",
        "VERIFIED_OK",
    )
    # Each decision point must use at least one of these verdict labels
    for verdict in required_verdicts:
        assert verdict in text, f"Verdict label missing: {verdict}"

    # All 7 points should be classified - count occurrences
    verdict_lines = [line for line in text.splitlines() if line.strip().startswith("**Verdict**:")]
    assert len(verdict_lines) == 7, (
        f"Expected 7 verdict lines, found {len(verdict_lines)}"
    )


def test_decision_states_u6h1_may_proceed_without_migration():
    text = _decision()

    assert "READY_FOR_U6H1_WITHOUT_MIGRATION" in text
    assert "Zero migrations required" in text
    assert "Zero production code changes needed" in text


def test_decision_states_no_migration_required():
    text = _decision()

    assert "No migration needed" in text
    assert "Zero migrations required" in text


def test_decision_confirms_public_signup_verify_status_remain_non_provisioning():
    text = _decision()

    for endpoint in (
        "POST /api/v1/auth/signup",
        "POST /api/v1/auth/verify-email",
        "POST /api/v1/auth/onboarding/status",
    ):
        assert endpoint in text
    assert "non-provisioning" in text


def test_decision_confirms_no_production_code_migration_frontend_deploy_changed():
    text = _decision()

    assert "No forbidden files touched" in text
    assert "zero production code" in text
    assert "zero migration" in text
    assert "zero frontend" in text
    assert "zero deploy/VPS" in text

    assert "allowed" in text.lower()


# ---------------------------------------------------------------------------
# Current schema consistency assertions
# ---------------------------------------------------------------------------


def test_current_schema_matches_decision_point_1_provisioned_at():
    """provisioning_completed_at exists, provisioned_at does not."""
    columns = {column.name for column in TenantRegistration.__table__.columns}

    assert "provisioning_completed_at" in columns, (
        "provisioning_completed_at is the canonical provisioning timestamp"
    )
    assert "provisioned_at" not in columns, (
        "provisioned_at is not a tenant_registrations column - "
        "provisioning_completed_at is canonical"
    )


def test_current_schema_matches_decision_point_2_attempt_count():
    """provisioning_attempt_count is missing, failure/retry fields exist."""
    columns = {column.name for column in TenantRegistration.__table__.columns}

    assert "provisioning_attempt_count" not in columns
    for field in ("failed_at", "failure_code", "failure_message", "retry_allowed_until"):
        assert field in columns, f"Required failure/retry field missing: {field}"


def test_current_schema_matches_decision_point_3_lock_version():
    """No lock/version column exists; unique indexes exist."""
    columns = {column.name for column in TenantRegistration.__table__.columns}
    indexes = {index.name for index in TenantRegistration.__table__.indexes}

    assert "provisioning_lock" not in columns
    assert "version" not in columns

    # Concurrency safety via unique indexes
    assert "ux_tenant_registrations_tenant_schema" in indexes
    assert "ux_tenant_registrations_wholesaler_id" in indexes


def test_current_schema_matches_decision_point_4_last_error():
    """failure_code/failure_message/failed_at/retry_allowed_until are present."""
    columns = {column.name for column in TenantRegistration.__table__.columns}

    assert "provisioning_last_error" not in columns
    for field in ("failure_code", "failure_message", "failed_at", "retry_allowed_until"):
        assert field in columns, f"Required error state field missing: {field}"


def test_current_schema_matches_decision_point_5_admin_linkage():
    """admin_user_id is missing; owner_email exists for derivation."""
    columns = {column.name for column in TenantRegistration.__table__.columns}

    assert "admin_user_id" not in columns
    assert "owner_email" in columns, (
        "owner_email is required for deriving first admin in tenant schema"
    )


def test_current_schema_matches_decision_point_6_audit_table():
    """No provisioning event table fields exist in tenant_registrations."""
    columns = {column.name for column in TenantRegistration.__table__.columns}

    audit_fields = (
        "created_at",
        "updated_at",
        "provisioning_started_at",
        "provisioning_completed_at",
        "failed_at",
        "failure_code",
        "failure_message",
    )
    for field in audit_fields:
        assert field in columns, (
            f"Required audit/timeline field missing: {field}"
        )


def test_current_schema_matches_decision_point_7_wholesaler_linkage():
    """Partial unique indexes exist; wholesalers has sufficient fields."""
    reg_columns = {column.name for column in TenantRegistration.__table__.columns}
    reg_indexes = {index.name for index in TenantRegistration.__table__.indexes}
    ws_columns = {column.name for column in Wholesaler.__table__.columns}

    # tenant_registrations linkage
    assert "wholesaler_id" in reg_columns
    assert "tenant_schema" in reg_columns
    assert "ux_tenant_registrations_wholesaler_id" in reg_indexes
    assert "ux_tenant_registrations_tenant_schema" in reg_indexes

    # wholesalers has sufficient fields for deterministic provisioning
    required_ws_fields = (
        "id",
        "code",
        "name",
        "status",
        "provisioned_at",
    )
    for field in required_ws_fields:
        assert field in ws_columns, f"Wholesaler field missing: {field}"

    # Schema derivation methods exist
    assert hasattr(Wholesaler, "get_tenant_schema")
    assert hasattr(Wholesaler, "derive_schema_from_id")


# ---------------------------------------------------------------------------
# Production code boundary assertions
# ---------------------------------------------------------------------------


def test_current_public_onboarding_service_contains_no_tenant_provisioning_calls():
    """Public onboarding routes remain non-provisioning."""
    source = ONBOARDING_SERVICE_PATH.read_text(encoding="utf-8")

    forbidden_terms = (
        "Wholesaler(",
        "bootstrap_tenant_schema",
        "bootstrap(",
        "CREATE SCHEMA",
        "User(",
        "Role(",
        "Permission(",
        "user_roles",
        "role_permissions",
        "provisioning_completed_at =",
        "tenant_schema =",
        "wholesaler_id =",
        'status = "active"',
    )
    for term in forbidden_terms:
        assert term not in source, f"Provisioning call found in public service: {term}"


# ---------------------------------------------------------------------------
# U6-G contract alignment assertions
# ---------------------------------------------------------------------------


def test_decision_aligns_with_u6g_contract_schema_gap_findings():
    """U6-H0 decision must not contradict U6-G schema gap audit."""
    contract_text = _contract()
    decision_text = _decision()

    # U6-G gap findings that U6-H0 addresses
    gap_patterns = (
        "provisioned_at",  # gap identified
        "provisioning_attempt_count",  # gap identified
        "provisioning_last_error",  # gap identified
        "provisioning_lock",  # gap identified
        "Admin user linkage",  # gap identified
        "event table",  # gap identified
    )
    for pattern in gap_patterns:
        assert pattern in contract_text, f"U6-G gap not found in contract: {pattern}"

    # Decision must reference U6-G
    assert "U6-G" in decision_text


def test_decision_contains_final_verdict_table():
    text = _decision()

    assert "## Final Verdict: READY_FOR_U6H1_WITHOUT_MIGRATION" in text
    for dp_num in range(1, 8):
        assert f"| {dp_num} |" in text, f"Decision point {dp_num} not in verdict table"


def test_decision_lists_what_u6h1_must_use_from_current_schema():
    text = _decision()

    required_sections = (
        "provisioning_completed_at",
        "failure_code",
        "SELECT ... FOR UPDATE",
        "owner_email",
    )
    for section in required_sections:
        assert section in text, (
            f"U6-H1 usage instruction missing: {section}"
        )
