#!/usr/bin/env bash
# =============================================================================
# Track E2: Reset Staging Environment
#
# Drops all tenant schemas, runs public migrations, bootstraps tenant schema
# via the seed script, and populates demo data.
#
# Usage:
#   # From repo root - targets the Docker Compose stack:
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

psql_scalar() {
    run_psql "$1" 2>/dev/null | sed -n '3p' | tr -d ' '
}

assert_tenant_table() {
    local table_name="$1"
    local exists
    exists=$(psql_scalar "SELECT 1 FROM information_schema.tables WHERE table_schema = '$TENANT_SCHEMA' AND table_name = '$table_name';")
    if [[ "$exists" == "1" ]]; then
        echo "  table:$table_name OK"
        return
    fi

    echo "  table:$table_name MISSING"
    exit 1
}

assert_tenant_column() {
    local table_name="$1"
    local column_name="$2"
    local exists
    exists=$(psql_scalar "SELECT 1 FROM information_schema.columns WHERE table_schema = '$TENANT_SCHEMA' AND table_name = '$table_name' AND column_name = '$column_name';")
    if [[ "$exists" == "1" ]]; then
        echo "  column:$table_name.$column_name OK"
        return
    fi

    echo "  column:$table_name.$column_name MISSING"
    exit 1
}

echo ""
echo "============================================="
echo "  Mpango ERP - Reset Staging Environment"
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
# Step 2: Run public schema migrations to current head
# ---------------------------------------------------------------------------
echo ""
echo "[2/4] Running Alembic migrations (public schema)..."

if $INSIDE_CONTAINER; then
    cd /app
    : "${REPORTING_USER_PASSWORD:?REPORTING_USER_PASSWORD environment variable must be set}"
    MPANGO_ENV=staging python -m alembic upgrade head
else
    $COMPOSE_CMD exec -T "$BACKEND_SERVICE" bash -c \
        ': "${REPORTING_USER_PASSWORD:?REPORTING_USER_PASSWORD environment variable must be set}"; MPANGO_ENV=staging python -m alembic upgrade head'
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
TENANT_SCHEMA=$(psql_scalar "SELECT 't_' || replace(id::text, '-', '') FROM public.wholesalers WHERE code = 'DEMO001';")

if [[ -z "$TENANT_SCHEMA" ]]; then
    echo "  tenant_schema MISSING"
    exit 1
fi

echo "  tenant_schema:$TENANT_SCHEMA OK"

echo "  Reconciling demo tenant schema to current MVP contract..."
if $INSIDE_CONTAINER; then
    cd /app
    MPANGO_ENV=staging python /app/scripts/bootstrap_tenant_schema.py "$TENANT_SCHEMA"
else
    $COMPOSE_CMD cp "$REPO_ROOT/scripts/bootstrap_tenant_schema.py" "$BACKEND_SERVICE:/tmp/bootstrap_tenant_schema.py"
    $COMPOSE_CMD exec -T "$BACKEND_SERVICE" bash -c \
        "MPANGO_ENV=staging python /tmp/bootstrap_tenant_schema.py \"$TENANT_SCHEMA\""
fi

echo "  Verifying current MVP tenant schema contract..."
for table_name in \
    import_runs \
    inventory_reservations \
    intake_workspaces \
    intake_uploads \
    intake_product_rows \
    intake_validation_issues
do
    assert_tenant_table "$table_name"
done

for column_name in \
    apply_status \
    applied_at \
    applied_by \
    apply_result
do
    assert_tenant_column intake_workspaces "$column_name"
done

for column_name in \
    apply_status \
    target_sku_id \
    apply_error_code \
    apply_error_message
do
    assert_tenant_column intake_product_rows "$column_name"
done

if [[ -n "$TENANT_SCHEMA" ]]; then
    ORDER_COUNT=$(psql_scalar "SELECT count(*) FROM \"$TENANT_SCHEMA\".orders;")
    SKU_COUNT=$(psql_scalar "SELECT count(*) FROM \"$TENANT_SCHEMA\".skus;")
    LEDGER_COUNT=$(psql_scalar "SELECT count(*) FROM \"$TENANT_SCHEMA\".ledger_entries;")
    USER_COUNT=$(psql_scalar "SELECT count(*) FROM \"$TENANT_SCHEMA\".users;")
    echo "  Users:       $USER_COUNT"
    echo "  SKUs:        $SKU_COUNT"
    echo "  Orders:      $ORDER_COUNT"
    echo "  Ledger:      $LEDGER_COUNT"
fi

echo ""
echo "============================================="
echo "  Staging Reset Complete!"
echo "  Login: admin@mpango.demo"
echo "============================================="
echo ""
