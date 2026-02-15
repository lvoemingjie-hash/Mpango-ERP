#!/usr/bin/env bash
# =============================================================================
# Track E2: Reset Staging Environment
#
# Drops all tenant schemas, runs public migrations, bootstraps tenant schema
# via the seed script, and populates demo data.
#
# Usage:
#   # From repo root — targets the Docker Compose stack:
#   bash scripts/reset-staging.sh
#
#   # Or inside the backend container:
#   bash /app/../scripts/reset-staging.sh --inside-container
#
# Prerequisites:
#   - Docker Compose stack running (postgres healthy)
#   - POSTGRES_PASSWORD set in environment or .env
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
COMPOSE_CMD="docker compose"
BACKEND_SERVICE="backend"
POSTGRES_SERVICE="postgres"

DB_NAME="${POSTGRES_DB:-mpango_erp}"
DB_USER="${POSTGRES_USER:-mpango}"

# Detect if we're inside the container already
INSIDE_CONTAINER=false
if [[ "${1:-}" == "--inside-container" ]]; then
    INSIDE_CONTAINER=true
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
run_in_backend() {
    if $INSIDE_CONTAINER; then
        eval "$@"
    else
        $COMPOSE_CMD exec -T "$BACKEND_SERVICE" bash -c "$*"
    fi
}

run_psql() {
    if $INSIDE_CONTAINER; then
        PGPASSWORD="${POSTGRES_PASSWORD}" psql -h postgres -U "$DB_USER" -d "$DB_NAME" -c "$1"
    else
        $COMPOSE_CMD exec -T "$POSTGRES_SERVICE" \
            psql -U "$DB_USER" -d "$DB_NAME" -c "$1"
    fi
}

echo ""
echo "============================================="
echo "  Mpango ERP — Reset Staging Environment"
echo "============================================="
echo ""

# ---------------------------------------------------------------------------
# Step 1: Drop all tenant schemas (t_*)
# ---------------------------------------------------------------------------
echo "[1/4] Dropping tenant schemas..."

SCHEMAS=$(run_psql "SELECT string_agg(schema_name, ',') FROM information_schema.schemata WHERE schema_name LIKE 't_%';" 2>/dev/null | sed -n '3p' | tr -d ' ')

if [[ -n "$SCHEMAS" && "$SCHEMAS" != "" ]]; then
    IFS=',' read -ra SCHEMA_ARRAY <<< "$SCHEMAS"
    for schema in "${SCHEMA_ARRAY[@]}"; do
        schema=$(echo "$schema" | tr -d '[:space:]')
        if [[ -n "$schema" ]]; then
            echo "  Dropping schema: $schema"
            run_psql "DROP SCHEMA IF EXISTS \"$schema\" CASCADE;" >/dev/null 2>&1
        fi
    done
else
    echo "  No tenant schemas found."
fi

# Reset alembic version so migrations re-run cleanly
run_psql "DELETE FROM public.alembic_version;" >/dev/null 2>&1 || true

# Drop public tables (wholesalers, retailers, etc.) for a clean slate
echo "  Dropping public tables..."
run_psql "DROP TABLE IF EXISTS public.wholesaler_retailer_bindings CASCADE;" >/dev/null 2>&1 || true
run_psql "DROP TABLE IF EXISTS public.invitations CASCADE;" >/dev/null 2>&1 || true
run_psql "DROP TABLE IF EXISTS public.retailers CASCADE;" >/dev/null 2>&1 || true
run_psql "DROP TABLE IF EXISTS public.wholesalers CASCADE;" >/dev/null 2>&1 || true
echo "  Done."

# ---------------------------------------------------------------------------
# Step 2: Run public schema migrations (001-006)
# ---------------------------------------------------------------------------
echo ""
echo "[2/4] Running Alembic migrations (public schema)..."

if $INSIDE_CONTAINER; then
    cd /app
    MPANGO_ENV=staging REPORTING_USER_PASSWORD="${REPORTING_USER_PASSWORD:-ReportingPass_staging_2026}" \
        python -m alembic upgrade 006_phase_b6_payments_idempotency_key
else
    $COMPOSE_CMD exec -T "$BACKEND_SERVICE" bash -c \
        'MPANGO_ENV=staging REPORTING_USER_PASSWORD="${REPORTING_USER_PASSWORD:-ReportingPass_staging_2026}" python -m alembic upgrade 006_phase_b6_payments_idempotency_key'
fi

echo "  Public migrations complete."

# ---------------------------------------------------------------------------
# Step 3: Seed demo data (uses backend Services + guardrails)
# ---------------------------------------------------------------------------
echo ""
echo "[3/4] Seeding demo data..."

if $INSIDE_CONTAINER; then
    cd /app
    MPANGO_ENV=staging python /app/../scripts/seed_demo_data.py --allow-production
else
    # Copy seed script into container and run
    $COMPOSE_CMD cp "$REPO_ROOT/scripts/seed_demo_data.py" "$BACKEND_SERVICE:/tmp/seed_demo_data.py"
    $COMPOSE_CMD exec -T "$BACKEND_SERVICE" bash -c \
        'MPANGO_ENV=staging python /tmp/seed_demo_data.py --allow-production'
fi

# ---------------------------------------------------------------------------
# Step 4: Verify
# ---------------------------------------------------------------------------
echo ""
echo "[4/4] Verifying..."

WHOLESALER_COUNT=$(run_psql "SELECT count(*) FROM public.wholesalers;" 2>/dev/null | sed -n '3p' | tr -d ' ')
echo "  Wholesalers: $WHOLESALER_COUNT"

RETAILER_COUNT=$(run_psql "SELECT count(*) FROM public.retailers;" 2>/dev/null | sed -n '3p' | tr -d ' ')
echo "  Retailers:   $RETAILER_COUNT"

# Get the demo tenant schema name
TENANT_SCHEMA=$(run_psql "SELECT 't_' || replace(id::text, '-', '') FROM public.wholesalers WHERE code = 'DEMO001';" 2>/dev/null | sed -n '3p' | tr -d ' ')

if [[ -n "$TENANT_SCHEMA" ]]; then
    ORDER_COUNT=$(run_psql "SELECT count(*) FROM \"$TENANT_SCHEMA\".orders;" 2>/dev/null | sed -n '3p' | tr -d ' ')
    SKU_COUNT=$(run_psql "SELECT count(*) FROM \"$TENANT_SCHEMA\".skus;" 2>/dev/null | sed -n '3p' | tr -d ' ')
    LEDGER_COUNT=$(run_psql "SELECT count(*) FROM \"$TENANT_SCHEMA\".ledger_entries;" 2>/dev/null | sed -n '3p' | tr -d ' ')
    USER_COUNT=$(run_psql "SELECT count(*) FROM \"$TENANT_SCHEMA\".users;" 2>/dev/null | sed -n '3p' | tr -d ' ')
    echo "  Users:       $USER_COUNT"
    echo "  SKUs:        $SKU_COUNT"
    echo "  Orders:      $ORDER_COUNT"
    echo "  Ledger:      $LEDGER_COUNT"
fi

echo ""
echo "============================================="
echo "  Staging Reset Complete!"
echo "  Login: admin@mpango.demo / DemoAdmin2026!"
echo "============================================="
echo ""
