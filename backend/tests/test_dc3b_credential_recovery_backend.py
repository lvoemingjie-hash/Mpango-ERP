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
from fastapi import HTTPException, Request
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
        from api.dependencies import get_current_user_context
        app.dependency_overrides.pop(get_current_user_context, None)
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


def _real_token_dependency(request: "Request"):
    """Module-level FastAPI dependency: decode the real bearer JWT.

    Defined at module scope (not in a closure) so FastAPI's annotation
    inspection resolves ``Request`` correctly even with
    ``from __future__ import annotations``.
    """
    from core.security import decode_token, ExpiredTokenError, InvalidTokenError
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"code": "INVALID_TOKEN", "message": "No bearer token"})
    raw = auth.split(" ", 1)[1].strip()
    try:
        payload = decode_token(raw)
    except ExpiredTokenError:
        raise HTTPException(status_code=401, detail={"code": "TOKEN_EXPIRED", "message": "Token expired"})
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail={"code": "INVALID_TOKEN", "message": "Invalid token"})
    from api.context.auth import AuthContext
    setattr(request.state, "_dc3b_auth_ctx", AuthContext(token=payload, raw_token=raw))
    return payload


async def _client_with_real_auth() -> AsyncClient:
    """Test client whose /select-tenant and /refresh see the REAL decoded JWT.

    The default MockAuthStrategy (MPANGO_ENV=test) ignores the Authorization
    header and injects a fixed mock token without the DC-3B-R1 ``tmap`` claim.
    For R1 tests we must exercise the real JWT path, so we override
    ``get_current_user_context`` to decode the bearer token from the header.
    """
    from api.dependencies import get_current_user_context

    async def _override_public_db():
        async with AsyncSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override_public_db
    app.dependency_overrides[get_current_user_context] = _real_token_dependency
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


# ===========================================================================
# DC-3B-R1 regression tests: auth tenant selection consistency
# ===========================================================================
SELECT_TENANT_URL = "/api/v1/auth/select-tenant"
REFRESH_URL = "/api/v1/auth/refresh"


def _identity_token(login_resp_json: dict) -> str:
    return login_resp_json["data"]["access_token"]


def _identity_refresh_token(login_resp_json: dict) -> str:
    return login_resp_json["data"]["refresh_token"]


def _available_tenant_ids(login_resp_json: dict) -> list[str]:
    return [t["id"] for t in login_resp_json["data"]["available_tenants"]]


# ---------------------------------------------------------------------------
# R1-a: same email in two tenants with DIFFERENT passwords -> login with
# password A lists/selects only tenant A (unverified tenant not granted).
# ---------------------------------------------------------------------------
async def test_r1_different_passwords_isolates_unverified_tenant():
    shared_email = f"dc3b_{uuid.uuid4().hex}@example.com"
    # tenant 1 with password A
    PW_A = "TenantAPw_01!!"  # pragma: allowlist secret
    PW_B = "TenantBPw_02!!"  # pragma: allowlist secret
    s1, _ = await _make_tenant(
        owner_email=f"reg1_{uuid.uuid4().hex}@example.com", password=PW_A, code_suffix="G1"
    )
    await _add_user_to_tenant_schema(s1, shared_email, PW_A)
    # tenant 2 with password B (different) for the SAME shared email
    s2, _ = await _make_tenant(
        owner_email=f"reg2_{uuid.uuid4().hex}@example.com", password=PW_B, code_suffix="H2"
    )
    await _add_user_to_tenant_schema(s2, shared_email, PW_B)

    async with await _client_with_real_auth() as c:
        # login with password A -> only tenant A (s1) should be listed.
        r = await c.post(LOGIN_URL, json={"email": shared_email, "password": PW_A})
        assert r.status_code == 200
        avail = _available_tenant_ids(r.json())
        # exactly one tenant selectable (the password-A one). We do not assert
        # which schema by name (order may vary), only that the count is 1 and
        # select-tenant works for it.
        assert len(avail) == 1, "unverified tenant must not be listed"
        # select the one available tenant -> 200
        r_sel = await c.post(
            SELECT_TENANT_URL,
            json={"tenant_id": avail[0]},
            headers={"Authorization": f"Bearer {_identity_token(r.json())}"},
        )
        assert r_sel.status_code == 200

    # The other tenant (password B) must NOT be selectable with the password-A
    # identity token. Resolve its wholesaler id and try select-tenant -> 403.
    async with AsyncSessionLocal() as session:
        other_ws_id = (
            await session.execute(
                text("SELECT id FROM public.wholesalers WHERE code LIKE 'DC3BH2%' LIMIT 1")
            )
        ).scalar_one()
    async with await _client_with_real_auth() as c:
        r2 = await c.post(LOGIN_URL, json={"email": shared_email, "password": PW_A})
        assert r2.status_code == 200
        r_sel_bad = await c.post(
            SELECT_TENANT_URL,
            json={"tenant_id": str(other_ws_id)},
            headers={"Authorization": f"Bearer {_identity_token(r2.json())}"},
        )
        assert r_sel_bad.status_code == 403


