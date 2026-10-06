#!/usr/bin/env bash
# CI test-database supply for the Deploy Staging backend test job (R3).
#
# CTO-C91-CI-EXECUTABLE-CONTRACT-ZCODEW-R3-20261006
#
# Reproduces the verified Linux five-phase product recipe
# (backend/scripts/setup.sh, backend/tests/task_owned_pg_resources.py)
# against a task-owned PG16/Redis7 pair:
#
#   phase 1  provision  (admin, maintenance DB)  mpango_migrate/mpango_app
#            roles + application test DB via provision_runtime_db_roles.py
#   phase 1b task operator supply (admin)       ci_r3_operator: LOGIN +
#            CREATEDB/CREATEROLE (task-exclusive authorization) and a
#            non-inherited, SET-only grant to the migration owner
#   phase 1c pgcrypto pre-install (admin, task DB, before/after catalog
#            facts) — tests need it; app never gains public CREATE
#   phase 2  migrate    (migration authority)    alembic through exactly
#            039_order_credit_holds + REPORTING_USER_PASSWORD (migration 011)
#   phase 3  grants     (migration authority)    provisioner --apply-grants
#   phase 4  verify     (read-only)              provisioner --verify
#   phase 4b read-only capability probe          operator attributes and
#            SET-only membership facts from the live catalog
#   phase 5  bootstrap  (runtime role)           bootstrap_tenant_schema.py
#
# Credential discipline (R3 §3): secrets travel ONLY via environment or
# private stdin. No Python argv secrets, no `psql -v`, no `-c` SQL carrying
# a secret; role DDL is piped through stdin and EVERY tool's output is
# filtered through a small local redactor so a failing statement can never
# echo a password. Runtime passwords and full DSNs are registered with
# ::add-mask:: before any possible output. No `set -x`, no env dumps.
#
# The emitted test topology satisfies backend/tests/async_test_utils.py and
# the R0 invariants guards: one endpoint, one test-marked source database,
# pairwise-distinct identities (mpango_app / mpango_migrate /
# ci_r3_operator / container admin), admin bound to the maintenance
# database, container facts (exact IDs, owner label, loopback mapping)
# declared for the ownership guard when provided.
#
# Outputs:
#   --plan-file FILE   supply plan + profile partition (JSON)
#   --profile-dir DIR  per-profile pytest argfiles
#   --env-file FILE    versioned environment build for test processes (0600)
#   --github-env FILE  append the same keys to a GitHub env file
set -Eeuo pipefail

_on_err() {
    local line="$1" status="${2:-1}"
    echo "bootstrap_backend_test_db: refused at line $line (exit $status)" >&2
    echo "bootstrap_backend_test_db: pytest MUST NOT start after a supply failure" >&2
    exit "$status"
}
trap '_on_err "$LINENO" "$?"' ERR

# PYTHON_BIN allows offline contract tests (and Windows hosts whose
# "python3" is a store stub) to pin a real interpreter; CI uses python3.
PY_RUNNER="${PYTHON_BIN:-python3}"

if "$PY_RUNNER" -c "import sys; d = open(sys.argv[1], 'rb').read(); sys.exit(0 if b'\r' in d else 1)" "${BASH_SOURCE[0]}" 2>/dev/null; then
    echo "bootstrap_backend_test_db.sh contains CRLF line endings" >&2
    exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PREFLIGHT_ONLY=0
PLAN_FILE=""
PROFILE_DIR=""
ENV_FILE=""
GITHUB_ENV_FILE=""
MAX_WAIT_SECONDS="${CI_SUPPLY_MAX_WAIT_SECONDS:-120}"

usage() {
    echo "usage: bootstrap_backend_test_db.sh [--repo-root DIR] [--preflight-only] [--plan-file FILE] [--profile-dir DIR] [--env-file FILE] [--github-env FILE]"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --repo-root) REPO_ROOT="$(cd "$2" && pwd)"; shift 2 ;;
        --preflight-only) PREFLIGHT_ONLY=1; shift ;;
        --plan-file) PLAN_FILE="$2"; shift 2 ;;
        --profile-dir) PROFILE_DIR="$2"; shift 2 ;;
        --env-file) ENV_FILE="$2"; shift 2 ;;
        --github-env) GITHUB_ENV_FILE="$2"; shift 2 ;;
        *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

