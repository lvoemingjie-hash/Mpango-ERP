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

# Resolve the validated DATABASE_URL and REPORTING_USER_PASSWORD from
# backend/.env via the SAME strict parser the preflight uses
# (setup_preflight.parse_env_file) — no second handwritten parser, no `set -a`,
# no sourcing of .env. Values are captured into temporary shell variables and
# never printed. Both are exported BEFORE Alembic (migrations including
# 011_s6_p_reporting_role require REPORTING_USER_PASSWORD). It is unset before
# tenant bootstrap so the reporting password does not extend its lifetime.
_NATIVE_CREDS="$(python -c "import sys; sys.path.insert(0, sys.argv[1]); from setup_preflight import parse_env_file; e=parse_env_file('.env'); print(e.get('DATABASE_URL','')); print(e.get('REPORTING_USER_PASSWORD',''))" "$SCRIPT_DIR" 2>/dev/null)" \
    || { echo "Could not resolve credentials from backend/.env." >&2; exit 1; }
_NATIVE_DB_URL="${_NATIVE_CREDS%%$'\n'*}"
_NATIVE_DB_URL="${_NATIVE_DB_URL%$'\r'}"
_NATIVE_RUP="${_NATIVE_CREDS#*$'\n'}"
_NATIVE_RUP="${_NATIVE_RUP%$'\r'}"
[ -n "$_NATIVE_DB_URL" ] || { echo "DATABASE_URL missing from backend/.env." >&2; exit 1; }
[ -n "$_NATIVE_RUP" ] || { echo "REPORTING_USER_PASSWORD missing from backend/.env." >&2; exit 1; }
export DATABASE_URL="$_NATIVE_DB_URL"
export REPORTING_USER_PASSWORD="$_NATIVE_RUP"

echo "Running public Alembic migration"
alembic upgrade head

# REPORTING_USER_PASSWORD is only needed by Alembic migrations; drop it before
# tenant bootstrap so the reporting password does not extend its lifetime.
unset REPORTING_USER_PASSWORD _NATIVE_RUP

echo "Bootstrapping tenant schema"
python scripts/bootstrap_tenant_schema.py "${DEFAULT_TENANT_SCHEMA:-t_dev}"

# Drop the connection URL and all temporary variables.
unset DATABASE_URL _NATIVE_DB_URL _NATIVE_CREDS

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
