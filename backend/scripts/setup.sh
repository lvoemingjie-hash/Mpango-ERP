#!/bin/bash
# Mpango ERP Setup Script  (H7-R5-R6 — extracted preflight module)
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
COMPOSE=()
if command -v docker &> /dev/null && docker compose version &> /dev/null; then
    COMPOSE=(docker compose)
elif command -v docker-compose &> /dev/null && docker-compose version &> /dev/null; then
    if docker-compose config --format json &> /dev/null < /dev/null; then
        COMPOSE=(docker-compose)
    fi
fi
if [ "${#COMPOSE[@]}" -eq 0 ]; then
    echo "Docker Compose v2 is required." >&2; exit 1
fi

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

# Preflight via extracted module — pipe Compose JSON through setup_preflight.py
"${COMPOSE[@]}" config --format json | python "$SCRIPT_DIR/setup_preflight.py" \
    --env-file "$REPO_ROOT/backend/.env" \
    --process-db "${DATABASE_URL:-}" \
    --process-redis "${REDIS_URL:-}" || {
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

echo "Running public Alembic migration"
alembic upgrade head

echo "Bootstrapping tenant schema"
# Re-read DATABASE_URL for the bootstrap env var
_POSTGRES_URL="$(python -c "
seen={}
for l in open('.env'):
    s=l.strip()
    if s and not s.startswith('#') and '=' in s:
        k,v=s.split('=',1); seen[k.strip()]=v.strip().strip(chr(39)).strip(chr(34))
print(seen.get('DATABASE_URL',''))
" 2>/dev/null)"
export DATABASE_URL="$_POSTGRES_URL"
python scripts/bootstrap_tenant_schema.py "${DEFAULT_TENANT_SCHEMA:-t_dev}"
unset DATABASE_URL

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