# ---- inputs -----------------------------------------------------------------
PG_HOST="${CI_PG_HOST:-localhost}"
PG_PORT="${CI_PG_PORT:-5432}"
ADMIN_USER="${CI_PG_ADMIN_USER:-postgres}"
ADMIN_PASSWORD="${CI_PG_ADMIN_PASSWORD:-}"
TEST_DB="${CI_TEST_DB:-test_ci_mpango}"
MIGRATE_USER="${CI_MIGRATE_USER:-mpango_migrate}"
APP_USER="${CI_APP_USER:-mpango_app}"
OPERATOR_USER="${CI_OPERATOR_USER:-ci_r3_operator}"
TENANT_SCHEMA="${CI_TEST_TENANT_SCHEMA:-t_test}"
REDIS_URL="${CI_REDIS_URL:-redis://localhost:6379/0}"
PW1R3_REDIS_URL="${PW1R3_TEST_REDIS_URL:-}"
PG_CONTAINER_ID="${CI_PG_CONTAINER_ID:-}"
REDIS_CONTAINER_ID="${CI_REDIS_CONTAINER_ID:-}"
OWNER_LABEL="${CI_OWNER_LABEL:-}"
SKIP_SERVICE_WAIT="${CI_SUPPLY_SKIP_SERVICE_WAIT:-0}"
# Task-scoped credential store: re-running the supply against an already
# provisioned task cluster MUST reuse the original role passwords (the
# product provisioner refuses re-provisioning with non-connectable URLs).
CREDS_FILE="${CI_CREDENTIALS_FILE:-}"

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
if migrate_user != "mpango_migrate" or app_user != "mpango_app":
    refusals.append(
        "R3 contract: the verified recipe role names mpango_migrate/mpango_app "
        "are required (suite consumers hardcode them); arbitrary renames refused"
    )
users = {admin_user, migrate_user, app_user, operator_user}
if len(users) != 4:
    refusals.append(
        "identities must be pairwise-distinct users "
        "(admin, migration authority, operator, runtime app)"
    )
if operator_user.startswith("mpango"):
    refusals.append("the task operator must not borrow the product mpango_* namespace")
if refusals:
    print(
        "bootstrap_backend_test_db: REFUSED: topology validation failed:\n  - "
        + "\n  - ".join(refusals),
        file=sys.stderr,
    )
    sys.exit(3)
print(f"[supply] topology ok: host={host}:{port} db={test_db} "
      f"identities={sorted(users)} admin-target=/postgres "
      f"roles: migrate={migrate_user} app={app_user} operator={operator_user}")
PY

# ---- plan + AST-import profile partition (offline; both modes) --------------
if [ -z "$PLAN_FILE" ] && [ -z "$PROFILE_DIR" ]; then
    PLAN_FILE="$(mktemp -d)/supply-plan.json"
fi
if [ -z "$PROFILE_DIR" ]; then
    PROFILE_DIR="$(dirname "$PLAN_FILE")"
fi
mkdir -p "$PROFILE_DIR" "$(dirname "$PLAN_FILE")"

"$PY_RUNNER" - "$REPO_ROOT" "$PLAN_FILE" "$PROFILE_DIR" "$TEST_DB" "$ADMIN_USER" "$MIGRATE_USER" "$APP_USER" "$OPERATOR_USER" "$PG_CONTAINER_ID" "$REDIS_CONTAINER_ID" "$OWNER_LABEL" <<'PY'
import ast
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1])
plan_path = Path(sys.argv[2])
profile_dir = Path(sys.argv[3])
test_db, admin_user, migrate_user, app_user, operator_user = sys.argv[4:9]
pg_container, redis_container, owner_label = sys.argv[9:12]

frozen_ignores = [
    "tests/test_s3c_cache.py",
    "tests/test_s3c_integration.py",
    "tests/test_s6_p_reporting_constraints.py",
    "tests/test_b5_real_db.py",
    "tests/test_reliability.py",
    "tests/test_s3_profiling.py",
]
TOPOLOGY_KEYS = {
    "TEST_MIGRATION_DATABASE_URL",
    "TEST_OPERATOR_DATABASE_URL",
    "TEST_ADMIN_DATABASE_URL",
    "MPANGO_ALLOW_TEMP_DB_CREATE",
}
TOPOLOGY_MODULES = {"async_test_utils"}
INVARIANTS_MODULES = {"mpango_invariants_r0_support"}
TASKMANAGED_MODULES = {"task_owned_pg_resources"}
PROFILE_ORDER = ["task-managed-pg", "topology", "invariants-jwt", "runtime"]
PROFILE_ENV = {
    "runtime": [],
    "topology": ["MPANGO_ALLOW_TEMP_DB_CREATE=1"],
    "invariants-jwt": ["MPANGO_ENV=staging (real JwtAuthStrategy)"],
    "task-managed-pg": ["C91_R3_RESOURCE_ROOT (0700 private root)"],
}

