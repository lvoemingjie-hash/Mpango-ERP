#!/bin/bash
# Mpango ERP Setup Script  (H7-R5-R1 — canonical tenant bootstrap)
# Requires: bash >= 4, Docker (compose v1 or v2), Python 3.11+, pip, pnpm/corepack.
set -Eeuo pipefail

# ---------------------------------------------------------------------------
# ERR trap: preserve non-zero exit, identify the failing line, and truthfully
# state that setup stopped with possible partial local artifacts.  Never claim
# rollback or "no changes applied"; never print "Setup complete" after failure.
# ---------------------------------------------------------------------------
_on_err() {
    echo "❌ Setup stopped at line $1 (exit status preserved). Partial local artifacts may exist; inspect and re-run after fixing the cause." >&2
    exit 1
}
trap '_on_err $LINENO' ERR

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

# ---- directories --------------------------------------------------------
echo "📁 Creating directories …"
mkdir -p logs uploads

# ---- environment files --------------------------------------------------
if [ ! -f backend/.env ]; then
    echo "📝 Creating backend .env file …"
    cp backend/.env.example backend/.env
fi
if [ ! -f frontend/.env ]; then
    echo "📝 Creating frontend .env file …"
    echo "VITE_API_URL=http://localhost:8000/api/v1" > frontend/.env
fi

# ---- start Docker services ----------------------------------------------
echo "🐳 Starting Docker services …"
"${COMPOSE[@]}" up -d postgres redis

# ---- bounded PostgreSQL readiness (Compose-scoped, no hardcoded user) ---
echo "⏳ Waiting for PostgreSQL …"
MAX_ATTEMPTS="${SETUP_TIMEOUT_ATTEMPTS:-30}"
SLEEP_SECS="${SETUP_TIMEOUT_INTERVAL:-2}"
for i in $(seq 1 "$MAX_ATTEMPTS"); do
    if "${COMPOSE[@]}" exec -T postgres \
         pg_isready -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-mpango_erp}" \
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

# ---- canonical tenant bootstrap (replaces the alembic -x no-op) ---------
echo "🏗️ Bootstrapping tenant schema …"
python scripts/bootstrap_tenant_schema.py \
    "${DEFAULT_TENANT_SCHEMA:-t_dev}" \
    --database-url "$RESOLVED_DATABASE_URL"

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
