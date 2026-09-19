#!/bin/sh
# Mpango ERP backend RUNTIME entrypoint.
#
# R1-R3 (CTO-AUTH-ORDER-R2-DB-AUTHORITY-INTEGRATION-R1-R3-TOPOLOGY-AND-READINESS-CLOSURE-2026-09-19):
# this entrypoint performs ZERO migration, provisioning, grant, public DDL or
# tenant-bootstrap writes.  The container receives ONLY the runtime-role
# DATABASE_URL (container context), so every write the old entrypoint
# performed is owned exclusively by the five-stage setup.sh sequence, which
# must complete BEFORE the runtime starts:
#
#   1 provision (admin) -> 2 alembic through 039 (migration authority)
#   -> 3 minimum grants -> 4 read-only verify -> 5 tenant bootstrap (runtime)
#
# Because /health/live is a liveness probe only (no dependency checks), the
# entrypoint enforces setup completion ONCE, here, with a strictly READ-ONLY
# structural gate: the runtime role can connect, the public migration head
# is exactly 039_order_credit_holds, the migration-owned ledger guard
# matches its exact authority contract, the public credit-hold balance
# contract is intact, and the default tenant bootstrap state exists.  Any
# refusal exits non-zero — the container never becomes a partially prepared
# traffic-ready backend.  The gate issues SELECT/catalog reads only.

set -e

echo "=== Mpango ERP Backend Startup (runtime only) ==="

# Read-only readiness gate.  No DDL, no migrations, no bootstrap — observe
# only, and refuse unless the completed five-stage contract is present.
echo "[ready] Verifying the five-stage setup contract (read-only)..."
python - <<'PY'
import asyncio
import importlib.util
import os
import sys
import time
from pathlib import Path

url = os.environ.get("DATABASE_URL", "")
if not url:
    print("[ready] DATABASE_URL is required", file=sys.stderr)
    sys.exit(1)

REQUIRED_REVISION = "039_order_credit_holds"
DEFAULT_TENANT = os.environ.get("DEFAULT_TENANT_SCHEMA", "t_dev")

REASONS = []


async def _connect_once():
    import asyncpg
    conn = await asyncpg.connect(url)
    try:
        head = await conn.fetchval(
            "SELECT version_num FROM public.alembic_version")
        if head != REQUIRED_REVISION:
            REASONS.append(
                f"migration head is {head!r}, requires exactly "
                f"{REQUIRED_REVISION!r} - the five-stage setup has not "
                "completed")
            return
        tenant_table = await conn.fetchval(
            "SELECT to_regclass($1) IS NOT NULL",
            f'"{DEFAULT_TENANT}".order_credit_holds')
        if not tenant_table:
            REASONS.append(
                f"default tenant bootstrap state missing: "
                f'{DEFAULT_TENANT!r}.order_credit_holds does not exist - '
                "setup phase 5 has not run")
            return
    finally:
        await conn.close()


async def _structural_contract():
    from sqlalchemy.ext.asyncio import create_async_engine

    backend = Path.cwd()
    spec = importlib.util.spec_from_file_location(
        "r1r3_gate_bootstrap", backend / "scripts" / "bootstrap_tenant_schema.py")
    bts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bts)

    engine = create_async_engine(
        url.replace("postgresql://", "postgresql+asyncpg://", 1))
    try:
        async with engine.connect() as conn:
            # read-only product assertions: catalog-only, fail-closed
            await bts._assert_ledger_guard_function_authority(conn)
            await bts._assert_public_binding_balance_contract(conn)
    finally:
        await engine.dispose()


deadline = time.monotonic() + 30
while True:
    try:
        asyncio.run(_connect_once())
        asyncio.run(_structural_contract())
    except Exception as exc:
        # the read-only product assertions raise named failures
        # (LedgerGuardAuthorityError / PublicContractError / ...) — surface
        # the message, never any credential material
        REASONS.append(f"{type(exc).__name__}: {exc}")
    if not REASONS:
        print("[ready] five-stage setup contract verified (read-only)")
        break
    for reason in REASONS:
        print(f"[ready] REFUSED: {reason}", file=sys.stderr)
    if time.monotonic() > deadline:
        print("[ready] the five-stage setup contract is not satisfied; "
              "refusing to start (run backend/scripts/setup.sh first)",
              file=sys.stderr)
        sys.exit(1)
    time.sleep(2)
PY

echo "Starting Uvicorn..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
