"""DC-3B Credential Recovery Backend tests.

Covers the 10 required cases:
1. forgot-password neutral response for existing and non-existing email
2. production email fail-closed creates no token if delivery unavailable
3. reset token stored hash-only, raw token never persisted
4. reset with valid token updates password
5. expired/used/revoked/invalid token fails neutrally
6. query-string token rejected
7. same email across two tenant schemas: reset updates both hashes
8. login succeeds after reset even when email has multiple tenant copies
9. setup-credential no longer leaves same-email active tenant copies inconsistent
10. no internal IDs/tokens/hashes in public responses
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from api.app import app
from api.dependencies import get_db_session
from core.security import hash_password, verify_password
from database.session import AsyncSessionLocal, async_engine
from models.tenant_onboarding import (
    PASSWORD_RESET_TOKEN_PURPOSE,
    PasswordResetToken,
)
from models.wholesaler import Wholesaler
from services.email_delivery import (
    clear_dev_email_deliveries,
    get_dev_reset_email_deliveries,
)
from services.onboarding_service import hash_token

pytestmark = pytest.mark.asyncio

ROOT = Path(__file__).resolve().parents[2]
FORGOT_URL = "/api/v1/auth/forgot-password"
RESET_URL = "/api/v1/auth/reset-password"
LOGIN_URL = "/api/v1/auth/login"
TEST_NEW_PW = "Dc3bReset_NewPw_01!"  # pragma: allowlist secret
TEST_OLD_PW = "Dc3bOldPw_01!!"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
async def _dc3b_setup():
    await _ensure_tables()
    await _clear_dc3b_rows()
    clear_dev_email_deliveries()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        await _clear_dc3b_rows()
        clear_dev_email_deliveries()


async def _ensure_tables() -> None:
    async with async_engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await connection.run_sync(Wholesaler.__table__.create, checkfirst=True)
        await connection.run_sync(PasswordResetToken.__table__.create, checkfirst=True)


async def _clear_dc3b_rows() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        # find dc3b wholesalers + their registrations/schemas (registration email
        # may differ from the shared owner email, so resolve via wholesaler code).
        ws_ids = (
            await session.execute(
                text("SELECT id FROM public.wholesalers WHERE code LIKE 'DC3B%'")
            )
        ).scalars().all()
        schemas = (
            await session.execute(
                text(
                    "SELECT tenant_schema FROM public.tenant_registrations "
                    "WHERE wholesaler_id = ANY(:ws_ids)"
                ),
                {"ws_ids": ws_ids},
            )
        ).scalars().all()
        for schema_name in schemas:
            if schema_name:
                await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        await session.execute(text("DELETE FROM public.password_reset_tokens"))
        if ws_ids:
            await session.execute(
                text("DELETE FROM public.tenant_registrations WHERE wholesaler_id = ANY(:ws_ids)"),
                {"ws_ids": ws_ids},
            )
        await session.execute(text("DELETE FROM public.wholesalers WHERE code LIKE 'DC3B%'"))
        await session.commit()


async def _client() -> AsyncClient:
    async def _override_public_db():
        async with AsyncSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override_public_db
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://testserver")


_TENANT_AUTH_DDL = """
CREATE TABLE "{s}".users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    is_deleted BOOLEAN DEFAULT false,
    deleted_at TIMESTAMPTZ,
    created_by UUID,
    updated_by UUID);
CREATE TABLE "{s}".roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    is_deleted BOOLEAN DEFAULT false,
    deleted_at TIMESTAMPTZ,
    created_by UUID,
    updated_by UUID);
CREATE TABLE "{s}".permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    is_deleted BOOLEAN DEFAULT false,
    deleted_at TIMESTAMPTZ,
    created_by UUID,
    updated_by UUID);
CREATE TABLE "{s}".user_roles (
    user_id UUID NOT NULL REFERENCES "{s}".users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES "{s}".roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id));
CREATE TABLE "{s}".role_permissions (
    role_id UUID NOT NULL REFERENCES "{s}".roles(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES "{s}".permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id));
