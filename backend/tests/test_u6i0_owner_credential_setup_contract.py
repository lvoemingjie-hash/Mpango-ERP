"""U6-I0 static contract tests for owner credential setup."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = (
    ROOT
    / "ai-ledger"
    / "product-ai"
    / "2026-07-08_u6i0_owner_credential_setup_contract.md"
)
BASE_REF = "origin/product-dev-recovered"
ALLOWED_CHANGED_PATHS = {
    "ai-ledger/product-ai/2026-07-08_u6i0_owner_credential_setup_contract.md",
    "backend/tests/test_u6i0_owner_credential_setup_contract.py",
}
PUBLIC_BOUNDARY_PATHS = (
    ROOT / "backend" / "api" / "v1" / "auth.py",
    ROOT / "backend" / "services" / "onboarding_service.py",
    ROOT / "backend" / "services" / "tenant_provisioning_service.py",
)


def _contract() -> str:
    return CONTRACT_PATH.read_text(encoding="utf-8")


def _changed_paths() -> set[str]:
    diff = subprocess.run(
        ["git", "diff", "--name-only", BASE_REF, "--"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    status = subprocess.run(
        ["git", "status", "--short", "--porcelain"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    changed = set(diff.stdout.splitlines())
    for line in status.stdout.splitlines():
        changed.add(line[3:])
    return changed


def test_contract_document_exists_and_defines_required_sections():
    text = _contract()

    assert "# U6-I0 Owner Credential Setup Contract Gate" in text
    for heading in (
        "## Scope",
        "## Contract Decisions",
        "### 1. No Invented Admin Credentials",
        "### 2. Token-Based Owner Setup",
        "### 3. First Admin Creation Boundary",
        "### 4. Proof Before Tenant User Creation",
        "### 5. Registration Credential Cleanup Remains Valid",
        "### 6. U6-H4 Dependency",
        "### 7. Public Endpoint Disclosure Boundary",
        "## Future U6-I Test Plan",
    ):
        assert heading in text


def test_contract_forbids_invented_first_admin_credentials():
    text = _contract()
    lower_text = text.lower()

    assert "must not invent credentials" in lower_text
    assert "system-selected credential" in lower_text
    for forbidden_phrase in (
        "admin_password",
        "admin-password",
        "changeme",
        "default password",
        "temporary password",
        "random password",
        "placeholder password",
    ):
        assert forbidden_phrase not in lower_text


def test_contract_requires_hash_only_single_use_expiring_setup_token():
    text = _contract()
    lower_text = text.lower()

    for required_phrase in (
        "persist only a hash of the setup token",
        "delivered exactly once",
        "must expire",
        "must be single-use",
        "replay after successful use must fail closed",
    ):
        assert required_phrase in lower_text


def test_contract_forbids_query_string_token_transport():
    text = _contract()
    lower_text = text.lower()

    assert "must not be transported in url query strings" in lower_text
    assert "post body or an http header only" in lower_text


def test_contract_blocks_u6h4_until_credential_setup_completion():
    text = _contract()
    lower_text = text.lower()

    assert "u6-h4 first tenant admin and rbac creation remains blocked" in lower_text
    assert "credential setup flow can prove owner possession" in lower_text
    assert "tenant user password hash" in lower_text


def test_contract_preserves_registration_credential_cleanup():
    text = _contract()
    lower_text = text.lower()

    assert "credential cleanup remains valid" in lower_text
    assert "must not require preserving, restoring, logging, or exposing" in lower_text
    assert "registration credential hash after provisioning completion" in lower_text


def test_contract_and_runtime_lock_public_endpoint_disclosure_boundary():
    text = _contract()

    for term in (
        "Public registration credential hashes",
        "Raw setup tokens",
        "Setup-token hashes",
        "Tenant schema names",
        "Whether the first tenant admin user exists",
    ):
        assert term in text

    auth_source = PUBLIC_BOUNDARY_PATHS[0].read_text(encoding="utf-8")
    onboarding_source = PUBLIC_BOUNDARY_PATHS[1].read_text(encoding="utf-8")
    provisioning_source = PUBLIC_BOUNDARY_PATHS[2].read_text(encoding="utf-8")

    assert '"/onboarding/setup-credential"' in auth_source
    assert "OwnerCredentialSetupService" in auth_source
    assert "OwnerCredentialSetupService" in onboarding_source
    assert "OwnerCredentialSetupService" not in provisioning_source
    assert "owner_credential_service" not in provisioning_source


def test_integrated_baseline_retains_contract_and_runtime_artifacts():
    assert CONTRACT_PATH.is_file()
    assert all(path.is_file() for path in PUBLIC_BOUNDARY_PATHS)
    assert (ROOT / "backend" / "services" / "owner_credential_service.py").is_file()


def test_integrated_baseline_retains_owner_credential_runtime_foundation():
    migration = ROOT / "backend" / "alembic" / "versions" / "028_owner_credential_setup_tokens.py"
    model = ROOT / "backend" / "models" / "tenant_onboarding.py"
    service = ROOT / "backend" / "services" / "owner_credential_service.py"

    assert migration.is_file()
    assert model.is_file()
    assert service.is_file()
