"""DC-11T4C reporting bootstrap contract tests."""

from __future__ import annotations

import pytest

from database.session import AsyncSessionLocal
from tests.reporting_bootstrap_contract_helpers import (
    assert_public_alembic_does_not_create_schema,
    assert_supported_bootstrap_reporting_contract,
    cleanup_reporting_tenant,
    provision_reporting_tenant_for_contract,
    reporting_tenant_teardown_snapshot,
)


pytestmark = pytest.mark.asyncio
pytest_plugins = ("tests.reporting_bootstrap_contract_helpers",)


async def test_public_alembic_alone_does_not_manufacture_tenant_schema():
    async with AsyncSessionLocal() as session:
        await assert_public_alembic_does_not_create_schema(
            session,
            "t_dc11t4c_public_alembic_probe",
        )


async def test_supported_tenant_bootstrap_creates_reporting_contract(
    reporting_tenant_session,
    provisioned_reporting_tenant,
):
    await assert_supported_bootstrap_reporting_contract(
        reporting_tenant_session,
        provisioned_reporting_tenant.tenant_schema,
    )


async def test_reporting_tenant_teardown_removes_schema_and_registry_rows():
    reporting_tenant = await provision_reporting_tenant_for_contract()
    await cleanup_reporting_tenant(reporting_tenant)

    async with AsyncSessionLocal() as session:
        snapshot = await reporting_tenant_teardown_snapshot(session, reporting_tenant)

    assert snapshot == {
        "schema_exists": False,
        "registration_count": 0,
        "wholesaler_count": 0,
    }
