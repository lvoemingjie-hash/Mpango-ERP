#!/bin/sh
set -e

echo "=== Mpango ERP Backend Startup ==="

# ---------------------------------------------------------------------------
# NOTE: Automatic Alembic migrations are DISABLED.
#
# This project uses a multi-tenant migration architecture where migrations
# must be run separately for public schema and each tenant schema:
#
#   # Public schema (wholesalers table):
#   docker compose exec backend alembic upgrade head
#
#   # Tenant schema (users, roles, orders, etc.):
#   docker compose exec backend alembic upgrade head -x tenant_schema=t_dev
#
# Running "alembic upgrade head" without -x tenant_schema only creates
# public tables. Later migrations (007+) assume tenant tables exist and
# will fail if run in public-only context.
#
# For first-time setup, use: deploy/init_staging.sh
# ---------------------------------------------------------------------------

echo "Starting Uvicorn..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