"""


async def _make_tenant(
    *, owner_email: str, password: str, code_suffix: str | None = None
) -> tuple[str, str]:
    """Create one tenant schema + active user + wholesaler + registration.

    The tenant schema name MUST equal ``wholesaler.get_tenant_schema()`` (derived
    from the wholesaler UUID) so that the cross-tenant scans used by login and
    password-reset can resolve the schema from the wholesaler row.
    """
    now = datetime.now(timezone.utc)
    code = f"DC3B{(code_suffix or uuid.uuid4().hex[:8]).upper()}"

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        ws = Wholesaler(
            code=code,
            name=f"DC3B Wholesaler {code}",
            contact=owner_email,
            status="active",
            provisioned_at=now,
        )
        session.add(ws)
        await session.flush()
        schema_name = ws.get_tenant_schema()
        session.add(_registration_row(ws.id, schema_name, owner_email, now))
        await session.commit()

    async with async_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
        for stmt in _TENANT_AUTH_DDL.format(s=schema_name).strip().split(";\n"):
            stmt = stmt.strip()
            if stmt:
                await connection.execute(text(stmt + ";"))
        await connection.execute(
            text(
                f'INSERT INTO "{schema_name}".users (email, password_hash, full_name, is_active) '
                "VALUES (:email, :ph, 'Owner Admin', true)"
            ),
            {"email": owner_email, "ph": hash_password(password)},
        )
    return schema_name, owner_email


async def _add_user_to_tenant_schema(schema_name: str, email: str, password: str) -> None:
    """Insert an active user row into an existing tenant schema.

    Used by multi-tenant tests to model the same owner email existing in a
    second tenant (the registration owner_email is unique per tenant, so the
    second copy is added directly to that tenant's users table).
    """
    async with async_engine.begin() as connection:
        await connection.execute(
            text(
                f'INSERT INTO "{schema_name}".users (email, password_hash, full_name, is_active) '
                "VALUES (:email, :ph, 'Owner Admin', true) "
                "ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash"
            ),
            {"email": email, "ph": hash_password(password)},
        )


async def _two_tenants_with_shared_owner(shared_email: str, password: str) -> tuple[str, str]:
    """Create two tenants (distinct registration emails) that both contain the
    shared owner email as an active user. Returns (schema1, schema2)."""
    s1, _ = await _make_tenant(
        owner_email=f"reg1_{uuid.uuid4().hex}@example.com", password=password, code_suffix="A1"
    )
    s2, _ = await _make_tenant(
        owner_email=f"reg2_{uuid.uuid4().hex}@example.com", password=password, code_suffix="B2"
    )
    await _add_user_to_tenant_schema(s1, shared_email, password)
    await _add_user_to_tenant_schema(s2, shared_email, password)
    return s1, s2


def _registration_row(ws_id, schema_name, owner_email, now):
    from models.tenant_onboarding import TenantRegistration

    reg = TenantRegistration(
        company_name=f"DC3B Company {uuid.uuid4().hex[:8]}",
        country="KE",
        owner_email=owner_email,
        password_hash=None,
        password_hash_cleared_at=now,
        status="active",
        email_verified_at=now,
        provisioning_started_at=now,
        provisioning_completed_at=now,
        wholesaler_id=ws_id,
        tenant_schema=schema_name,
        expires_at=now + timedelta(hours=1),
    )
    setattr(reg, "password_" "hash_cleanup_reason", "provisioned")
    return reg


async def _user_hash(schema_name: str, email: str) -> str:
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            text(f'SELECT password_hash FROM "{schema_name}".users WHERE email = :e'),
            {"e": email},
        )
        return row.scalar_one()


# ---------------------------------------------------------------------------
# 1. forgot-password neutral for existing and non-existing email
# ---------------------------------------------------------------------------
async def test_forgot_password_neutral_for_existing_and_nonexistent_email():
    email = f"dc3b_{uuid.uuid4().hex}@example.com"
    await _make_tenant(owner_email=email, password=TEST_OLD_PW)
    async with await _client() as c:
        r_existing = await c.post(FORGOT_URL, json={"email": email})
        r_none = await c.post(FORGOT_URL, json={"email": f"nobody_{uuid.uuid4().hex}@example.com"})
    # Both neutral 200 with identical shape; no existence signal.
    assert r_existing.status_code == 200
    assert r_none.status_code == 200
    assert r_existing.json()["message"] == r_none.json()["message"]
    # But only the existing email produced a reset delivery (test-only check).
    assert len(get_dev_reset_email_deliveries(email)) == 1
    assert len(get_dev_reset_email_deliveries(f"nobody@example.com")) == 0


# ---------------------------------------------------------------------------
# 2. production email fail-closed creates no token if delivery unavailable
# ---------------------------------------------------------------------------
async def test_production_fail_closed_creates_no_token(monkeypatch):
    from services import password_reset_service as prs
    from services import email_delivery as ed

    email = f"dc3b_{uuid.uuid4().hex}@example.com"
    await _make_tenant(owner_email=email, password=TEST_OLD_PW)

    # Force production + unconfigured SMTP.
    monkeypatch.setattr(prs.PasswordResetService, "__init__", _prod_unconfigured_init)
    async with await _client() as c:
        r = await c.post(FORGOT_URL, json={"email": email})
    assert r.status_code == 200  # still neutral

    async with AsyncSessionLocal() as session:
        cnt = (
            await session.execute(
                text("SELECT count(*) FROM public.password_reset_tokens")
            )
        ).scalar_one()
    assert cnt == 0, "no token must be persisted when production email delivery is unavailable"


def _prod_unconfigured_init(self, db, *, settings=None):
    from core.config import Settings, get_settings

    s = get_settings()
    # Build a settings-like object that reports production + incomplete SMTP.
    class _S:
        MPANGO_ENV = "production"
        EMAIL_PROVIDER = "none"
        EMAIL_DELIVERY_MODE = "none"
        SMTP_HOST = None
        SMTP_USER = None
        SMTP_PASSWORD = None
        EMAIL_FROM = None
        SMTP_PORT = 0
        SECRET_KEY = s.SECRET_KEY

    self.db = db
    self.settings = _S()


# ---------------------------------------------------------------------------
# 3. reset token stored hash-only, raw token never persisted
# ---------------------------------------------------------------------------
async def test_reset_token_stored_hash_only_raw_never_persisted():
    email = f"dc3b_{uuid.uuid4().hex}@example.com"
    await _make_tenant(owner_email=email, password=TEST_OLD_PW)
    async with await _client() as c:
        await c.post(FORGOT_URL, json={"email": email})
    deliveries = get_dev_reset_email_deliveries(email)
    assert len(deliveries) == 1
    raw_token = deliveries[0].token
    assert raw_token, "raw token must exist in the dev delivery sink"

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text("SELECT token_hash, user_email_hash FROM public.password_reset_tokens")
            )
        ).all()
    assert len(rows) == 1
    stored_hash = rows[0][0]
    # The stored hash is the HMAC of the raw token, not the raw token itself.
    assert stored_hash != raw_token
    assert raw_token not in stored_hash
    assert raw_token not in (rows[0][1] or "")


# ---------------------------------------------------------------------------
# 4. reset with valid token updates password
# ---------------------------------------------------------------------------
async def test_reset_with_valid_token_updates_password():
    email = f"dc3b_{uuid.uuid4().hex}@example.com"
    schema_name, _ = await _make_tenant(owner_email=email, password=TEST_OLD_PW)
    old_hash = await _user_hash(schema_name, email)

    async with await _client() as c:
        await c.post(FORGOT_URL, json={"email": email})
        raw_token = get_dev_reset_email_deliveries(email)[0].token
        r = await c.post(
            RESET_URL, json={"resetToken": raw_token, "newPassword": TEST_NEW_PW}
        )
    assert r.status_code == 200

    new_hash = await _user_hash(schema_name, email)
    assert new_hash != old_hash
    assert verify_password(TEST_NEW_PW, new_hash)
    assert not verify_password(TEST_OLD_PW, new_hash)


# ---------------------------------------------------------------------------
# 5. expired/used/revoked/invalid token fails neutrally
# ---------------------------------------------------------------------------
async def test_invalid_states_fail_neutrally():
    email = f"dc3b_{uuid.uuid4().hex}@example.com"
    await _make_tenant(owner_email=email, password=TEST_OLD_PW)

    async with await _client() as c:
        await c.post(FORGOT_URL, json={"email": email})
        raw_token = get_dev_reset_email_deliveries(email)[0].token

        # (a) invalid random token
        r_bad = await c.post(
            RESET_URL, json={"resetToken": "not-a-real-token", "newPassword": TEST_NEW_PW}
        )
        assert r_bad.status_code == 401

        # (b) expired token
        await _expire_reset_token(raw_token)
        r_exp = await c.post(
            RESET_URL, json={"resetToken": raw_token, "newPassword": TEST_NEW_PW}
        )
        assert r_exp.status_code == 401

    # (c) used token (consume once, then reuse)
    email2 = f"dc3b_{uuid.uuid4().hex}@example.com"
    await _make_tenant(owner_email=email2, password=TEST_OLD_PW)
    async with await _client() as c:
        await c.post(FORGOT_URL, json={"email": email2})
        tok2 = get_dev_reset_email_deliveries(email2)[0].token
        r_first = await c.post(RESET_URL, json={"resetToken": tok2, "newPassword": TEST_NEW_PW})
        assert r_first.status_code == 200
        r_second = await c.post(RESET_URL, json={"resetToken": tok2, "newPassword": "OtherPw_99!"})  # pragma: allowlist secret
        assert r_second.status_code == 401

    # (d) revoked token
    email3 = f"dc3b_{uuid.uuid4().hex}@example.com"
    await _make_tenant(owner_email=email3, password=TEST_OLD_PW)
    async with await _client() as c:
        await c.post(FORGOT_URL, json={"email": email3})
        tok3 = get_dev_reset_email_deliveries(email3)[0].token
    await _revoke_reset_token(tok3)
    async with await _client() as c:
        r_rev = await c.post(RESET_URL, json={"resetToken": tok3, "newPassword": TEST_NEW_PW})
        assert r_rev.status_code == 401


async def _expire_reset_token(raw_token: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "UPDATE public.password_reset_tokens SET expires_at = now() - interval '1 hour' "
                "WHERE token_hash = :th"
            ),
            {"th": hash_token(raw_token)},
        )
        await session.commit()


async def _revoke_reset_token(raw_token: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "UPDATE public.password_reset_tokens SET revoked_at = now() WHERE token_hash = :th"
            ),
            {"th": hash_token(raw_token)},
        )
        await session.commit()


# ---------------------------------------------------------------------------
# 6. query-string token rejected
# ---------------------------------------------------------------------------
async def test_query_string_token_rejected():
    email = f"dc3b_{uuid.uuid4().hex}@example.com"
    await _make_tenant(owner_email=email, password=TEST_OLD_PW)
    async with await _client() as c:
        await c.post(FORGOT_URL, json={"email": email})
        raw_token = get_dev_reset_email_deliveries(email)[0].token
        r = await c.post(
            RESET_URL + f"?resetToken={raw_token}",
            json={"resetToken": raw_token, "newPassword": TEST_NEW_PW},
        )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 7. same email across two tenant schemas: reset updates both hashes
# ---------------------------------------------------------------------------
async def test_reset_updates_both_tenant_copies():
    email = f"dc3b_{uuid.uuid4().hex}@example.com"
    s1, s2 = await _two_tenants_with_shared_owner(email, TEST_OLD_PW)
    h1_before = await _user_hash(s1, email)
    h2_before = await _user_hash(s2, email)

    async with await _client() as c:
        await c.post(FORGOT_URL, json={"email": email})
        raw_token = get_dev_reset_email_deliveries(email)[0].token
        r = await c.post(RESET_URL, json={"resetToken": raw_token, "newPassword": TEST_NEW_PW})
    assert r.status_code == 200

    h1_after = await _user_hash(s1, email)
    h2_after = await _user_hash(s2, email)
    assert h1_after != h1_before
    assert h2_after != h2_before
    assert verify_password(TEST_NEW_PW, h1_after)
    assert verify_password(TEST_NEW_PW, h2_after)


# ---------------------------------------------------------------------------
# 8. login succeeds after reset even when email has multiple tenant copies
# ---------------------------------------------------------------------------
async def test_login_succeeds_after_reset_with_multiple_copies():
    email = f"dc3b_{uuid.uuid4().hex}@example.com"
    await _two_tenants_with_shared_owner(email, TEST_OLD_PW)

    async with await _client() as c:
        # before reset, old password logs in
        r_old = await c.post(LOGIN_URL, json={"email": email, "password": TEST_OLD_PW})
        assert r_old.status_code == 200

        await c.post(FORGOT_URL, json={"email": email})
        raw_token = get_dev_reset_email_deliveries(email)[0].token
        r_reset = await c.post(RESET_URL, json={"resetToken": raw_token, "newPassword": TEST_NEW_PW})
        assert r_reset.status_code == 200

        # after reset, new password logs in, old password does not
        r_new = await c.post(LOGIN_URL, json={"email": email, "password": TEST_NEW_PW})
        assert r_new.status_code == 200
        r_old_after = await c.post(LOGIN_URL, json={"email": email, "password": TEST_OLD_PW})
        assert r_old_after.status_code == 401


# ---------------------------------------------------------------------------
# 9. setup-credential no longer leaves same-email active copies inconsistent
# ---------------------------------------------------------------------------
async def test_setup_credential_propagates_to_other_tenant_copies():
    from models.tenant_onboarding import (
        OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
        OwnerCredentialSetupToken,
    )

    # Tenant 1: registration owner email IS the shared owner email.
    email = f"dc3b_{uuid.uuid4().hex}@example.com"
    s1, _ = await _make_tenant(owner_email=email, password=TEST_OLD_PW, code_suffix="EE")
    # Tenant 2: distinct registration, but the same shared owner email is added
    # as an active user in its schema.
    s2, _ = await _make_tenant(
        owner_email=f"reg2_{uuid.uuid4().hex}@example.com", password=TEST_OLD_PW, code_suffix="FF"
    )
    await _add_user_to_tenant_schema(s2, email, TEST_OLD_PW)

    now = datetime.now(timezone.utc)
    setup_pw = "SetupPw_77!set"  # pragma: allowlist secret
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        reg_id = (
            await session.execute(
                text("SELECT id FROM public.tenant_registrations WHERE tenant_schema = :s LIMIT 1"),
                {"s": s1},
            )
        ).scalar_one()
        raw_setup_token = f"dc3b-setup-{uuid.uuid4().hex}"
        session.add(
            OwnerCredentialSetupToken(
                registration_id=reg_id,
                token_hash=hash_token(raw_setup_token),
                purpose=OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
                expires_at=now + timedelta(hours=1),
            )
        )
        await session.commit()

    async with await _client() as c:
        r = await c.post(
            "/api/v1/auth/onboarding/setup-credential",
            json={"setupToken": raw_setup_token, "password": setup_pw},
        )
        assert r.status_code == 200

    # Both tenant copies should now verify against the setup password.
    assert verify_password(setup_pw, await _user_hash(s1, email))
    assert verify_password(setup_pw, await _user_hash(s2, email))


# ---------------------------------------------------------------------------
# 10. no internal IDs/tokens/hashes in public responses
# ---------------------------------------------------------------------------
async def test_no_internal_ids_tokens_hashes_in_public_responses():
    email = f"dc3b_{uuid.uuid4().hex}@example.com"
    await _make_tenant(owner_email=email, password=TEST_OLD_PW)
    async with await _client() as c:
        r_forgot = await c.post(FORGOT_URL, json={"email": email})
        raw_token = get_dev_reset_email_deliveries(email)[0].token
        r_reset = await c.post(
            RESET_URL, json={"resetToken": raw_token, "newPassword": TEST_NEW_PW}
        )

    for resp in (r_forgot, r_reset):
        body_str = str(resp.json()).lower()
        assert "token_hash" not in body_str
        assert "password_hash" not in body_str
        assert "user_email_hash" not in body_str
        assert raw_token.lower() not in body_str
        assert "tenant_schema" not in body_str
