#!/usr/bin/env python3
"""Read-only runtime readiness gate (R1-R4 extraction of the entrypoint
heredoc; CTO-AUTH-ORDER-R2-DB-AUTHORITY-INTEGRATION-R1-R4-BOUNDED-RUNTIME-CONTRACT-CORRECTION-2026-09-19).

The backend container receives ONLY the runtime-role DATABASE_URL.  This gate
verifies, strictly read-only, that the five-stage setup completed:

  * public migration head is exactly ``039_order_credit_holds``;
  * the migration-owned ledger guard matches its authority contract and the
    public binding-balance contract is intact (the product's own read-only
    catalog assertions);
  * the default tenant bootstrap state exists.

Contract notes (R1-R4):
  * BOTH preflight-accepted URL schemes (``postgresql://`` and
    ``postgresql+asyncpg://``) are normalized onto one SQLAlchemy async
    engine — the URL is never handed to a raw driver whose DSN grammar
    differs, and no string replacement can produce a double driver suffix.
  * Refusal reasons are scoped to ONE attempt: ``evaluate_contract`` returns
    the attempt's reasons and ``run_gate`` clears them per attempt, so a
    transient first failure followed by a valid attempt inside the retry
    budget starts successfully, while permanent failure still exits
    non-zero.

This module performs NO writes: catalog reads, SELECTs and the two product
read-only assertions only.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

REQUIRED_REVISION = "039_order_credit_holds"
DEFAULT_REQUIRED_TENANT_TABLE = "order_credit_holds"


def normalize_async_url(url: str) -> str:
    """Map both accepted PostgreSQL schemes onto the SQLAlchemy asyncpg
    dialect without string replacement (no double-suffix risk)."""
    parts = urlsplit(url)
    if parts.scheme not in ("postgresql", "postgresql+asyncpg"):
        raise ValueError(
            f"unsupported DATABASE_URL scheme: {parts.scheme!r} "
            "(expected postgresql:// or postgresql+asyncpg://)")
    return parts._replace(scheme="postgresql+asyncpg").geturl()


def evaluate_contract(database_url: str, tenant: str = "t_dev",
                      backend_dir: str | os.PathLike | None = None) -> list[str]:
    """One readiness attempt.  Returns the attempt's named refusal reasons;
    an EMPTY list means the completed five-stage contract is present."""
    reasons: list[str] = []

    def reason(message: str) -> None:
        reasons.append(message)

    async def run() -> None:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        backend = Path(backend_dir).resolve() if backend_dir \
            else Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "rrg_bootstrap", backend / "scripts" / "bootstrap_tenant_schema.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("bootstrap script not found")
        bts = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bts)

        engine = create_async_engine(normalize_async_url(database_url))
        try:
            async with engine.connect() as conn:
                head = (await conn.execute(
                    text("SELECT version_num FROM public.alembic_version")
                )).scalar()
                if head != REQUIRED_REVISION:
                    reason(
                        f"migration head is {head!r}, requires exactly "
                        f"{REQUIRED_REVISION!r} - the five-stage setup has "
                        "not completed")
                    return
                tenant_table = (await conn.execute(
                    text("SELECT to_regclass(:qualified) IS NOT NULL"),
                    {"qualified": f'"{tenant}".{DEFAULT_REQUIRED_TENANT_TABLE}'}
                )).scalar()
                if not tenant_table:
                    reason(
                        f"default tenant bootstrap state missing: "
                        f"{tenant!r}.{DEFAULT_REQUIRED_TENANT_TABLE} does "
                        "not exist - setup phase 5 has not run")
                    return
                # the product's own read-only catalog assertions (named
                # LedgerGuardAuthorityError / PublicContractError on drift)
                await bts._assert_ledger_guard_function_authority(conn)
                await bts._assert_public_binding_balance_contract(conn)
        except Exception as exc:  # noqa: BLE001 — named, credential-free
            reason(f"{type(exc).__name__}: {exc}")
        finally:
            await engine.dispose()

    asyncio.run(run())
    return reasons


def run_gate(database_url: str, tenant: str = "t_dev",
             backend_dir: str | os.PathLike | None = None,
             deadline_seconds: float = 30.0, interval_seconds: float = 2.0,
             stream=None) -> int:
    """Retry loop.  Refusal reasons are scoped to ONE attempt (cleared at the
    start of every attempt): fail-then-ready inside the budget starts
    successfully; permanent failure returns 1."""
    stream = stream or sys.stderr
    deadline = time.monotonic() + deadline_seconds
    while True:
        # ONE attempt, ONE reason set — never carried across attempts
        reasons = evaluate_contract(database_url, tenant, backend_dir)
        if not reasons:
            print("[ready] five-stage setup contract verified (read-only)",
                  file=stream)
            return 0
        for reason in reasons:
            print(f"[ready] REFUSED: {reason}", file=stream)
        if time.monotonic() > deadline:
            print("[ready] the five-stage setup contract is not satisfied; "
                  "refusing to start (run backend/scripts/setup.sh first)",
                  file=stream)
            return 1
        time.sleep(interval_seconds)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Read-only five-stage setup readiness gate")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--tenant",
                        default=os.environ.get("DEFAULT_TENANT_SCHEMA", "t_dev"))
    args = parser.parse_args()
    if not args.database_url:
        print("[ready] DATABASE_URL is required", file=sys.stderr)
        return 1
    return run_gate(args.database_url, args.tenant)


if __name__ == "__main__":
    sys.exit(main())