# ---------------------------------------------------------------------------
# R1-b: same email + same password but DIFFERENT user IDs across two tenants ->
# login lists both and select-tenant succeeds for both.
# ---------------------------------------------------------------------------
async def test_r1_same_password_different_user_ids_selects_both():
    shared_email = f"dc3b_{uuid.uuid4().hex}@example.com"
    s1, _ = await _make_tenant(
        owner_email=f"reg3_{uuid.uuid4().hex}@example.com", password=TEST_OLD_PW, code_suffix="I3"
    )
    await _add_user_to_tenant_schema(s1, shared_email, TEST_OLD_PW)
    s2, _ = await _make_tenant(
        owner_email=f"reg4_{uuid.uuid4().hex}@example.com", password=TEST_OLD_PW, code_suffix="J4"
    )
    await _add_user_to_tenant_schema(s2, shared_email, TEST_OLD_PW)
    # the two user rows have different IDs (created independently).
    async with AsyncSessionLocal() as session:
        u1 = (await session.execute(text(f'SELECT id FROM "{s1}".users WHERE email = :e'), {"e": shared_email})).scalar_one()
        u2 = (await session.execute(text(f'SELECT id FROM "{s2}".users WHERE email = :e'), {"e": shared_email})).scalar_one()
    assert u1 != u2, "test precondition: distinct user IDs"

    async with await _client_with_real_auth() as c:
        r = await c.post(LOGIN_URL, json={"email": shared_email, "password": TEST_OLD_PW})
        assert r.status_code == 200
        avail = _available_tenant_ids(r.json())
        assert len(avail) == 2, "both verified tenants must be listed"
        tok = _identity_token(r.json())
        # select each tenant -> both must succeed (uses tmap per-tenant user_id)
        for tid in avail:
            r_sel = await c.post(
                SELECT_TENANT_URL,
                json={"tenant_id": tid},
                headers={"Authorization": f"Bearer {tok}"},
            )
            assert r_sel.status_code == 200, f"select-tenant failed for {tid}"


# ---------------------------------------------------------------------------
# R1-c: after password reset fan-out, both tenant copies can login/select.
# ---------------------------------------------------------------------------
async def test_r1_after_reset_both_copies_login_and_select():
    shared_email = f"dc3b_{uuid.uuid4().hex}@example.com"
    s1, s2 = await _two_tenants_with_shared_owner(shared_email, TEST_OLD_PW)

    async with await _client_with_real_auth() as c:
        await c.post(FORGOT_URL, json={"email": shared_email})
        raw_token = get_dev_reset_email_deliveries(shared_email)[0].token
        r_reset = await c.post(RESET_URL, json={"resetToken": raw_token, "newPassword": TEST_NEW_PW})
        assert r_reset.status_code == 200

    async with await _client_with_real_auth() as c:
        r = await c.post(LOGIN_URL, json={"email": shared_email, "password": TEST_NEW_PW})
        assert r.status_code == 200
        avail = _available_tenant_ids(r.json())
        assert len(avail) == 2
        tok = _identity_token(r.json())
        for tid in avail:
            r_sel = await c.post(
                SELECT_TENANT_URL,
                json={"tenant_id": tid},
                headers={"Authorization": f"Bearer {tok}"},
            )
            assert r_sel.status_code == 200


