#!/bin/bash
# Mpango ERP Setup Script  (H7-R5-R4 — real Compose preflight)
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

# ---- docker compose (must be v2 for JSON config output) ----------------
COMPOSE=()
if command -v docker &> /dev/null && docker compose version &> /dev/null; then
    COMPOSE=(docker compose)
elif command -v docker-compose &> /dev/null && docker-compose version &> /dev/null; then
    # docker-compose v1 does not support --format json; require v2
    if docker-compose config --format json &> /dev/null; then
        COMPOSE=(docker-compose)
    fi
fi
if [ "${#COMPOSE[@]}" -eq 0 ]; then
    echo "Docker Compose v2 is required (JSON config output). Neither 'docker compose' nor a JSON-capable 'docker-compose' is available." >&2
    exit 1
fi

# =========================================================================
# PREFLIGHT — validate everything BEFORE any filesystem or service side effect
# No core.config or project-package import before pip.
# =========================================================================

# 1. backend/.env present, no placeholder credentials
if [ ! -f backend/.env ]; then
    echo "backend/.env not found." >&2; exit 1
fi
if grep -qiE '(^|[^A-Z_])CHANGE_ME|CHANGEME' backend/.env 2>/dev/null; then
    echo "backend/.env contains CHANGE_ME placeholder values." >&2; exit 1
fi

# 2. Compose config renders successfully
if ! "${COMPOSE[@]}" config --quiet 2>/dev/null; then
    echo "docker-compose configuration is invalid." >&2; exit 1
fi

# 3. Parse backend/.env for DATABASE_URL and REDIS_URL (stdlib only, no core.config)
PREFLIGHT_ENV="$(python -c "
import sys
seen = {}
try:
    for line in open('backend/.env'):
        s = line.strip()
        if not s or s.startswith('#'): continue
        if '=' not in s:
            sys.stderr.write('malformed .env line (no = sign)\n'); sys.exit(1)
        k, v = s.split('=', 1)
        k = k.strip()
        if not k:
            sys.stderr.write('malformed .env line (empty key)\n'); sys.exit(1)
        if k in seen:
            sys.stderr.write(f'duplicate key: {k}\n'); sys.exit(1)
        seen[k] = v.strip().strip(chr(39)).strip(chr(34))
except FileNotFoundError:
    sys.stderr.write('backend/.env not readable\n'); sys.exit(1)
print(seen.get('DATABASE_URL', ''), seen.get('REDIS_URL', ''), sep='|')
" 2>/dev/null)" || { echo "Could not parse backend/.env." >&2; exit 1; }
PREFLIGHT_DB_URL="${PREFLIGHT_ENV%%|*}"
PREFLIGHT_REDIS_URL="${PREFLIGHT_ENV#*|}"
if [ -z "$PREFLIGHT_DB_URL" ]; then
    echo "DATABASE_URL not found in backend/.env." >&2; exit 1
fi

# 4. Render Compose config as JSON and extract postgres/redis identity + ports
COMPOSE_INFO="$("${COMPOSE[@]}" config --format json 2>/dev/null | python -c "
import sys, json
cfg = json.load(sys.stdin)
services = cfg.get('services', {})

def parse_port_mapping(p):
    host_ip = ''; target = ''; published = ''
    if isinstance(p, dict):
        host_ip = str(p.get('host_ip', ''))
        target = str(p.get('target', ''))
        published = str(p.get('published', ''))
    elif isinstance(p, str):
        parts = p.split(':')
        if len(parts) == 3:
            host_ip, published, target = parts
        elif len(parts) == 2:
            published, target = parts
    return host_ip, target, published

# postgres identity
pg = services.get('postgres')
if pg is None:
    sys.stderr.write('postgres service not found\n'); sys.exit(1)
env = pg.get('environment') or {}
if isinstance(env, list):
    env = dict(item.split('=', 1) for item in env if '=' in item)
pg_user = env.get('POSTGRES_USER', '')
pg_pass = env.get('POSTGRES_PASSWORD', '')
pg_db = env.get('POSTGRES_DB', '')
if not pg_user or not pg_db:
    sys.stderr.write('missing POSTGRES_USER/POSTGRES_DB\n'); sys.exit(1)

# postgres port mapping (require exactly one mapping for target 5432)
pg_ports_raw = pg.get('ports') or []
pg_mappings = [parse_port_mapping(p) for p in pg_ports_raw]
pg_5432 = [m for m in pg_mappings if m[1] == '5432']
if len(pg_5432) != 1:
    sys.stderr.write(f'expected exactly one postgres mapping for target 5432, got {len(pg_5432)}\n'); sys.exit(1)
pg_host_ip, _, pg_pub_port = pg_5432[0]
if pg_host_ip != '127.0.0.1':
    sys.stderr.write(f'postgres host_ip must be 127.0.0.1, got {pg_host_ip}\n'); sys.exit(1)

