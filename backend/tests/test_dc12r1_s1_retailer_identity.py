"""DC-12R1-S1 retailer identity & provisioning integration tests.

Runs against a real PostgreSQL 16 DB (migrated to head 036). Tests the atomic
invitation lifecycle (CTO order B), unified credentials, pending-user safety,
retailer-owned credential APIs, and the authoritative tenant_user_id mapping.

These tests are self-contained: they create their own public rows + a real
tenant schema with RBAC tables, exercise the service layer, and assert the
S1 invariants. They do NOT depend on the t_test conftest bootstrap.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from core.config import get_settings
from core.security import hash_password, verify_password
from database.session import async_engine as _default_engine  # noqa: F401
from services.email_delivery import clear_dev_email_deliveries, get_dev_retailer_email_deliveries
from services.retailer_provisioning_service import (
    CREDENTIAL_ALREADY_ESTABLISHED,
    INVITATION_ALREADY_USED,
    INVITATION_EXPIRED,
    INVITATION_PHONE_MISMATCH,
    INVITATION_REVOKED,
    RETAILER_CREDENTIAL_CONFLICT,
    RETAILER_IDENTITY_CONFLICT,
    RetailerCredentialTokenInvalidError,
    RetailerProvisioningError,
    RetailerProvisioningService,
)

pytestmark = pytest.mark.asyncio

# A real tenant-schema-shaped name so Wholesaler.get_tenant_schema() derivation
# (t_ + hex(wholesaler_id)) is exercised end-to-end.


async def _execute(db: AsyncSession, sql: str, params: dict | None = None) -> None:
    await db.execute(text(sql), params or {})


async def _make_tenant(db: AsyncSession, *, code: str) -> tuple[str, str]:
    """Create a wholesaler + its derived tenant schema with RBAC tables.

    Returns (wholesaler_id_str, tenant_schema). The schema name is derived from
    the wholesaler UUID exactly as Wholesaler.get_tenant_schema() does.
    """
    ws_id = uuid.uuid4()
    tenant_schema = f"t_{ws_id.hex}"
    await _execute(
        db,
        "INSERT INTO public.wholesalers (id, code, name, status, is_deleted) "
        "VALUES (:id, :code, :name, 'active', false)",
        {"id": ws_id, "code": code, "name": f"Tenant {code}"},
    )
    await _execute(db, f'CREATE SCHEMA IF NOT EXISTS "{tenant_schema}"')
    # RBAC DDL (mirrors dc3b _TENANT_AUTH_DDL + retailer_operator role).
    for stmt in (
        f'CREATE TABLE "{tenant_schema}".users ('
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "email VARCHAR(255) NOT NULL UNIQUE, "
        "password_hash VARCHAR(255) NOT NULL, "
        "full_name TEXT, is_active BOOLEAN NOT NULL DEFAULT true, "
        "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), "
        "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, "
        "created_by UUID, updated_by UUID)",
        f'CREATE TABLE "{tenant_schema}".roles ('
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "name VARCHAR(100) NOT NULL UNIQUE, description TEXT, "
        "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), "
        "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, "
        "created_by UUID, updated_by UUID)",
        f'CREATE TABLE "{tenant_schema}".permissions ('
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "code VARCHAR(100) NOT NULL UNIQUE, description TEXT, "
        "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), "
        "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, "
        "created_by UUID, updated_by UUID)",
        f'CREATE TABLE "{tenant_schema}".user_roles ('
        'user_id UUID NOT NULL REFERENCES "' + tenant_schema + '".users(id) ON DELETE CASCADE, '
        'role_id UUID NOT NULL REFERENCES "' + tenant_schema + '".roles(id) ON DELETE CASCADE, '
        "PRIMARY KEY (user_id, role_id))",
        f'CREATE TABLE "{tenant_schema}".role_permissions ('
        'role_id UUID NOT NULL REFERENCES "' + tenant_schema + '".roles(id) ON DELETE CASCADE, '
        'permission_id UUID NOT NULL REFERENCES "' + tenant_schema + '".permissions(id) ON DELETE CASCADE, '
        "PRIMARY KEY (role_id, permission_id))",
        f'CREATE UNIQUE INDEX ux_users_email_active ON "{tenant_schema}".users (email) '
        "WHERE is_deleted IS FALSE",
    ):
        await _execute(db, stmt)
    # Seed retailer_operator role + client:* permissions (mirrors migration 036).
    await _execute(
        db,
        f'INSERT INTO "{tenant_schema}".roles (name, description) '
        "VALUES ('retailer_operator', 'Retailer MVP') ON CONFLICT (name) DO NOTHING",
    )
    for code_, desc in (
        ("client:catalog:read", "x"),
        ("client:orders:read", "x"),
        ("client:orders:create", "x"),
        ("client:payments:read", "x"),
        ("client:payments:create", "x"),
        ("client:finance:read", "x"),
    ):
        await _execute(
            db,
            f'INSERT INTO "{tenant_schema}".permissions (code, description) '
            "VALUES (:c, :d) ON CONFLICT (code) DO NOTHING",
            {"c": code_, "d": desc},
        )
    await db.commit()
    return str(ws_id), tenant_schema


async def _create_invitation(
    db: AsyncSession, *, wholesaler_id: str, phone: str | None, expires_at=None
) -> str:
    # Migration 036 makes expires_at NOT NULL; always provide a finite TTL
    # unless the caller explicitly passes a (possibly past) timestamp.
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
async def s1_db():
    """A system-scoped session on the migrated test DB (no tenant search_path)."""
    engine = create_async_engine(get_settings().DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"))
    async with AsyncSession(engine, expire_on_commit=False) as session:
        # Clean S1 tables for isolation.
        for tbl in (
            "retailer_credential_setup_tokens",
            "retailer_password_reset_tokens",
        ):
            await session.execute(text(f"DELETE FROM public.{tbl}"))
        await session.execute(text("DELETE FROM public.invitations"))
        await session.execute(text("DELETE FROM public.wholesaler_retailer_bindings"))
        await session.execute(text("DELETE FROM public.retailers"))
        await session.execute(text("DELETE FROM public.wholesalers WHERE code LIKE 'S1T%'"))
        await session.commit()
        clear_dev_email_deliveries()
        yield session
        await session.rollback()
    await engine.dispose()


# ---------------------------------------------------------------------------
# Core happy path + atomic lifecycle
# ---------------------------------------------------------------------------

async def test_register_with_invitation_provisions_pending_user_and_setup_token(s1_db):
    ws_id, schema = await _make_tenant(s1_db, code=f"S1T{uuid.uuid4().hex[:6]}".upper())
    phone = "+15550001"
    email = "retailer1@example.com"
    code = await _create_invitation(s1_db, wholesaler_id=ws_id, phone=phone)

    service = RetailerProvisioningService(s1_db)
    result = await service.register_with_invitation(
        invitation_code=code, phone=phone, name="R1", email=email
    )
    await s1_db.commit()

    assert result.setup_token_issued is True
    # Pending user created is_active=false with an unrecoverable placeholder hash.
    row = (
        await s1_db.execute(
            text(f'SELECT is_active, password_hash FROM "{schema}".users WHERE email = :e'),
            {"e": email},
        )
    ).first()
    assert row is not None
    assert row[0] is False  # pending, not yet active
    # Placeholder hash must NOT verify against any guessable password.
    assert verify_password("password", row[1]) is False
    assert verify_password(email, row[1]) is False

    # Binding carries the authoritative tenant_user_id mapping.
    binding_row = (
        await s1_db.execute(
            text(
                "SELECT tenant_user_id, retailer_id FROM public.wholesaler_retailer_bindings "
                "WHERE wholesaler_id = :ws"
            ),
            {"ws": ws_id},
        )
    ).first()
    assert binding_row[0] is not None  # tenant_user_id written
    # retailer_operator role granted.
    role_row = (
        await s1_db.execute(
            text(
                f'SELECT r.name FROM "{schema}".user_roles ur '
                f'JOIN "{schema}".roles r ON r.id = ur.role_id '
                f'JOIN "{schema}".users u ON u.id = ur.user_id '
                "WHERE u.email = :e AND r.name = 'retailer_operator'"
            ),
            {"e": email},
        )
    ).first()
    assert role_row is not None
    # Canonical email NOT yet verified (setup not consumed).
    retailer_row = (
        await s1_db.execute(
            text("SELECT email_verified_at FROM public.retailers WHERE phone = :p"), {"p": phone}
        )
    ).first()
    assert retailer_row[0] is None
    # Setup email captured (dev sink).
    assert len(get_dev_retailer_email_deliveries(email)) == 1


async def test_setup_consumption_activates_user_and_verifies_email(s1_db):
    ws_id, schema = await _make_tenant(s1_db, code=f"S1T{uuid.uuid4().hex[:6]}".upper())
    phone = "+15550002"
    email = "retailer2@example.com"
    code = await _create_invitation(s1_db, wholesaler_id=ws_id, phone=phone)

    svc = RetailerProvisioningService(s1_db)
    await svc.register_with_invitation(invitation_code=code, phone=phone, email=email)
    await s1_db.commit()

    # Capture the raw setup token from the dev sink (memory-only in production).
    delivery = get_dev_retailer_email_deliveries(email)[0]
    raw_token = delivery.token

    await svc.consume_setup_token(raw_token, "NewStrongPass1")
    await s1_db.commit()

    row = (
        await s1_db.execute(
            text(f'SELECT is_active, password_hash FROM "{schema}".users WHERE email = :e'),
            {"e": email},
        )
    ).first()
    assert row[0] is True  # activated
    assert verify_password("NewStrongPass1", row[1]) is True
    # Canonical email now verified.
    retailer_row = (
        await s1_db.execute(
            text("SELECT email_verified_at FROM public.retailers WHERE phone = :p"), {"p": phone}
        )
    ).first()
    assert retailer_row[0] is not None


# ---------------------------------------------------------------------------
# Invitation lifecycle controlled codes
# ---------------------------------------------------------------------------

async def test_expired_invitation_rejected(s1_db):
    ws_id, _ = await _make_tenant(s1_db, code=f"S1T{uuid.uuid4().hex[:6]}".upper())
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    code = await _create_invitation(s1_db, wholesaler_id=ws_id, phone="+15550003", expires_at=past)
    svc = RetailerProvisioningService(s1_db)
    with pytest.raises(RetailerProvisioningError) as exc:
        await svc.register_with_invitation(invitation_code=code, phone="+15550003", email="x@y.com")
    assert exc.value.code == INVITATION_EXPIRED


async def test_phone_mismatch_rejected(s1_db):
    ws_id, _ = await _make_tenant(s1_db, code=f"S1T{uuid.uuid4().hex[:6]}".upper())
    code = await _create_invitation(s1_db, wholesaler_id=ws_id, phone="+15550004")
    svc = RetailerProvisioningService(s1_db)
    with pytest.raises(RetailerProvisioningError) as exc:
        await svc.register_with_invitation(invitation_code=code, phone="+1999", email="x@y.com")
    assert exc.value.code == INVITATION_PHONE_MISMATCH


async def test_reused_invitation_rejected(s1_db):
    ws_id, schema = await _make_tenant(s1_db, code=f"S1T{uuid.uuid4().hex[:6]}".upper())
    phone = "+15550005"
    code = await _create_invitation(s1_db, wholesaler_id=ws_id, phone=phone)
    svc = RetailerProvisioningService(s1_db)
    await svc.register_with_invitation(invitation_code=code, phone=phone, email="r5@example.com")
    await s1_db.commit()
    with pytest.raises(RetailerProvisioningError) as exc:
        await svc.register_with_invitation(invitation_code=code, phone=phone, email="r5@example.com")
    assert exc.value.code == INVITATION_ALREADY_USED


async def test_revoked_invitation_rejected(s1_db):
    ws_id, _ = await _make_tenant(s1_db, code=f"S1T{uuid.uuid4().hex[:6]}".upper())
    code = await _create_invitation(s1_db, wholesaler_id=ws_id, phone="+15550006")
    # Mark revoked directly.
    await s1_db.execute(
        text(
            "UPDATE public.invitations SET status = 'revoked', revoked_at = now() "
            "WHERE code = :c"
        ),
        {"c": code},
    )
    await s1_db.commit()
    svc = RetailerProvisioningService(s1_db)
    with pytest.raises(RetailerProvisioningError) as exc:
        await svc.register_with_invitation(invitation_code=code, phone="+15550006", email="r6@example.com")
    assert exc.value.code == INVITATION_REVOKED


# ---------------------------------------------------------------------------
# Unified credentials (A+B one effective password)
# ---------------------------------------------------------------------------

async def test_AB_mapped_copies_preserve_one_effective_password(s1_db):
    """A retailer bound to A then B shares one effective password."""
    ws_a_id, schema_a = await _make_tenant(s1_db, code=f"S1TA{uuid.uuid4().hex[:5]}".upper())
    ws_b_id, schema_b = await _make_tenant(s1_db, code=f"S1TB{uuid.uuid4().hex[:5]}".upper())
    phone = "+15550007"
    email = "ab@example.com"
    code_a = await _create_invitation(s1_db, wholesaler_id=ws_a_id, phone=phone)
    code_b = await _create_invitation(s1_db, wholesaler_id=ws_b_id, phone=phone)

    svc = RetailerProvisioningService(s1_db)
    # Accept A -> pending user + setup token.
    await svc.register_with_invitation(invitation_code=code_a, phone=phone, email=email)
    await s1_db.commit()
    raw_a = get_dev_retailer_email_deliveries(email)[0].token
    # Set the canonical password via A's setup.
    await svc.consume_setup_token(raw_a, "SharedPass1")
    await s1_db.commit()

    # Accept B -> existing identical hash must be COPIED (no setup token, no reset).
    clear_dev_email_deliveries()
    result_b = await svc.register_with_invitation(invitation_code=code_b, phone=phone, email=email)
    await s1_db.commit()
    assert result_b.setup_token_issued is False  # copied, not re-issued
    assert len(get_dev_retailer_email_deliveries(email)) == 0  # no setup email

    # B's user is active and accepts the SAME password.
    row_b = (
        await s1_db.execute(
            text(f'SELECT is_active, password_hash FROM "{schema_b}".users WHERE email = :e'),
            {"e": email},
        )
    ).first()
    assert row_b[0] is True
    assert verify_password("SharedPass1", row_b[1]) is True

    # A's user still accepts the same password (one effective password).
    row_a = (
        await s1_db.execute(
            text(f'SELECT password_hash FROM "{schema_a}".users WHERE email = :e'),
            {"e": email},
        )
    ).first()
    assert verify_password("SharedPass1", row_a[0]) is True


async def test_retailer_self_reset_updates_both_AB_copies(s1_db):
    ws_a_id, schema_a = await _make_tenant(s1_db, code=f"S1TA{uuid.uuid4().hex[:5]}".upper())
    ws_b_id, schema_b = await _make_tenant(s1_db, code=f"S1TB{uuid.uuid4().hex[:5]}".upper())
    phone = "+15550008"
    email = "ab8@example.com"
    code_a = await _create_invitation(s1_db, wholesaler_id=ws_a_id, phone=phone)
    code_b = await _create_invitation(s1_db, wholesaler_id=ws_b_id, phone=phone)
    svc = RetailerProvisioningService(s1_db)
    await svc.register_with_invitation(invitation_code=code_a, phone=phone, email=email)
    await s1_db.commit()
    await svc.consume_setup_token(get_dev_retailer_email_deliveries(email)[0].token, "OldPass1")
    await s1_db.commit()
    await svc.register_with_invitation(invitation_code=code_b, phone=phone, email=email)
    await s1_db.commit()

    # Retailer self-service reset.
    clear_dev_email_deliveries()
    wholesaler_code_a = (
        await s1_db.execute(text("SELECT code FROM public.wholesalers WHERE id = :i"), {"i": ws_a_id})
    ).scalar_one()
    issued = await svc.request_password_reset(email=email, wholesaler_code=wholesaler_code_a)
    await s1_db.commit()
    assert issued is True
    raw_reset = get_dev_retailer_email_deliveries(email)[0].token
    await svc.consume_password_reset(raw_reset, "BrandNewPass1")
    await s1_db.commit()

    # Both copies updated to the new password (unified credential).
    for schema in (schema_a, schema_b):
        h = (
            await s1_db.execute(
                text(f'SELECT password_hash FROM "{schema}".users WHERE email = :e'), {"e": email}
            )
        ).scalar_one()
        assert verify_password("BrandNewPass1", h) is True
        assert verify_password("OldPass1", h) is False


# ---------------------------------------------------------------------------
# Isolation: pending user cannot auth; wholesaler reissue boundary
# ---------------------------------------------------------------------------

async def test_pending_user_cannot_authenticate(s1_db):
    """A pending (is_active=false) user with a placeholder hash has no valid password."""
    ws_id, schema = await _make_tenant(s1_db, code=f"S1T{uuid.uuid4().hex[:6]}".upper())
    phone = "+15550009"
    email = "pend@example.com"
    code = await _create_invitation(s1_db, wholesaler_id=ws_id, phone=phone)
    svc = RetailerProvisioningService(s1_db)
    await svc.register_with_invitation(invitation_code=code, phone=phone, email=email)
    await s1_db.commit()

    row = (
        await s1_db.execute(
            text(f'SELECT is_active, password_hash FROM "{schema}".users WHERE email = :e'),
            {"e": email},
        )
    ).first()
    # No recoverable/default password: a wide set of guesses all fail.
    for guess in ("", "password", "placeholder", email, "secret", "changeme", "12345678"):
        assert verify_password(guess, row[1]) is False


async def test_reissue_denied_after_credential_established(s1_db):
    ws_id, _ = await _make_tenant(s1_db, code=f"S1T{uuid.uuid4().hex[:6]}".upper())
    phone = "+15550010"
    email = "reissue@example.com"
    code = await _create_invitation(s1_db, wholesaler_id=ws_id, phone=phone)
    svc = RetailerProvisioningService(s1_db)
    await svc.register_with_invitation(invitation_code=code, phone=phone, email=email)
    await s1_db.commit()
    await svc.consume_setup_token(get_dev_retailer_email_deliveries(email)[0].token, "SetPass1")
    await s1_db.commit()

    retailer_id = (
        await s1_db.execute(text("SELECT id FROM public.retailers WHERE phone = :p"), {"p": phone})
    ).scalar_one()
    # After establishment, reissue is denied (wholesaler cannot reset).
    with pytest.raises(RetailerProvisioningError) as exc:
        await svc.reissue_setup_token(
            wholesaler_id=uuid.UUID(ws_id),
            retailer_id=retailer_id,
            issued_by_user_id=uuid.UUID(ws_id),
        )
    assert exc.value.code == CREDENTIAL_ALREADY_ESTABLISHED


async def test_cross_tenant_reissue_is_neutral_404(s1_db):
    ws_a_id, _ = await _make_tenant(s1_db, code=f"S1TA{uuid.uuid4().hex[:5]}".upper())
    ws_b_id, _ = await _make_tenant(s1_db, code=f"S1TB{uuid.uuid4().hex[:5]}".upper())
    phone = "+15550011"
    email = "cross@example.com"
    code_a = await _create_invitation(s1_db, wholesaler_id=ws_a_id, phone=phone)
    svc = RetailerProvisioningService(s1_db)
    await svc.register_with_invitation(invitation_code=code_a, phone=phone, email=email)
    await s1_db.commit()
    retailer_id = (
        await s1_db.execute(text("SELECT id FROM public.retailers WHERE phone = :p"), {"p": phone})
    ).scalar_one()
    # Wholesaler B does NOT own this retailer -> neutral 404, no relationship leak.
    with pytest.raises(RetailerProvisioningError) as exc:
        await svc.reissue_setup_token(
            wholesaler_id=uuid.UUID(ws_b_id),
            retailer_id=retailer_id,
            issued_by_user_id=uuid.UUID(ws_b_id),
        )
    assert exc.value.http_status == 404


# ---------------------------------------------------------------------------
# Token rejection (used/expired/revoked setup+reset)
# ---------------------------------------------------------------------------

async def test_used_setup_token_rejected(s1_db):
    ws_id, _ = await _make_tenant(s1_db, code=f"S1T{uuid.uuid4().hex[:6]}".upper())
    phone = "+15550012"
    email = "used@example.com"
    code = await _create_invitation(s1_db, wholesaler_id=ws_id, phone=phone)
    svc = RetailerProvisioningService(s1_db)
    await svc.register_with_invitation(invitation_code=code, phone=phone, email=email)
    await s1_db.commit()
    raw = get_dev_retailer_email_deliveries(email)[0].token
    await svc.consume_setup_token(raw, "FirstPass1")
    await s1_db.commit()
    # Re-using the same token fails.
    with pytest.raises(RetailerCredentialTokenInvalidError):
        await svc.consume_setup_token(raw, "SecondPass1")


async def test_invalid_reset_token_rejected(s1_db):
    svc = RetailerProvisioningService(s1_db)
    with pytest.raises(RetailerCredentialTokenInvalidError):
        await svc.consume_password_reset("nonexistent-token", "AnyPass1")


# ---------------------------------------------------------------------------
# Forgot-password true-neutrality
# ---------------------------------------------------------------------------

async def test_forgot_password_neutral_for_unknown_account(s1_db):
    ws_id, _ = await _make_tenant(s1_db, code=f"S1T{uuid.uuid4().hex[:6]}".upper())
    ws_code = (
        await s1_db.execute(text("SELECT code FROM public.wholesalers WHERE id = :i"), {"i": ws_id})
    ).scalar_one()
    svc = RetailerProvisioningService(s1_db)
    # No account, wrong code, unverified email -> all neutral (issued=False), no email.
    clear_dev_email_deliveries()
    issued = await svc.request_password_reset(email="ghost@example.com", wholesaler_code=ws_code)
    assert issued is False
    assert len(get_dev_retailer_email_deliveries("ghost@example.com")) == 0
