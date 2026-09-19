#!/bin/bash
# Mpango ERP Setup Script  (H7-R11 — Compose project isolation + native env-file)
set -Eeuo pipefail

_on_err() {
    local line="$1" status="${2:-1}"
    echo "Setup stopped at line $line (exit status $status). Partial local artifacts may exist." >&2
    exit "$status"
}
trap '_on_err "$LINENO" "$?"' ERR

# Fail closed on CRLF line endings (committed scripts are LF-only).
# Python reads raw bytes: MSYS shell tools strip CR in text-mode file reads,
# and raw CR bytes cannot be passed reliably through argv.
if python -c "import sys; d = open(sys.argv[1], 'rb').read(); sys.exit(0 if b'\r' in d else 1)" "${BASH_SOURCE[0]}" 2>/dev/null; then
    echo "setup.sh contains CRLF line endings; re-checkout with LF." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

echo "Setting up Mpango ERP (root: $REPO_ROOT)"

# ---- docker compose v2 (required for JSON config output) ---------------
# backend/.env is passed to Compose explicitly via the global --env-file
# option (before the subcommand) so setup works without exporting the file
# into the caller environment. A caller-provided COMPOSE_PROJECT_NAME is
# honoured unchanged; Compose namespaces resources from it naturally.
# Candidate selection uses `version` probes ONLY: no config operation may
# run before the --env-file-bearing array exists (a standalone
# docker-compose config probe without --env-file would fail interpolation
# and silently reject an otherwise-valid standalone Compose).
BACKEND_ENV="$REPO_ROOT/backend/.env"
COMPOSE_BASE=()
if command -v docker &> /dev/null && docker compose version &> /dev/null; then
    COMPOSE_BASE=(docker compose)
elif command -v docker-compose &> /dev/null && docker-compose version &> /dev/null; then
    COMPOSE_BASE=(docker-compose)
fi
if [ "${#COMPOSE_BASE[@]}" -eq 0 ]; then
    echo "Docker Compose v2 is required." >&2; exit 1
fi
# Same array for config, up and exec; --env-file precedes the subcommand.
# The real capability checks (config --quiet / config --format json below)
# run through THIS array, so they carry --env-file too.
COMPOSE=("${COMPOSE_BASE[@]}" --env-file "$BACKEND_ENV")

# =========================================================================
# PREFLIGHT — validate everything BEFORE any filesystem or service side effect
# =========================================================================

if [ ! -f backend/.env ]; then
    echo "backend/.env not found." >&2; exit 1
fi
if grep -qiE '(^|[^A-Z_])CHANGE_ME|CHANGEME' backend/.env 2>/dev/null; then
    echo "backend/.env contains CHANGE_ME placeholder values." >&2; exit 1
fi
if ! "${COMPOSE[@]}" config --quiet 2>/dev/null; then
    echo "docker-compose configuration is invalid." >&2; exit 1
fi

# Preflight via extracted module — pipe Compose JSON through setup_preflight.py.
# DATABASE_URL/REDIS_URL are read from the environment inside the helper
# (never passed on argv, so no secret lands in process listings or logs).
"${COMPOSE[@]}" config --format json | python "$SCRIPT_DIR/setup_preflight.py" \
    --env-file "$REPO_ROOT/backend/.env" || {
    echo "Preflight failed." >&2; exit 1
}
echo "Preflight OK."

# =========================================================================
# SIDE EFFECTS BEGIN HERE
# =========================================================================
mkdir -p logs uploads

if [ ! -f frontend/.env ]; then
    echo "Creating frontend .env"
    echo "VITE_API_URL=http://localhost:8000/api/v1" > frontend/.env
fi

echo "Starting Docker services"
"${COMPOSE[@]}" up -d postgres redis

MAX_ATTEMPTS="${SETUP_TIMEOUT_ATTEMPTS:-30}"
SLEEP_SECS="${SETUP_TIMEOUT_INTERVAL:-2}"

for i in $(seq 1 "$MAX_ATTEMPTS"); do
    if "${COMPOSE[@]}" exec -T postgres sh -ec 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' &> /dev/null; then break; fi
    [ "$i" -eq "$MAX_ATTEMPTS" ] && { echo "PostgreSQL not ready." >&2; exit 1; }
    sleep "$SLEEP_SECS"
done

for i in $(seq 1 "$MAX_ATTEMPTS"); do
    if "${COMPOSE[@]}" exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then break; fi
    [ "$i" -eq "$MAX_ATTEMPTS" ] && { echo "Redis not ready." >&2; exit 1; }
    sleep "$SLEEP_SECS"
done

echo "Installing backend dependencies"
cd "$REPO_ROOT/backend"
pip install -r requirements.txt

# Post-install verification via extracted preflight module
python "$SCRIPT_DIR/setup_preflight.py" --env-file .env --post-install || {
    echo "Post-install verification failed." >&2; exit 1; }

