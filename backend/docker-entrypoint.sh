#!/bin/sh
# Mpango ERP backend RUNTIME entrypoint.
#
# R1-R2 (CTO-AUTH-ORDER-R2-DB-AUTHORITY-INTEGRATION-R1-R2-RUNTIME-ENTRYPOINT-CLOSURE-2026-09-19):
# this entrypoint performs ZERO migration, provisioning, grant, public DDL or
# tenant-bootstrap writes.  The container receives ONLY the runtime-role
# DATABASE_URL, so the write steps the old entrypoint performed (public
# migrations, tenant bootstrap) are unauthorized under the three-role
# contract and are owned exclusively by the five-stage setup.sh sequence,
# which must complete BEFORE the runtime starts:
#
#   1 provision (admin) -> 2 alembic through 039 (migration authority)
#   -> 3 minimum grants -> 4 read-only verify -> 5 tenant bootstrap (runtime)
#
# If this container is started against a database that has not completed
# that sequence, API requests fail closed (missing relations) instead of the
# runtime silently escalating its own privileges.

set -e

echo "=== Mpango ERP Backend Startup (runtime only) ==="

# Strictly read-only readiness gate: a single SELECT against the runtime
# URL.  No DDL, no migrations, no bootstrap — the gate may only observe.
echo "[ready] Checking runtime database reachability (read-only)..."
python - <<'PY'
import asyncio
import os
import sys
import time

url = os.environ.get("DATABASE_URL", "")
if not url:
    print("[ready] DATABASE_URL is required", file=sys.stderr)
    sys.exit(1)

async def probe() -> bool:
    import asyncpg
    try:
        conn = await asyncpg.connect(url)
    except Exception as exc:
        print(f"[ready] not ready: {type(exc).__name__}")
        return False
    try:
        await conn.fetchval("SELECT 1")
    finally:
        await conn.close()
    return True

deadline = time.monotonic() + 30
while True:
    if asyncio.run(probe()):
        print("[ready] runtime database reachable")
        break
    if time.monotonic() > deadline:
        print("[ready] runtime database unreachable after 30s", file=sys.stderr)
        sys.exit(1)
    time.sleep(2)
PY

echo "Starting Uvicorn..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