# redis port mapping (require exactly one mapping for target 6379)
rd = services.get('redis')
if rd is None:
    sys.stderr.write('redis service not found\n'); sys.exit(1)
rd_ports_raw = rd.get('ports') or []
rd_mappings = [parse_port_mapping(p) for p in rd_ports_raw]
rd_6379 = [m for m in rd_mappings if m[1] == '6379']
if len(rd_6379) != 1:
    sys.stderr.write(f'expected exactly one redis mapping for target 6379, got {len(rd_6379)}\n'); sys.exit(1)
rd_host_ip, _, rd_pub_port = rd_6379[0]
if rd_host_ip != '127.0.0.1':
    sys.stderr.write(f'redis host_ip must be 127.0.0.1, got {rd_host_ip}\n'); sys.exit(1)

# Output identity (password included for in-memory comparison, NEVER printed by caller)
print(f'{pg_user}|{pg_pass}|{pg_db}|{pg_pub_port}|{rd_pub_port}')
")" || { echo "Could not extract Compose identity from rendered config." >&2; exit 1; }

C_PG_USER="${COMPOSE_INFO%%|*}"; _R="${COMPOSE_INFO#*|}"
C_PG_PASS="${_R%%|*}"; _R="${_R#*|}"
C_PG_DB="${_R%%|*}"; _R="${_R#*|}"
C_PG_PORT="${_R%%|*}"; _R="${_R#*|}"
C_RD_PORT="${_R}"

# 5. Parse DATABASE_URL tuple (password never printed, compared only in memory)
DB_TUPLE="$(DATABASE_URL="$PREFLIGHT_DB_URL" python -c "
import os
from urllib.parse import urlparse, unquote
u = urlparse(os.environ['DATABASE_URL'].replace('postgresql+asyncpg', 'postgresql'))
print(unquote(u.username or ''), unquote(u.password or ''), u.hostname or '', u.port or 5432, u.path.lstrip('/') or '', sep='|')
" 2>/dev/null)" || { echo "Could not parse DATABASE_URL." >&2; exit 1; }
DB_USER="${DB_TUPLE%%|*}"; _T="${DB_TUPLE#*|}"
DB_PASS="${_T%%|*}"; _T="${_T#*|}"
DB_HOST="${_T%%|*}"; _T="${_T#*|}"
DB_PORT="${_T%%|*}"; _T="${_T#*|}"
DB_NAME="${_T}"

# 6. Cross-verify DB identity (in-memory comparison, never printed)
[ -n "$DB_USER" ] || { echo "DATABASE_URL has no username." >&2; exit 1; }
[ -n "$DB_NAME" ] || { echo "DATABASE_URL has no database name." >&2; exit 1; }
[ "$DB_USER" = "$C_PG_USER" ] || { echo "DATABASE_URL user mismatch." >&2; exit 1; }
[ "$DB_NAME" = "$C_PG_DB" ] || { echo "DATABASE_URL database mismatch." >&2; exit 1; }
[ "$DB_PASS" = "$C_PG_PASS" ] || { echo "DATABASE_URL password mismatch." >&2; exit 1; }
case "$DB_HOST" in localhost|127.0.0.1|::1) ;; *) echo "DATABASE_URL host must be local." >&2; exit 1;; esac
[ "$DB_PORT" = "$C_PG_PORT" ] || { echo "DATABASE_URL port mismatch." >&2; exit 1; }

# 7. Verify Redis URL host/port
if [ -n "$PREFLIGHT_REDIS_URL" ]; then
    RD_TUPLE="$(REDIS_URL="$PREFLIGHT_REDIS_URL" python -c "
import os
from urllib.parse import urlparse
u = urlparse(os.environ['REDIS_URL'])
print(u.hostname or '', u.port or 6379, sep='|')
" 2>/dev/null)" || RD_TUPLE="|"
    RD_HOST="${RD_TUPLE%%|*}"; RD_PORT="${RD_TUPLE#*|}"
    case "$RD_HOST" in localhost|127.0.0.1|::1) ;; *) echo "REDIS_URL host must be local." >&2; exit 1;; esac
    [ "$RD_PORT" = "$C_RD_PORT" ] || { echo "REDIS_URL port mismatch." >&2; exit 1; }
fi

echo "Preflight OK: DATABASE_URL and Redis URL match Compose identity."

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

# Re-resolve through core.config.settings and assert equality (detects env drift)
POSTINSTALL_DB_URL="$(python -c "from core.config import settings; print(settings.DATABASE_URL)" 2>/dev/null)" \
    || { echo "Could not re-resolve DATABASE_URL after pip install." >&2; exit 1; }
[ "$POSTINSTALL_DB_URL" = "$PREFLIGHT_DB_URL" ] || {
    echo "DATABASE_URL changed after dependency installation (env drift)." >&2; exit 1
}

echo "Running public Alembic migration"
alembic upgrade head

echo "Bootstrapping tenant schema"
export DATABASE_URL="$PREFLIGHT_DB_URL"
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