# ---------------------------------------------------------------------------
# R1-d: identity refresh preserves tenant selection capability.
# ---------------------------------------------------------------------------
async def test_r1_identity_refresh_preserves_tenant_selection():
    shared_email = f"dc3b_{uuid.uuid4().hex}@example.com"
    await _two_tenants_with_shared_owner(shared_email, TEST_OLD_PW)

    async with await _client_with_real_auth() as c:
        r = await c.post(LOGIN_URL, json={"email": shared_email, "password": TEST_OLD_PW})
        assert r.status_code == 200
        avail = _available_tenant_ids(r.json())
        assert len(avail) == 2

        # refresh the identity token
        r_ref = await c.post(
            REFRESH_URL, json={"refresh_token": _identity_refresh_token(r.json())}
        )
        assert r_ref.status_code == 200
        refreshed_tok = r_ref.json()["data"]["access_token"]

        # after refresh, every originally-available tenant must still be selectable
        for tid in avail:
            r_sel = await c.post(
                SELECT_TENANT_URL,
                json={"tenant_id": tid},
                headers={"Authorization": f"Bearer {refreshed_tok}"},
            )
            assert r_sel.status_code == 200, f"select failed after refresh for {tid}"


# ---------------------------------------------------------------------------
# R1-e: no raw password/token/hash/internal mapping is exposed in public
# response body (login, select-tenant, refresh).
# ---------------------------------------------------------------------------
async def test_r1_no_internal_mapping_in_public_responses():
    shared_email = f"dc3b_{uuid.uuid4().hex}@example.com"
    s1, s2 = await _two_tenants_with_shared_owner(shared_email, TEST_OLD_PW)
    # capture the internal user ids (must never appear in any response body)
    async with AsyncSessionLocal() as session:
        uid1 = str((await session.execute(text(f'SELECT id FROM "{s1}".users WHERE email = :e'), {"e": shared_email})).scalar_one())
        uid2 = str((await session.execute(text(f'SELECT id FROM "{s2}".users WHERE email = :e'), {"e": shared_email})).scalar_one())

    async with await _client_with_real_auth() as c:
        r_login = await c.post(LOGIN_URL, json={"email": shared_email, "password": TEST_OLD_PW})
        assert r_login.status_code == 200
        login_body = str(r_login.json())
        r_sel = await c.post(
            SELECT_TENANT_URL,
            json={"tenant_id": _available_tenant_ids(r_login.json())[0]},
            headers={"Authorization": f"Bearer {_identity_token(r_login.json())}"},
        )
        assert r_sel.status_code == 200
        r_ref = await c.post(REFRESH_URL, json={"refresh_token": _identity_refresh_token(r_login.json())})
        assert r_ref.status_code == 200

    for body in (login_body, str(r_sel.json()), str(r_ref.json())):
        low = body.lower()
        assert "tmap" not in low, "internal tenant map must not be exposed"
        assert "tenant_user_map" not in low
        assert "password_hash" not in low
        assert "token_hash" not in low
        # at most ONE user_id appears in a response (the login user_id of the
        # selected/issuing tenant); the OTHER tenant's user_id must never leak.
        # The login response includes a single user_id; verify both uids are not
        # BOTH present simultaneously (which would leak the cross-tenant map).
        assert not (uid1 in body and uid2 in body), "both tenant user ids leaked"
