"""H2-B-R1/R2: forgot-password scan-level closure + consume-stage atomicity.

R0 (93382cb2) closed endpoint-level observability only; R1 (fc2db4fe)
closed the request-stage silent scan path; R2 (this revision) closes the
consume stage: fail-closed on ANY incomplete tenant scan (even when
reachable copies exist) and an all-or-nothing password fan-out so tenant
copies can never diverge. R1's verdict is superseded by R2; R1's full-stack
gates were non-regression evidence, not a zero-red PASS (see R2 ledger).

R1 contract proven here against REAL PostgreSQL through the real ASGI app:

  T1  old-code RED reproduction (endpoint level): unexpected internal error
      -> neutral 200 + structured log with fixed event class + request_id.
  T2  healthy OFFICIAL-LIFECYCLE account (signup -> verify-email ->
      setup-credential through the real endpoints): neutral 200 + exactly
      one token + one reset email.
  T3  all scans successful + no account: same neutral 200 with ZERO side
      effects and NO internal failure event (no log, no metric delta).
  T4  unrelated tenant scan fails + target account found: exactly one
      token + one email + sanitized PARTIAL-scan telemetry (counters only).
  T5  delivery failure: neutral response, zero persisted live token
      (rollback proven).
  T6  unexpected internal failure: neutral public response + internal
      structured log + internal-failures metric incremented.
  T7  reset replay: exact 401 for the used token, token REMAINS used, and
      the replay password is NOT applied to any tenant copy.
  T8  query-string token rejection (boundary regression).
  T9  TARGET tenant scan fails (committed users table renamed — the user
      row evidence is preserved, not deleted): neutral 200, zero token,
      zero email, and EXACTLY ONE deterministic internal incomplete-scan
      event + metric; evidence intact; renaming the table back restores
      issuance (non-destructive causal proof).
  T10 consume-path incomplete scan: valid token whose tenant copies are
      all unreachable -> neutral 401 + one internal event, token NOT
      consumed; after repair the SAME token resets successfully.

R2 (consume-stage atomicity closure) adds:

  T11 partial scan at consume: same email in two tenant schemas, one
      committed users table renamed (row evidence preserved), the other
      copy reachable -> reset fails closed with the neutral 401, BOTH
      hashes remain the old password, token used_at stays NULL, and after
      restoring the table the SAME token resets both copies exactly once.
  T12 partial apply: both copies scan successfully but a real PostgreSQL
      BEFORE UPDATE trigger forces the second copy's UPDATE to fail ->
      reset fails closed, the FIRST copy's staged update is rolled back,
      both retain the old password, token remains unused; removing the
      trigger lets the SAME token reset both copies. R2-R1: the two
      wholesaler IDs are retained with explicit distinct committed
      created_at values (s1 < s2) and the REAL enumerator is invoked
      before the trigger to prove the target-copy order is exactly
      [s1, s2] — the fan-out order is deterministic, not incidental.

All internal-event assertions check sanitization: payloads must never
contain the email, tenant schema names, SQL text, tokens, or credentials.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qs

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from api.app import app
from api.dependencies import get_db_session
from database.session import AsyncSessionLocal
from services.email_delivery import (
    EmailDeliveryNotConfiguredError,
    clear_dev_email_deliveries,
    get_dev_email_deliveries,
    get_dev_reset_email_deliveries,
)
from services.onboarding_service import hash_token

pytestmark = pytest.mark.asyncio

FORGOT_URL = "/api/v1/auth/forgot-password"
RESET_URL = "/api/v1/auth/reset-password"

TEST_PW = "H2bRuntimePw_01!"  # pragma: allowlist secret
LIFECYCLE_PW = "H2bLifecyclePw_1!"  # pragma: allowlist secret

EVENT_CLASSES = (
    "EMAIL_DELIVERY_NOT_CONFIGURED",
    "UNEXPECTED",
    "PASSWORD_RESET_SCAN_INCOMPLETE",
    "PASSWORD_RESET_SCAN_PARTIAL",
    "PASSWORD_RESET_APPLY_FAILED",
)


@pytest.fixture(autouse=True)
async def _h2b_setup():
    await _prepare_tables()
    await _reset_wholesaler_state()
    clear_dev_email_deliveries()
    async with AsyncSessionLocal() as db:
        await db.execute(text("TRUNCATE public.password_reset_tokens"))
        await db.commit()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db_session, None)


async def _reset_wholesaler_state() -> None:
    """Deterministic scan isolation: this task's DB is single-suite, so remove
    every wholesaler + derived tenant schema (including leftover renamed
    evidence tables from earlier runs) before each test. Without this, a
    tenant left broken by a previous test makes every later request emit
    partial/incomplete-scan events and breaks zero-event assertions."""
    async with AsyncSessionLocal() as db:
        ids = (
            await db.execute(text("SELECT id FROM public.wholesalers"))
        ).scalars().all()
        for wid in ids:
            schema = f"t_{str(wid).replace('-', '')}"
            await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        if ids:
            await db.execute(
                text("DELETE FROM public.tenant_registrations")
            )
        await db.execute(text("DELETE FROM public.wholesalers"))
        await db.commit()


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
    db,
    *,
    code: str,
    email: str,
    password_hash: str,
    schema_has_users: bool = True,
    created_at: datetime | None = None,
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
    if created_at is not None:
        # Explicit committed created_at makes the scan order deterministic
        # (the column DEFAULT now() gives same-transaction inserts
        # identical timestamps, leaving created_at ties undefined).
        await db.execute(
            text("UPDATE public.wholesalers SET created_at = :ca WHERE id = :id"),
            {"ca": created_at, "id": ws_id},
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


async def _rename_users_table(schema: str, new_name: str) -> None:
    """Make the committed users table INACCESSIBLE to the scan without
    deleting any user evidence: the committed rows stay in the renamed
    table, only the ``users`` name disappears."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(f'ALTER TABLE "{schema}".users RENAME TO "{new_name}"')
        )
        await db.commit()


