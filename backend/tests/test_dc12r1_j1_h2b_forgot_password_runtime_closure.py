"""H2-B-R0: forgot-password runtime causal closure (F-05).

Causal findings proven in Phase 1 (see ledger):
  - RLS/GUC hypothesis DISPROVEN: no ROW LEVEL SECURITY policy exists in the
    migrations; the reset scan runs under an explicit system scope
    (mark_session_as_system + run_as_system + ignore_tenant) and token
    issuance succeeds against a fresh stack through the real HTTP endpoint.
  - The real defect is OBSERVABILITY: POST /auth/forgot-password swallowed
    every internal failure with a bare ``except Exception: rollback`` and
    emitted no structured log/metric — exactly matching H1's "no error
    trail" observation. The H1-era trigger (an in-app exception during the
    scan/issuance path) is no longer reproducible with healthy data on this
    baseline (tokens issue; broken schemas are isolated by SAVEPOINT), so
    the fix is bounded to making internal failures observable while keeping
    the external envelope perfectly neutral.

This suite runs through the REAL FastAPI app + ASGI + PostgreSQL:

  T1  old-code RED: internal failure -> neutral 200, zero tokens, and (new)
      a structured log with the fixed event class + request_id.
  T2  existing active account: neutral 200 + exactly one token + one email.
  T3  nonexistent / inactive account: same neutral envelope, zero token,
      zero email, no existence disclosure.
  T4  broken schema (no users table) before a healthy tenant: token still
      issued for the healthy tenant (no poisoning).
  T5  delivery failure: neutral response, zero persisted live token
      (rollback proven).
  T6  unexpected internal failure: neutral public response + internal
      structured log (event_class=UNEXPECTED, exception TYPE only, request_id)
      + internal-failures metric incremented.
  T7  single-use reset + cross-tenant password consistency.
  T8  query-string token rejection (boundary regression).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from api.app import app
from api.dependencies import get_db_session
from database.session import AsyncSessionLocal
from services.email_delivery import (
    EmailDeliveryNotConfiguredError,
    clear_dev_email_deliveries,
    get_dev_reset_email_deliveries,
)

pytestmark = pytest.mark.asyncio

FORGOT_URL = "/api/v1/auth/forgot-password"
RESET_URL = "/api/v1/auth/reset-password"

TEST_PW = "H2bRuntimePw_01!"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
async def _h2b_setup():
    await _prepare_tables()
    clear_dev_email_deliveries()
    async with AsyncSessionLocal() as db:
        await db.execute(text("TRUNCATE public.password_reset_tokens"))
        await db.commit()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db_session, None)


async def _prepare_tables() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        for ddl in (
            """CREATE TABLE IF NOT EXISTS public.wholesalers (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                code VARCHAR(32) NOT NULL UNIQUE, name VARCHAR(255) NOT NULL,
                address TEXT, contact TEXT, plan_type VARCHAR(50),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false, deleted_at TIMESTAMPTZ,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                provisioned_at TIMESTAMPTZ, suspended_at TIMESTAMPTZ, suspension_reason TEXT)""",
            """CREATE TABLE IF NOT EXISTS public.password_reset_tokens (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_email_hash VARCHAR(64) NOT NULL,
                token_hash VARCHAR(255) NOT NULL,
                purpose VARCHAR(50) NOT NULL,
                tenant_id UUID, tenant_schema VARCHAR(255),
                expires_at TIMESTAMPTZ NOT NULL,
                used_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false, deleted_at TIMESTAMPTZ)""",
        ):
            await db.execute(text(ddl))
        await db.commit()


async def _seed_wholesaler_with_user(
    db, *, code: str, email: str, password_hash: str, schema_has_users: bool = True
) -> tuple[str, str]:
    ws_id = uuid.uuid4()
    schema = f"t_{str(ws_id).replace('-', '')}"
    await db.execute(
        text(
            "INSERT INTO public.wholesalers (id, code, name, status, is_deleted) "
            "VALUES (:id, :code, :name, 'active', false)"
        ),
        {"id": ws_id, "code": code, "name": f"Tenant {code}"},
    )
    await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    if schema_has_users:
        await db.execute(
            text(
                f'CREATE TABLE IF NOT EXISTS "{schema}".users ('
                "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
                "email VARCHAR(255) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL, "
                "full_name TEXT, is_active BOOLEAN NOT NULL DEFAULT true, "
                "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), "
                "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, "
                "created_by UUID, updated_by UUID)"
            )
        )
        await db.execute(
            text(
                f'INSERT INTO "{schema}".users (email, password_hash, is_active, is_deleted) '
                "VALUES (:e, :h, true, false)"
            ),
            {"e": email, "h": password_hash},
        )
    await db.flush()
    return str(ws_id), schema


def _client(db) -> AsyncClient:
    async def _override():
        try:
            yield db
        finally:
            # The real app's get_db commits on request completion; the test
            # override must mirror that so token writes actually persist.
            await db.commit()

    app.dependency_overrides[get_db_session] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def _token_count() -> int:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            text("SELECT COUNT(*) FROM public.password_reset_tokens WHERE is_deleted = false")
        )
        return r.scalar_one()


async def test_t1_internal_failure_neutral_200_zero_tokens_plus_observable_log(monkeypatch):
    """Old code: bare rollback, no log (RED). New code: structured log with
    fixed event class + request_id (GREEN). External stays neutral 200."""
    from services import password_reset_service as prs

    async def _boom(*a, **k):
        raise RuntimeError("simulated internal failure")

    monkeypatch.setattr(prs.PasswordResetService, "request_reset", _boom)

    async with AsyncSessionLocal() as db:
        email = f"t1-{uuid.uuid4().hex[:6]}@example.com"
        await _seed_wholesaler_with_user(
            db, code=f"T1{uuid.uuid4().hex[:6].upper()}", email=email,
            password_hash="x", schema_has_users=True,
        )
        await db.commit()

        # Framework-independent capture (immune to cross-suite logging-state
        # changes): the endpoint module's logger.error is intercepted directly.
        import api.v1.auth as auth_module

        log_calls: list[dict] = []

        def _capture_error(msg, *args, **kwargs):
            log_calls.append({"msg": msg, "kwargs": kwargs})

        monkeypatch.setattr(auth_module.logger, "error", _capture_error)
        async with _client(db) as client:
            r = await client.post(
                FORGOT_URL, json={"email": email},
                headers={"X-Request-ID": "h2b-t1-req-1000"},
            )

        # Neutral public envelope; zero tokens persisted (rollback).
        assert r.status_code == 200
        assert "disclosed" in r.text
        assert await _token_count() == 0  # fresh per-test table: nothing persisted

        # Internal observability: fixed event class + request_id + type only.
        assert len(log_calls) == 1
        call = log_calls[0]
        assert call["msg"] == "password_reset.internal_failure"
        extra = call["kwargs"].get("extra", {})
        assert extra.get("event_class") == "UNEXPECTED"
        assert extra.get("request_id") == "h2b-t1-req-1000"
        assert extra.get("exception_type") == "RuntimeError"
        # Never email/schema/token/password/hash/credentials.
        payload = str(call)
        assert email not in payload
        assert "password_hash" not in payload


async def test_t2_existing_active_account_token_and_email():
    from core.security import hash_password

    async with AsyncSessionLocal() as db:
        email = f"t2-{uuid.uuid4().hex[:6]}@example.com"
        await _seed_wholesaler_with_user(
            db, code=f"T2{uuid.uuid4().hex[:6].upper()}", email=email,
            password_hash=hash_password(TEST_PW), schema_has_users=True,
        )
        await db.commit()
        before = await _token_count()

        async with _client(db) as client:
            r = await client.post(FORGOT_URL, json={"email": email})

        assert r.status_code == 200
        assert "disclosed" in r.text
        assert await _token_count() == before + 1
        emails = get_dev_reset_email_deliveries(email)
        assert len(emails) == 1
        assert "resetToken=" in emails[0].reset_link


async def test_t3_nonexistent_and_inactive_neutral_zero_side_effects():
    from core.security import hash_password

    async with AsyncSessionLocal() as db:
        inactive_email = f"t3i-{uuid.uuid4().hex[:6]}@example.com"
        ws_id, schema = await _seed_wholesaler_with_user(
            db, code=f"T3{uuid.uuid4().hex[:6].upper()}", email=inactive_email,
            password_hash=hash_password(TEST_PW), schema_has_users=True,
        )
        await db.execute(
            text(f'UPDATE "{schema}".users SET is_active = false WHERE email = :e'),
            {"e": inactive_email},
        )
        await db.commit()
        before = await _token_count()

        async with _client(db) as client:
            missing = await client.post(
                FORGOT_URL, json={"email": f"nobody-{uuid.uuid4().hex[:6]}@example.com"}
            )
            inactive = await client.post(FORGOT_URL, json={"email": inactive_email})

        for r in (missing, inactive):
            assert r.status_code == 200
            assert "disclosed" in r.text
            assert r.json()["data"] == {}
        assert await _token_count() == before
        assert get_dev_reset_email_deliveries() == []


async def test_t4_broken_schema_before_healthy_tenant_no_poisoning():
    """One missing-schema tenant must not hide a valid active user later."""
    from core.security import hash_password

    async with AsyncSessionLocal() as db:
        # Broken tenant first (created earlier => scanned first by created_at).
        await _seed_wholesaler_with_user(
            db, code=f"BRK{uuid.uuid4().hex[:6].upper()}",
            email=f"broken-{uuid.uuid4().hex[:6]}@example.com",
            password_hash="x", schema_has_users=False,
        )
        healthy_email = f"t4-{uuid.uuid4().hex[:6]}@example.com"
        await _seed_wholesaler_with_user(
            db, code=f"HTH{uuid.uuid4().hex[:6].upper()}", email=healthy_email,
            password_hash=hash_password(TEST_PW), schema_has_users=True,
        )
        await db.commit()
        before = await _token_count()

        async with _client(db) as client:
            r = await client.post(FORGOT_URL, json={"email": healthy_email})

        assert r.status_code == 200
        assert await _token_count() == before + 1
        assert len(get_dev_reset_email_deliveries(healthy_email)) == 1


async def test_t5_delivery_failure_rollback(monkeypatch):
    from core.security import hash_password
    from services import password_reset_service as prs

    def _raise(*a, **k):
        raise EmailDeliveryNotConfiguredError("EMAIL_DELIVERY_NOT_CONFIGURED")

    # The service binds the import at module load; patch THAT binding.
    monkeypatch.setattr(prs, "record_password_reset_email", _raise)

    async with AsyncSessionLocal() as db:
        email = f"t5-{uuid.uuid4().hex[:6]}@example.com"
        await _seed_wholesaler_with_user(
            db, code=f"T5{uuid.uuid4().hex[:6].upper()}", email=email,
            password_hash=hash_password(TEST_PW), schema_has_users=True,
        )
        await db.commit()
        before = await _token_count()

        async with _client(db) as client:
            r = await client.post(FORGOT_URL, json={"email": email})

        assert r.status_code == 200
        assert "disclosed" in r.text
        assert await _token_count() == before  # rollback: zero persisted live token
        assert get_dev_reset_email_deliveries(email) == []


async def test_t6_unexpected_failure_metric_and_neutral_external(monkeypatch):
    """The internal-failures metric increments for the fixed event class."""
    from api.v1.auth import _password_reset_internal_failures_total
    from services import password_reset_service as prs

    async def _boom(*a, **k):
        raise ValueError("simulated")

    monkeypatch.setattr(prs.PasswordResetService, "request_reset", _boom)
    before = _password_reset_internal_failures_total.labels(event_class="UNEXPECTED")._value.get()

    async with AsyncSessionLocal() as db:
        email = f"t6-{uuid.uuid4().hex[:6]}@example.com"
        await _seed_wholesaler_with_user(
            db, code=f"T6{uuid.uuid4().hex[:6].upper()}", email=email,
            password_hash="x", schema_has_users=True,
        )
        await db.commit()
        async with _client(db) as client:
            r = await client.post(FORGOT_URL, json={"email": email})

        assert r.status_code == 200
        assert "disclosed" in r.text
        assert await _token_count() == 0  # rollback: no token persisted
        after = _password_reset_internal_failures_total.labels(event_class="UNEXPECTED")._value.get()
        assert after == before + 1


async def test_t7_single_use_reset_and_cross_tenant_consistency():
    """Token resets the password once; replay is rejected; all active tenant
    copies of the same email end with the same new hash."""
    from core.security import hash_password, verify_password

    async with AsyncSessionLocal() as db:
        email = f"t7-{uuid.uuid4().hex[:6]}@example.com"
        ws1, s1 = await _seed_wholesaler_with_user(
            db, code=f"T7A{uuid.uuid4().hex[:6].upper()}", email=email,
            password_hash=hash_password("OldPw_01!")  # pragma: allowlist secret, schema_has_users=True,
        )
        ws2, s2 = await _seed_wholesaler_with_user(
            db, code=f"T7B{uuid.uuid4().hex[:6].upper()}", email=email,
            password_hash=hash_password("OldPw_01!")  # pragma: allowlist secret, schema_has_users=True,
        )
        await db.commit()

        async with _client(db) as client:
            r = await client.post(FORGOT_URL, json={"email": email})
            assert r.status_code == 200
            reset_mail = get_dev_reset_email_deliveries(email)[0]
            from urllib.parse import parse_qs

            frag = reset_mail.reset_link.split("#", 1)[1]
            raw_token = parse_qs(frag)["resetToken"][0]

            ok = await client.post(
                RESET_URL, json={"reset_token": raw_token, "new_password": "NewPw_02!!"}  # pragma: allowlist secret
            )
            assert ok.status_code == 200

            replay = await client.post(
                RESET_URL, json={"reset_token": raw_token, "new_password": "NewPw_03!!"}  # pragma: allowlist secret
            )
            # Replay rejected (neutral), token single-use.
            assert replay.status_code in (200, 400, 401)

            # Cross-tenant consistency: both copies now verify with the NEW pw.
            for schema in (s1, s2):
                row = (
                    await db.execute(
                        text(
                            f'SELECT password_hash FROM "{schema}".users '
                            "WHERE lower(email) = lower(:e) AND is_active = true"
                        ),
                        {"e": email},
                    )
                ).first()
                assert row is not None
                assert verify_password("NewPw_02!!", row.password_hash)


async def test_t8_query_string_token_rejected():
    """Secret-boundary regression: tokens in query strings are rejected."""
    from core.security import hash_password

    async with AsyncSessionLocal() as db:
        email = f"t8-{uuid.uuid4().hex[:6]}@example.com"
        await _seed_wholesaler_with_user(
            db, code=f"T8{uuid.uuid4().hex[:6].upper()}", email=email,
            password_hash=hash_password(TEST_PW), schema_has_users=True,
        )
        await db.commit()
        async with _client(db) as client:
            r = await client.post(
                RESET_URL + "?reset_token=leak&new_password=x",
                json={"reset_token": "whatever", "new_password": "NewPw_04!!"}  # pragma: allowlist secret,
            )
        assert r.status_code == 401
        assert "INVALID_OR_EXPIRED" in r.text or "invalid" in r.text.lower()
