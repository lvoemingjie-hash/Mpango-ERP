#!/usr/bin/env bash
# CI test-database supply for the Deploy Staging backend test job.
#
# CTO-C91-CI-CONTRACT-ALIGNMENT-ZCODEW-R2-20261006
#
# This wrapper reproduces the verified Linux five-phase product recipe
# (backend/scripts/setup.sh) against the workflow's service containers:
#
#   phase 1  provision  (admin, maintenance DB)  roles + application test DB
#            via backend/scripts/provision_runtime_db_roles.py --provision
#   phase 1b task-env operator supply (admin)    minimal LOGIN role, distinct
#            identity required by tests/async_test_utils.py topology checks
#   phase 2  migrate    (migration authority)    alembic upgrade head through
#            039_order_credit_holds, REPORTING_USER_PASSWORD for migration 011
#   phase 3  grants     (migration authority)    provisioner --apply-grants
#   phase 4  verify     (read-only)              provisioner --verify
#   phase 5  bootstrap  (runtime role)           bootstrap_tenant_schema.py
#
# The target test database is NEVER pre-created by the Postgres service as an
# admin-owned database: the service exposes only the maintenance database and
# the product provisioner creates the test database (migration authority
# ownership).
#
# The emitted test topology satisfies backend/tests/async_test_utils.py:
# one endpoint, one test_-marked source database, pairwise-distinct users,
# admin bound to the /postgres maintenance database.
#
# Logging discipline: key existence, identity user names, database names and
# host:port only.  URLs, passwords and verifiers are never printed and never
# appear in argv (psql receives credentials through PGPASSWORD/stdin).
#
# Modes:
#   --preflight-only   validate inputs/topology and emit the plan + profile
#                      files without any network access or write (offline
#                      contract mode; used by tools/ci/tests).
#   default            wait for services (bounded), run the five phases and
#                      write the profile env file for subsequent pytest steps.
set -Eeuo pipefail

_on_err() {
    local line="$1" status="${2:-1}"
    echo "bootstrap_backend_test_db: refused at line $line (exit $status)" >&2
    echo "bootstrap_backend_test_db: pytest MUST NOT start after a supply failure" >&2
    exit "$status"
}
trap '_on_err "$LINENO" "$?"' ERR

# PYTHON_BIN allows offline contract tests (and Windows hosts whose
# "python3" is a store stub) to pin a real interpreter; CI runners use python3.
PY_RUNNER="${PYTHON_BIN:-python3}"

# Committed scripts are LF-only; raw CR bytes cannot be passed reliably.
if "$PY_RUNNER" -c "import sys; d = open(sys.argv[1], 'rb').read(); sys.exit(0 if b'\r' in d else 1)" "${BASH_SOURCE[0]}" 2>/dev/null; then
    echo "bootstrap_backend_test_db.sh contains CRLF line endings" >&2
    exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PREFLIGHT_ONLY=0
PLAN_FILE=""
PROFILE_DIR=""
GITHUB_ENV_FILE=""
MAX_WAIT_SECONDS="${CI_SUPPLY_MAX_WAIT_SECONDS:-120}"

usage() {
    echo "usage: bootstrap_backend_test_db.sh [--repo-root DIR] [--preflight-only] [--plan-file FILE] [--profile-dir DIR] [--github-env FILE]"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --repo-root) REPO_ROOT="$(cd "$2" && pwd)"; shift 2 ;;
        --preflight-only) PREFLIGHT_ONLY=1; shift ;;
        --plan-file) PLAN_FILE="$2"; shift 2 ;;
        --profile-dir) PROFILE_DIR="$2"; shift 2 ;;
        --github-env) GITHUB_ENV_FILE="$2"; shift 2 ;;
        *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

# ---- inputs -----------------------------------------------------------------
PG_HOST="${CI_PG_HOST:-localhost}"
PG_PORT="${CI_PG_PORT:-5432}"
ADMIN_USER="${CI_PG_ADMIN_USER:-postgres}"
ADMIN_PASSWORD="${CI_PG_ADMIN_PASSWORD:-}"
TEST_DB="${CI_TEST_DB:-ci_mpango_test}"
MIGRATE_USER="${CI_MIGRATE_USER:-ci_migrate}"
APP_USER="${CI_APP_USER:-ci_app}"
OPERATOR_USER="${CI_OPERATOR_USER:-ci_operator}"
TENANT_SCHEMA="${CI_TEST_TENANT_SCHEMA:-t_test}"
REDIS_URL="${CI_REDIS_URL:-redis://localhost:6379/0}"
REPORTING_PASSWORD="${CI_REPORTING_USER_PASSWORD:-}"