async def _users_table_row_count(schema: str, table: str, email: str) -> int:
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(
                text(
                    f'SELECT COUNT(*) FROM "{schema}"."{table}" '
                    "WHERE lower(email) = lower(:e)"
                ),
                {"e": email},
            )
        ).scalar_one()


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


def _real_client() -> AsyncClient:
    """Per-request session override (mirrors the production dependency)."""

    async def _override():
        async with AsyncSessionLocal() as session:
            await session.execute(text("SET search_path TO public"))
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def _token_count() -> int:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            text("SELECT COUNT(*) FROM public.password_reset_tokens WHERE is_deleted = false")
        )
        return r.scalar_one()


def _capture_auth_logs(monkeypatch) -> dict[str, list[dict]]:
    """Capture the endpoint module's logger output, framework-independent."""
    import api.v1.auth as auth_module

    calls: dict[str, list[dict]] = {"error": [], "warning": []}

    def _capture(level: str):
        def _fn(msg, *args, **kwargs):
            calls[level].append({"msg": msg, "kwargs": kwargs})

        return _fn

    monkeypatch.setattr(auth_module.logger, "error", _capture("error"))
    monkeypatch.setattr(auth_module.logger, "warning", _capture("warning"))
    return calls


def _metric_snapshot() -> dict[str, int]:
    from api.v1.auth import _password_reset_internal_failures_total

    return {
        cls: _password_reset_internal_failures_total.labels(event_class=cls)._value.get()
        for cls in EVENT_CLASSES
    }


