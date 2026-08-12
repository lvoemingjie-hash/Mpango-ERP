#!/bin/bash
# Mpango ERP Setup Script  (H7-R5-R3 — preflight before side effects)
set -Eeuo pipefail

_on_err() {
    local line="$1" status="${2:-1}"
    echo "Setup stopped at line $line (exit status $status). Partial local artifacts may exist." >&2
    exit "$status"
}
trap '_on_err "$LINENO" "$?"' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

echo "Setting up Mpango ERP (root: $REPO_ROOT)"

# ---- docker compose (stored as a shell array) ---------------------------
COMPOSE=()
if command -v docker &> /dev/null; then
    if docker compose version &> /dev/null; then
        COMPOSE=(docker compose)
    elif command -v docker-compose &> /dev/null; then
        COMPOSE=(docker-compose)
    fi
fi
if [ "${#COMPOSE[@]}" -eq 0 ]; then
    echo "Neither 'docker compose' nor 'docker-compose' is available." >&2
    exit 1
fi

# =========================================================================
# PREFLIGHT — validate everything BEFORE any filesystem or service side effect
# =========================================================================

# 1. backend/.env present and no placeholder credentials (do NOT source as shell)
if [ ! -f backend/.env ]; then
    echo "backend/.env not found." >&2; exit 1
fi
if grep -qiE '(^|[^A-Z_])CHANGE_ME|CHANGEME' backend/.env 2>/dev/null; then
    echo "backend/.env contains CHANGE_ME placeholder values." >&2; exit 1
fi

# 2. Compose config must render successfully
if ! "${COMPOSE[@]}" config --quiet 2>/dev/null; then
    echo "docker-compose configuration is invalid." >&2; exit 1
fi

# 3. Resolve DATABASE_URL from core.config.settings (never printed)
PREFLIGHT_DB_URL="$(cd "$REPO_ROOT/backend" && python -c "from core.config import settings; print(settings.DATABASE_URL)" 2>/dev/null)" \
    || { echo "Could not resolve DATABASE_URL from core.config.settings." >&2; exit 1; }
if [ -z "$PREFLIGHT_DB_URL" ]; then
    echo "Resolved DATABASE_URL is empty." >&2; exit 1
fi

# 4. Render Compose config as JSON and extract postgres identity (stdlib parse)
COMPOSE_PG_INFO="$("${COMPOSE[@]}" config --format json 2>/dev/null | python -c "
import sys, json, re
cfg = json.load(sys.stdin)
services = cfg.get('services', {})
pg = services.get('postgres')
if pg is None:
    sys.stderr.write('postgres service not found in Compose config\n'); sys.exit(1)
env = pg.get('environment') or {}
if isinstance(env, list):
    env = dict(item.split('=', 1) for item in env if '=' in item)
pg_user = env.get('POSTGRES_USER')
pg_db = env.get('POSTGRES_DB')
if not pg_user or not pg_db:
    sys.stderr.write('missing POSTGRES_USER/POSTGRES_DB in Compose config\n'); sys.exit(1)
ports = pg.get('ports') or []
host_ip = ''
pub_port = ''
for p in ports:
    s = str(p)
    m = re.match(r'(\d+(?:\.\d+){3}):(\d+):(\d+)', s) or re.match(r'(\d+):(\d+)', s)
    if m:
        g = m.groups()
        host_ip = g[0] if len(g) == 3 else ''
        pub_port = g[1] if len(g) == 3 else g[0]
        break
if host_ip == '0.0.0.0':
    sys.stderr.write('postgres bound to 0.0.0.0\n'); sys.exit(1)
print(f'{pg_user}|{pg_db}|{pub_port}')
")" || { echo "Could not extract Compose postgres identity from rendered config." >&2; exit 1; }
COMPOSE_USER="${COMPOSE_PG_INFO%%|*}"; _R="${COMPOSE_PG_INFO#*|}"
COMPOSE_DB="${_R%%|*}"; _R="${_R#*|}"
COMPOSE_PORT="${_R}"

