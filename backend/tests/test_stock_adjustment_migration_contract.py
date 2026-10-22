"""044 exact source and native catalog checks, not a claim that 043 was rewritten."""
import ast
from pathlib import Path
import re

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.staff_approval_support import staff_world

ROOT=Path(__file__).resolve().parents[1]
PUBLIC_BASE='4122883c7779d379e8aa0df3d3dd78457d2692db'


def constants(path):
    tree=ast.parse(path.read_text())
    names={'revision','down_revision','TENANT_DDL','STOCK_APPROVAL_DDL'}
    return {n.targets[0].id:ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
            and isinstance(n.targets[0],ast.Name) and n.targets[0].id in names}


def test_044_is_self_contained_and_bootstrap_ddl_is_independent_equal():
    import subprocess
    predecessor=ROOT/'alembic/versions/043_staff_authority_and_credentials.py'
    assert subprocess.check_output(['git','show',PUBLIC_BASE+':backend/alembic/versions/043_staff_authority_and_credentials.py'],cwd=ROOT)==predecessor.read_bytes()
    path=ROOT/'alembic/versions/044_inventory_adjustment_approval.py'
    values=constants(path)
    assert values['revision']=='044_inventory_adjustment_approval'
    assert values['down_revision']=='043_staff_authority_and_credentials'
    assert values['TENANT_DDL']==constants(ROOT/'scripts/bootstrap_tenant_schema.py')['STOCK_APPROVAL_DDL']
    imports=[n.module for n in ast.walk(ast.parse(path.read_text())) if isinstance(n,ast.ImportFrom)]
    assert not any((s or '').startswith(('services','models','scripts')) for s in imports)


async def test_bootstrap_repeat_keeps_policy_and_rejects_disabled_guard(staff_world):
    from scripts.bootstrap_tenant_schema import _reconcile_stock_approval
    from services.inventory_adjustment_service import InventoryAdjustmentService
    world=staff_world
    async with world.session() as db:
        service=InventoryAdjustmentService(db,world.wid,world.schema)
        policy=await service.policy(world.actor)
        await service.set_policy(world.actor,approver_ids=[world.actor],owner_direct_enabled=False,expected_policy_version=policy['policy_version'])
    async with world.session() as db:
        await _reconcile_stock_approval(db,world.schema)
        await _reconcile_stock_approval(db,world.schema)
        assert await db.scalar(text('SELECT policy_version FROM staff_authority'))==2
        assert await db.scalar(text('SELECT owner_direct_enabled FROM staff_authority')) is False
        await db.execute(text('ALTER TABLE inventory_stocks DISABLE TRIGGER stock_revision_monotonic'))
    with pytest.raises(RuntimeError,match='ADJUSTMENT_BOOTSTRAP_TRIGGER_MISMATCH'):
        async with world.session() as db:await _reconcile_stock_approval(db,world.schema)


async def test_stock_revision_cannot_be_decreased_or_changed_by_metadata(staff_world):
    async with staff_world.session() as db:
        await db.execute(text('UPDATE inventory_stocks SET quantity_on_hand=101'))
        assert await db.scalar(text('SELECT stock_revision FROM inventory_stocks'))==2
        await db.execute(text('UPDATE inventory_stocks SET stock_revision=1,updated_at=now()'))
        assert await db.scalar(text('SELECT stock_revision FROM inventory_stocks'))==2


@pytest.mark.parametrize('damage',['state_check','movement_unique'])
async def test_repeat_refuses_malformed_new_constraints(staff_world,damage):
    from scripts.bootstrap_tenant_schema import _reconcile_stock_approval
    async with staff_world.session() as db:
        if damage=='state_check':
            await db.execute(text('ALTER TABLE inventory_adjustment_requests DROP CONSTRAINT ck_adjustment_state'))
            await db.execute(text('ALTER TABLE inventory_adjustment_requests ADD CONSTRAINT ck_adjustment_state CHECK (true)'))
        else:
            await db.execute(text('ALTER TABLE inventory_movements DROP CONSTRAINT uq_movement_manual_adjustment'))
    with pytest.raises(RuntimeError,match='ADJUSTMENT_BOOTSTRAP_CONSTRAINT_MISMATCH'):
        async with staff_world.session() as db:await _reconcile_stock_approval(db,staff_world.schema)