# =========================================================================
# TWO-ROLE DB AUTHORITY - five ordered operator phases
# (MPANGO-TENANT-BOOTSTRAP-DB-AUTHORITY R1; combined-candidate P0 closure)
#
#   phase 1  provision  (admin)               roles + application database
#   phase 2  migrate    (migration authority) alembic through 039
#   phase 3  grants     (migration authority) minimum runtime grants
#   phase 4  verify     (read-only)           authority contract verification
#   phase 5  bootstrap  (runtime role)        tenant schema via DATABASE_URL
#
# DATABASE_URL - here and in the runtime environment - binds the RUNTIME role
# only.  Admin and migration credentials are resolved from backend/.env into
# temporary shell variables, exported ONLY for their own phase, never
# printed, and unset again before the next phase, so they never linger in the
# backend runtime environment.
# =========================================================================
_NATIVE_KEYS=(MPANGO_DB_ADMIN_URL MPANGO_DB_MIGRATE_URL DATABASE_URL MPANGO_DB_MIGRATE_PASSWORD MPANGO_DB_APP_PASSWORD REPORTING_USER_PASSWORD)
_NATIVE_VALUES="$(python -c "
import sys; sys.path.insert(0, sys.argv[1])
from setup_preflight import parse_env_file
e = parse_env_file('.env')
for k in sys.argv[2:]:
    print(e.get(k, ''))
" "$SCRIPT_DIR" "${_NATIVE_KEYS[@]}" 2>/dev/null)"     || { echo "Could not resolve two-role credentials from backend/.env." >&2; exit 1; }
mapfile -t _V <<<"$_NATIVE_VALUES"
unset _NATIVE_VALUES
_ADMIN_URL="${_V[0]%$''}"; _MIGRATE_URL="${_V[1]%$''}"; _RUNTIME_DB_URL="${_V[2]%$''}"
_MIGRATE_PW="${_V[3]%$''}"; _APP_PW="${_V[4]%$''}"; _RUP="${_V[5]%$''}"
unset _V
for _k in _ADMIN_URL:_MPANGO_DB_ADMIN_URL _MIGRATE_URL:_MPANGO_DB_MIGRATE_URL _RUNTIME_DB_URL:DATABASE_URL _MIGRATE_PW:_MPANGO_DB_MIGRATE_PASSWORD _APP_PW:_MPANGO_DB_APP_PASSWORD _RUP:REPORTING_USER_PASSWORD; do
    _var="${_k%%:*}"; _envn="${_k##*:}"
    [ -n "${!_var}" ] || { echo "${_envn} missing from backend/.env." >&2; exit 1; }
done
unset _k _var _envn

echo "Phase 1/5: provisioning DB roles and application database (admin)"
export MPANGO_DB_ADMIN_URL="$_ADMIN_URL" MPANGO_DB_MIGRATE_URL="$_MIGRATE_URL" MPANGO_DB_APP_URL="$_RUNTIME_DB_URL"
export MPANGO_DB_MIGRATE_PASSWORD="$_MIGRATE_PW" MPANGO_DB_APP_PASSWORD="$_APP_PW"
python scripts/provision_runtime_db_roles.py --provision
unset MPANGO_DB_ADMIN_URL MPANGO_DB_MIGRATE_URL MPANGO_DB_APP_URL MPANGO_DB_MIGRATE_PASSWORD MPANGO_DB_APP_PASSWORD

echo "Phase 2/5: running migrations through 039 as the migration authority"
export DATABASE_URL="$_MIGRATE_URL"
export REPORTING_USER_PASSWORD="$_RUP"
alembic upgrade head
unset DATABASE_URL REPORTING_USER_PASSWORD

echo "Phase 3/5: applying minimum runtime grants (migration authority)"
export MPANGO_DB_ADMIN_URL="$_ADMIN_URL" MPANGO_DB_MIGRATE_URL="$_MIGRATE_URL" MPANGO_DB_APP_URL="$_RUNTIME_DB_URL"
python scripts/provision_runtime_db_roles.py --apply-grants

echo "Phase 4/5: verifying the authority contract (read-only)"
python scripts/provision_runtime_db_roles.py --verify
unset MPANGO_DB_ADMIN_URL MPANGO_DB_MIGRATE_URL MPANGO_DB_APP_URL

echo "Phase 5/5: bootstrapping tenant schema as the runtime role"
export DATABASE_URL="$_RUNTIME_DB_URL"
python scripts/bootstrap_tenant_schema.py "${DEFAULT_TENANT_SCHEMA:-t_dev}"

# Drop the runtime URL and every temporary credential variable.
unset DATABASE_URL _ADMIN_URL _MIGRATE_URL _RUNTIME_DB_URL _MIGRATE_PW _APP_PW _RUP _NATIVE_KEYS

cd "$REPO_ROOT"
echo "Setting up frontend"
cd "$REPO_ROOT/frontend"
if command -v pnpm &> /dev/null; then
    PNPM_BIN="pnpm"
elif command -v corepack &> /dev/null; then
    corepack enable
    PNPM_BIN="pnpm"
else
    echo "pnpm is not installed." >&2; exit 1
fi
"$PNPM_BIN" install --frozen-lockfile

cd "$REPO_ROOT"
echo ""
echo "Setup complete!"