async def _official_lifecycle_active_user() -> tuple[str, str]:
    """Provision a real active owner through the official lifecycle:
    signup -> verify-email -> setup-credential (all real HTTP endpoints)."""
    email = f"h2b_{uuid.uuid4().hex}@example.com"
    async with _real_client() as client:
        r = await client.post(
            "/api/v1/auth/signup",
            json={
                "companyName": f"H2B Company {uuid.uuid4().hex[:8]}",
                "country": "KE",
                "email": email,
                "phone": "+254700000000",
                "businessType": "wholesale",
                "password": LIFECYCLE_PW,
            },
        )
        assert r.status_code == 202, r.text
    verify_token = [
        d for d in get_dev_email_deliveries(email) if d.purpose == "email_verification"
    ][0].token
    async with _real_client() as client:
        v = await client.post("/api/v1/auth/verify-email", json={"token": verify_token})
        assert v.status_code == 200, v.text
    setup_token = [
        d for d in get_dev_email_deliveries(email) if d.purpose == "owner_setup"
    ][0].token
    async with _real_client() as client:
        s = await client.post(
            "/api/v1/auth/onboarding/setup-credential",
            json={"setupToken": setup_token, "password": LIFECYCLE_PW},
        )
        assert s.status_code == 200, s.text

    async with AsyncSessionLocal() as db:
        schema = (
            await db.execute(
                text(
                    "SELECT tenant_schema FROM public.tenant_registrations "
                    "WHERE owner_email = :e"
                ),
                {"e": email},
            )
        ).scalar_one()
        active_users = (
            await db.execute(
                text(
                    f'SELECT COUNT(*) FROM "{schema}".users '
                    "WHERE is_active = true AND is_deleted = false "
                    "AND lower(email) = lower(:e)"
                ),
                {"e": email},
            )
        ).scalar_one()
    assert active_users == 1
    return email, schema


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

        calls = _capture_auth_logs(monkeypatch)
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
        assert len(calls["error"]) == 1
        call = calls["error"][0]
        assert call["msg"] == "password_reset.internal_failure"
        extra = call["kwargs"].get("extra", {})
        assert extra.get("event_class") == "UNEXPECTED"
        assert extra.get("request_id") == "h2b-t1-req-1000"
        assert extra.get("exception_type") == "RuntimeError"
        # Never email/schema/token/password/hash/credentials.
        payload = str(call)
        assert email not in payload
        assert "password_hash" not in payload


async def test_t2_official_lifecycle_account_token_and_email():
    """Healthy account provisioned through the OFFICIAL lifecycle: forgot
    password issues exactly one token and one reset email (GREEN path)."""
    email, _schema = await _official_lifecycle_active_user()
    before = await _token_count()

    async with _real_client() as client:
        r = await client.post(FORGOT_URL, json={"email": email})

    assert r.status_code == 200
    assert "disclosed" in r.text
    assert await _token_count() == before + 1
    emails = get_dev_reset_email_deliveries(email)
    assert len(emails) == 1
    assert "resetToken=" in emails[0].reset_link


async def test_t3_nonexistent_and_inactive_neutral_zero_side_effects_and_zero_events(
    monkeypatch,
):
    """All scans successful + no account: neutral 200, no token, no email,
    and NO internal failure event (neither log nor metric)."""
    from core.security import hash_password

    calls = _capture_auth_logs(monkeypatch)
    metrics_before = _metric_snapshot()

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

        # A clean "no account" answer is NOT an internal failure: no event.
        assert calls["error"] == []
        assert calls["warning"] == []
        assert _metric_snapshot() == metrics_before


async def test_t4_unrelated_scan_failure_target_found_partial_telemetry(monkeypatch):
    """An UNRELATED tenant's committed users table fails to scan while the
    target account is found later in the scan: exactly one token + one
    email + sanitized PARTIAL-scan telemetry (no poisoning)."""
    from core.security import hash_password

    async with AsyncSessionLocal() as db:
        # Broken unrelated tenant first (created earlier => scanned first).
        broken_email = f"broken-{uuid.uuid4().hex[:6]}@example.com"
        _, broken_schema = await _seed_wholesaler_with_user(
            db, code=f"BRK{uuid.uuid4().hex[:6].upper()}",
            email=broken_email, password_hash="x", schema_has_users=True,
        )
        await db.commit()
        # Make its COMMITTED users table inaccessible WITHOUT deleting the
        # user evidence (the row survives inside the renamed table).
        await _rename_users_table(broken_schema, "users_evidence_t4")
        assert await _users_table_row_count(broken_schema, "users_evidence_t4", broken_email) == 1

        healthy_email = f"t4-{uuid.uuid4().hex[:6]}@example.com"
        await _seed_wholesaler_with_user(
            db, code=f"HTH{uuid.uuid4().hex[:6].upper()}", email=healthy_email,
            password_hash=hash_password(TEST_PW), schema_has_users=True,
        )
        await db.commit()
        before = await _token_count()

    calls = _capture_auth_logs(monkeypatch)
    metrics_before = _metric_snapshot()

    async with AsyncSessionLocal() as db:
        async with _client(db) as client:
            r = await client.post(FORGOT_URL, json={"email": healthy_email})

    # Target account still gets exactly one token + one email.
    assert r.status_code == 200
    assert "disclosed" in r.text
    assert await _token_count() == before + 1
    assert len(get_dev_reset_email_deliveries(healthy_email)) == 1

    # Sanitized partial-scan telemetry: exactly one warning, counters only.
    assert len(calls["warning"]) == 1
    call = calls["warning"][0]
    assert call["msg"] == "password_reset.partial_scan"
    extra = call["kwargs"].get("extra", {})
    assert extra.get("event_class") == "PASSWORD_RESET_SCAN_PARTIAL"
    assert extra.get("failed_schema_count", 0) >= 1
    payload = str(call)
    assert healthy_email not in payload
    assert broken_schema not in payload
    assert broken_email not in payload
    assert calls["error"] == []

    after = _metric_snapshot()
    assert after["PASSWORD_RESET_SCAN_PARTIAL"] == metrics_before["PASSWORD_RESET_SCAN_PARTIAL"] + 1
    for cls in EVENT_CLASSES:
        if cls != "PASSWORD_RESET_SCAN_PARTIAL":
            assert after[cls] == metrics_before[cls]


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


