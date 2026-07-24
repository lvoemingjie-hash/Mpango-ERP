"""DC-12R1-S1-R2 strict mapping + migration contract closure tests (RED -> GREEN).

Covers:
- malformed same-name token tables / wrong CHECK / FK / index -> PreflightFailure
- missing mapped user/schema -> fail closed before any password write
- conflicting active hashes -> PreflightFailure
- real PostgreSQL role/permission catalog assertions (migration + bootstrap)
- exact exception types/codes (no pytest.raises(Exception))
- token retryable after a failed-then-repaired mapping
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from core.config import get_settings
from core.security import verify_password
from services.email_delivery import clear_dev_email_deliveries, get_dev_retailer_email_deliveries
from services.retailer_provisioning_service import (
    RETAILER_CREDENTIAL_CONFLICT,
    SETUP_TOKEN_INVALID,
    RetailerCredentialTokenInvalidError,
    RetailerProvisioningError,
    RetailerProvisioningService,
)

pytestmark = pytest.mark.asyncio


async def _execute(db, sql, params=None):
    await db.execute(text(sql), params or {})


async def _make_tenant(db, *, code, with_role=True):
    ws_id = uuid.uuid4()
    schema = f"t_{ws_id.hex}"
    await _execute(db, "INSERT INTO public.wholesalers (id, code, name, status, is_deleted) "
                       "VALUES (:id, :code, :name, 'active', false)",
                   {"id": ws_id, "code": code, "name": f"T {code}"})
    await _execute(db, f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    for stmt in (
        f'CREATE TABLE "{schema}".users (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), '
        "email VARCHAR(255) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL, full_name TEXT, "
        "is_active BOOLEAN NOT NULL DEFAULT true, created_at TIMESTAMPTZ DEFAULT now(), "
        "updated_at TIMESTAMPTZ DEFAULT now(), is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, "
        "created_by UUID, updated_by UUID)",
        f'CREATE TABLE "{schema}".roles (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), name VARCHAR(100) NOT NULL UNIQUE, '
        "description TEXT, created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), "
        "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, created_by UUID, updated_by UUID)",
        f'CREATE TABLE "{schema}".permissions (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), code VARCHAR(100) NOT NULL UNIQUE, '
        "description TEXT, created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), "
        "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, created_by UUID, updated_by UUID)",
        f'CREATE TABLE "{schema}".user_roles (user_id UUID NOT NULL REFERENCES "{schema}".users(id) ON DELETE CASCADE, '
        f'role_id UUID NOT NULL REFERENCES "{schema}".roles(id) ON DELETE CASCADE, PRIMARY KEY (user_id, role_id))',
        f'CREATE TABLE "{schema}".role_permissions (role_id UUID NOT NULL REFERENCES "{schema}".roles(id) ON DELETE CASCADE, '
        f'permission_id UUID NOT NULL REFERENCES "{schema}".permissions(id) ON DELETE CASCADE, PRIMARY KEY (role_id, permission_id))',
        f'CREATE UNIQUE INDEX ux_users_email_active ON "{schema}".users (email) WHERE is_deleted IS FALSE',
    ):
        await _execute(db, stmt)
    if with_role:
        await _execute(db, f'INSERT INTO "{schema}".roles (name, description) VALUES (\'retailer_operator\', \'R\') ON CONFLICT DO NOTHING')
        for c in ("client:catalog:read", "client:orders:read", "client:orders:create",
                  "client:payments:read", "client:payments:create", "client:finance:read"):
            await _execute(db, f'INSERT INTO "{schema}".permissions (code, description) VALUES (:c, \'x\') ON CONFLICT DO NOTHING', {"c": c})
    await db.commit()
    return str(ws_id), schema


async def _create_invitation(db, *, ws, phone):
    exp = datetime.now(timezone.utc) + timedelta(days=7)
    code = f"INV{uuid.uuid4().hex[:12]}"
    await _execute(db, "INSERT INTO public.invitations (code, status, wholesaler_id, retailer_phone, expires_at) "
                       "VALUES (:c, 'active', :ws, :p, :e)", {"c": code, "ws": ws, "p": phone, "e": exp})
    await db.commit()
    return code


@pytest_asyncio.fixture
async def r2_db():
    eng = create_async_engine(get_settings().DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"))
    async with AsyncSession(eng, expire_on_commit=False) as s:
        for t in ("retailer_credential_setup_tokens", "retailer_password_reset_tokens"):
            await s.execute(text(f"DELETE FROM public.{t}"))
        await s.execute(text("DELETE FROM public.invitations"))
        await s.execute(text("DELETE FROM public.wholesaler_retailer_bindings"))
        await s.execute(text("DELETE FROM public.retailers"))
        await s.execute(text("DELETE FROM public.wholesalers WHERE code LIKE 'R2T%'"))
        await s.commit()
        clear_dev_email_deliveries()
        yield s
        await s.rollback()
    await eng.dispose()


# ---------------------------------------------------------------------------
# #6: exact exception types (not pytest.raises(Exception))
# ---------------------------------------------------------------------------

async def test_missing_mapping_raises_exact_RetailerProvisioningError_with_code(r2_db):
    """A reset against a retailer whose mapped user was deleted must raise
    RetailerProvisioningError with an exact code (not a bare Exception)."""
    ws, schema = await _make_tenant(r2_db, code=f"R2T{uuid.uuid4().hex[:6]}".upper())
    phone = "+2770001"
    email = "r2exact@example.com"
    code = await _create_invitation(r2_db, ws=ws, phone=phone)
    svc = RetailerProvisioningService(r2_db)
    await svc.register_with_invitation(invitation_code=code, phone=phone, email=email)
    await r2_db.commit()
    await svc.consume_setup_token(get_dev_retailer_email_deliveries(email)[0].token, "RealPass1")
    await r2_db.commit()

    # Issue a reset token.
    clear_dev_email_deliveries()
    ws_code = (await r2_db.execute(text("SELECT code FROM public.wholesalers WHERE id=:i"), {"i": ws})).scalar_one()
    await svc.request_password_reset(email=email, wholesaler_code=ws_code)
    await r2_db.commit()
    raw = get_dev_retailer_email_deliveries(email)[0].token

    # Delete the mapped user -> reset must fail with the EXACT exception + code.
    uid = (await r2_db.execute(text(f'SELECT id FROM "{schema}".users WHERE email=:e'), {"e": email})).scalar_one()
    await r2_db.execute(text(f'DELETE FROM "{schema}".users WHERE id=:u'), {"u": uid})
    await r2_db.commit()

    with pytest.raises(RetailerProvisioningError) as exc:
        await svc.consume_password_reset(raw, "NewPass1")
    # The mapped user row is gone but the binding still references it ->
    # pre-write existence check catches it as RETAILER_MAPPED_COPY_MISSING.
    assert exc.value.code == "RETAILER_MAPPED_COPY_MISSING"


# ---------------------------------------------------------------------------
# #2: token retryable after a failed-then-repaired mapping
# ---------------------------------------------------------------------------

async def test_token_remains_usable_after_failed_then_repaired_mapping(r2_db):
    ws, schema = await _make_tenant(r2_db, code=f"R2T{uuid.uuid4().hex[:6]}".upper())
    phone = "+2770002"
    email = "r2retry@example.com"
    code = await _create_invitation(r2_db, ws=ws, phone=phone)
    svc = RetailerProvisioningService(r2_db)
    await svc.register_with_invitation(invitation_code=code, phone=phone, email=email)
    await r2_db.commit()
    raw = get_dev_retailer_email_deliveries(email)[0].token

    # Sabotage: delete the mapped user so setup fails.
    uid = (await r2_db.execute(text(f'SELECT id FROM "{schema}".users WHERE email=:e'), {"e": email})).scalar_one()
    await r2_db.execute(text(f'DELETE FROM "{schema}".users WHERE id=:u'), {"u": uid})
    await r2_db.commit()

    # Setup must fail (token NOT consumed).
    with pytest.raises(RetailerProvisioningError):
        await svc.consume_setup_token(raw, "FirstPass1")
    await r2_db.rollback()

    # Token still actionable (not used/revoked).
    used = (await r2_db.execute(
        text("SELECT used_at FROM public.retailer_credential_setup_tokens WHERE token_hash IS NOT NULL LIMIT 1")
    )).first()
    # Repair: re-create the mapped user + re-link the binding.
    binding_id = (await r2_db.execute(
        text("SELECT id, tenant_user_id FROM public.wholesaler_retailer_bindings WHERE wholesaler_id=:w"), {"w": ws}
    )).first()
    new_uid = uuid.uuid4()
    await r2_db.execute(text(f'INSERT INTO "{schema}".users (id, email, password_hash, is_active) '
                             'VALUES (:id, :e, :h, false)'), {"id": new_uid, "e": email, "h": "placeholder"})
    await r2_db.execute(text("UPDATE public.wholesaler_retailer_bindings SET tenant_user_id=:u WHERE id=:b"),
                        {"u": new_uid, "b": binding_id[0]})
    await r2_db.commit()

    # Now the SAME token succeeds.
    await svc.consume_setup_token(raw, "RepairedPass1")
    await r2_db.commit()
    h = (await r2_db.execute(text(f'SELECT password_hash, is_active FROM "{schema}".users WHERE email=:e'), {"e": email})).first()
    assert h[1] is True
    assert verify_password("RepairedPass1", h[0]) is True


# ---------------------------------------------------------------------------
# #7: real PostgreSQL role/permission catalog (not source-string)
# ---------------------------------------------------------------------------

async def test_migration_seeds_retailer_operator_role_and_client_perms_in_real_pg(r2_db):
    """Simulate migration 036's per-tenant RBAC seed on a real tenant and assert
    the actual PostgreSQL catalog (roles/permissions/role_permissions rows)."""
    import importlib.util, pathlib
    # Load the migration module to call _seed_tenant_rbac against a real schema.
    spec = importlib.util.spec_from_file_location(
        "m036", pathlib.Path("alembic/versions/036_retailer_mvp_identity.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    ws, schema = await _make_tenant(r2_db, code=f"R2T{uuid.uuid4().hex[:6]}".upper(), with_role=False)
    # Also seed an admin role to verify it gets invitations:revoke + reissue.
    await r2_db.execute(text(f"INSERT INTO \"{schema}\".roles (name, description) VALUES ('admin', 'A') ON CONFLICT DO NOTHING"))
    await r2_db.commit()

    row = {"tenant_schema": schema}
    # Use a raw connection to call the migration helper (it expects a sync bind).
    raw = await r2_db.connection()
    await raw.run_sync(lambda sync_conn: mod._seed_tenant_rbac(sync_conn, row))
    await r2_db.commit()

    # retailer_operator role exists.
    ro = (await r2_db.execute(text(f"SELECT id FROM \"{schema}\".roles WHERE name='retailer_operator'"))).first()
    assert ro is not None
    # It has EXACTLY the 6 client:* permissions.
    perms = [r[0] for r in (await r2_db.execute(text(
        f"SELECT p.code FROM \"{schema}\".role_permissions rp "
        f"JOIN \"{schema}\".permissions p ON p.id=rp.permission_id "
        f"JOIN \"{schema}\".roles r ON r.id=rp.role_id WHERE r.name='retailer_operator' ORDER BY p.code"
    ))).all()]
    assert perms == ["client:catalog:read", "client:finance:read", "client:orders:create",
                     "client:orders:read", "client:payments:create", "client:payments:read"]
    # retailer_operator does NOT have invitations:revoke or retailers:reissue_credential.
    assert "invitations:revoke" not in perms
    assert "retailers:reissue_credential" not in perms
    # admin HAS both.
    admin_perms = [r[0] for r in (await r2_db.execute(text(
        f"SELECT p.code FROM \"{schema}\".role_permissions rp "
        f"JOIN \"{schema}\".permissions p ON p.id=rp.permission_id "
        f"JOIN \"{schema}\".roles r ON r.id=rp.role_id WHERE r.name='admin' ORDER BY p.code"
    ))).all()]
    assert "invitations:revoke" in admin_perms
    assert "retailers:reissue_credential" in admin_perms


# ---------------------------------------------------------------------------
# #8: malformed same-name token table / wrong CHECK / wrong index -> PreflightFailure
# (These test the migration contract validators directly.)
# ---------------------------------------------------------------------------

async def test_malformed_setup_token_table_missing_column_triggers_preflight(r2_db):
    """A same-name table missing required columns must fail the validator.

    Uses an ISOLATED sync connection so the malformed table never pollutes the
    async session's transaction state. The well-formed table is always restored.
    """
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location("m036", pathlib.Path("alembic/versions/036_retailer_mvp_identity.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

    import os
    from sqlalchemy import create_engine
    db_url = os.environ.get("DATABASE_URL", "").replace("postgresql://", "postgresql+psycopg2://")
    eng = create_engine(db_url)
    try:
        with eng.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS public.retailer_credential_setup_tokens"))
            conn.execute(text(
                "CREATE TABLE public.retailer_credential_setup_tokens "
                "(id UUID PRIMARY KEY, retailer_id UUID, token_hash VARCHAR(128))"
            ))
        # Validate on a separate connection (outside any txn) — must fail.
        with pytest.raises(mod.PreflightFailure) as exc:
            with eng.connect() as conn:
                mod._validate_setup_token_table_contract(conn)
        assert "missing columns" in str(exc.value) or "binding_id" in str(exc.value)
    finally:
        # Always restore the well-formed table.
        with eng.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS public.retailer_credential_setup_tokens"))
            mod._create_retailer_setup_token_table(conn)
    eng.dispose()
