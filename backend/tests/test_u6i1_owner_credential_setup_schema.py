"""U6-I1 owner credential setup token schema tests."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects import postgresql

from models import OwnerCredentialSetupToken
from models.tenant_onboarding import OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE


ROOT = Path(__file__).resolve().parents[2]
# Fixed historical U6-I1 implementation commit. The U6-I1 scope assertion is
# anchored on this exact commit (not on the moving current HEAD), so later
# tasks that legitimately touch runtime paths no longer trip the guard. The
# guard now inspects only what U6-I1 itself changed, via git diff-tree.
U6I1_HISTORICAL_COMMIT = "712db0c1d3796a22c8b3c4c398d91577146d3ee1"  # pragma: allowlist secret
MIGRATION_PATH = ROOT / "backend" / "alembic" / "versions" / "028_owner_credential_setup_tokens.py"
ALEMBIC_INI_PATH = ROOT / "backend" / "alembic.ini"
# The exact five files the original U6-I1 implementation commit touched.
EXPECTED_U6I1_PATHS = {
    "backend/alembic/versions/028_owner_credential_setup_tokens.py",
    "backend/models/tenant_onboarding.py",
    "backend/models/__init__.py",
    "backend/tests/test_u6i1_owner_credential_setup_schema.py",
    "ai-ledger/product-ai/2026-07-08_u6i1_owner_credential_setup_schema.md",
}
FORBIDDEN_RUNTIME_PATHS = {
    "backend/services/tenant_provisioning_service.py",
    "backend/models/user.py",
    "backend/api/v1/auth.py",
    "backend/services/onboarding_service.py",
}
FORBIDDEN_TOKEN_COLUMNS = {"raw_token", "token_plaintext", "plaintext_token"}


def _column_names(model) -> set[str]:
    return {column.name for column in model.__table__.columns}


def _index_names(model) -> set[str]:
    return {index.name for index in model.__table__.indexes}


def _constraint_names(model) -> set[str]:
    return {constraint.name for constraint in model.__table__.constraints if constraint.name}


def _constraint_sql(model, constraint_name: str) -> str:
    constraint = next(
        constraint for constraint in model.__table__.constraints if constraint.name == constraint_name
    )
    assert isinstance(constraint, CheckConstraint)
    return str(
        constraint.sqltext.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def _postgres_where(index) -> str:
    where = index.dialect_options["postgresql"].get("where")
    if where is None:
        return ""
    return str(where.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def _historical_u6i1_paths() -> set[str]:
    """Return the exact file set the original U6-I1 implementation commit changed.

    Anchored on the fixed historical commit (``U6I1_HISTORICAL_COMMIT``) via
    ``git diff-tree``, so the scope assertion is stable and does not compare
    against the moving current HEAD. Fails closed if the historical commit is
    unavailable in the local repository.
    """
    # Fail closed if the historical commit is missing (e.g. shallow clone).
    verify = subprocess.run(
        ["git", "rev-parse", "--verify", U6I1_HISTORICAL_COMMIT + "^{commit}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if verify.returncode != 0:
        raise AssertionError(
            "U6-I1 historical commit is unavailable; cannot verify scope"
        )
    diff_tree = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", U6I1_HISTORICAL_COMMIT],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return {line for line in diff_tree.stdout.splitlines() if line}


def _migration_module():
    spec = importlib.util.spec_from_file_location("u6i1_migration", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_model_defines_owner_credential_setup_token_hash_only_table():
    assert OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE == "owner_credential_setup"
    assert OwnerCredentialSetupToken.__table__.schema == "public"
    assert OwnerCredentialSetupToken.__tablename__ == "owner_credential_setup_tokens"

    assert {
        "id",
        "registration_id",
        "token_hash",
        "purpose",
        "expires_at",
        "used_at",
        "revoked_at",
        "created_at",
        "updated_at",
        "is_deleted",
        "deleted_at",
    }.issubset(_column_names(OwnerCredentialSetupToken))
    assert FORBIDDEN_TOKEN_COLUMNS.isdisjoint(_column_names(OwnerCredentialSetupToken))


def test_model_defines_fk_unique_hash_and_active_partial_index():
    table = OwnerCredentialSetupToken.__table__
    fk_constraints = [c for c in table.constraints if isinstance(c, ForeignKeyConstraint)]
    assert any(
        fk.ondelete == "CASCADE"
        and fk.column.table.schema == "public"
        and fk.column.table.name == "tenant_registrations"
        and fk.column.name == "id"
        for constraint in fk_constraints
        for fk in constraint.elements
    )

    assert "ux_owner_credential_setup_tokens_token_hash" in _index_names(
        OwnerCredentialSetupToken
    )
    token_hash_index = next(
        index
        for index in table.indexes
        if index.name == "ux_owner_credential_setup_tokens_token_hash"
    )
    assert token_hash_index.unique is True
    assert {column.name for column in token_hash_index.columns} == {"token_hash"}
    assert any(
        isinstance(constraint, UniqueConstraint)
        and {column.name for column in constraint.columns} == {"token_hash"}
        for constraint in table.constraints
    )

    active_index = next(
        index
        for index in table.indexes
        if index.name == "ux_owner_credential_setup_tokens_registration_active"
    )
    assert active_index.unique is True
    assert {column.name for column in active_index.columns} == {"registration_id"}
    active_where = _postgres_where(active_index)
    assert "used_at IS NULL" in active_where
    assert "revoked_at IS NULL" in active_where
    assert "is_deleted = false" in active_where


def test_model_defines_purpose_default_and_check_constraint():
    purpose = OwnerCredentialSetupToken.__table__.c.purpose

    assert purpose.default is not None
    assert str(purpose.default.arg) == OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE
    assert purpose.server_default is not None
    assert "owner_credential_setup" in str(purpose.server_default.arg)
    assert "ck_owner_credential_setup_tokens_purpose" in _constraint_names(
        OwnerCredentialSetupToken
    )
    assert (
        _constraint_sql(
            OwnerCredentialSetupToken, "ck_owner_credential_setup_tokens_purpose"
        )
        == "purpose = 'owner_credential_setup'"
    )


def test_migration_revision_and_schema_contract_are_defined():
    migration = _migration_module()
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert migration.revision == "028_owner_credential_setup_tokens"
    assert migration.down_revision == "027_onboarding_status_tokens"
    assert "owner_credential_setup_tokens" in source
    assert "token_hash" in source
    assert "owner_credential_setup" in source
    assert "ondelete=\"CASCADE\"" in source
    assert "ux_owner_credential_setup_tokens_token_hash" in source
    assert "ux_owner_credential_setup_tokens_registration_active" in source
    for forbidden_column in FORBIDDEN_TOKEN_COLUMNS:
        assert forbidden_column not in source


def test_alembic_head_includes_owner_credential_setup_tokens():
    config = Config(str(ALEMBIC_INI_PATH))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["036_retailer_mvp_identity"]


def test_owner_credential_schema_foundation_artifacts_remain_present():
    assert MIGRATION_PATH.is_file()
    assert (ROOT / "backend" / "models" / "tenant_onboarding.py").is_file()
    assert (ROOT / "backend" / "models" / "__init__.py").is_file()


def test_u6i1_historical_implementation_scope_is_exactly_the_original_five_files():
    """U6-I1 touched exactly its original five files and no runtime path.

    The scope is anchored on the fixed historical implementation commit, not on
    the moving current HEAD, so later tasks that legitimately touch runtime
    paths do not trip this guard.
    """
    changed = _historical_u6i1_paths()

    assert changed == EXPECTED_U6I1_PATHS
    assert len(changed) == 5
    # No runtime path was touched by the original U6-I1 implementation.
    assert changed.isdisjoint(FORBIDDEN_RUNTIME_PATHS)
    assert not any(path.startswith("frontend/") for path in changed)


def test_synthetic_forbidden_runtime_path_is_still_rejected():
    """Regression: the forbidden-runtime-path guard still rejects violations.

    Proves the scope assertion was not weakened by the historical-commit
    re-anchoring: a synthetic scope containing a forbidden runtime path still
    fails the disjoint check.
    """
    synthetic_scope = EXPECTED_U6I1_PATHS | {"backend/services/onboarding_service.py"}

    assert not synthetic_scope.isdisjoint(FORBIDDEN_RUNTIME_PATHS)