async def _token_used_at(raw_token: str) -> datetime | None:
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(
                text(
                    "SELECT used_at FROM public.password_reset_tokens "
                    "WHERE token_hash = :th AND purpose = 'password_reset'"
                ),
                {"th": hash_token(raw_token)},
            )
        ).scalar_one()


async def test_t7_replay_exact_401_token_remains_used_password_not_applied():
    """Reset replay contract: used token -> EXACTLY 401; the token REMAINS
    used; the replay password is NOT applied to any tenant copy."""
    from core.security import hash_password, verify_password

    first_pw = "NewPw_02!!"  # pragma: allowlist secret
    replay_pw = "NewPw_03!!"  # pragma: allowlist secret

    async with AsyncSessionLocal() as db:
        email = f"t7-{uuid.uuid4().hex[:6]}@example.com"
        ws1, s1 = await _seed_wholesaler_with_user(
            db, code=f"T7A{uuid.uuid4().hex[:6].upper()}", email=email,
            password_hash=hash_password("OldPw_01!"), schema_has_users=True,  # pragma: allowlist secret
        )
        ws2, s2 = await _seed_wholesaler_with_user(
            db, code=f"T7B{uuid.uuid4().hex[:6].upper()}", email=email,
            password_hash=hash_password("OldPw_01!"), schema_has_users=True,  # pragma: allowlist secret
        )
        await db.commit()

        async with _client(db) as client:
            r = await client.post(FORGOT_URL, json={"email": email})
            assert r.status_code == 200
            reset_mail = get_dev_reset_email_deliveries(email)[0]
            frag = reset_mail.reset_link.split("#", 1)[1]
            raw_token = parse_qs(frag)["resetToken"][0]

            ok = await client.post(
                RESET_URL, json={"reset_token": raw_token, "new_password": first_pw}
            )
            assert ok.status_code == 200

            used_at_first = await _token_used_at(raw_token)
            assert used_at_first is not None  # token is used

            replay = await client.post(
                RESET_URL, json={"reset_token": raw_token, "new_password": replay_pw}
            )
            # Replay is rejected with the EXACT neutral 401 (not 200/400).
            assert replay.status_code == 401
            assert (
                replay.json()["detail"]["code"] == "INVALID_OR_EXPIRED_PASSWORD_RESET_TOKEN"
            )
            assert "disclosed" in replay.text

            # Token remains used (used_at set and unchanged by the replay).
            used_at_after_replay = await _token_used_at(raw_token)
            assert used_at_after_replay == used_at_first

            # A second replay is still rejected (single-use persists).
            replay2 = await client.post(
                RESET_URL, json={"reset_token": raw_token, "new_password": replay_pw}
            )
            assert replay2.status_code == 401
            assert await _token_used_at(raw_token) == used_at_first

        # The replay password was NOT applied to ANY tenant copy: every copy
        # still verifies the FIRST new password and rejects the replay one.
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
            assert verify_password(first_pw, row.password_hash)
            assert not verify_password(replay_pw, row.password_hash)


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
                json={"reset_token": "whatever", "new_password": "NewPw_04!!"},  # pragma: allowlist secret
            )
        assert r.status_code == 401
        assert "INVALID_OR_EXPIRED" in r.text or "invalid" in r.text.lower()


