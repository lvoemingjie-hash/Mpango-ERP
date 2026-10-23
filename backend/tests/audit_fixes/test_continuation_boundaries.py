"""Narrow controls for mapped-column parity and timezone-safe new payments."""
import ast
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from tests.audit_fixes.support import create_confirmed, full_world, retain

pytestmark = pytest.mark.asyncio(loop_scope='session')


def migration_platform_columns():
    path = Path(__file__).resolve().parents[2] / 'alembic/versions/018_platform_p0_lifecycle.py'
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'create_table' and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == 'platform_tenants'):
            return {arg.args[0].value for arg in node.args[1:]
                    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute)
                    and arg.func.attr == 'Column' and isinstance(arg.args[0], ast.Constant)}
    raise AssertionError('PLATFORM_MIGRATION_CONTRACT_NOT_FOUND')


async def test_platform_mapping_exactly_matches_existing_migration():
    from models.platform_tenant import PlatformTenant
    assert set(PlatformTenant.__table__.columns.keys()) == migration_platform_columns(), 'PLATFORM-MAPPING-EXACT-MIGRATION'
    assert PlatformTenant.__table__.c.created_at.type.timezone
    assert PlatformTenant.__table__.c.updated_at.type.timezone


async def test_payment_repository_passes_aware_utc_not_naive_datetime():
    from repositories.payment_repository import PaymentRepository
    class Capture:
        async def execute(self, _statement, parameters):
            return SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: parameters))
    row = await PaymentRepository().create(Capture(), order_id=uuid4(), retailer_id=uuid4(),
        transaction_id=None, idempotency_key=str(uuid4()), amount=Decimal('40'),
        method='cash', status='pending', created_by=uuid4())
    assert row['created_at'].tzinfo is not None, 'PAYMENT-WRITE-MUST-BE-UTC-AWARE'
    assert row['created_at'].utcoffset().total_seconds() == 0
    assert row['created_at'] == row['updated_at']


async def test_platform_mapping_matches_live_migration044_catalog():
    from models.platform_tenant import PlatformTenant
    async with full_world() as w:
        rows = await w.sql("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='platform_tenants' ORDER BY ordinal_position")
        actual = {row['column_name'] for row in rows}
        retain('platform-model-catalog-parity', {'columns': rows, 'mapped': list(PlatformTenant.__table__.columns.keys())})
        assert actual == set(PlatformTenant.__table__.columns.keys()), 'PLATFORM-LIVE-CATALOG-PARITY'


async def test_new_payment_real_timestamp_within_request_window():
    async with full_world() as w:
        oid = await create_confirmed(w)
        before = datetime.now(timezone.utc)
        response = await w.client.post(f'/api/v1/orders/{oid}/pay', headers={'X-Idempotency-Key': str(uuid4())},
            json={'amount': '40', 'method': 'cash'})
        after = datetime.now(timezone.utc)
        assert response.status_code == 200, response.text
        row = (await w.sql('SELECT p.created_at,h.created_at AS held_at FROM payments p JOIN order_credit_holds h ON h.order_id=p.order_id WHERE p.order_id=:o',
            {'o': UUID(oid)}))[0]
        retain('utc-request-window', {'before': before, 'after': after, 'payment': row})
        assert before <= row['created_at'] <= after, 'PAYMENT-UTC-REQUEST-WINDOW'
        assert row['created_at'] >= row['held_at']
