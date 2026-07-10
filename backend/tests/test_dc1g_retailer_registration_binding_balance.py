"""DC-1G retailer registration binding balance regressions."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.tenant_filter import run_as_system
from repositories.binding_repository import BindingRepository
from repositories.invitation_repository import InvitationRepository
from services.retailer_service import RetailerService


async def _prepare_public_registration_tables(db: AsyncSession) -> None:
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
                outstanding_balance NUMERIC(12, 2) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false,
                deleted_at TIMESTAMP WITH TIME ZONE,
                CONSTRAINT uq_wholesaler_retailer UNIQUE (wholesaler_id, retailer_id)
            )
            """
        )
    )
    await db.execute(
        text(
            """
            ALTER TABLE public.wholesaler_retailer_bindings
            ADD COLUMN IF NOT EXISTS outstanding_balance NUMERIC(12, 2)
            """
        )
    )
    await db.execute(
        text(
            """
            UPDATE public.wholesaler_retailer_bindings
               SET outstanding_balance = 0
             WHERE outstanding_balance IS NULL
            """
        )
    )
    await db.execute(
        text(
            """
            ALTER TABLE public.wholesaler_retailer_bindings
            ALTER COLUMN outstanding_balance SET NOT NULL,
            ALTER COLUMN outstanding_balance DROP DEFAULT
            """
        )
    )


async def _seed_wholesaler(db: AsyncSession, *, wholesaler_id: uuid.UUID, code: str) -> None:
    await db.execute(
        text(
            """
            INSERT INTO public.wholesalers (id, code, name, status, is_deleted)
            VALUES (:id, :code, :name, 'active', false)
            ON CONFLICT (id) DO UPDATE
            SET code = EXCLUDED.code,
                name = EXCLUDED.name,
                status = 'active',
                is_deleted = false
            """
        ),
        {"id": wholesaler_id, "code": code, "name": f"{code} Wholesaler"},
    )


async def _seed_retailer(db: AsyncSession, *, retailer_id: uuid.UUID, phone: str) -> None:
    await db.execute(
        text(
            """
            INSERT INTO public.retailers (id, phone, name, is_deleted)
            VALUES (:id, :phone, :name, false)
            ON CONFLICT (id) DO UPDATE
            SET phone = EXCLUDED.phone,
                name = EXCLUDED.name,
                is_deleted = false
            """
        ),
        {"id": retailer_id, "phone": phone, "name": f"Retailer {phone}"},
    )


@pytest.mark.asyncio
async def test_binding_repository_create_sets_zero_outstanding_balance(async_session):
    await _prepare_public_registration_tables(async_session)
    wholesaler_id = uuid.uuid4()
    retailer_id = uuid.uuid4()
    await _seed_wholesaler(async_session, wholesaler_id=wholesaler_id, code="DC1GREP")
    await _seed_retailer(async_session, retailer_id=retailer_id, phone="+15550000001")

    with run_as_system(reason="dc1g_public_binding_create_regression"):
        binding = await BindingRepository().create(
            async_session,
            wholesaler_id=wholesaler_id,
            retailer_id=retailer_id,
        )

    assert binding.outstanding_balance == Decimal("0.00")
    result = await async_session.execute(
        text(
            """
            SELECT outstanding_balance
              FROM public.wholesaler_retailer_bindings
             WHERE id = :binding_id
            """
        ),
        {"binding_id": binding.id},
    )
    assert result.scalar_one() == Decimal("0.00")


@pytest.mark.asyncio
async def test_retailer_registration_creates_binding_with_zero_outstanding_balance(async_session):
    await _prepare_public_registration_tables(async_session)
    wholesaler_id = uuid.uuid4()
    invitation_code = "DC1GREG"
    phone = "+15550000002"
    await _seed_wholesaler(async_session, wholesaler_id=wholesaler_id, code="DC1GREG")
    with run_as_system(reason="dc1g_public_invitation_setup"):
        await InvitationRepository().create(
            async_session,
            code=invitation_code,
            wholesaler_id=wholesaler_id,
            retailer_phone=phone,
        )

    invitation, retailer, binding, error_code = await RetailerService().register_with_invitation(
        async_session,
        invitation_code=invitation_code,
        phone=phone,
        name="DC-1G Retailer",
        email="dc1g-retailer@example.test",
        address="DC-1G Test Address",
    )

    assert error_code is None
    assert invitation is not None
    assert retailer is not None
    assert binding is not None
    assert binding.outstanding_balance == Decimal("0.00")
    result = await async_session.execute(
        text(
            """
            SELECT outstanding_balance
              FROM public.wholesaler_retailer_bindings
             WHERE wholesaler_id = :wholesaler_id
               AND retailer_id = :retailer_id
            """
        ),
        {"wholesaler_id": wholesaler_id, "retailer_id": retailer.id},
    )
    assert result.scalar_one() == Decimal("0.00")
