"""Permanent tests for the backend RUNTIME entrypoint and Compose topology
contract (CTO-AUTH-ORDER-R2-DB-AUTHORITY-INTEGRATION-R1-R2-RUNTIME-ENTRYPOINT-CLOSURE-2026-09-19).

The container receives ONLY the runtime-role DATABASE_URL, so the committed
runtime entrypoint must contain ZERO migration, provisioning, grant, public
DDL or tenant-bootstrap invocations: it may run a strictly read-only
readiness gate (SELECT only) and then exec the application runtime — nothing
else.  The Compose PostgreSQL service provides the MAINTENANCE database and
must NOT mount database/init.sql (or any application-schema initializer)
into it, and must stay on the accepted PostgreSQL 16 line.

The audit logic lives in module-level functions so the negative mutation
tests can execute it against mutated entrypoint text and watch it go RED.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
ENTRYPOINT = BACKEND_DIR / "docker-entrypoint.sh"
COMPOSE = REPO_ROOT / "docker-compose.yml"
INIT_SQL = REPO_ROOT / "database" / "init.sql"

# write verbs / forbidden invocations, evaluated on comment-stripped code
_FORBIDDEN_CODE = [
    r"\balembic\b",
    r"bootstrap_tenant_schema",
    r"provision_runtime_db_roles",
    r"\bGRANT\b",
    r"\bCREATE\b",
    r"\bALTER\b",
    r"\bDROP\b",
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bDELETE\b",
    r"docker-entrypoint-initdb\.d",
]


def audit_runtime_entrypoint(text: str) -> list[str]:
    """Return the contract violations of a candidate runtime entrypoint.
    Empty list == compliant: no migration/provisioning/grant/bootstrap
    invocations in code, exactly one runtime exec, and a strictly read-only
    readiness gate (SELECT only, no write verbs)."""
    violations: list[str] = []
    code_lines = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            continue
        # strip trailing comments (conservative: quotes are not used with #)
        code = raw.split("#", 1)[0]
        code_lines.append(code)
    code = "\n".join(code_lines)
    for pattern in _FORBIDDEN_CODE:
        if re.search(pattern, code, re.IGNORECASE):
            violations.append(f"forbidden invocation/statement in code: {pattern}")
    exec_lines = [l for l in code_lines if l.strip().startswith("exec ")]
    if len(exec_lines) != 1:
        violations.append(f"expected exactly one exec (the application runtime), found {len(exec_lines)}")
    else:
        if "uvicorn main:app" not in exec_lines[0]:
            violations.append("the single exec is not the application runtime (uvicorn main:app)")
        if text.splitlines()[-1].strip() != exec_lines[0].strip() and \
                not code.rstrip().endswith(exec_lines[0].strip()):
            violations.append("the runtime exec is not the final command")
    # readiness gate, if present, must be strictly read-only
    gate = re.search(r"python - <<'PY'\n(.*?)\nPY", text, re.DOTALL)
    if gate is not None:
        gate_code = gate.group(1)
        for verb in ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "GRANT"):
            if re.search(rf"\b{verb}\b", gate_code):
                violations.append(f"readiness gate contains write verb {verb}")
        if "SELECT" not in gate_code:
            violations.append("readiness gate does not issue a read-only SELECT probe")
    return violations


@pytest.fixture(scope="module")
def entrypoint_text() -> str:
    return ENTRYPOINT.read_text(encoding="utf-8")


def test_runtime_entrypoint_has_no_migration_provision_or_bootstrap_invocations(
    entrypoint_text,
):
    violations = audit_runtime_entrypoint(entrypoint_text)
    assert violations == [], violations


def test_runtime_entrypoint_starts_only_the_application_runtime(entrypoint_text):
    # the single exec is uvicorn and the script ends with it: everything
    # before it may only observe (read-only gate)
    violations = audit_runtime_entrypoint(entrypoint_text)
    assert violations == []
    assert "exec uvicorn main:app" in entrypoint_text
    assert entrypoint_text.rstrip().endswith("exec uvicorn main:app --host 0.0.0.0 --port 8000")


def test_runtime_entrypoint_readiness_gate_is_strictly_read_only(entrypoint_text):
    gate = re.search(r"python - <<'PY'\n(.*?)\nPY", entrypoint_text, re.DOTALL)
    assert gate is not None, "the retained readiness gate must be present and auditable"
    assert "SELECT 1" in gate.group(1)
    assert audit_runtime_entrypoint(entrypoint_text) == []


def test_compose_postgres_service_on_accepted_pg16_line():
    text = COMPOSE.read_text(encoding="utf-8")
    assert "postgres:15" not in text, "compose must not silently diverge to PostgreSQL 15"
    assert re.search(r"^    image: postgres:16$", text, re.MULTILINE), \
        "the compose postgres service must pin the accepted postgres:16 line"


def test_compose_postgres_service_mounts_no_application_initializer():
    text = COMPOSE.read_text(encoding="utf-8")
    assert "init.sql" not in text, \
        "database/init.sql must not be mounted into the maintenance database"
    assert "/docker-entrypoint-initdb.d/" not in text, \
        "no application-schema initializer may be mounted into the maintenance database"


def test_compose_documents_that_setup_completes_before_runtime():
    text = COMPOSE.read_text(encoding="utf-8")
    assert "is NOT a fresh-database" in text
    assert "setup.sh" in text


def test_historical_init_sql_file_is_preserved_untouched():
    """The mount is removed from compose, but the historical file itself must
    remain in the tree (this round must not delete or rewrite it)."""
    assert INIT_SQL.is_file(), "database/init.sql must remain in the tree"
    assert "alembic_version" in INIT_SQL.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# negative mutation counterexamples: reintroducing the old runtime writes
# into the entrypoint must turn the invariant audit RED
# ---------------------------------------------------------------------------
def test_mutation_reintroducing_alembic_upgrade_turns_audit_red(entrypoint_text):
    mutated = entrypoint_text.replace(
        "echo \"Starting Uvicorn...\"",
        "echo \"[migrate] Running public schema migrations...\"\n"
        "alembic upgrade head\n"
        "echo \"Starting Uvicorn...\"")
    assert mutated != entrypoint_text
    violations = audit_runtime_entrypoint(mutated)
    assert any("alembic" in v for v in violations), violations


def test_mutation_reintroducing_tenant_bootstrap_turns_audit_red(entrypoint_text):
    mutated = entrypoint_text.replace(
        "echo \"Starting Uvicorn...\"",
        "echo \"[bootstrap] Bootstrapping tenant schema 't_dev'...\"\n"
        "python scripts/bootstrap_tenant_schema.py \"${DEFAULT_TENANT_SCHEMA:-t_dev}\"\n"
        "echo \"Starting Uvicorn...\"")
    assert mutated != entrypoint_text
    violations = audit_runtime_entrypoint(mutated)
    assert any("bootstrap_tenant_schema" in v for v in violations), violations
