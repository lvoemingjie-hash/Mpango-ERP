"""S5-A fresh tenant real user journey gate.

This file starts with a strict fresh-bootstrap audit because the real user
journey cannot safely pass if a newly bootstrapped tenant cannot persist the
``returned`` order status used by the return endpoint.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from core.config import get_settings
from database.session import AsyncSessionLocal
from scripts.bootstrap_tenant_schema import bootstrap


@pytest.mark.asyncio
async def test_fresh_tenant_bootstrap_supports_returned_order_status_for_real_return_journey():
    """Fresh tenants must support the returned status used by return_order.

    S5-A requires a real fulfilled-order return path. A tenant bootstrapped from
    scratch must therefore have ``returned`` in its tenant-local order_status
    enum before the end-to-end journey can be promoted to a passing gate.
    """
    schema = f"t_s5a_return_audit_{uuid.uuid4().hex[:12]}"

    try:
        await bootstrap(schema, get_settings().DATABASE_URL)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    "SELECT enumlabel "
                    "FROM pg_enum e "
                    "JOIN pg_type t ON t.oid = e.enumtypid "
                    "JOIN pg_namespace n ON n.oid = t.typnamespace "
                    "WHERE n.nspname = :schema "
                    "AND t.typname = 'order_status' "
                    "ORDER BY e.enumsortorder"
                ),
                {"schema": schema},
            )
            enum_labels = list(result.scalars().all())

        assert "returned" in enum_labels, (
            "STOP_AND_REPORT_CTO: fresh tenant bootstrap creates order_status "
            f"without 'returned'. labels={enum_labels!r}. The real return "
            "journey cannot persist OrderStatus.RETURNED until bootstrap or "
            "migration reconciliation is fixed."
        )
    finally:
        async with AsyncSessionLocal() as cleanup:
            await cleanup.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await cleanup.commit()