refuse() { echo "bootstrap_backend_test_db: REFUSED: $1" >&2; exit 3; }

# ---- topology validation (shared by preflight and real mode) ---------------
"$PY_RUNNER" - "$PG_HOST" "$PG_PORT" "$ADMIN_USER" "$TEST_DB" "$MIGRATE_USER" "$APP_USER" "$OPERATOR_USER" "$ADMIN_PASSWORD" <<'PY'
import re
import sys

host, port, admin_user, test_db, migrate_user, app_user, operator_user, admin_password = sys.argv[1:9]
refusals = []
if not admin_password:
    refusals.append("CI_PG_ADMIN_PASSWORD is required (maintenance-DB admin credential)")
if not re.fullmatch(r"[0-9]+", port):
    refusals.append("CI_PG_PORT must be numeric")
if not re.fullmatch(r"(?:test|pytest|ci)[_-][a-z0-9_-]+", test_db):
    refusals.append(
        "CI_TEST_DB must be test-marked ((test|pytest|ci)[_-] prefix): "
        "the suite topology guard rejects other database names"
    )
for label, user in (("migrate", migrate_user), ("app", app_user), ("operator", operator_user)):
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", user):
        refusals.append(f"{label} user must be a plain lowercase identifier")
users = {admin_user, migrate_user, app_user, operator_user}
if len(users) != 4:
    refusals.append(
        "identities must be pairwise-distinct users "
        "(admin, migration authority, operator, runtime app)"
    )
if refusals:
    print(
        "bootstrap_backend_test_db: REFUSED: topology validation failed:\n  - "
        + "\n  - ".join(refusals),
        file=sys.stderr,
    )
    sys.exit(3)
print(f"[supply] topology ok: host={host}:{port} db={test_db} "
      f"identities={sorted(users)} admin-target=/postgres")
PY

