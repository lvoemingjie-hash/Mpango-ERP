"""R2 contract helpers for hand-built test schemas.

The post-039 contract: a CONFIRMED order carries exactly one active credit
hold (amount = remaining = total) and its (wholesaler, retailer) binding
exists and is live. Test harnesses that seed orders directly via SQL use
these helpers to produce the same state the production commands would.
"""
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

HOLD_TABLE_DDL = """
    CREATE TABLE IF NOT EXISTS {schema}.order_credit_holds (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        order_id UUID NOT NULL UNIQUE
            REFERENCES {schema}.orders(id) ON DELETE RESTRICT,
        amount NUMERIC(12, 2) NOT NULL,
        remaining_amount NUMERIC(12, 2) NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'active',
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        created_by UUID,
        updated_by UUID,
        CONSTRAINT ck_order_credit_holds_status CHECK (
            status IN ('active', 'released', 'settled', 'converted')),
        CONSTRAINT ck_order_credit_holds_amount_positive CHECK (amount > 0),
        CONSTRAINT ck_order_credit_holds_remaining_cap CHECK (
            remaining_amount <= amount),
        CONSTRAINT ck_order_credit_holds_lifecycle_shape CHECK (
            (status = 'active' AND remaining_amount > 0)
            OR (status IN ('released', 'settled', 'converted')
                AND remaining_amount = 0))
    )
"""


async def ensure_hold_table(session: AsyncSession, schema: str) -> None:
    await session.execute(text(HOLD_TABLE_DDL.format(schema=f'"{schema}"')))
    await session.execute(text(
        f'CREATE INDEX IF NOT EXISTS ix_order_credit_holds_active '
        f'ON "{schema}".order_credit_holds (order_id) WHERE status = \'active\''))


async def ensure_binding(
    session: AsyncSession, wholesaler_id, retailer_id,
) -> None:
    """A confirmable order needs a live binding for its (ws, retailer)."""
    await session.execute(text(
        "INSERT INTO public.wholesalers (id, code, name, status, is_deleted) "
        "VALUES (:w, :code, 'Contract Fixture Wholesaler', 'active', FALSE) "
        "ON CONFLICT (id) DO NOTHING"
    ), {"w": str(wholesaler_id),
        "code": f"CFX{str(wholesaler_id).replace('-', '')[:12].upper()}"})
    await session.execute(text(
        "INSERT INTO public.retailers (id, phone, name, is_deleted) "
        "VALUES (:r, :phone, 'Contract Fixture Retailer', FALSE) "
        "ON CONFLICT (id) DO NOTHING"
    ), {"r": str(retailer_id), "phone": f"+1999{str(retailer_id).replace('-', '')[:10]}"})
    await session.execute(text(
        "INSERT INTO public.wholesaler_retailer_bindings "
        "(wholesaler_id, retailer_id, status, outstanding_balance, is_deleted) "
        "VALUES (:w, :r, 'active', 0, FALSE) "
        "ON CONFLICT (wholesaler_id, retailer_id) DO NOTHING"
    ), {"w": str(wholesaler_id), "r": str(retailer_id)})


async def seed_active_hold(
    session: AsyncSession, schema: str, order_id, total: Decimal,
) -> None:
    """The lifecycle row confirm_order would have created for a CONFIRMED
    order seeded directly via SQL."""
    await session.execute(text(
        f'INSERT INTO "{schema}".order_credit_holds '
        "(order_id, amount, remaining_amount, status) "
        "VALUES (:o, :t, :t, 'active') "
        "ON CONFLICT (order_id) DO NOTHING"
    ), {"o": order_id, "t": total})


async def add_binding_hold_cache(
    session: AsyncSession, wholesaler_id, retailer_id, total: Decimal,
) -> None:
    """Include the seeded hold in the binding cache (cache = holds + exposure)."""
    await session.execute(text(
        "UPDATE public.wholesaler_retailer_bindings "
        "SET outstanding_balance = outstanding_balance + :t, updated_at = now() "
        "WHERE wholesaler_id = :w AND retailer_id = :r AND is_deleted IS FALSE"
    ), {"w": str(wholesaler_id), "r": str(retailer_id), "t": total})