tests_root = repo / "backend" / "tests"
if not tests_root.is_dir():
    print("REFUSED: backend/tests source directory is missing; no profile plan may claim a selection", file=sys.stderr)
    sys.exit(3)


def classify(source):
    """Structural classification: module-level imports plus module-level
    os.environ constant references (AST nodes — never substring matching)."""
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[-1])
        elif isinstance(node, ast.Import):
            imported.update(a.name.split(".")[-1] for a in node.names)
    env_keys = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in {"get", "getenv", "pop", "setdefault"}):
            continue
        receiver = func.value
        ok = (isinstance(receiver, ast.Name) and receiver.id in {"environ", "os"}) or (
            isinstance(receiver, ast.Attribute) and receiver.attr == "environ"
        )
        if not ok:
            continue
        for arg in node.args[:1]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                env_keys.add(arg.value)
    markers = []
    if imported & TASKMANAGED_MODULES:
        markers.append("task-managed-pg")
    if (imported & TOPOLOGY_MODULES) or (env_keys & TOPOLOGY_KEYS):
        markers.append("topology")
    if imported & INVARIANTS_MODULES:
        markers.append("invariants-jwt")
    if not markers:
        return "runtime", []
    for profile in PROFILE_ORDER[:-1]:
        if profile in markers:
            return profile, markers


all_files = sorted(
    str(p.relative_to(repo / "backend")).replace("\\", "/")
    for p in tests_root.rglob("test_*.py")
)
selected = [f for f in all_files if f not in frozen_ignores]
if not selected:
    print("REFUSED: empty selection (no test_*.py remain after the frozen ignores); refusing to emit a zero-test plan", file=sys.stderr)
    sys.exit(3)

partition = {p: [] for p in PROFILE_ORDER}
mixed = {}
for rel in selected:
    source = (repo / "backend" / rel).read_text(encoding="utf-8", errors="replace")
    try:
        profile, markers = classify(source)
    except SyntaxError:
        print(f"REFUSED: {rel} does not parse; profiles may not classify an unparseable selection", file=sys.stderr)
        sys.exit(3)
    partition[profile].append(rel)
    if markers:
        mixed[rel] = markers

if sum(len(v) for v in partition.values()) != len(selected):
    print("REFUSED: profile partition is not an exact partition of the frozen selection", file=sys.stderr)
    sys.exit(3)