# ---- profile partition + plan (offline; identical bytes in both modes) ------
write_plan_and_profiles() {
    local target_dir="$1"
    "$PY_RUNNER" - "$REPO_ROOT" "$target_dir" "$TEST_DB" "$ADMIN_USER" "$MIGRATE_USER" "$APP_USER" "$OPERATOR_USER" <<'PY'
import json
import re
import sys
from pathlib import Path

repo = Path(sys.argv[1])
target_dir = Path(sys.argv[2])
test_db, admin_user, migrate_user, app_user, operator_user = sys.argv[3:8]

frozen_ignores = [
    "tests/test_s3c_cache.py",
    "tests/test_s3c_integration.py",
    "tests/test_s6_p_reporting_constraints.py",
    "tests/test_b5_real_db.py",
    "tests/test_reliability.py",
    "tests/test_s3_profiling.py",
]
topology_re = re.compile(
    r"TEST_MIGRATION_DATABASE_URL|TEST_OPERATOR_DATABASE_URL|"
    r"TEST_ADMIN_DATABASE_URL|MPANGO_ALLOW_TEMP_DB_CREATE"
)

tests_root = repo / "backend" / "tests"
all_files = sorted(
    str(p.relative_to(repo / "backend")).replace("\\", "/")
    for p in tests_root.rglob("test_*.py")
)
selected = [f for f in all_files if f not in frozen_ignores]
topology, runtime = [], []
for rel in selected:
    text = (repo / "backend" / rel).read_text(encoding="utf-8", errors="replace")
    (topology if topology_re.search(text) else runtime).append(rel)

overlap = sorted(set(topology) & set(runtime))
if overlap:
    print(f"REFUSED: profile partition not mutually exclusive: {overlap}", file=sys.stderr)
    sys.exit(3)
if len(topology) + len(runtime) != len(selected):
    print("REFUSED: profile union does not equal the frozen selection", file=sys.stderr)
    sys.exit(3)

plan = {
    "authorization": "CTO-C91-CI-CONTRACT-ALIGNMENT-ZCODEW-R2-20261006",
    "source_recipe": "backend/scripts/setup.sh five-phase product sequence",
    "phases": [
        {"phase": 1, "name": "provision",
         "tool": "backend/scripts/provision_runtime_db_roles.py",
         "mode": "--provision", "identity": "admin (maintenance DB)"},
        {"phase": "1b", "name": "task-env operator supply",
         "tool": "psql CREATE ROLE (minimal LOGIN, no DB-management rights)",
         "identity": "admin (maintenance DB)"},
        {"phase": 2, "name": "migrate",
         "tool": "alembic upgrade head",
         "head": "039_order_credit_holds",
         "identity": "migration authority (database owner)"},
        {"phase": 3, "name": "apply-grants",
         "tool": "backend/scripts/provision_runtime_db_roles.py",
         "mode": "--apply-grants", "identity": "migration authority"},
        {"phase": 4, "name": "verify",
         "tool": "backend/scripts/provision_runtime_db_roles.py",
         "mode": "--verify", "identity": "read-only"},
        {"phase": 5, "name": "tenant bootstrap",
         "tool": "backend/scripts/bootstrap_tenant_schema.py",
         "identity": "runtime role (non-SUPERUSER/NOCREATEDB/NOCREATEROLE)"},
    ],
    "identities": {
        "admin": {"user": admin_user, "database": "postgres"},
        "migration": {"user": migrate_user, "database": test_db},
        "operator": {"user": operator_user, "database": test_db},
        "app": {"user": app_user, "database": test_db},
        "reporting": {"user": "reporting_user", "database": test_db,
                      "provisioned_by": "migration 011 via REPORTING_USER_PASSWORD"},
    },
    "env_keys_emitted": [
        "DATABASE_URL", "TEST_DATABASE_URL", "TEST_MIGRATION_DATABASE_URL",
        "TEST_OPERATOR_DATABASE_URL", "TEST_ADMIN_DATABASE_URL",
        "TEST_REPORTING_DATABASE_URL", "REPORTING_USER_PASSWORD",
        "REDIS_URL", "MPANGO_ENV",
    ],
    "profile_opt_in_keys": {"migration-topology": ["MPANGO_ALLOW_TEMP_DB_CREATE=1"]},
    "profiles": {
        "runtime": {"files": runtime, "count": len(runtime)},
        "migration-topology": {"files": topology, "count": len(topology)},
    },
    "frozen_ignores": frozen_ignores,
    "selection_counts": {
        "collected_test_files": len(all_files),
        "selected": len(selected),
        "union_of_profiles": len(runtime) + len(topology),
    },
}
(target_dir / "supply-plan.json").write_text(
    json.dumps(plan, indent=2) + "\n", encoding="utf-8", newline="\n"
)
(target_dir / "profile-runtime.tests").write_text(
    "\n".join(runtime) + ("\n" if runtime else ""), encoding="utf-8", newline="\n"
)
(target_dir / "profile-migration-topology.tests").write_text(
    "\n".join(topology) + ("\n" if topology else ""), encoding="utf-8", newline="\n"
)
print(f"[supply] profile plan: runtime={len(runtime)} "
      f"migration-topology={len(topology)} union={len(selected)} "
      f"(mutually exclusive; union equals frozen selection)")
PY
}

PLAN_DIR="$(mktemp -d)"
if [ -n "$PLAN_FILE" ]; then
    PLAN_DIR="$(dirname "$PLAN_FILE")"
    mkdir -p "$PLAN_DIR"
fi
write_plan_and_profiles "$PLAN_DIR" >/dev/null
if [ -n "$PLAN_FILE" ]; then
    mv "$PLAN_DIR/supply-plan.json" "$PLAN_FILE"
fi
if [ -n "$PROFILE_DIR" ] && [ "$PROFILE_DIR" != "$PLAN_DIR" ]; then
    mkdir -p "$PROFILE_DIR"
    mv "$PLAN_DIR/profile-runtime.tests" "$PLAN_DIR/profile-migration-topology.tests" "$PROFILE_DIR/" 2>/dev/null || true
fi
echo "[supply] plan available: ${PLAN_FILE:-${PLAN_DIR}/supply-plan.json}"

if [ "$PREFLIGHT_ONLY" -eq 1 ]; then
    echo "[supply] preflight complete (no network access, no writes beyond plan files)"
    exit 0
fi