async def test_t9_target_scan_failure_one_internal_event_evidence_preserved(monkeypatch):
    """TARGET tenant scan fails: neutral 200, zero token, zero email, and
    exactly ONE deterministic internal incomplete-scan event + metric.

    The committed users table is RENAMED (inaccessible to the scan) while
    the user evidence survives untouched in the renamed table — the scan
    failure, not user absence, is what suppresses issuance. Restoring the
    name restores issuance: proof that nothing was deleted."""
    from core.security import hash_password

    async with AsyncSessionLocal() as db:
        email = f"t9-{uuid.uuid4().hex[:6]}@example.com"
        _, schema = await _seed_wholesaler_with_user(
            db, code=f"T9{uuid.uuid4().hex[:6].upper()}", email=email,
            password_hash=hash_password(TEST_PW), schema_has_users=True,
        )
        await db.commit()
        await _rename_users_table(schema, "users_evidence_t9")
        assert await _users_table_row_count(schema, "users_evidence_t9", email) == 1
        before = await _token_count()

    calls = _capture_auth_logs(monkeypatch)
    metrics_before = _metric_snapshot()

    async with AsyncSessionLocal() as db:
        async with _client(db) as client:
            r = await client.post(
                FORGOT_URL, json={"email": email},
                headers={"X-Request-ID": "h2b-t9-req-2001"},
            )

    # Public envelope stays perfectly neutral; nothing is issued.
    assert r.status_code == 200
    assert "disclosed" in r.text
    assert r.json()["data"] == {}
    assert await _token_count() == before  # zero token
    assert get_dev_reset_email_deliveries(email) == []  # zero email

    # Exactly ONE internal event, deterministic class, sanitized payload.
    assert len(calls["error"]) == 1
    call = calls["error"][0]
    assert call["msg"] == "password_reset.internal_failure"
    extra = call["kwargs"].get("extra", {})
    assert extra.get("event_class") == "PASSWORD_RESET_SCAN_INCOMPLETE"
    assert extra.get("phase") == "reset_request_scan"
    assert extra.get("request_id") == "h2b-t9-req-2001"
    assert extra.get("failed_schema_count", 0) >= 1
    payload = str(call)
    assert email not in payload
    assert schema not in payload
    assert "SELECT" not in payload
    assert calls["warning"] == []

    after = _metric_snapshot()
    assert (
        after["PASSWORD_RESET_SCAN_INCOMPLETE"]
        == metrics_before["PASSWORD_RESET_SCAN_INCOMPLETE"] + 1
    )
    for cls in EVENT_CLASSES:
        if cls != "PASSWORD_RESET_SCAN_INCOMPLETE":
            assert after[cls] == metrics_before[cls]

    # User evidence still intact (renamed table still holds the active row).
    assert await _users_table_row_count(schema, "users_evidence_t9", email) == 1

    # Repair restores issuance with zero data loss: rename back -> token.
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(f'ALTER TABLE "{schema}"."users_evidence_t9" RENAME TO "users"')
        )
        await db.commit()
        async with _client(db) as client:
            repaired = await client.post(FORGOT_URL, json={"email": email})
    assert repaired.status_code == 200
    assert await _token_count() == before + 1
    assert len(get_dev_reset_email_deliveries(email)) == 1


