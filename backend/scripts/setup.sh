#!/bin/bash
set -Eeuo pipefail

# ---------------------------------------------------------------------------
# Mpango ERP Setup Script  (H7-R5 — native fail-closed repair)
#
# Requires: bash >= 4, Docker, pnpm (or corepack), Python 3.11+, pip.
# Invoke from the repository root (the script resolves its own location).
# ---------------------------------------------------------------------------

trap 'echo "❌ Setup failed at line $LINENO.  No changes have been applied." >&2; exit 1' ERR

# ---- resolve repository root from script location -----------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

echo "🚀 Setting up Mpango ERP (root: $REPO_ROOT) …"

# ---- docker-compose / docker compose ------------------------------------
DOCKER_COMPOSE=""
if command -v docker &> /dev/null; then
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    elif command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE="docker-compose"
    fi
fi
if [ -z "$DOCKER_COMPOSE" ]; then
    echo "❌ Neither 'docker compose' (Docker Compose v2) nor 'docker-compose' (v1) is available." >&2
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
$DOCKER_COMPOSE up -d postgres redis

# ---- bounded health polling ---------------------------------------------
MAX_ATTEMPTS=30
SLEEP_SECS=2

# PostgreSQL (pg_isready in container)
echo "⏳ Waiting for PostgreSQL …"
for i in $(seq 1 $MAX_ATTEMPTS); do
    if docker exec "$($DOCKER_COMPOSE ps -q postgres)" pg_isready -U postgres &> /dev/null; then
        echo "   PostgreSQL ready (attempt $i)"
        break
    fi
    if [ "$i" -eq "$MAX_ATTEMPTS" ]; then
        echo "❌ PostgreSQL did not become ready within $((MAX_ATTEMPTS * SLEEP_SECS))s" >&2
        exit 1
    fi
    sleep "$SLEEP_SECS"
done

# Redis
echo "⏳ Waiting for Redis …"
for i in $(seq 1 $MAX_ATTEMPTS); do
    if docker exec "$($DOCKER_COMPOSE ps -q redis)" redis-cli ping | grep -q PONG; then
        echo "   Redis ready (attempt $i)"
        break
    fi
    if [ "$i" -eq "$MAX_ATTEMPTS" ]; then
        echo "❌ Redis did not become ready within $((MAX_ATTEMPTS * SLEEP_SECS))s" >&2
        exit 1
    fi
    sleep "$SLEEP_SECS"
done

# ---- backend dependencies + migrations ----------------------------------
echo "🔧 Setting up backend …"
cd "$REPO_ROOT/backend"
pip install -r requirements.txt

echo "🗄️ Running database migrations …"
alembic upgrade head                                      # public schema first
alembic -x tenant_schema="${DEFAULT_TENANT_SCHEMA:-t_dev}" upgrade head

# ---- frontend dependencies (pnpm frozen-lockfile) -----------------------
echo "🎨 Setting up frontend …"
cd "$REPO_ROOT/frontend"

if command -v pnpm &> /dev/null; then
    PNPM="pnpm"
elif command -v corepack &> /dev/null; then
    corepack enable
    PNPM="pnpm"
else
    echo "❌ pnpm is not installed and corepack is not available." >&2
    echo "   Install pnpm (https://pnpm.io/installation) or enable corepack." >&2
    exit 1
fi
$PNPM install --frozen-lockfile

# ---- done ---------------------------------------------------------------
echo ""
echo "✅ Setup complete!"
echo ""
echo "To start the development servers:"
echo "  1. Backend : cd backend && uvicorn main:app --reload"
echo "  2. Frontend: cd frontend && pnpm run dev"
echo ""
echo "Or use Docker Compose:"
echo "  $DOCKER_COMPOSE up backend frontend"