plan = {
    "authorization": "CTO-C91-CI-EXECUTABLE-CONTRACT-ZCODEW-R3-20261006",
    "classifier": "AST module imports + module-level os.environ constant references (structural; no substring keyword matching)",
    "source_recipe": "backend/scripts/setup.sh + backend/tests/task_owned_pg_resources.py",
    "container_facts": {
        "pg_container_id_declared": bool(pg_container),
        "redis_container_id_declared": bool(redis_container),
        "owner_label": owner_label,
        "note": "container facts are verified live via docker inspect when declared; the R0 ownership guard proves the provisioned target through read-only connections",
    },
    "phases": [
        {"phase": 1, "name": "provision", "tool": "backend/scripts/provision_runtime_db_roles.py", "mode": "--provision", "identity": "admin (maintenance DB)", "roles": [migrate_user, app_user]},
        {"phase": "1b", "name": "task operator supply", "tool": "psql via private stdin", "identity": "admin (maintenance DB)", "grants": ["LOGIN", "CREATEDB (task authorization)", "CREATEROLE (task authorization)", "SET-only membership of " + migrate_user + " (non-inheriting)"]},
        {"phase": "1c", "name": "pgcrypto pre-install", "tool": "psql admin on task DB", "identity": "admin", "evidence": "before/after pg_extension catalog facts"},
        {"phase": 2, "name": "migrate", "tool": "alembic upgrade head", "head": "039_order_credit_holds", "identity": "migration authority (database owner)"},
        {"phase": 3, "name": "apply-grants", "tool": "backend/scripts/provision_runtime_db_roles.py", "mode": "--apply-grants", "identity": "migration authority"},
        {"phase": 4, "name": "verify", "tool": "backend/scripts/provision_runtime_db_roles.py", "mode": "--verify", "identity": "read-only"},
        {"phase": "4b", "name": "capability probe", "tool": "read-only catalog SELECTs", "checks": ["operator rolcreatedb/rolcreaterole true, rolsuper/rolinherit false", "SET-only membership (set_option true, inherit_option false)"]},
        {"phase": 5, "name": "tenant bootstrap", "tool": "backend/scripts/bootstrap_tenant_schema.py", "identity": "runtime role (non-SUPERUSER/NOCREATEDB/NOCREATEROLE)"},
    ],
    "identities": {
        "admin": {"user": admin_user, "database": "postgres"},
        "migration": {"user": migrate_user, "database": test_db},
        "operator": {"user": operator_user, "database": test_db,
                     "authorization": "task-exclusive CREATEDB/CREATEROLE + SET-only to migration owner; never a data source, never SUPERUSER"},
        "app": {"user": app_user, "database": test_db},
        "reporting": {"user": "reporting_user", "database": test_db, "provisioned_by": "migration 011 via REPORTING_USER_PASSWORD"},
    },
    "env_keys_emitted": [
        "DATABASE_URL", "TEST_DATABASE_URL", "TEST_MIGRATION_DATABASE_URL",
        "TEST_OPERATOR_DATABASE_URL", "TEST_ADMIN_DATABASE_URL",
        "TEST_REPORTING_DATABASE_URL", "REPORTING_USER_PASSWORD",
        "REDIS_URL", "PW1R3_TEST_REDIS_URL", "MPANGO_ENV", "SECRET_KEY",
        "MPANGO_INVARIANTS_R0_PG_CONTAINER", "MPANGO_INVARIANTS_R0_PG_OWNER",
        "MPANGO_INVARIANTS_R0_REDIS_CONTAINER",
        "MPANGO_INVARIANTS_R0_MIGRATION_DATABASE_URL",
        "MPANGO_INVARIANTS_R0_ADMIN_DATABASE_URL",
    ],
    "profile_extra_env": PROFILE_ENV,
    "profiles": {p: {"files": partition[p], "count": len(partition[p])} for p in PROFILE_ORDER},
    "mixed_premise_files": mixed,
    "frozen_ignores": frozen_ignores,
    "selection_counts": {
        "collected_test_files": len(all_files),
        "selected": len(selected),
        "partition_total": sum(len(v) for v in partition.values()),
    },
}
plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8", newline="\n")
for profile in PROFILE_ORDER:
    body = "\n".join(partition[profile]) + ("\n" if partition[profile] else "")
    (profile_dir / f"profile-{profile}.tests").write_text(body, encoding="utf-8", newline="\n")
print("[supply] plan: " + ", ".join(f"{p}={len(partition[p])}" for p in PROFILE_ORDER)
      + f"; mixed-premise files disclosed: {len(mixed)}; selection={len(selected)}")
PY

echo "[supply] plan written: $PLAN_FILE; profiles in: $PROFILE_DIR"

if [ "$PREFLIGHT_ONLY" -eq 1 ]; then
    echo "[supply] preflight complete (no network access, no writes beyond plan/profile files)"
    exit 0
fi

# ---- real mode ---------------------------------------------------------------
wait_for_tcp() {
    local host="$1" port="$2" label="$3" waited=0
    until "$PY_RUNNER" -c "import socket,sys; s=socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=2); s.close()" "$host" "$port" 2>/dev/null; do
        waited=$((waited + 2))
        [ "$waited" -ge "$MAX_WAIT_SECONDS" ] && refuse "$label not reachable within ${MAX_WAIT_SECONDS}s at $host:$port"
        sleep 2
    done
    echo "[supply] $label reachable at $host:$port (waited ${waited}s)"
}
if [ "$SKIP_SERVICE_WAIT" != "1" ]; then
    wait_for_tcp "$PG_HOST" "$PG_PORT" "postgres"
    REDIS_HOST_PARSED="$("$PY_RUNNER" -c "import urllib.parse,sys; print(urllib.parse.urlparse(sys.argv[1]).hostname or 'localhost')" "$REDIS_URL")"
    REDIS_PORT_PARSED="$("$PY_RUNNER" -c "import urllib.parse,sys; print(urllib.parse.urlparse(sys.argv[1]).port or 6379)" "$REDIS_URL")"
    wait_for_tcp "$REDIS_HOST_PARSED" "$REDIS_PORT_PARSED" "redis"
fi

