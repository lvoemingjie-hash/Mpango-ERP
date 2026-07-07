"""U6-G static contract tests for future tenant provisioning."""

from __future__ import annotations

from pathlib import Path

from models.tenant_onboarding import TenantRegistration


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "docs" / "contracts" / "tenant_onboarding_provisioning_contract.md"
ONBOARDING_SERVICE_PATH = ROOT / "backend" / "services" / "onboarding_service.py"


def _contract() -> str:
    return CONTRACT_PATH.read_text(encoding="utf-8")


def test_contract_document_exists_and_defines_required_sections():
    text = _contract()

    assert "# Tenant Onboarding Provisioning Contract" in text
    for heading in (
        "## 1. Preconditions",
        "## 2. Provisioning Outputs",
        "## 3. Transaction And Rollback Boundary",
        "## 4. Idempotency",
        "## 5. Security And Public Boundaries",
        "## 6. Schema Gaps",
        "## 7. Future U6-H Test Plan",
        "## 8. Recommended Implementation Plan",
    ):
        assert heading in text


def test_contract_locks_public_endpoint_no_provisioning_boundary():
    text = _contract()

    for endpoint in (
        "POST /api/v1/auth/signup",
        "POST /api/v1/auth/verify-email",
        "POST /api/v1/auth/onboarding/status",
    ):
        assert endpoint in text
    assert "MUST NOT provision tenants" in text
    assert "Email verification tokens and onboarding status tokens MUST NOT be accepted" in text
    assert "identity-only super admin" in text
    assert "system:admin" in text


def test_contract_defines_outputs_and_credential_cleanup():
    text = _contract()

    required_terms = (
        "public.wholesalers",
        "backend/scripts/bootstrap_tenant_schema.py",
        "first admin user",
        "admin role",
        "Full MVP admin permissions",
        "status = 'active'",
        "wholesaler_id",
        "tenant_schema",
        "provisioning_completed_at",
        "password_hash = NULL",
        "password_hash_cleared_at",
        "password_hash_cleanup_reason = 'provisioned'",  # pragma: allowlist secret
    )
    for term in required_terms:
        assert term in text


def test_contract_defines_saga_fail_closed_and_idempotency_cases():
    text = _contract()

    for case in (
        "Wholesaler created but schema bootstrap fails",
        "Schema created but admin user fails",
        "Admin user created but RBAC assignment fails",
        "Registration final update fails",
        "Duplicate retry after partial failure",
        "Repeated provisioning for an already-active registration",
        "Concurrent provisioning requests MUST NOT create duplicate tenant schemas",
    ):
        assert case in text
    assert "SELECT ... FOR UPDATE" in text
    assert "advisory lock" in text
    assert "multi-step saga" in text


def test_schema_gap_audit_matches_current_tenant_registration_model():
    text = _contract()
    columns = {column.name for column in TenantRegistration.__table__.columns}
    indexes = {index.name for index in TenantRegistration.__table__.indexes}

    assert "provisioning_completed_at" in columns
    assert "provisioned_at" not in columns
    assert "provisioning_attempt_count" not in columns
    assert "provisioning_last_error" not in columns
    assert "provisioning_lock" not in columns
    assert "version" not in columns
    assert "admin_user_id" not in columns
    assert "ux_tenant_registrations_tenant_schema" in indexes
    assert "ux_tenant_registrations_wholesaler_id" in indexes

    assert "`tenant_registrations.provisioned_at`: missing" in text
    assert "`tenant_registrations.provisioning_attempt_count`: missing" in text
    assert "`tenant_registrations.provisioning_last_error`: missing" in text
    assert "`tenant_registrations.provisioning_lock` or `version`: missing" in text
    assert "Admin user linkage from registration: missing" in text
    assert "tenant_schema` uniqueness: present" in text
    assert "wholesaler_id` uniqueness: present" in text


def test_current_public_onboarding_service_contains_no_tenant_provisioning_calls():
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
        "status = \"active\"",
    )
    for term in forbidden_terms:
        assert term not in source


def test_contract_lists_future_u6h_slices_and_required_tests():
    text = _contract()

    for slice_name in ("U6-H0", "U6-H1", "U6-H2", "U6-H3", "U6-H4"):
        assert slice_name in text
    for future_test in (
        "Happy path creates public wholesaler",
        "Registration that is not `email_verified` is blocked",
        "Concurrent provisioning requests cannot create duplicate",
        "Public signup, verify-email, and onboarding-status endpoints remain no-provisioning gates",
        "No raw password, token, token hash, password hash, JWT, or DB credential leakage",
        "Canonical bootstrap schema completeness on a fresh DB",
        "RBAC completeness for first admin",
        "Runtime smoke on a fresh DB",
    ):
        assert future_test in text
