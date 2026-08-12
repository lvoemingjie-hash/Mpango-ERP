#!/bin/bash
# Mpango ERP Setup Script  (H7-R5-R2 — executable truth closure)
set -Eeuo pipefail

# ---------------------------------------------------------------------------
# ERR trap: preserve exact failure status, identify the line, and truthfully
# state that setup stopped with possible partial local artifacts.
# ---------------------------------------------------------------------------
_on_err() {
    local line="$1" status="${2:-1}"
    echo "❌ Setup stopped at line $line (exit status $status). Partial local artifacts may exist; inspect and re-run after fixing the cause." >&2
    exit "$status"
}
trap '_on_err "$LINENO" "$?"' ERR

# ---- resolve repository root from script location -----------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

echo "🚀 Setting up Mpango ERP (root: $REPO_ROOT) …"

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
    echo "❌ Neither 'docker compose' nor 'docker-compose' is available." >&2
    exit 1
fi

# ---- configuration preflight (before any filesystem/service side effect) -
if [ ! -f backend/.env ]; then
    echo "❌ backend/.env not found. Copy backend/.env.example and configure real values first." >&2
    exit 1
fi
# reject placeholder credentials (do NOT source .env as shell code)
if grep -qiE '(^|[^A-Z_])CHANGE_ME|CHANGEME' backend/.env 2>/dev/null; then
    echo "❌ backend/.env still contains CHANGE_ME placeholder values." >&2
    exit 1
fi
# validate Compose config before touching services
if ! "${COMPOSE[@]}" config --quiet 2>/dev/null; then
    echo "❌ docker-compose configuration is invalid." >&2
    exit 1
fi

# ---- directories --------------------------------------------------------
echo "📁 Creating directories …"
mkdir -p logs uploads

# ---- frontend env ------------------------------------------------------
if [ ! -f frontend/.env ]; then
    echo "📝 Creating frontend .env …"
    echo "VITE_API_URL=http://localhost:8000/api/v1" > frontend/.env
fi

# ---- start Docker services ----------------------------------------------
echo "🐳 Starting Docker services …"
"${COMPOSE[@]}" up -d postgres redis

# ---- bounded PostgreSQL readiness (container-owned env, no host fallback) -
echo "⏳ Waiting for PostgreSQL …"
MAX_ATTEMPTS="${SETUP_TIMEOUT_ATTEMPTS:-30}"
SLEEP_SECS="${SETUP_TIMEOUT_INTERVAL:-2}"
for i in $(seq 1 "$MAX_ATTEMPTS"); do
    if "${COMPOSE[@]}" exec -T postgres sh -ec \
         'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
         &> /dev/null; then
        echo "   PostgreSQL ready (attempt $i/$MAX_ATTEMPTS)"
        break
    fi
    if [ "$i" -eq "$MAX_ATTEMPTS" ]; then
        echo "❌ PostgreSQL did not become ready within $((MAX_ATTEMPTS * SLEEP_SECS))s." >&2
        exit 1
    fi
    sleep "$SLEEP_SECS"
done

# ---- bounded Redis readiness --------------------------------------------
echo "⏳ Waiting for Redis …"
for i in $(seq 1 "$MAX_ATTEMPTS"); do
    if "${COMPOSE[@]}" exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
        echo "   Redis ready (attempt $i/$MAX_ATTEMPTS)"
        break
    fi
    if [ "$i" -eq "$MAX_ATTEMPTS" ]; then
        echo "❌ Redis did not become ready within $((MAX_ATTEMPTS * SLEEP_SECS))s." >&2
        exit 1
    fi
    sleep "$SLEEP_SECS"
done

# ---- backend dependencies -----------------------------------------------
echo "🔧 Installing backend dependencies …"
cd "$REPO_ROOT/backend"
pip install -r requirements.txt

# ---- public Alembic migration -------------------------------------------
echo "🗄️ Running public Alembic migration …"
alembic upgrade head

# ---- resolve DATABASE_URL from core.config.settings (never printed) -----
RESOLVED_DATABASE_URL="$(python -c "from core.config import settings; print(settings.DATABASE_URL)" 2>/dev/null)" \
    || { echo "❌ Could not resolve DATABASE_URL from core.config.settings." >&2; exit 1; }