if [ -n "$PG_CONTAINER_ID" ] && command -v docker >/dev/null 2>&1; then
    FACT="$(docker inspect --format '{{.Config.Image}}|{{index .Config.Labels "mpango.owner"}}' "$PG_CONTAINER_ID")"
    case "$FACT" in
        postgres:16*) echo "[supply] PG container fact verified: $PG_CONTAINER_ID ($FACT |label|)" ;;
        *) refuse "declared PG container $PG_CONTAINER_ID is not postgres:16 (fact: $FACT)" ;;
    esac
fi

gen_password() { "$PY_RUNNER" -c "import secrets; print(secrets.token_hex(16))"; }
load_or_gen() {
    local key="$1" value=""
    if [ -n "$CREDS_FILE" ] && [ -f "$CREDS_FILE" ]; then
        value="$(grep -m1 "^${key}=" "$CREDS_FILE" | cut -d= -f2- || true)"
    fi
    if [ -z "$value" ]; then
        value="$(gen_password)"
    fi
    printf '%s' "$value"
}
MIGRATE_PASSWORD="$(load_or_gen MIGRATE_PASSWORD)"
APP_PASSWORD="$(load_or_gen APP_PASSWORD)"
OPERATOR_PASSWORD="$(load_or_gen OPERATOR_PASSWORD)"
REPORTING_PASSWORD="${CI_REPORTING_USER_PASSWORD:-}"
if [ -z "$REPORTING_PASSWORD" ]; then
    REPORTING_PASSWORD="$(load_or_gen REPORTING_PASSWORD)"
fi
SECRET_KEY="$("$PY_RUNNER" - <<'PYKEY'
import secrets
while True:
    key = secrets.token_hex(32)
    if not any(weak in key for weak in ("123456", "abc123")):
        print(key)
        break
PYKEY
)"
if [ -z "$PW1R3_REDIS_URL" ]; then
    PW1R3_REDIS_URL="$("$PY_RUNNER" -c "import sys;u=sys.argv[1];print(u.rsplit('/',1)[0]+'/15')" "$REDIS_URL")"
fi

if [ -n "$CREDS_FILE" ] && [ ! -f "$CREDS_FILE" ]; then
    umask 177
    {
        echo "MIGRATE_PASSWORD=$MIGRATE_PASSWORD"
        echo "APP_PASSWORD=$APP_PASSWORD"
        echo "OPERATOR_PASSWORD=$OPERATOR_PASSWORD"
        echo "REPORTING_PASSWORD=$REPORTING_PASSWORD"
        echo "SECRET_KEY=$SECRET_KEY"
    } > "$CREDS_FILE"
    chmod 600 "$CREDS_FILE"
    echo "[supply] task credential store written (mode 0600)"
fi
MAINT_URL="postgresql://${ADMIN_USER}:${ADMIN_PASSWORD}@${PG_HOST}:${PG_PORT}/postgres"
MIGRATE_URL="postgresql://${MIGRATE_USER}:${MIGRATE_PASSWORD}@${PG_HOST}:${PG_PORT}/${TEST_DB}"
APP_URL="postgresql://${APP_USER}:${APP_PASSWORD}@${PG_HOST}:${PG_PORT}/${TEST_DB}"
OPERATOR_URL="postgresql://${OPERATOR_USER}:${OPERATOR_PASSWORD}@${PG_HOST}:${PG_PORT}/${TEST_DB}"
REPORTING_URL="postgresql://reporting_user:${REPORTING_PASSWORD}@${PG_HOST}:${PG_PORT}/${TEST_DB}"

# masks are registered BEFORE any value can possibly reach an output stream
for secret_value in "$ADMIN_PASSWORD" "$MIGRATE_PASSWORD" "$APP_PASSWORD" "$OPERATOR_PASSWORD" "$REPORTING_PASSWORD" "$SECRET_KEY" \
    "$MAINT_URL" "$MIGRATE_URL" "$APP_URL" "$OPERATOR_URL" "$REPORTING_URL"; do
    echo "::add-mask::$secret_value"
done

redact_stream() {
    "$PY_RUNNER" -c '
import os, sys
data = sys.stdin.read()
for secret in os.environ.get("C91_REDACT_SECRETS", "").splitlines():
    if secret:
        data = data.replace(secret, "***")
sys.stdout.write(data)'
}