async def test_t10_consume_scan_incomplete_token_stays_actionable(monkeypatch):
    """Consume-path scan failure: neutral 401 + exactly one internal event,
    the token is NOT consumed; after repair the SAME token succeeds."""
    from core.security import hash_password, verify_password

    new_pw = "NewPw_05!!"  # pragma: allowlist secret

    async with AsyncSessionLocal() as db:
        email = f"t10-{uuid.uuid4().hex[:6]}@example.com"
        _, schema = await _seed_wholesaler_with_user(
            db, code=f"TA{uuid.uuid4().hex[:6].upper()}", email=email,
            password_hash=hash_password(TEST_PW), schema_has_users=True,
        )
        await db.commit()

        async with _client(db) as client:
            r = await client.post(FORGOT_URL, json={"email": email})
            assert r.status_code == 200
            reset_mail = get_dev_reset_email_deliveries(email)[0]
            raw_token = parse_qs(reset_mail.reset_link.split("#", 1)[1])["resetToken"][0]

        await _rename_users_table(schema, "users_evidence_t10")
        assert await _users_table_row_count(schema, "users_evidence_t10", email) == 1

        calls = _capture_auth_logs(monkeypatch)
        metrics_before = _metric_snapshot()

        async with _client(db) as client:
            broken = await client.post(
                RESET_URL, json={"reset_token": raw_token, "new_password": new_pw}
            )

        # Public: the same neutral 401 envelope as any non-actionable token.
        assert broken.status_code == 401
        assert broken.json()["detail"]["code"] == "INVALID_OR_EXPIRED_PASSWORD_RESET_TOKEN"

        # Internal: exactly one sanitized incomplete-scan event.
        assert len(calls["error"]) == 1
        extra = calls["error"][0]["kwargs"].get("extra", {})
        assert extra.get("event_class") == "PASSWORD_RESET_SCAN_INCOMPLETE"
        assert extra.get("phase") == "reset_consume_scan"
        assert extra.get("failed_schema_count", 0) >= 1
        payload = str(calls["error"][0])
        assert email not in payload
        assert schema not in payload
        assert _metric_snapshot()["PASSWORD_RESET_SCAN_INCOMPLETE"] == (
            metrics_before["PASSWORD_RESET_SCAN_INCOMPLETE"] + 1
        )

        # Token NOT consumed: still actionable after repair.
        assert await _token_used_at(raw_token) is None

        async with AsyncSessionLocal() as repair_db:
            await repair_db.execute(
                text(f'ALTER TABLE "{schema}"."users_evidence_t10" RENAME TO "users"')
            )
            await repair_db.commit()

        async with AsyncSessionLocal() as db2:
            async with _client(db2) as client:
                repaired = await client.post(
                    RESET_URL, json={"reset_token": raw_token, "new_password": new_pw}
                )
        assert repaired.status_code == 200
        assert await _token_used_at(raw_token) is not None

        assert verify_password(new_pw, await _copy_password_hash(schema, email))


async def _copy_password_hash(schema: str, email: str, table: str = "users") -> str | None:
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(
                text(
                    f'SELECT password_hash FROM "{schema}"."{table}" '
                    "WHERE lower(email) = lower(:e) AND is_active = true"
                ),
                {"e": email},
            )
        ).scalar_one()


async def _issue_reset_token(email: str) -> str:
    async with AsyncSessionLocal() as db:
        async with _client(db) as client:
            r = await client.post(FORGOT_URL, json={"email": email})
        assert r.status_code == 200
    reset_mail = get_dev_reset_email_deliveries(email)[0]
    return parse_qs(reset_mail.reset_link.split("#", 1)[1])["resetToken"][0]


async def _seed_two_tenant_copies(email: str, old_pw: str) -> tuple[str, str, str, str]:
    """Same email as an active user in two tenant schemas.

    The two wholesaler IDs are retained and their committed ``created_at``
    values are explicit and distinct (s1 strictly earlier than s2), so the
    enumerator's ``created_at`` scan order — and therefore the fan-out
    order — is deterministic. Returns (ws1_id, s1, ws2_id, s2).
    """
    from datetime import timedelta

    from core.security import hash_password

    base = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        ws1, s1 = await _seed_wholesaler_with_user(
            db, code=f"R2A{uuid.uuid4().hex[:6].upper()}", email=email,
            password_hash=hash_password(old_pw), schema_has_users=True,
            created_at=base - timedelta(hours=2),
        )
        ws2, s2 = await _seed_wholesaler_with_user(
            db, code=f"R2B{uuid.uuid4().hex[:6].upper()}", email=email,
            password_hash=hash_password(old_pw), schema_has_users=True,
            created_at=base - timedelta(hours=1),
        )
        await db.commit()
    return ws1, s1, ws2, s2