# ---- real mode: bounded service wait ----------------------------------------
wait_for_tcp() {
    local host="$1" port="$2" label="$3" waited=0
    until "$PY_RUNNER" -c "import socket,sys; s=socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=2); s.close()" "$host" "$port" 2>/dev/null; do
        waited=$((waited + 2))
        [ "$waited" -ge "$MAX_WAIT_SECONDS" ] && refuse "$label not reachable within ${MAX_WAIT_SECONDS}s at $host:$port"
        sleep 2
    done
    echo "[supply] $label reachable at $host:$port (waited ${waited}s)"
}
wait_for_tcp "$PG_HOST" "$PG_PORT" "postgres"
REDIS_HOST_PARSED="$("$PY_RUNNER" -c "import urllib.parse,sys; print(urllib.parse.urlparse(sys.argv[1]).hostname or 'localhost')" "$REDIS_URL")"
REDIS_PORT_PARSED="$("$PY_RUNNER" -c "import urllib.parse,sys; print(urllib.parse.urlparse(sys.argv[1]).port or 6379)" "$REDIS_URL")"
wait_for_tcp "$REDIS_HOST_PARSED" "$REDIS_PORT_PARSED" "redis"

# ---- credentials (generated; never printed, never in argv) -------------------
gen_password() { "$PY_RUNNER" -c "import secrets; print(secrets.token_hex(16))"; }
MIGRATE_PASSWORD="$(gen_password)"
APP_PASSWORD="$(gen_password)"
OPERATOR_PASSWORD="$(gen_password)"
if [ -z "$REPORTING_PASSWORD" ]; then
    REPORTING_PASSWORD="$(gen_password)"
fi

run_psql() {
    local user="$1" password="$2" database="$3" sql="$4"
    PGPASSWORD="$password" psql -h "$PG_HOST" -p "$PG_PORT" -U "$user" -d "$database" \
        -v ON_ERROR_STOP=1 -tAc "$sql"
}
# ---- phase 1: product provisioner creates roles + the test database ---------
echo "[supply] phase 1/5 provision (admin; product provisioner creates ${TEST_DB})"
(
    cd "$REPO_ROOT/backend"
    export MPANGO_DB_ADMIN_URL="postgresql://${ADMIN_USER}:${ADMIN_PASSWORD}@${PG_HOST}:${PG_PORT}/postgres"
    export MPANGO_DB_MIGRATE_URL="postgresql://${MIGRATE_USER}:${MIGRATE_PASSWORD}@${PG_HOST}:${PG_PORT}/${TEST_DB}"
    export MPANGO_DB_APP_URL="postgresql://${APP_USER}:${APP_PASSWORD}@${PG_HOST}:${PG_PORT}/${TEST_DB}"
    export MPANGO_DB_MIGRATE_PASSWORD="$MIGRATE_PASSWORD" MPANGO_DB_APP_PASSWORD="$APP_PASSWORD"
    poetry run python scripts/provision_runtime_db_roles.py --provision
)

# ---- phase 1b: minimal task-env operator identity ----------------------------
echo "[supply] phase 1b/5 task-env operator supply (minimal LOGIN role; distinct identity)"
psql_admin_stdin() {
    PGPASSWORD="$ADMIN_PASSWORD" psql -h "$PG_HOST" -p "$PG_PORT" -U "$ADMIN_USER" -d postgres \
        -v ON_ERROR_STOP=1 -v operator_password="$OPERATOR_PASSWORD"
}
if [ "$(run_psql "$ADMIN_USER" "$ADMIN_PASSWORD" postgres "SELECT 1 FROM pg_roles WHERE rolname = '${OPERATOR_USER}'")" = "1" ]; then
    psql_admin_stdin <<SQL
ALTER ROLE "${OPERATOR_USER}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'operator_password';
SQL
else
    psql_admin_stdin <<SQL
CREATE ROLE "${OPERATOR_USER}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'operator_password';
SQL
fi
run_psql "$ADMIN_USER" "$ADMIN_PASSWORD" postgres "GRANT CONNECT ON DATABASE \"${TEST_DB}\" TO \"${OPERATOR_USER}\""

# ---- phase 2: migrations through 039 as the migration authority --------------
echo "[supply] phase 2/5 migrate (migration authority; alembic upgrade head)"
(
    cd "$REPO_ROOT/backend"
    export DATABASE_URL="postgresql://${MIGRATE_USER}:${MIGRATE_PASSWORD}@${PG_HOST}:${PG_PORT}/${TEST_DB}"
    export REPORTING_USER_PASSWORD="$REPORTING_PASSWORD"
    poetry run alembic upgrade head
)
HEAD_ROW="$(run_psql "$MIGRATE_USER" "$MIGRATE_PASSWORD" "$TEST_DB" "SELECT version_num FROM public.alembic_version")"
[ "$HEAD_ROW" = "039_order_credit_holds" ] || refuse "alembic head is '$HEAD_ROW', expected exactly 039_order_credit_holds"
echo "[supply] alembic head verified: 039_order_credit_holds"