run_psql() {
    local user="$1" password="$2" database="$3" sql="$4" out
    if ! out="$(PGPASSWORD="$password" psql -h "$PG_HOST" -p "$PG_PORT" -U "$user" -d "$database" -v ON_ERROR_STOP=1 -tAc "$sql" 2>&1)"; then
        printf '%s\n' "$out" | C91_REDACT_SECRETS="$ADMIN_PASSWORD
$MIGRATE_PASSWORD
$APP_PASSWORD
$OPERATOR_PASSWORD
$REPORTING_PASSWORD
$SECRET_KEY" redact_stream >&2
        return 1
    fi
    printf '%s\n' "$out"
}
run_psql_secret_stdin() {
    local user="$1" password="$2" database="$3" sql="$4" out
    if ! out="$(printf '%s\n' "$sql" | PGPASSWORD="$password" psql -h "$PG_HOST" -p "$PG_PORT" -U "$user" -d "$database" -v ON_ERROR_STOP=1 2>&1)"; then
        printf '%s\n' "$out" | C91_REDACT_SECRETS="$ADMIN_PASSWORD
$MIGRATE_PASSWORD
$APP_PASSWORD
$OPERATOR_PASSWORD
$REPORTING_PASSWORD
$SECRET_KEY" redact_stream >&2
        return 1
    fi
    printf '%s\n' "$out"
}
REDACTED_TOOL_PIPE() {
    C91_REDACT_SECRETS="$ADMIN_PASSWORD
$MIGRATE_PASSWORD
$APP_PASSWORD
$OPERATOR_PASSWORD
$REPORTING_PASSWORD
$SECRET_KEY" redact_stream
}

# ---- phase 1: product provisioner creates roles + the test database --------
echo "[supply] phase 1/5 provision (admin; product provisioner creates ${TEST_DB} with roles ${MIGRATE_USER}/${APP_USER})"
(
    cd "$REPO_ROOT/backend"
    export MPANGO_DB_ADMIN_URL="$MAINT_URL" MPANGO_DB_MIGRATE_URL="$MIGRATE_URL" MPANGO_DB_APP_URL="$APP_URL"
    export MPANGO_DB_MIGRATE_ROLE="$MIGRATE_USER" MPANGO_DB_APP_ROLE="$APP_USER"
    export MPANGO_DB_MIGRATE_PASSWORD="$MIGRATE_PASSWORD" MPANGO_DB_APP_PASSWORD="$APP_PASSWORD"
    poetry run python scripts/provision_runtime_db_roles.py --provision 2>&1 | REDACTED_TOOL_PIPE
)

# ---- phase 1b: task operator (authorized capability, distinct identity) ----
echo "[supply] phase 1b/5 task operator supply (LOGIN + task CREATEDB/CREATEROLE + SET-only membership; distinct from ${MIGRATE_USER}/${APP_USER}/${ADMIN_USER})"
if [ "$(run_psql "$ADMIN_USER" "$ADMIN_PASSWORD" postgres "SELECT 1 FROM pg_roles WHERE rolname = '${OPERATOR_USER}'")" != "1" ]; then
    run_psql_secret_stdin "$ADMIN_USER" "$ADMIN_PASSWORD" postgres \
        "CREATE ROLE \"${OPERATOR_USER}\" LOGIN NOSUPERUSER CREATEDB CREATEROLE NOINHERIT NOREPLICATION PASSWORD '${OPERATOR_PASSWORD}';" >/dev/null
else
    run_psql_secret_stdin "$ADMIN_USER" "$ADMIN_PASSWORD" postgres \
        "ALTER ROLE \"${OPERATOR_USER}\" LOGIN NOSUPERUSER CREATEDB CREATEROLE NOINHERIT NOREPLICATION PASSWORD '${OPERATOR_PASSWORD}';" >/dev/null
fi
run_psql_secret_stdin "$ADMIN_USER" "$ADMIN_PASSWORD" postgres \
    "GRANT \"${MIGRATE_USER}\" TO \"${OPERATOR_USER}\" WITH SET TRUE, INHERIT FALSE;" >/dev/null
run_psql "$ADMIN_USER" "$ADMIN_PASSWORD" postgres \
    "GRANT CONNECT ON DATABASE \"${TEST_DB}\" TO \"${OPERATOR_USER}\"" >/dev/null