# 5. Parse DATABASE_URL tuple safely (password never printed or compared in logs)
DB_TUPLE="$(DATABASE_URL="$PREFLIGHT_DB_URL" python -c "
import os
from urllib.parse import urlparse
u = urlparse(os.environ['DATABASE_URL'].replace('postgresql+asyncpg', 'postgresql'))
print(u.username or '', u.password or '', u.hostname or '', u.port or 5432, u.path.lstrip('/') or '', sep='|')
" 2>/dev/null)" || { echo "Could not parse DATABASE_URL." >&2; exit 1; }
DB_USER="${DB_TUPLE%%|*}"; _T="${DB_TUPLE#*|}"
DB_PASS="${_T%%|*}"; _T="${_T#*|}"   # DB_PASS is NEVER printed
DB_HOST="${_T%%|*}"; _T="${_T#*|}"
DB_PORT="${_T%%|*}"; _T="${_T#*|}"
DB_NAME="${_T}"

# 6. Cross-verify identity (fail closed before side effects)
[ -n "$DB_USER" ] || { echo "DATABASE_URL has no username." >&2; exit 1; }
[ -n "$DB_NAME" ] || { echo "DATABASE_URL has no database name." >&2; exit 1; }
[ "$DB_USER" = "$COMPOSE_USER" ] || { echo "DATABASE_URL user does not match Compose POSTGRES_USER." >&2; exit 1; }
[ "$DB_NAME" = "$COMPOSE_DB" ] || { echo "DATABASE_URL database does not match Compose POSTGRES_DB." >&2; exit 1; }
case "$DB_HOST" in localhost|127.0.0.1|::1) ;; *) echo "DATABASE_URL host must be local." >&2; exit 1;; esac
if [ -n "$COMPOSE_PORT" ] && [ "$DB_PORT" != "$COMPOSE_PORT" ]; then
    echo "DATABASE_URL port does not match Compose published port." >&2; exit 1
fi

echo "Preflight OK: DATABASE_URL matches Compose postgres identity."

# =========================================================================
# SIDE EFFECTS BEGIN HERE
# =========================================================================

# directories
mkdir -p logs uploads

# frontend env
if [ ! -f frontend/.env ]; then
    echo "Creating frontend .env"
    echo "VITE_API_URL=http://localhost:8000/api/v1" > frontend/.env
fi

# start services
echo "Starting Docker services"
"${COMPOSE[@]}" up -d postgres redis

# bounded PostgreSQL readiness (container-owned env)
MAX_ATTEMPTS="${SETUP_TIMEOUT_ATTEMPTS:-30}"
SLEEP_SECS="${SETUP_TIMEOUT_INTERVAL:-2}"
for i in $(seq 1 "$MAX_ATTEMPTS"); do
    if "${COMPOSE[@]}" exec -T postgres sh -ec 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' &> /dev/null; then
        break
    fi
    [ "$i" -eq "$MAX_ATTEMPTS" ] && { echo "PostgreSQL not ready." >&2; exit 1; }
    sleep "$SLEEP_SECS"
done

# bounded Redis readiness
for i in $(seq 1 "$MAX_ATTEMPTS"); do
    if "${COMPOSE[@]}" exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
        break
    fi
    [ "$i" -eq "$MAX_ATTEMPTS" ] && { echo "Redis not ready." >&2; exit 1; }
    sleep "$SLEEP_SECS"
done

# backend deps
echo "Installing backend dependencies"
cd "$REPO_ROOT/backend"
pip install -r requirements.txt

# re-resolve DATABASE_URL and assert equals preflight (detects env drift)
POSTINSTALL_DB_URL="$(python -c "from core.config import settings; print(settings.DATABASE_URL)" 2>/dev/null)" \
    || { echo "Could not re-resolve DATABASE_URL after pip install." >&2; exit 1; }
[ "$POSTINSTALL_DB_URL" = "$PREFLIGHT_DB_URL" ] || {
    echo "DATABASE_URL changed after dependency installation (env drift)." >&2; exit 1
}

# public Alembic
echo "Running public Alembic migration"
alembic upgrade head

# canonical tenant bootstrap (DATABASE_URL via env, never in argv)
echo "Bootstrapping tenant schema"
export DATABASE_URL="$PREFLIGHT_DB_URL"
python scripts/bootstrap_tenant_schema.py "${DEFAULT_TENANT_SCHEMA:-t_dev}"
unset DATABASE_URL

cd "$REPO_ROOT"

# frontend pnpm
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