async def test_t11_consume_partial_scan_fails_closed_both_old_token_intact(monkeypatch):
    """R2 test A — partial scan at consume: one of two committed users tables
    renamed (evidence preserved) while the other copy is reachable. Reset
    must fail closed: neutral 401, BOTH hashes still the old password (the
    reachable copy is NOT partially updated), token used_at NULL; after
    restoring the table the SAME token resets both copies exactly once."""
    from core.security import verify_password

    old_pw = "OldR2Pw_01!"  # pragma: allowlist secret
    new_pw = "NewR2Pw_02!"  # pragma: allowlist secret
    email = f"t11-{uuid.uuid4().hex[:6]}@example.com"
    ws1, s1, ws2, s2 = await _seed_two_tenant_copies(email, old_pw)

    raw_token = await _issue_reset_token(email)

    await _rename_users_table(s2, "users_evidence_t11")
    assert await _users_table_row_count(s2, "users_evidence_t11", email) == 1

    calls = _capture_auth_logs(monkeypatch)
    metrics_before = _metric_snapshot()

    async with AsyncSessionLocal() as db:
        async with _client(db) as client:
            broken = await client.post(
                RESET_URL, json={"reset_token": raw_token, "new_password": new_pw}
            )

    # Fails closed with the exact neutral 401 envelope.
    assert broken.status_code == 401
    assert broken.json()["detail"]["code"] == "INVALID_OR_EXPIRED_PASSWORD_RESET_TOKEN"

    # Exactly one sanitized SCAN_INCOMPLETE event for the consume scan.
    assert len(calls["error"]) == 1
    extra = calls["error"][0]["kwargs"].get("extra", {})
    assert extra.get("event_class") == "PASSWORD_RESET_SCAN_INCOMPLETE"
    assert extra.get("phase") == "reset_consume_scan"
    assert extra.get("failed_schema_count", 0) >= 1
    payload = str(calls["error"][0])
    assert email not in payload
    assert s1 not in payload and s2 not in payload
    after = _metric_snapshot()
    assert after["PASSWORD_RESET_SCAN_INCOMPLETE"] == (
        metrics_before["PASSWORD_RESET_SCAN_INCOMPLETE"] + 1
    )
    for cls in EVENT_CLASSES:
        if cls != "PASSWORD_RESET_SCAN_INCOMPLETE":
            assert after[cls] == metrics_before[cls]

    # BOTH copies keep the old password (no partial fan-out, outer rollback).
    # The renamed copy's evidence row is read from the renamed table.
    assert verify_password(old_pw, await _copy_password_hash(s1, email))
    assert not verify_password(new_pw, await _copy_password_hash(s1, email))
    assert verify_password(
        old_pw, await _copy_password_hash(s2, email, table="users_evidence_t11")
    )

    # Token NOT consumed: used_at NULL, stays actionable after repair.
    assert await _token_used_at(raw_token) is None

    async with AsyncSessionLocal() as db:
        await db.execute(
            text(f'ALTER TABLE "{s2}"."users_evidence_t11" RENAME TO "users"')
        )
        await db.commit()

    async with AsyncSessionLocal() as db:
        async with _client(db) as client:
            repaired = await client.post(
                RESET_URL, json={"reset_token": raw_token, "new_password": new_pw}
            )
            replay = await client.post(
                RESET_URL, json={"reset_token": raw_token, "new_password": new_pw}
            )
    assert repaired.status_code == 200
    # Exactly once: both copies carry the new password, token used, replay 401.
    for schema in (s1, s2):
        assert verify_password(new_pw, await _copy_password_hash(schema, email))
        assert not verify_password(old_pw, await _copy_password_hash(schema, email))
    assert await _token_used_at(raw_token) is not None
    assert replay.status_code == 401


