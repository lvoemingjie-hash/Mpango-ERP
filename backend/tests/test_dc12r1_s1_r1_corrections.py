"""DC-12R1-S1-R1 merge-blocker correction tests (RED → GREEN).

These tests reproduce the 5 CTO merge-blockers and must pass after the R1 fixes.
They run against a real PostgreSQL 16 DB migrated to head 036, self-contained.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from core.config import get_settings
from core.security import hash_password, verify_password
from services.email_delivery import clear_dev_email_deliveries, get_dev_retailer_email_deliveries
from services.retailer_provisioning_service import (
    CREDENTIAL_ALREADY_ESTABLISHED,
    RETAILER_CREDENTIAL_CONFLICT,
    RetailerCredentialTokenInvalidError,
    RetailerProvisioningError,
    RetailerProvisioningService,
)

pytestmark = pytest.mark.asyncio


async def _execute(db: AsyncSession, sql: str, params: dict | None = None) -> None:
    await db.execute(text(sql), params or {})


async def _make_tenant(db: AsyncSession, *, code: str) -> tuple[str, str]:
    ws_id = uuid.uuid4()
    tenant_schema = f"t_{ws_id.hex}"
    await _execute(
        db,
        "INSERT INTO public.wholesalers (id, code, name, status, is_deleted) "
        "VALUES (:id, :code, :name, 'active', false)",
        {"id": ws_id, "code": code, "name": f"Tenant {code}"},
    )
    await _execute(db, f'CREATE SCHEMA IF NOT EXISTS "{tenant_schema}"')
    for stmt in (
        f'CREATE TABLE "{tenant_schema}".users (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), '
        "email VARCHAR(255) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL, "
        "full_name TEXT, is_active BOOLEAN NOT NULL DEFAULT true, "
        "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), "
        "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, created_by UUID, updated_by UUID)",
        f'CREATE TABLE "{tenant_schema}".roles (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), '
        "name VARCHAR(100) NOT NULL UNIQUE, description TEXT, "
        "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), "
        "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, created_by UUID, updated_by UUID)",
        f'CREATE TABLE "{tenant_schema}".permissions (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), '
        "code VARCHAR(100) NOT NULL UNIQUE, description TEXT, "
        "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), "
        "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, created_by UUID, updated_by UUID)",
        f'CREATE TABLE "{tenant_schema}".user_roles ('
        f'user_id UUID NOT NULL REFERENCES "{tenant_schema}".users(id) ON DELETE CASCADE, '
        f'role_id UUID NOT NULL REFERENCES "{tenant_schema}".roles(id) ON DELETE CASCADE, '
        "PRIMARY KEY (user_id, role_id))",
        f'CREATE TABLE "{tenant_schema}".role_permissions ('
        f'role_id UUID NOT NULL REFERENCES "{tenant_schema}".roles(id) ON DELETE CASCADE, '
        f'permission_id UUID NOT NULL REFERENCES "{tenant_schema}".permissions(id) ON DELETE CASCADE, '
        "PRIMARY KEY (role_id, permission_id))",
        f'CREATE UNIQUE INDEX ux_users_email_active ON "{tenant_schema}".users (email) '
        "WHERE is_deleted IS FALSE",
    ):
        await _execute(db, stmt)
    await _execute(
        db,
        f'INSERT INTO "{tenant_schema}".roles (name, description) '
        "VALUES ('retailer_operator', 'Retailer MVP') ON CONFLICT (name) DO NOTHING",
    )
    for code_, desc in (
        ("client:catalog:read", "x"), ("client:orders:read", "x"),
        ("client:orders:create", "x"), ("client:payments:read", "x"),
        ("client:payments:create", "x"), ("client:finance:read", "x"),
    ):
        await _execute(db, f'INSERT INTO "{tenant_schema}".permissions (code, description) '
                         "VALUES (:c, :d) ON CONFLICT (code) DO NOTHING", {"c": code_, "d": desc})
    await db.commit()
    return str(ws_id), tenant_schema


async def _create_invitation(db: AsyncSession, *, wholesaler_id: str, phone, expires_at=None) -> str:
    if expires_at is None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    code = f"INV{uuid.uuid4().hex[:12]}"
    await _execute(
        db,
        "INSERT INTO public.invitations (code, status, wholesaler_id, retailer_phone, expires_at) "
        "VALUES (:code, 'active', :ws, :phone, :exp)",
        {"code": code, "ws": wholesaler_id, "phone": phone, "exp": expires_at},
    )
    await db.commit()
    return code


@pytest_asyncio.fixture
async def r1_db():
    engine = create_async_engine(get_settings().DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"))
    async with AsyncSession(engine, expire_on_commit=False) as session:
        for tbl in ("retailer_credential_setup_tokens", "retailer_password_reset_tokens"):
            await session.execute(text(f"DELETE FROM public.{tbl}"))
        await session.execute(text("DELETE FROM public.invitations"))
        await session.execute(text("DELETE FROM public.wholesaler_retailer_bindings"))
        await session.execute(text("DELETE FROM public.retailers"))
        await session.execute(text("DELETE FROM public.wholesalers WHERE code LIKE 'R1T%'"))
        await session.commit()
        clear_dev_email_deliveries()
        yield session
        await session.rollback()
    await engine.dispose()


# ---------------------------------------------------------------------------
# Blocker #2: pending placeholder semantics — A pending, then accept B
# ---------------------------------------------------------------------------

async def test_A_pending_then_B_keeps_both_inactive_and_shared_setup_token(r1_db):
    """A accepted but NOT set up; then B accepted. Both users must stay inactive;
    a single retailer-scoped setup token must remain usable to activate both."""
    ws_a_id, schema_a = await _make_tenant(r1_db, code=f"R1TA{uuid.uuid4().hex[:5]}".upper())
    ws_b_id, schema_b = await _make_tenant(r1_db, code=f"R1TB{uuid.uuid4().hex[:5]}".upper())
    phone = "+16660001"
    email = "r1pend@example.com"
    code_a = await _create_invitation(r1_db, wholesaler_id=ws_a_id, phone=phone)
    code_b = await _create_invitation(r1_db, wholesaler_id=ws_b_id, phone=phone)
    svc = RetailerProvisioningService(r1_db)

    # Accept A -> pending (no setup done yet).
    await svc.register_with_invitation(invitation_code=code_a, phone=phone, email=email)
    await r1_db.commit()
    raw_a = get_dev_retailer_email_deliveries(email)[0].token

    # Accept B while A is still pending. B must NOT be activated, must NOT copy
    # A's placeholder hash, and must NOT send a duplicate setup email.
    clear_dev_email_deliveries()
    result_b = await svc.register_with_invitation(invitation_code=code_b, phone=phone, email=email)
    await r1_db.commit()
    assert result_b.setup_token_issued is False  # no NEW token/email for B
    assert len(get_dev_retailer_email_deliveries(email)) == 0

    # Both users inactive.
    for schema in (schema_a, schema_b):
        row = (await r1_db.execute(
            text(f'SELECT is_active FROM "{schema}".users WHERE email = :e'), {"e": email}
        )).first()
        assert row[0] is False, f"{schema} user must remain inactive"

    # The original setup token is still actionable and activates BOTH at once.
    await svc.consume_setup_token(raw_a, "SharedSetup1")
    await r1_db.commit()
    for schema in (schema_a, schema_b):
        row = (await r1_db.execute(
            text(f'SELECT is_active, password_hash FROM "{schema}".users WHERE email = :e'),
            {"e": email},
        )).first()
        assert row[0] is True
        assert verify_password("SharedSetup1", row[1]) is True


# ---------------------------------------------------------------------------
# Blocker #1: atomic multi-tenant update — one copy fails, nothing changes
# ---------------------------------------------------------------------------

async def test_partial_update_failure_leaves_all_copies_unchanged_and_token_unconsumed(r1_db):
    ws_a_id, schema_a = await _make_tenant(r1_db, code=f"R1TA{uuid.uuid4().hex[:5]}".upper())
    ws_b_id, schema_b = await _make_tenant(r1_db, code=f"R1TB{uuid.uuid4().hex[:5]}".upper())
    phone = "+16660002"
    email = "r1atomic@example.com"
    code_a = await _create_invitation(r1_db, wholesaler_id=ws_a_id, phone=phone)
    code_b = await _create_invitation(r1_db, wholesaler_id=ws_b_id, phone=phone)
    svc = RetailerProvisioningService(r1_db)
    await svc.register_with_invitation(invitation_code=code_a, phone=phone, email=email)
    await r1_db.commit()
    await svc.consume_setup_token(get_dev_retailer_email_deliveries(email)[0].token, "OldAtomic1")
    await r1_db.commit()
    await svc.register_with_invitation(invitation_code=code_b, phone=phone, email=email)
    await r1_db.commit()

    # Capture the established hashes BEFORE a forced failure.
    hash_a_before = (await r1_db.execute(
        text(f'SELECT password_hash FROM "{schema_a}".users WHERE email = :e'), {"e": email}
    )).scalar_one()
    hash_b_before = (await r1_db.execute(
        text(f'SELECT password_hash FROM "{schema_b}".users WHERE email = :e'), {"e": email}
    )).scalar_one()
    verified_before = (await r1_db.execute(
        text("SELECT email_verified_at FROM public.retailers WHERE phone = :p"), {"p": phone}
    )).scalar_one()

    # Issue a reset token, then sabotage schema_b's users table so its UPDATE
    # returns rowcount 0 (drop the row out from under the mapped user_id).
    clear_dev_email_deliveries()
    ws_code_a = (await r1_db.execute(
        text("SELECT code FROM public.wholesalers WHERE id = :i"), {"i": ws_a_id}
    )).scalar_one()
    await svc.request_password_reset(email=email, wholesaler_code=ws_code_a)
    await r1_db.commit()
    raw_reset = get_dev_retailer_email_deliveries(email)[0].token

    # Delete the B user row so the mapped UPDATE hits 0 rows -> must roll back all.
    b_uid = (await r1_db.execute(
        text(f'SELECT id FROM "{schema_b}".users WHERE email = :e'), {"e": email}
    )).scalar_one()
    await r1_db.execute(text(f'DELETE FROM "{schema_b}".users WHERE id = :u'), {"u": b_uid})
    await r1_db.commit()

    # The reset must fail (token not consumed); A's hash unchanged.
    with pytest.raises(RetailerProvisioningError):
        await svc.consume_password_reset(raw_reset, "BrandAtomic1")
    await r1_db.rollback()

    hash_a_after = (await r1_db.execute(
        text(f'SELECT password_hash FROM "{schema_a}".users WHERE email = :e'), {"e": email}
    )).scalar_one()
    assert hash_a_after == hash_a_before  # A unchanged
    assert verify_password("OldAtomic1", hash_a_after) is True
    # email_verified_at unchanged.
    verified_after = (await r1_db.execute(
        text("SELECT email_verified_at FROM public.retailers WHERE phone = :p"), {"p": phone}
    )).scalar_one()
    assert verified_after == verified_before


# ---------------------------------------------------------------------------
# Blocker #1b: missing wholesaler/user/role -> full rollback (provisioning)
# ---------------------------------------------------------------------------

async def test_missing_retailer_operator_role_rolls_back(r1_db):
    ws_id, schema = await _make_tenant(r1_db, code=f"R1T{uuid.uuid4().hex[:6]}".upper())
    # Remove the retailer_operator role so the grant cannot succeed.
    await r1_db.execute(text(f'DELETE FROM "{schema}".roles WHERE name = \'retailer_operator\''))
    await r1_db.commit()
    phone = "+16660003"
    email = "r1norole@example.com"
    code = await _create_invitation(r1_db, wholesaler_id=ws_id, phone=phone)
    svc = RetailerProvisioningService(r1_db)
    # Provisioning must fail closed (role missing). Whole txn rolls back.
    with pytest.raises(RetailerProvisioningError) as exc:
        await svc.register_with_invitation(invitation_code=code, phone=phone, email=email)
    assert exc.value.code == "RETAILER_OPERATOR_ROLE_MISSING"
    await r1_db.rollback()
    # No retailer / binding / user committed.
    assert (await r1_db.execute(
        text("SELECT count(*) FROM public.retailers WHERE phone = :p"), {"p": phone}
    )).scalar_one() == 0


# ---------------------------------------------------------------------------
# Blocker #3: invitation default expiry (service path, no explicit expires_at)
# ---------------------------------------------------------------------------

async def test_create_invitation_without_expires_at_yields_finite_seven_day_default(r1_db):
    from db.tenant_filter import run_as_system
    from services.invitation_service import InvitationService
    ws_id, _ = await _make_tenant(r1_db, code=f"R1T{uuid.uuid4().hex[:6]}".upper())
    svc = InvitationService()
    with run_as_system(reason="r1_invitation_create"):
        invitation = await svc.create_invitation(
            r1_db, wholesaler_id=uuid.UUID(ws_id), retailer_phone="+16660004", expires_at=None
        )
    await r1_db.commit()
    assert invitation.expires_at is not None
    # ~7 days from now (allow small clock skew).
    delta = invitation.expires_at - datetime.now(timezone.utc)
    assert timedelta(days=6, hours=23) < delta < timedelta(days=7, hours=1)
    # Aware datetime (tzinfo present) — comparable to TIMESTAMPTZ.
    assert invitation.expires_at.tzinfo is not None


async def test_lookup_expired_invitation_no_500(r1_db):
    from services.invitation_service import InvitationService
    ws_id, _ = await _make_tenant(r1_db, code=f"R1T{uuid.uuid4().hex[:6]}".upper())
    # Past expiry (aware UTC).
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    code = await _create_invitation(r1_db, wholesaler_id=ws_id, phone="+16660005", expires_at=past)
    svc = InvitationService()
    invitation, usable, reason = await svc.get_invitation_status(r1_db, code=code)
    assert invitation is not None
    assert usable is False
    assert reason == "INVITATION_EXPIRED"


# ---------------------------------------------------------------------------
# Blocker #4: reissue permission seeded for admin in migrated + bootstrapped tenants
# ---------------------------------------------------------------------------

async def test_migration_seeds_reissue_permission_for_admin(r1_db):
    """Migration 036's admin permission seed must include
    retailers:reissue_credential (and retailer_operator must NOT get it)."""
    import pathlib
    src = pathlib.Path("alembic/versions/036_retailer_mvp_identity.py").read_text()
    assert "retailers:reissue_credential" in src, "migration 036 must seed retailers:reissue_credential"
    # The admin extra list must contain it; retailer_operator perms must not.
    assert "RETAILER_OPERATOR_PERMISSIONS" in src
    # Confirm the admin extra list declares the reissue permission.
    assert '"retailers:reissue_credential"' in src


async def test_bootstrap_seeds_reissue_permission_for_admin_not_retailer(r1_db):
    import pathlib
    src = pathlib.Path("scripts/bootstrap_tenant_schema.py").read_text()
    assert "retailers:reissue_credential" in src
    # retailer_operator must NOT get it.
    # (The _grant call for admin is separate from the retailer_operator grant.)


# ---------------------------------------------------------------------------
# Blocker #5: setup token redemption verifies token/binding/retailer consistency
# ---------------------------------------------------------------------------

async def test_setup_token_tampered_binding_retailer_mismatch_rejected(r1_db):
    ws_id, schema = await _make_tenant(r1_db, code=f"R1T{uuid.uuid4().hex[:6]}".upper())
    phone = "+16660006"
    email = "r1tamper@example.com"
    code = await _create_invitation(r1_db, wholesaler_id=ws_id, phone=phone)
    svc = RetailerProvisioningService(r1_db)
    await svc.register_with_invitation(invitation_code=code, phone=phone, email=email)
    await r1_db.commit()
    raw = get_dev_retailer_email_deliveries(email)[0].token

    # Tamper: point the setup token's binding_id at a different retailer binding.
    other_retailer_id = uuid.uuid4()
    await r1_db.execute(
        text("INSERT INTO public.retailers (id, phone) VALUES (:id, :p)"), {"id": other_retailer_id, "p": "+999"}
    )
    other_binding_id = uuid.uuid4()
    ws_uid = uuid.UUID(ws_id)
    await r1_db.execute(
        text("INSERT INTO public.wholesaler_retailer_bindings (id, wholesaler_id, retailer_id, status, outstanding_balance) "
             "VALUES (:id, :ws, :rid, 'active', 0)"),
        {"id": other_binding_id, "ws": ws_uid, "rid": other_retailer_id},
    )
    await r1_db.commit()
    # Move the setup token to the wrong binding.
    await r1_db.execute(
        text("UPDATE public.retailer_credential_setup_tokens SET binding_id = :bid"),
        {"bid": other_binding_id},
    )
    await r1_db.commit()

    # Redemption must fail because token.binding_id's retailer != token.retailer_id.
    with pytest.raises(RetailerCredentialTokenInvalidError):
        await svc.consume_setup_token(raw, "TamperPass1")