if [ -z "$RESOLVED_DATABASE_URL" ]; then
    echo "❌ Resolved DATABASE_URL is empty." >&2
    exit 1
fi

# ---- verify DATABASE_URL matches the running Compose PostgreSQL ----------
# Parse the tuple safely via an env var (never in argv, never printed).
DB_TUPLE="$(DATABASE_URL="$RESOLVED_DATABASE_URL" python -c "
import os
from urllib.parse import urlparse
u = urlparse(os.environ['DATABASE_URL'].replace('postgresql+asyncpg', 'postgresql'))
print(u.username or '', u.password or '', u.hostname or '', u.port or 5432, u.path.lstrip('/') or '', sep='|')
" 2>/dev/null)" || { echo "❌ Could not parse DATABASE_URL." >&2; exit 1; }
DB_USER="${DB_TUPLE%%|*}"; _T="${DB_TUPLE#*|}"
DB_PASS="${_T%%|*}"; _T="${_T#*|}"
DB_HOST="${_T%%|*}"; _T="${_T#*|}"
DB_PORT="${_T%%|*}"; _T="${_T#*|}"
DB_NAME="${_T}"
# NOTE: DB_PASS is never printed, compared, or echoed.

# Read the container-owned identity from the running Compose postgres service.
COMPOSE_ID="$( "${COMPOSE[@]}" exec -T postgres sh -ec 'printf "%s|%s" "$POSTGRES_USER" "$POSTGRES_DB"' 2>/dev/null )" \
    || { echo "❌ Could not read Compose postgres identity." >&2; exit 1; }
COMPOSE_USER="${COMPOSE_ID%%|*}"; COMPOSE_DB="${COMPOSE_ID#*|}"

# Fail clearly BEFORE Alembic/bootstrap on any identity mismatch.
if [ -z "$DB_USER" ] || [ -z "$DB_NAME" ]; then
    echo "❌ DATABASE_URL must carry a username and database name." >&2
    exit 1
fi
case "$DB_HOST" in
    localhost|127.0.0.1|::1) ;;
    *) echo "❌ DATABASE_URL host must resolve to the locally published Compose service." >&2; exit 1 ;;
esac
if [ "$DB_PORT" != "${POSTGRES_PUBLISHED_PORT:-5432}" ]; then
    echo "❌ DATABASE_URL port must match the published development port (${POSTGRES_PUBLISHED_PORT:-5432})." >&2
    exit 1
fi
if [ "$DB_USER" != "$COMPOSE_USER" ]; then
    echo "❌ DATABASE_URL user does not match Compose postgres (POSTGRES_USER)." >&2
    exit 1
fi
if [ "$DB_NAME" != "$COMPOSE_DB" ]; then
    echo "❌ DATABASE_URL database does not match Compose postgres (POSTGRES_DB)." >&2
    exit 1
fi

# ---- canonical tenant bootstrap (DATABASE_URL via env, not argv) --------
echo "🏗️ Bootstrapping tenant schema …"
export DATABASE_URL="$RESOLVED_DATABASE_URL"
python scripts/bootstrap_tenant_schema.py "${DEFAULT_TENANT_SCHEMA:-t_dev}"
unset DATABASE_URL

cd "$REPO_ROOT"

# ---- frontend dependencies (pnpm frozen-lockfile) -----------------------
echo "🎨 Setting up frontend …"
cd "$REPO_ROOT/frontend"

if command -v pnpm &> /dev/null; then
    PNPM_BIN="pnpm"
elif command -v corepack &> /dev/null; then
    corepack enable
    PNPM_BIN="pnpm"
else
    echo "❌ pnpm is not installed and corepack is not available." >&2
    echo "   Install pnpm (https://pnpm.io/installation) or enable corepack." >&2
    exit 1
fi
"$PNPM_BIN" install --frozen-lockfile

cd "$REPO_ROOT"

# ---- done ---------------------------------------------------------------
echo ""
echo "✅ Setup complete!"
echo ""
echo "To start the development servers:"
echo "  1. Backend : cd backend && uvicorn main:app --reload"
echo "  2. Frontend: cd frontend && pnpm run dev"
echo ""
echo "Or use Docker Compose:"
echo "  ${COMPOSE[*]} up backend frontend"
