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


# R1-R7: read-only reporting identity probes.  Every statement is a pure
# SELECT/catalog read; the probe issues no DDL and no DML and never tests
# write refusal by writing.
_REPORTING_PROBE_SQL = (
    ("identity", "SELECT current_user"),
    ("database", "SELECT current_database()"),
    ("role_membership",
     "SELECT pg_has_role('reporting_user', 'reporting_role', 'MEMBER')"),
    ("role_flags",
     "SELECT rolsuper, rolcreaterole, rolcreatedb FROM pg_roles "
     "WHERE rolname = 'reporting_user'"),
    ("public_schema_create",
     "SELECT has_schema_privilege('reporting_user', 'public', 'CREATE')"),
    ("tenant_schema_create",
     "SELECT has_schema_privilege('reporting_user', :tenant, 'CREATE')"),
    ("read_only_setting",
     "SELECT current_setting('default_transaction_read_only')"),
    ("statement_timeout",
     "SELECT current_setting('statement_timeout')"),
    ("public_select_wholesalers",
     "SELECT has_table_privilege('reporting_user', 'public.wholesalers', 'SELECT')"),
    ("public_select_retailers",
     "SELECT has_table_privilege('reporting_user', 'public.retailers', 'SELECT')"),
    ("public_select_wholesaler_retailer_bindings",
     "SELECT has_table_privilege('reporting_user', "
     "'public.wholesaler_retailer_bindings', 'SELECT')"),
    ("public_insert_wholesalers",
     "SELECT has_table_privilege('reporting_user', 'public.wholesalers', 'INSERT')"),
    ("public_update_wholesalers",
     "SELECT has_table_privilege('reporting_user', 'public.wholesalers', 'UPDATE')"),
    ("public_delete_wholesalers",
     "SELECT has_table_privilege('reporting_user', 'public.wholesalers', 'DELETE')"),
    ("tenant_select_rpt_receivables_summary",
     "SELECT has_table_privilege('reporting_user', :tenant_table, 'SELECT')"),
    ("tenant_insert_rpt_receivables_summary",
     "SELECT has_table_privilege('reporting_user', :tenant_table, 'INSERT')"),
    ("tenant_update_rpt_receivables_summary",
     "SELECT has_table_privilege('reporting_user', :tenant_table, 'UPDATE')"),
    ("tenant_delete_rpt_receivables_summary",
     "SELECT has_table_privilege('reporting_user', :tenant_table, 'DELETE')"),
)


def _normalize_reporting_async_url(url: str) -> str:
    """Structural single normalization of the reporting DSN (R1-R7): same
    two-scheme policy as the runtime URL; errors are credential-free."""
    parts = urlsplit(url)
    if parts.scheme not in ("postgresql", "postgresql+asyncpg"):
        raise ValueError(
            "unsupported REPORTING_DATABASE_URL scheme (expected "
            "postgresql:// or postgresql+asyncpg://)")
    return parts._replace(scheme="postgresql+asyncpg").geturl()


def _timeout_ms(raw) -> int:
    value = str(raw).strip().lower()
    if value.endswith("ms"):
        return int(value[:-2])
    if value.endswith("s"):
        return int(value[:-1]) * 1000
    return int(value)


async def _probe_reporting(reason, tenant: str, runtime_database_url: str) -> None:
    """Read-only reporting identity probe (R1-R7).  Catalog reads and SETTING
    reads only.  Every failure produces a named neutral reason and prevents
    Uvicorn; reasons never contain the DSN or any credential form."""
    from urllib.parse import urlsplit as _urlsplit
    from sqlalchemy import text as _text
    from sqlalchemy.ext.asyncio import create_async_engine as _engine

    dsn = os.environ.get("REPORTING_DATABASE_URL", "")
    if not dsn:
        reason("reporting runtime DSN missing: REPORTING_DATABASE_URL is not "
               "set - the reporting engine cannot initialize")
        return
    try:
        normalized = _normalize_reporting_async_url(dsn)
    except ValueError as exc:
        reason(str(exc))
        return
    runtime_db = _urlsplit(runtime_database_url).path.lstrip("/")
    tenant_table = '"' + tenant + '".rpt_receivables_summary'
    engine = _engine(normalized)
    try:
        async with engine.connect() as conn:
            identity = (await conn.execute(
                _text(_REPORTING_PROBE_SQL[0][1]))).scalar()
            if identity != "reporting_user":
                reason("reporting connection is not bound to reporting_user")
                return
            database = (await conn.execute(
                _text(_REPORTING_PROBE_SQL[1][1]))).scalar()
            if database != runtime_db:
                reason("reporting connection targets a different database "
                       "than the runtime application database")
                return
            member = (await conn.execute(
                _text(_REPORTING_PROBE_SQL[2][1]))).scalar()
            if not member:
                reason("reporting identity lacks reporting_role membership")
                return
            flags = (await conn.execute(
                _text(_REPORTING_PROBE_SQL[3][1]))).one()
            if flags.rolsuper or flags.rolcreaterole or flags.rolcreatedb:
                reason("reporting identity must not be superuser, createrole "
                       "or createdb")
                return
            public_create = (await conn.execute(
                _text(_REPORTING_PROBE_SQL[4][1]))).scalar()
            tenant_create = (await conn.execute(
                _text(_REPORTING_PROBE_SQL[5][1]),
                {"tenant": tenant})).scalar()
            if public_create or tenant_create:
                reason("reporting identity must not hold schema CREATE on "
                       "public or the default tenant")
                return
            read_only = (await conn.execute(
                _text(_REPORTING_PROBE_SQL[6][1]))).scalar()
            if str(read_only).lower() not in ("on", "true", "1"):
                reason("reporting identity must default to read-only "
                       "transactions")
                return
            timeout_raw = (await conn.execute(
                _text(_REPORTING_PROBE_SQL[7][1]))).scalar()
            if _timeout_ms(timeout_raw) != 30000:
                reason("reporting identity statement timeout must be the "
                       "migration-defined 30 seconds")
                return
            expectations = {
                "public_select_wholesalers": True,
                "public_select_retailers": True,
                "public_select_wholesaler_retailer_bindings": True,
                "public_insert_wholesalers": False,
                "public_update_wholesalers": False,
                "public_delete_wholesalers": False,
                "tenant_select_rpt_receivables_summary": True,
                "tenant_insert_rpt_receivables_summary": False,
                "tenant_update_rpt_receivables_summary": False,
                "tenant_delete_rpt_receivables_summary": False,
            }
            params = {"tenant": tenant, "tenant_table": tenant_table}
            for name, sql in _REPORTING_PROBE_SQL:
                if name not in expectations:
                    continue
                allowed = (await conn.execute(_text(sql), params)).scalar()
                if bool(allowed) is not expectations[name]:
                    reason("reporting identity privilege surface mismatch: "
                           + name + " expected " + str(expectations[name]))
                    return
    except Exception as exc:  # noqa: BLE001 - named type only, no detail echo
        reason("reporting connection refused or unusable: "
               + type(exc).__name__)
    finally:
        await engine.dispose()


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
                # R1-R7: read-only reporting identity probe (named
                # refusals; catalog/setting reads only).
                await _probe_reporting(reason, tenant, database_url)
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