async def test_t12_partial_apply_rolls_back_first_copy_token_intact(monkeypatch):
    """R2 test B — partial apply: both copies scan successfully, but a real
    PostgreSQL BEFORE UPDATE trigger forces the SECOND copy's UPDATE to
    fail. Reset fails closed; the FIRST copy's staged update is rolled back
    (both retain the old password); the token stays unused; removing the
    trigger lets the SAME token reset both copies."""
    from core.security import verify_password

    old_pw = "OldR2Pw_03!"  # pragma: allowlist secret
    new_pw = "NewR2Pw_04!"  # pragma: allowlist secret
    email = f"t12-{uuid.uuid4().hex[:6]}@example.com"
    ws1, s1, ws2, s2 = await _seed_two_tenant_copies(email, old_pw)

    # The retained wholesaler IDs derive exactly the scanned schemas.
    assert s1 == f"t_{ws1.replace('-', '')}"
    assert s2 == f"t_{ws2.replace('-', '')}"

    # Deterministic-order proof BEFORE any failure injection: the REAL
    # enumerator must complete cleanly and visit the target copies in
    # exactly [s1, s2] order (explicit distinct committed created_at).
    from services.password_reset_service import _enumerate_active_tenant_users

    async with AsyncSessionLocal() as db:
        pre_scan = await _enumerate_active_tenant_users(db)
    assert pre_scan.failed_schema_count == 0
    target_order = [
        row_schema
        for row_email, row_schema, _uid in pre_scan.rows
        if row_email == email
    ]
    assert target_order == [s1, s2]

    raw_token = await _issue_reset_token(email)

    # Real failure injection: SELECTs (the scan) still succeed, only the
    # UPDATE on the second copy raises.
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                f'CREATE FUNCTION "{s2}".h2b_r2_block_update() RETURNS trigger AS $$ '
                "BEGIN RAISE EXCEPTION 'forced apply failure'; END "
                "$$ LANGUAGE plpgsql"
            )
        )
        await db.execute(
            text(
                f'CREATE TRIGGER h2b_r2_block BEFORE UPDATE ON "{s2}".users '
                f'FOR EACH ROW EXECUTE FUNCTION "{s2}".h2b_r2_block_update()'
            )
        )
        await db.commit()

    calls = _capture_auth_logs(monkeypatch)
    metrics_before = _metric_snapshot()

    async with AsyncSessionLocal() as db:
        async with _client(db) as client:
            broken = await client.post(
                RESET_URL, json={"reset_token": raw_token, "new_password": new_pw}
            )

    # Fails closed with the exact neutral 401 envelope (no partial success).
    assert broken.status_code == 401
    assert broken.json()["detail"]["code"] == "INVALID_OR_EXPIRED_PASSWORD_RESET_TOKEN"

    # Exactly one sanitized APPLY_FAILED event for the consume fan-out.
    assert len(calls["error"]) == 1
    extra = calls["error"][0]["kwargs"].get("extra", {})
    assert extra.get("event_class") == "PASSWORD_RESET_APPLY_FAILED"
    assert extra.get("phase") == "reset_consume_apply"
    assert extra.get("updated_count") == 1  # first copy staged, then aborted
    assert extra.get("remaining_copy_count") == 1
    payload = str(calls["error"][0])
    assert email not in payload
    assert s1 not in payload and s2 not in payload
    after = _metric_snapshot()
    assert after["PASSWORD_RESET_APPLY_FAILED"] == (
        metrics_before["PASSWORD_RESET_APPLY_FAILED"] + 1
    )
    for cls in EVENT_CLASSES:
        if cls != "PASSWORD_RESET_APPLY_FAILED":
            assert after[cls] == metrics_before[cls]

    # Outer rollback: the FIRST copy's staged update is undone — BOTH copies
    # still verify the old password and reject the new one.
    for schema in (s1, s2):
        assert verify_password(old_pw, await _copy_password_hash(schema, email))
        assert not verify_password(new_pw, await _copy_password_hash(schema, email))

    # Token NOT consumed.
    assert await _token_used_at(raw_token) is None

    # Remove the failure condition; the SAME token resets both copies.
    async with AsyncSessionLocal() as db:
        await db.execute(text(f'DROP TRIGGER h2b_r2_block ON "{s2}".users'))
        await db.execute(text(f'DROP FUNCTION "{s2}".h2b_r2_block_update()'))
        await db.commit()

    async with AsyncSessionLocal() as db:
        async with _client(db) as client:
            repaired = await client.post(
                RESET_URL, json={"reset_token": raw_token, "new_password": new_pw}
            )
    assert repaired.status_code == 200
    for schema in (s1, s2):
        assert verify_password(new_pw, await _copy_password_hash(schema, email))
    assert await _token_used_at(raw_token) is not None