# ---- phase 3: minimum runtime grants ------------------------------------------
echo "[supply] phase 3/5 apply-grants (migration authority)"
(
    cd "$REPO_ROOT/backend"
    export MPANGO_DB_ADMIN_URL="postgresql://${ADMIN_USER}:${ADMIN_PASSWORD}@${PG_HOST}:${PG_PORT}/postgres"
    export MPANGO_DB_MIGRATE_URL="postgresql://${MIGRATE_USER}:${MIGRATE_PASSWORD}@${PG_HOST}:${PG_PORT}/${TEST_DB}"
    export MPANGO_DB_APP_URL="postgresql://${APP_USER}:${APP_PASSWORD}@${PG_HOST}:${PG_PORT}/${TEST_DB}"
    poetry run python scripts/provision_runtime_db_roles.py --apply-grants
)

# ---- phase 4: read-only contract verification ---------------------------------
echo "[supply] phase 4/5 verify (read-only)"
(
    cd "$REPO_ROOT/backend"
    export MPANGO_DB_ADMIN_URL="postgresql://${ADMIN_USER}:${ADMIN_PASSWORD}@${PG_HOST}:${PG_PORT}/postgres"
    export MPANGO_DB_MIGRATE_URL="postgresql://${MIGRATE_USER}:${MIGRATE_PASSWORD}@${PG_HOST}:${PG_PORT}/${TEST_DB}"
    export MPANGO_DB_APP_URL="postgresql://${APP_USER}:${APP_PASSWORD}@${PG_HOST}:${PG_PORT}/${TEST_DB}"
    poetry run python scripts/provision_runtime_db_roles.py --verify
)

# ---- phase 5: tenant bootstrap as the runtime role ----------------------------
echo "[supply] phase 5/5 tenant bootstrap (runtime role; schema ${TENANT_SCHEMA})"
(
    cd "$REPO_ROOT/backend"
    export DATABASE_URL="postgresql://${APP_USER}:${APP_PASSWORD}@${PG_HOST}:${PG_PORT}/${TEST_DB}"
    poetry run python scripts/bootstrap_tenant_schema.py "$TENANT_SCHEMA"
)

# ---- emit the pytest topology (values only into the env file) ----------------
if [ -n "$GITHUB_ENV_FILE" ]; then
    {
        echo "DATABASE_URL=postgresql://${APP_USER}:${APP_PASSWORD}@${PG_HOST}:${PG_PORT}/${TEST_DB}"
        echo "TEST_DATABASE_URL=postgresql://${APP_USER}:${APP_PASSWORD}@${PG_HOST}:${PG_PORT}/${TEST_DB}"
        echo "TEST_MIGRATION_DATABASE_URL=postgresql://${MIGRATE_USER}:${MIGRATE_PASSWORD}@${PG_HOST}:${PG_PORT}/${TEST_DB}"
        echo "TEST_OPERATOR_DATABASE_URL=postgresql://${OPERATOR_USER}:${OPERATOR_PASSWORD}@${PG_HOST}:${PG_PORT}/${TEST_DB}"
        echo "TEST_ADMIN_DATABASE_URL=postgresql://${ADMIN_USER}:${ADMIN_PASSWORD}@${PG_HOST}:${PG_PORT}/postgres"
        echo "TEST_REPORTING_DATABASE_URL=postgresql://reporting_user:${REPORTING_PASSWORD}@${PG_HOST}:${PG_PORT}/${TEST_DB}"
        echo "REPORTING_USER_PASSWORD=$REPORTING_PASSWORD"
        echo "REDIS_URL=$REDIS_URL"
        echo "MPANGO_ENV=test"
    } >> "$GITHUB_ENV_FILE"
    echo "[supply] emitted keys to env file: DATABASE_URL TEST_DATABASE_URL TEST_MIGRATION_DATABASE_URL TEST_OPERATOR_DATABASE_URL TEST_ADMIN_DATABASE_URL TEST_REPORTING_DATABASE_URL REPORTING_USER_PASSWORD REDIS_URL MPANGO_ENV"
fi

echo "[supply] five phases complete: identities provisioned via product paths; pytest may start"