# ---- phase 1c: pgcrypto pre-install with catalog facts ----------------------
echo "[supply] phase 1c/5 pgcrypto pre-install (admin on task DB; before/after catalog facts)"
PGCRYPTO_BEFORE="$(run_psql "$ADMIN_USER" "$ADMIN_PASSWORD" "$TEST_DB" "SELECT count(*) FROM pg_extension WHERE extname = 'pgcrypto'")"
run_psql "$ADMIN_USER" "$ADMIN_PASSWORD" "$TEST_DB" "CREATE EXTENSION IF NOT EXISTS pgcrypto" >/dev/null
PGCRYPTO_AFTER="$(run_psql "$ADMIN_USER" "$ADMIN_PASSWORD" "$TEST_DB" "SELECT count(*) FROM pg_extension WHERE extname = 'pgcrypto'")"
[ "$PGCRYPTO_AFTER" = "1" ] || refuse "pgcrypto not present after install (before=${PGCRYPTO_BEFORE}, after=${PGCRYPTO_AFTER})"
echo "[supply] pgcrypto catalog facts: before=${PGCRYPTO_BEFORE} after=${PGCRYPTO_AFTER}"

# ---- phase 2: migrations through exactly 039 as the migration authority ----
echo "[supply] phase 2/5 migrate (migration authority; alembic upgrade head)"
(
    cd "$REPO_ROOT/backend"
    export DATABASE_URL="$MIGRATE_URL" REPORTING_USER_PASSWORD="$REPORTING_PASSWORD"
    poetry run alembic upgrade head 2>&1 | REDACTED_TOOL_PIPE
)
HEAD_ROW="$(run_psql "$MIGRATE_USER" "$MIGRATE_PASSWORD" "$TEST_DB" "SELECT version_num FROM public.alembic_version")"
[ "$HEAD_ROW" = "039_order_credit_holds" ] || refuse "alembic head is '$HEAD_ROW', expected exactly 039_order_credit_holds"
echo "[supply] alembic head verified: 039_order_credit_holds"

# ---- phase 3: minimum runtime grants ----------------------------------------
echo "[supply] phase 3/5 apply-grants (migration authority)"
(
    cd "$REPO_ROOT/backend"
    export MPANGO_DB_ADMIN_URL="$MAINT_URL" MPANGO_DB_MIGRATE_URL="$MIGRATE_URL" MPANGO_DB_APP_URL="$APP_URL"
    export MPANGO_DB_MIGRATE_ROLE="$MIGRATE_USER" MPANGO_DB_APP_ROLE="$APP_USER"
    poetry run python scripts/provision_runtime_db_roles.py --apply-grants 2>&1 | REDACTED_TOOL_PIPE
)

# ---- phase 4: read-only product verification --------------------------------
echo "[supply] phase 4/5 verify (read-only product contract)"
(
    cd "$REPO_ROOT/backend"
    export MPANGO_DB_ADMIN_URL="$MAINT_URL" MPANGO_DB_MIGRATE_URL="$MIGRATE_URL" MPANGO_DB_APP_URL="$APP_URL"
    export MPANGO_DB_MIGRATE_ROLE="$MIGRATE_USER" MPANGO_DB_APP_ROLE="$APP_USER"
    poetry run python scripts/provision_runtime_db_roles.py --verify 2>&1 | REDACTED_TOOL_PIPE
)

# ---- phase 4b: read-only capability probe (operator authorization facts) ----
echo "[supply] phase 4b/5 capability probe (live catalog facts)"
OP_ATTRS="$(run_psql "$ADMIN_USER" "$ADMIN_PASSWORD" postgres "SELECT rolcreatedb, rolcreaterole, rolsuper, rolinherit FROM pg_roles WHERE rolname = '${OPERATOR_USER}'")"
[ "$OP_ATTRS" = "t|t|f|f" ] || refuse "operator ${OPERATOR_USER} attributes are '${OP_ATTRS}', expected CREATEDB/CREATEROLE true and SUPERUSER/INHERIT false"
OP_MEMBERSHIP="$(run_psql "$ADMIN_USER" "$ADMIN_PASSWORD" postgres "SELECT r.rolname || ':' || m.set_option::int || ':' || m.inherit_option::int FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid JOIN pg_roles rr ON rr.oid = m.member WHERE rr.rolname = '${OPERATOR_USER}' AND r.rolname = '${MIGRATE_USER}'")"
[ "$OP_MEMBERSHIP" = "${MIGRATE_USER}:1:0" ] || refuse "operator membership of ${MIGRATE_USER} is '${OP_MEMBERSHIP}', expected SET-only (set=1, inherit=0)"
echo "[supply] operator capability facts verified: CREATEDB+CREATEROLE, SET-only membership"

