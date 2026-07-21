"""DC-11T4C reporting bootstrap contract tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from database.session import AsyncSessionLocal
from tests.reporting_bootstrap_contract_helpers import (
    assert_public_alembic_upgrade_preserves_tenant_schema_set,
    assert_supported_bootstrap_reporting_contract,
    cleanup_reporting_tenant,
    provision_reporting_tenant_for_contract,
    reporting_tenant_teardown_snapshot,
)


pytest_plugins = ("tests.reporting_bootstrap_contract_helpers",)


def test_public_alembic_alone_preserves_tenant_schema_set():
    assert_public_alembic_upgrade_preserves_tenant_schema_set()


@pytest.mark.asyncio
async def test_supported_tenant_bootstrap_creates_reporting_contract(
    reporting_tenant_session,
    provisioned_reporting_tenant,
):
    await assert_supported_bootstrap_reporting_contract(
        reporting_tenant_session,
        provisioned_reporting_tenant.tenant_schema,
    )


@pytest.mark.asyncio
async def test_reporting_tenant_teardown_removes_schema_and_registry_rows():
    reporting_tenant = await provision_reporting_tenant_for_contract()
    await cleanup_reporting_tenant(reporting_tenant)
    await cleanup_reporting_tenant(reporting_tenant)

    async with AsyncSessionLocal() as session:
        snapshot = await reporting_tenant_teardown_snapshot(session, reporting_tenant)

    assert snapshot == {
        "schema_exists": False,
        "registration_count": 0,
        "wholesaler_count": 0,
    }


@pytest.mark.asyncio
async def test_reporting_tenant_teardown_is_bound_to_owned_registration():
    tenant_a = await provision_reporting_tenant_for_contract()
    tenant_b = await provision_reporting_tenant_for_contract()
    forged_tenant_a = replace(tenant_a, tenant_schema=tenant_b.tenant_schema)

    try:
        with pytest.raises(AssertionError):
            await cleanup_reporting_tenant(forged_tenant_a)

        async with AsyncSessionLocal() as session:
            tenant_b_snapshot = await reporting_tenant_teardown_snapshot(session, tenant_b)

        assert tenant_b_snapshot == {
            "schema_exists": True,
            "registration_count": 1,
            "wholesaler_count": 1,
        }

        await cleanup_reporting_tenant(tenant_a)

        async with AsyncSessionLocal() as session:
            tenant_a_snapshot = await reporting_tenant_teardown_snapshot(session, tenant_a)
            tenant_b_snapshot = await reporting_tenant_teardown_snapshot(session, tenant_b)

        assert tenant_a_snapshot == {
            "schema_exists": False,
            "registration_count": 0,
            "wholesaler_count": 0,
        }
        assert tenant_b_snapshot == {
            "schema_exists": True,
            "registration_count": 1,
            "wholesaler_count": 1,
        }
    finally:
        await cleanup_reporting_tenant(tenant_a)
        await cleanup_reporting_tenant(tenant_b)
