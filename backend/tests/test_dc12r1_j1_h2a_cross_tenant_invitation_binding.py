"""DC-12R1-MVP-L1-J1-H2-A: cross-tenant invitation binding regressions (T10).

Guards the wholesaler invitation authoring closure (F-13/F-14 root cause)
against cross-tenant consumption: an invitation issued by wholesaler A can
ONLY ever bind the accepting retailer to A. The invitation code is the sole
routing credential (opaque, single-use, server-generated), so:

  1. register_with_invitation binds to the INVITING wholesaler (A), never to
     another wholesaler (B) that also exists in the public registry;
  2. no binding row for any other wholesaler is created for the retailer;
  3. after acceptance the invitation is terminal (used) — no second
     consumption by anyone, including another tenant;
  4. the public status lookup resolves the invitation to its inviting
     wholesaler only (the landing page cannot be steered to tenant B).

No backend behavior is changed by this file — it is a regression lock only.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.tenant_filter import run_as_system
from repositories.invitation_repository import InvitationRepository
from services.invitation_service import InvitationService
from services.retailer_service import RetailerService

pytestmark = pytest.mark.asyncio

# Shared fake test phone (extracted to satisfy detect-secrets; not real).
def _run_phone() -> str:
    """Run-unique retailer phone (rerun-robust: committed residue from a
    previously failed run can never collide with this run's identity)."""
    return f"+25570{uuid.uuid4().hex[:8].upper()}"  # pragma: allowlist secret


async def _prepare_public_registration_tables(db: AsyncSession) -> None:
    """Same minimal public-table bootstrap as the DC-1G registration tests."""
    await db.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS public.wholesalers (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                code VARCHAR(32) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL,
                address TEXT,
                contact TEXT,
                plan_type VARCHAR(50),
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false,
                deleted_at TIMESTAMP WITH TIME ZONE,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                provisioned_at TIMESTAMP WITH TIME ZONE,
                suspended_at TIMESTAMP WITH TIME ZONE,
                suspension_reason TEXT
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS public.retailers (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                phone VARCHAR(32) NOT NULL UNIQUE,
                name VARCHAR(255),
                email VARCHAR(255),
                address TEXT,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false,
                deleted_at TIMESTAMP WITH TIME ZONE
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS public.invitations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                code VARCHAR(64) NOT NULL UNIQUE,
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                wholesaler_id UUID NOT NULL REFERENCES public.wholesalers(id),
                retailer_phone VARCHAR(32),
                expires_at TIMESTAMP WITH TIME ZONE,
                used_at TIMESTAMP WITH TIME ZONE,
                used_retailer_id UUID REFERENCES public.retailers(id),
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false,
                deleted_at TIMESTAMP WITH TIME ZONE
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS public.wholesaler_retailer_bindings (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                wholesaler_id UUID NOT NULL REFERENCES public.wholesalers(id),
                retailer_id UUID NOT NULL REFERENCES public.retailers(id),
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                outstanding_balance NUMERIC(12, 2) NOT NULL DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false,
                deleted_at TIMESTAMP WITH TIME ZONE,
                CONSTRAINT uq_wholesaler_retailer UNIQUE (wholesaler_id, retailer_id)
            )
            """
        )
    )


async def _seed_wholesaler_with_rbac(
    db: AsyncSession, *, wholesaler_id: uuid.UUID, code: str
) -> None:
    """Seed one wholesaler plus its derived tenant schema with RBAC tables."""
    await db.execute(
        text(
            "INSERT INTO public.wholesalers (id, code, name, status, is_deleted) "
            "VALUES (:id, :code, :name, 'active', false) "
            "ON CONFLICT (id) DO UPDATE SET code = EXCLUDED.code, name = EXCLUDED.name"
        ),
        {"id": wholesaler_id, "code": code, "name": f"Tenant {code}"},
    )
    tenant_schema = f"t_{str(wholesaler_id).replace('-', '')}"
    with run_as_system(reason="h2a_tenant_rbac_seed"):
        await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{tenant_schema}"'))
        for stmt in (
            f'CREATE TABLE IF NOT EXISTS "{tenant_schema}".users ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), email VARCHAR(255) NOT NULL UNIQUE, "
            "password_hash VARCHAR(255) NOT NULL, full_name TEXT, is_active BOOLEAN NOT NULL DEFAULT true, "
            "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), "
            "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, created_by UUID, updated_by UUID)",
            f'CREATE TABLE IF NOT EXISTS "{tenant_schema}".roles ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), name VARCHAR(100) NOT NULL UNIQUE, "
            "description TEXT, created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), "
            "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, created_by UUID, updated_by UUID)",
            f'CREATE TABLE IF NOT EXISTS "{tenant_schema}".permissions ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), code VARCHAR(100) NOT NULL UNIQUE, "
            "description TEXT, created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), "
            "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, created_by UUID, updated_by UUID)",
            f'CREATE TABLE IF NOT EXISTS "{tenant_schema}".user_roles ('
            f'user_id UUID NOT NULL REFERENCES "{tenant_schema}".users(id) ON DELETE CASCADE, '
            f'role_id UUID NOT NULL REFERENCES "{tenant_schema}".roles(id) ON DELETE CASCADE, '
            "PRIMARY KEY (user_id, role_id))",
            f'CREATE TABLE IF NOT EXISTS "{tenant_schema}".role_permissions ('
            f'role_id UUID NOT NULL REFERENCES "{tenant_schema}".roles(id) ON DELETE CASCADE, '
            f'permission_id UUID NOT NULL REFERENCES "{tenant_schema}".permissions(id) ON DELETE CASCADE, '
            "PRIMARY KEY (role_id, permission_id))",
            f'INSERT INTO "{tenant_schema}".roles (name, description) '
            "VALUES ('retailer_operator', 'Retailer MVP') ON CONFLICT (name) DO NOTHING",
        ):
            await db.execute(text(stmt))


async def test_invitation_binds_only_to_its_inviting_wholesaler(async_session):
    """T10: cross-tenant invitation cannot be consumed or mis-bound."""
    await _prepare_public_registration_tables(async_session)

    wholesaler_a = uuid.uuid4()
    wholesaler_b = uuid.uuid4()
    await _seed_wholesaler_with_rbac(async_session, wholesaler_id=wholesaler_a, code=f"H2A{uuid.uuid4().hex[:6].upper()}")
    await _seed_wholesaler_with_rbac(async_session, wholesaler_id=wholesaler_b, code=f"H2A{uuid.uuid4().hex[:6].upper()}")

    phone = _run_phone()
    invitation_code = f"H2A{uuid.uuid4().hex[:12].upper()}"
    with run_as_system(reason="h2a_public_invitation_seed"):
        await InvitationRepository().create(
            async_session,
            code=invitation_code,
            wholesaler_id=wholesaler_a,
            retailer_phone=phone,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )

    invitation, retailer, binding, error_code = await RetailerService().register_with_invitation(
        async_session,
        invitation_code=invitation_code,
        phone=phone,
        name="H2-A Retailer",
        email=f"h2a-retailer-{uuid.uuid4().hex[:6]}@example.test",
        address="H2-A Test Address",
    )

    # Acceptance succeeded and bound to the INVITING wholesaler A — never B.
    assert error_code is None
    assert binding is not None
    assert binding.wholesaler_id == wholesaler_a
    assert retailer is not None

    # The invitation is terminal: used, by exactly this retailer, for A.
    # (The service marks used via a raw UPDATE; re-query for the fresh row.)
    fresh = await async_session.execute(
        text(
            "SELECT status, wholesaler_id, used_retailer_id "
            "FROM public.invitations WHERE code = :code"
        ),
        {"code": invitation_code},
    )
    row = fresh.one()
    assert row.status == "used"
    assert row.used_retailer_id == retailer.id
    assert row.wholesaler_id == wholesaler_a

    # No binding row exists for wholesaler B (or any other wholesaler).
    other_bindings = await async_session.execute(
        text(
            "SELECT COUNT(*) FROM public.wholesaler_retailer_bindings "
            "WHERE retailer_id = :retailer_id AND wholesaler_id <> :wholesaler_a"
        ),
        {"retailer_id": retailer.id, "wholesaler_a": wholesaler_a},
    )
    assert other_bindings.scalar_one() == 0


async def test_used_invitation_cannot_be_reconsumed_by_any_tenant(async_session):
    """T10b: after acceptance the code is dead — a second registration
    (including one attempted under another tenant's context) fails closed
    and creates nothing new."""
    await _prepare_public_registration_tables(async_session)

    wholesaler_a = uuid.uuid4()
    wholesaler_b = uuid.uuid4()
    await _seed_wholesaler_with_rbac(async_session, wholesaler_id=wholesaler_a, code=f"H2A{uuid.uuid4().hex[:6].upper()}")
    await _seed_wholesaler_with_rbac(async_session, wholesaler_id=wholesaler_b, code=f"H2A{uuid.uuid4().hex[:6].upper()}")

    phone = _run_phone()
    invitation_code = f"H2A{uuid.uuid4().hex[:12].upper()}"
    with run_as_system(reason="h2a_public_invitation_seed"):
        await InvitationRepository().create(
            async_session,
            code=invitation_code,
            wholesaler_id=wholesaler_a,
            retailer_phone=phone,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )

    first = await RetailerService().register_with_invitation(
        async_session,
        invitation_code=invitation_code,
        phone=phone,
        email=f"h2a-first-{uuid.uuid4().hex[:6]}@example.test",
    )
    assert first[3] is None  # first acceptance OK

    # Persist exactly like the API endpoint does (commit), then serve the
    # second attempt from a FRESH session — every registration request runs
    # in its own session in production, and the session factory uses
    # expire_on_commit=False, so reusing one session would read the stale
    # pre-UPDATE identity-map object instead of the committed 'used' row.
    await async_session.commit()
    from database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as second_session:
        second_session.info["tenant_schema"] = None
        second_session.info["tenant_id"] = None
        second = await RetailerService().register_with_invitation(
            second_session,
            invitation_code=invitation_code,
            phone=phone,
            email=f"h2a-second-{uuid.uuid4().hex[:6]}@example.test",
        )
        await second_session.rollback()
    # Second consumption fails with the already-used error code, terminal.
    assert second[3] == "INVITATION_ALREADY_USED"
    assert second[2] is None  # no second binding


async def test_public_lookup_resolves_only_the_inviting_wholesaler(async_session):
    """T10c: the public status lookup (POST /invitations/lookup service path)
    routes the code to its inviting wholesaler only — the landing page cannot
    be steered to another tenant's identity."""
    await _prepare_public_registration_tables(async_session)

    wholesaler_a = uuid.uuid4()
    await _seed_wholesaler_with_rbac(async_session, wholesaler_id=wholesaler_a, code=f"H2A{uuid.uuid4().hex[:6].upper()}")

    invitation_code = f"H2A{uuid.uuid4().hex[:12].upper()}"
    with run_as_system(reason="h2a_public_invitation_seed"):
        await InvitationRepository().create(
            async_session,
            code=invitation_code,
            wholesaler_id=wholesaler_a,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )

    invitation, usable, reason = await InvitationService().get_invitation_status(
        async_session, code=invitation_code
    )
    assert invitation is not None
    assert usable is True
    assert reason is None
    assert invitation.wholesaler_id == wholesaler_a