# ---- phase 5: tenant bootstrap as the runtime role --------------------------
echo "[supply] phase 5/5 tenant bootstrap (runtime role; schema ${TENANT_SCHEMA})"
(
    cd "$REPO_ROOT/backend"
    export DATABASE_URL="$APP_URL"
    poetry run python scripts/bootstrap_tenant_schema.py "$TENANT_SCHEMA" 2>&1 | REDACTED_TOOL_PIPE
)

# ---- versioned environment build (single source for test processes) --------
if [ -n "$ENV_FILE" ]; then
    mkdir -p "$(dirname "$ENV_FILE")"
    {
        echo "# C91 test environment build (versioned; generated $(date -u '+%Y-%m-%dT%H:%M:%SZ'))"
        echo "# schema-version: 3"
        echo "export DATABASE_URL='${APP_URL}'"
        echo "export TEST_DATABASE_URL='${APP_URL}'"
        echo "export TEST_MIGRATION_DATABASE_URL='${MIGRATE_URL}'"
        echo "export TEST_OPERATOR_DATABASE_URL='${OPERATOR_URL}'"
        echo "export TEST_ADMIN_DATABASE_URL='${MAINT_URL}'"
        echo "export TEST_REPORTING_DATABASE_URL='${REPORTING_URL}'"
        echo "export REPORTING_USER_PASSWORD='${REPORTING_PASSWORD}'"
        echo "export REDIS_URL='${REDIS_URL}'"
        echo "export PW1R3_TEST_REDIS_URL='${PW1R3_REDIS_URL}'"
        echo "export MPANGO_ENV=test"
        echo "export SECRET_KEY='${SECRET_KEY}'"
        echo "export MPANGO_INVARIANTS_R0_PG_CONTAINER='${PG_CONTAINER_ID}'"
        echo "export MPANGO_INVARIANTS_R0_PG_OWNER='${OWNER_LABEL}'"
        echo "export MPANGO_INVARIANTS_R0_REDIS_CONTAINER='${REDIS_CONTAINER_ID}'"
        echo "export MPANGO_INVARIANTS_R0_MIGRATION_DATABASE_URL='${MIGRATE_URL}'"
        echo "export MPANGO_INVARIANTS_R0_ADMIN_DATABASE_URL='${MAINT_URL}'"
        echo "export MPANGO_TEMP_DB_ALLOWED_PORTS='${PG_PORT}'"
        echo "export MPANGO_TEMP_DB_ALLOWED_HOSTS='127.0.0.1,localhost'"
    } > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "[supply] versioned env file written (mode 0600): $ENV_FILE"
fi

if [ -n "$GITHUB_ENV_FILE" ]; then
    {
        echo "DATABASE_URL=$APP_URL"
        echo "TEST_DATABASE_URL=$APP_URL"
        echo "TEST_MIGRATION_DATABASE_URL=$MIGRATE_URL"
        echo "TEST_OPERATOR_DATABASE_URL=$OPERATOR_URL"
        echo "TEST_ADMIN_DATABASE_URL=$MAINT_URL"
        echo "TEST_REPORTING_DATABASE_URL=$REPORTING_URL"
        echo "REPORTING_USER_PASSWORD=$REPORTING_PASSWORD"
        echo "REDIS_URL=$REDIS_URL"
        echo "PW1R3_TEST_REDIS_URL=$PW1R3_REDIS_URL"
        echo "MPANGO_ENV=test"
        echo "SECRET_KEY=$SECRET_KEY"
        echo "MPANGO_INVARIANTS_R0_PG_CONTAINER=$PG_CONTAINER_ID"
        echo "MPANGO_INVARIANTS_R0_PG_OWNER=$OWNER_LABEL"
        echo "MPANGO_INVARIANTS_R0_REDIS_CONTAINER=$REDIS_CONTAINER_ID"
        echo "MPANGO_INVARIANTS_R0_MIGRATION_DATABASE_URL=$MIGRATE_URL"
        echo "MPANGO_INVARIANTS_R0_ADMIN_DATABASE_URL=$MAINT_URL"
        echo "MPANGO_TEMP_DB_ALLOWED_PORTS=$PG_PORT"
        echo "MPANGO_TEMP_DB_ALLOWED_HOSTS=127.0.0.1,localhost"
    } >> "$GITHUB_ENV_FILE"
    echo "[supply] github env keys appended (values masked; file never echoed or uploaded)"
fi

echo "[supply] five phases complete: identities provisioned via product paths; pytest may start"
