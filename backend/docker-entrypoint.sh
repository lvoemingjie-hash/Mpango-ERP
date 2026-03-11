#!/bin/sh
set -e

echo "=== Mpango ERP Backend Startup ==="

# ---------------------------------------------------------------------------
# Multi-tenant Alembic migration strategy
#
# This project uses a schema-per-tenant architecture where migrations must
# be run separately for the public schema and each tenant schema:
#
#   1. Public schema  — wholesalers, invitations, retailers, etc.
#   2. Tenant schema  — users, roles, orders, payments, inventory, etc.
#
# The DEFAULT_TENANT_SCHEMA env var (default: t_dev) is used by
# MockAuthStrategy when MPANGO_ENV=test.  We must ensure this schema is
# fully migrated before Uvicorn starts, otherwise all API requests that
# resolve to this tenant will fail with "relation does not exist".
# ---------------------------------------------------------------------------

TENANT="${DEFAULT_TENANT_SCHEMA:-t_dev}"

echo "[migrate] Running public schema migrations..."
alembic upgrade head
echo "[migrate] Public schema up-to-date."

echo "[bootstrap] Bootstrapping tenant schema '${TENANT}'..."
python scripts/bootstrap_tenant_schema.py "${TENANT}"

echo "Starting Uvicorn..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
