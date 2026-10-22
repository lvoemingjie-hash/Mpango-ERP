"""Manual adjustment safety on task-owned PG16; no task-private imports."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal, localcontext
import json
import os
from pathlib import Path
import secrets
import uuid

from fastapi import HTTPException
import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from core.security import TokenPayload
from models.inventory_movement import InventoryMovement
from models.inventory_stock import InventoryStock
from repositories.inventory_repository import InventoryRepository
from schemas.inventory import InventoryAdjustRequest
from services.inventory_service import InventoryService

pytestmark = pytest.mark.integration


def retain(label, value):
    """Optional raw, non-credential facts for the task's private evidence store."""
    directory = os.environ.get('INVENTORY_SAFETY_EVIDENCE_DIR')
    if not directory:
        return
    root = Path(directory)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = root / (label + '-' + uuid.uuid4().hex + '.json')
    with path.open('x', encoding='utf-8') as handle:
        os.chmod(path, 0o600)
        json.dump(value, handle, default=str, ensure_ascii=False, indent=2)
        handle.write('\n')


class StockWorld:
    """Product-provisioned synthetic tenant, with native Owner credentials."""

    async def initialize(self, *, country='KE', bind_owner=True):
        from db.tenant_filter import mark_session_as_system
        from services.owner_credential_service import OwnerCredentialSetupService
        from services.tenant_provisioning_service import TenantProvisioningService

        url = os.environ['TEST_DATABASE_URL'].replace('postgresql://', 'postgresql+asyncpg://', 1)
        self.engine = create_async_engine(url, poolclass=NullPool)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False, autoflush=False)
        self.registration = uuid.uuid4()
        self.retailer = uuid.uuid4()
        self.code = 'INV' + uuid.uuid4().hex[:14].upper()
        self.email = self.code.lower() + '@example.com'
        self.password = secrets.token_urlsafe(32)
        async with self.factory() as db:
            mark_session_as_system(db, reason='inventory safety synthetic registration')
            facts = (await db.execute(text(
                "SELECT current_user, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls, "
                "has_schema_privilege(current_user,'public','CREATE') "
                "FROM pg_roles WHERE rolname=current_user"
            ))).one()
            assert facts[0] == 'mpango_app' and tuple(facts[1:]) == (False,) * 5
            await db.execute(text(
                'INSERT INTO public.tenant_registrations '
                '(id,company_name,tenant_code,country,owner_email,status,expires_at,email_verified_at) '
                "VALUES (:id,'Inventory safety',:code,:country,:email,'email_verified',"
                "now()+interval '1 day',now())"
            ), {'id': self.registration, 'code': self.code, 'email': self.email, 'country': country})
            await db.commit()
            provisioner = TenantProvisioningService(db)
            claim = await provisioner.claim_registration_for_provisioning(str(self.registration))
            assert claim.action == 'claimed'
            await db.commit()
            result = await provisioner.provision_wholesaler_and_schema(str(self.registration))
            assert result.action == 'provisioned'
            await db.commit()
            self.wid, self.schema = (await db.execute(text(
                'SELECT wholesaler_id,tenant_schema FROM public.tenant_registrations WHERE id=:id'
            ), {'id': self.registration})).one()
            self.actor = None
            if bind_owner:
                owner = OwnerCredentialSetupService(db)
                issued = await owner.issue_setup_token(self.registration)
                assert issued.action == 'issued'
                setup = await owner.consume_setup_token(issued.raw_token, self.password)
                self.actor = (await owner.create_first_admin_rbac(setup)).user_id
            await db.execute(text(
                "INSERT INTO public.retailers (id,phone,name) VALUES (:id,:phone,'Inventory safety')"
            ), {'id': self.retailer, 'phone': '+254' + str(uuid.uuid4().int)[:12]})
            await db.execute(text(
                'INSERT INTO public.wholesaler_retailer_bindings '
                '(wholesaler_id,retailer_id,status,outstanding_balance) '
                "VALUES (:wid,:rid,'active',0)"
            ), {'wid': self.wid, 'rid': self.retailer})
            await db.commit()
        async with self.session() as db:
            from tests.catalog_identity_helpers import create_sku_with_catalog
            sku = await create_sku_with_catalog(db, sku_code='INV-BOX', name='Inventory box')
            sku.base_price = Decimal('1.00')
            self.sku = sku.id
            db.add(InventoryStock(sku_id=self.sku, quantity_on_hand=Decimal('100.00'),
                                  quantity_reserved=Decimal('0.00')))
        return self

    def session(self):
        db = self.factory()
        db.info.update(tenant_schema=self.schema, tenant_id=str(self.wid),_staff_stock_actor=str(self.actor))

        @event.listens_for(db.sync_session, 'after_begin')
        def set_path(_session, _transaction, connection):
            connection.execute(text(f'SET LOCAL search_path TO "{self.schema}", public'))

        @asynccontextmanager
        async def transaction():
            async with db:
                try:
                    yield db
                    await db.commit()
                except BaseException:
                    await db.rollback()
                    raise
        return transaction()

    async def reserve(self, quantity):
        from api.v1 import orders
        from schemas.order import WholesalerOrderCreateRequest
        from services.pricing_quote_service import build_quote, sign_quote

        token = TokenPayload(user_id=str(self.actor), tenant_id=str(self.wid),
                             tenant_schema=self.schema, roles=['admin'])
        async with self.session() as db:
            items = [{'sellable_unit_id': str(self.sku), 'quantity': quantity}]
            quote = await build_quote(db, wholesaler_id=self.wid, retailer_id=self.retailer,
                                      actor_id=self.actor, operation='merchant-create', items=items)
            response = await orders.create_order(
                request=WholesalerOrderCreateRequest(retailer_id=str(self.retailer), items=items,
                                                     quote_token=sign_quote(quote)),
                token=token, db=db, idempotency_key='inventory-' + uuid.uuid4().hex,
            )
            order_id = response.data.id
        async with self.session() as db:
            await orders.confirm_order(order_id=order_id, token=token, db=db)
        return order_id

    async def snapshot(self):
        result = {}
        async with self.session() as db:
            for table in ('inventory_stocks', 'inventory_movements', 'orders', 'order_items',
                          'inventory_reservations', 'payments', 'ledger_entries', 'order_credit_holds'):
                rows = await db.execute(text(
                    f'SELECT row_to_json(t)::text FROM "{self.schema}"."{table}" t ORDER BY id'
                ))
                result[table] = list(rows.scalars())
            result['binding'] = list((await db.execute(text(
                'SELECT row_to_json(b)::text FROM public.wholesaler_retailer_bindings b '
                'WHERE wholesaler_id=:wid AND retailer_id=:rid ORDER BY id'
            ), {'wid': self.wid, 'rid': self.retailer})).scalars())
        return result

    async def stock(self):
        async with self.session() as db:
            return (await db.execute(text(
                'SELECT quantity_on_hand,quantity_reserved FROM inventory_stocks WHERE sku_id=:id'
            ), {'id': self.sku})).one_or_none()

    async def adjust(self, quantity, *, repository=None, sku_code='INV-BOX'):
        async with self.session() as db:
            return await InventoryService(repository).adjust_stock(
                db, sku_code=sku_code, quantity=quantity, reason='inventory safety control',
                adjusted_by=str(self.actor),
                tenant_id=str(self.wid), tenant_schema=self.schema,
            )


@pytest_asyncio.fixture
async def stock_world():
    from tests.mpango_invariants_r0_support import verify_task_database_ownership_sync
    verify_task_database_ownership_sync()
    world = StockWorld()
    try:
        yield await world.initialize()
    finally:
        if hasattr(world, 'engine'):
            await world.engine.dispose()


def assert_non_stock_unchanged(before, after):
    for key in before.keys() - {'inventory_stocks', 'inventory_movements'}:
        assert before[key] == after[key], 'INVENTORY_ECONOMIC_VECTOR_CHANGED:' + key


@pytest.mark.parametrize('quantity', [
    Decimal('0'), Decimal('0.001'), Decimal('NaN'), Decimal('Infinity'), Decimal('-Infinity'),
    Decimal('10000000000'), True, False, Decimal('1e-1000000'),
    Decimal('1.0000000000000000000000000000000000000001'),
], ids=['zero', 'fraction', 'nan', 'inf', 'minus-inf', 'overflow', 'true', 'false', 'tiny', 'long-fraction'])
async def test_invalid_quantity_before_repository(quantity):
    class NoWrites:
        async def get_stock_by_sku_code(self, *args, **kwargs):
            raise AssertionError('INVALID_QUANTITY_REACHED_REPOSITORY')
    with pytest.raises(HTTPException) as caught:
        await InventoryService(NoWrites()).adjust_stock(
            None, sku_code='NO-ROW', quantity=quantity, reason='invalid',
        )
    assert caught.value.status_code == 422
    assert caught.value.detail['code'] == 'INVALID_ADJUSTMENT_QUANTITY'


@pytest.mark.parametrize('quantity', ['1.2300', '1.23', '1e-2'])
def test_equivalent_schema_quantities(quantity):
    body = InventoryAdjustRequest(sku_code='INV-BOX', quantity=quantity, reason='valid')
    assert body.quantity == Decimal(quantity)


async def test_reserved_lower_bound_service(stock_world):
    await stock_world.reserve(80)
    before = await stock_world.snapshot()
    assert len(before['orders']) == len(before['inventory_reservations']) == 1
    assert (await stock_world.stock()) == (Decimal('100'), Decimal('80'))
    caught = None
    try:
        await stock_world.adjust(Decimal('-30'))
    except HTTPException as error:
        caught = (error.status_code, error.detail['code'])
    after = await stock_world.snapshot()
    retain('service-reserved', {'before': before, 'after': after, 'rejection': caught})
    assert caught == (409, 'STOCK_RESERVED_CONFLICT'), 'INV_RESERVED_SERVICE_MISSING_REJECTION'
    assert before == after, 'INV_RESERVED_SERVICE_PERSISTED_WRITE'


async def test_reserved_equality_boundary(stock_world):
    await stock_world.reserve(80)
    before = await stock_world.snapshot()
    await stock_world.adjust(Decimal('-20'))
    after = await stock_world.snapshot()
    retain('service-boundary', {'before': before, 'after': after})
    assert await stock_world.stock() == (Decimal('80'), Decimal('80'))
    assert len(after['inventory_movements']) == len(before['inventory_movements']) + 1
    row = json.loads(after['inventory_movements'][-1], parse_float=Decimal)
    assert (row['quantity'], row['quantity_before'], row['quantity_after']) == (-20, 100, 80)
    assert row['created_by'] == str(stock_world.actor) and row['reference_type'] == 'manual'
    assert_non_stock_unchanged(before, after)


async def test_legal_adjustments_and_negative_compatibility(stock_world):
    await stock_world.adjust(Decimal('1.2300'))
    await stock_world.adjust(Decimal('-1.23'))
    before = await stock_world.snapshot()
    assert await stock_world.stock() == (Decimal('100'), Decimal('0'))
    with pytest.raises(HTTPException) as caught:
        await stock_world.adjust(Decimal('-101'))
    assert caught.value.status_code == 409 and caught.value.detail['code'] == 'NEGATIVE_STOCK'
    assert await stock_world.snapshot() == before


@pytest.mark.parametrize('on_hand,reserved', [('-1', '0'), ('100', '-1'), ('100', '101'), ('NaN', '0')])
async def test_corrupt_prestate_is_not_repaired(stock_world, on_hand, reserved):
    async with stock_world.session() as db:
        await db.execute(text(
            'UPDATE inventory_stocks SET quantity_on_hand=:h,quantity_reserved=:r WHERE sku_id=:id'
        ), {'h': Decimal(on_hand), 'r': Decimal(reserved), 'id': stock_world.sku})
    before = await stock_world.snapshot()
    with pytest.raises(HTTPException) as caught:
        await stock_world.adjust(Decimal('2'))
    assert caught.value.status_code == 409 and caught.value.detail['code'] == 'STOCK_STATE_INVALID'
    assert await stock_world.snapshot() == before


async def test_result_overflow_has_no_writes(stock_world):
    async with stock_world.session() as db:
        await db.execute(text('UPDATE inventory_stocks SET quantity_on_hand=9999999999.99'))
    before = await stock_world.snapshot()
    with pytest.raises(HTTPException) as caught:
        await stock_world.adjust(Decimal('0.01'))
    assert caught.value.status_code == 422
    assert caught.value.detail['code'] == 'INVALID_ADJUSTMENT_QUANTITY'
    assert await stock_world.snapshot() == before


async def test_invalid_quantity_does_not_create_stock(stock_world):
    async with stock_world.session() as db:
        await db.execute(text('DELETE FROM inventory_stocks WHERE sku_id=:id'), {'id': stock_world.sku})
    before = await stock_world.snapshot()
    assert before['inventory_stocks'] == []
    with pytest.raises(HTTPException) as caught:
        await stock_world.adjust(Decimal('0.001'))
    assert caught.value.detail['code'] == 'INVALID_ADJUSTMENT_QUANTITY'
    assert await stock_world.snapshot() == before


async def test_missing_sku_compatibility(stock_world):
    before = await stock_world.snapshot()
    with pytest.raises(HTTPException) as caught:
        await stock_world.adjust(Decimal('1'), sku_code='ABSENT')
    assert caught.value.status_code == 404 and caught.value.detail['code'] == 'SKU_NOT_FOUND'
    assert await stock_world.snapshot() == before


async def test_two_sessions_serialize_at_reserved_boundary(stock_world):
    await stock_world.reserve(80)
    before = await stock_world.snapshot()
    arrived = 0
    both = asyncio.Event()

    class ReadBarrier(InventoryRepository):
        async def get_stock_by_sku_code(self, *args, **kwargs):
            nonlocal arrived
            result = await super().get_stock_by_sku_code(*args, **kwargs)
            arrived += 1
            if arrived == 2:
                both.set()
            await asyncio.wait_for(both.wait(), 15)
            return result

    async def attempt(delta):
        try:
            await stock_world.adjust(Decimal(delta), repository=ReadBarrier())
            return ('committed', delta)
        except HTTPException as error:
            return (error.status_code, error.detail['code'])

    tasks = [asyncio.create_task(attempt(delta)) for delta in ('-20', '-1')]
    try:
        outcomes = await asyncio.wait_for(asyncio.gather(*tasks), 20)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    after = await stock_world.snapshot()
    retain('concurrency', {'before': before, 'after': after, 'outcomes': outcomes})
    assert sum(outcome[0] == 'committed' for outcome in outcomes) == 1
    assert (409, 'STOCK_RESERVED_CONFLICT') in outcomes
    winner = next(Decimal(delta) for result, delta in outcomes if result == 'committed')
    expected = Decimal('100') + winner
    assert await stock_world.stock() == (expected, Decimal('80'))
    assert len(after['inventory_movements']) == len(before['inventory_movements']) + 1
    added = [json.loads(row, parse_float=Decimal) for row in after['inventory_movements']
             if row not in before['inventory_movements']]
    assert len(added) == 1
    assert (added[0]['quantity'], added[0]['quantity_before'], added[0]['quantity_after']) == (winner, 100, expected)
    assert added[0]['created_by'] == str(stock_world.actor)
    assert_non_stock_unchanged(before, after)


async def test_lock_refresh_reads_new_reservation(stock_world):
    await stock_world.reserve(40)
    read = asyncio.Event()
    resume = asyncio.Event()

    class StaleRead(InventoryRepository):
        async def get_stock_by_sku_code(self, *args, **kwargs):
            result = await super().get_stock_by_sku_code(*args, **kwargs)
            assert result[1].quantity_reserved == Decimal('40')
            read.set()
            await asyncio.wait_for(resume.wait(), 20)
            return result

    task = asyncio.create_task(stock_world.adjust(Decimal('-30'), repository=StaleRead()))
    try:
        await asyncio.wait_for(read.wait(), 15)
        await stock_world.reserve(40)
        before = await stock_world.snapshot()
        assert await stock_world.stock() == (Decimal('100'), Decimal('80'))
        resume.set()
        with pytest.raises(HTTPException) as caught:
            await asyncio.wait_for(task, 15)
        assert caught.value.detail['code'] == 'STOCK_RESERVED_CONFLICT'
        assert await stock_world.snapshot() == before
    finally:
        resume.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize('without_stock', [False, True])
async def test_movement_failure_rolls_back_whole_transaction(stock_world, without_stock):
    if without_stock:
        async with stock_world.session() as db:
            await db.execute(text('DELETE FROM inventory_stocks WHERE sku_id=:id'), {'id': stock_world.sku})
    else:
        await stock_world.reserve(80)
    before = await stock_world.snapshot()
    reached = []
    with pytest.raises(RuntimeError, match='INV_MOVEMENT_AFTER_FLUSH'):
        async with stock_world.session() as db:
            original = db.flush

            async def failed_flush(*args, **kwargs):
                writing_movement = any(isinstance(obj, InventoryMovement) for obj in db.new)
                await original(*args, **kwargs)
                if writing_movement:
                    reached.append(True)
                    raise RuntimeError('INV_MOVEMENT_AFTER_FLUSH')

            db.flush = failed_flush
            await InventoryService().adjust_stock(
                db, sku_code='INV-BOX', quantity=Decimal('1'), reason='fault',
                adjusted_by=str(stock_world.actor), tenant_id=str(stock_world.wid),
                tenant_schema=stock_world.schema)
    assert reached == [True]
    after = await stock_world.snapshot()
    retain('movement-fault', {'before': before, 'after': after, 'without_stock': without_stock})
    assert before == after


async def test_decimal_context_cannot_round_adjustment(stock_world):
    with localcontext() as context:
        context.prec = 2
        await stock_world.adjust(Decimal('0.01'))
    assert await stock_world.stock() == (Decimal('100.01'), Decimal('0.00'))


async def test_exact_numeric_extremes(stock_world):
    async with stock_world.session() as db:
        await db.execute(text('UPDATE inventory_stocks SET quantity_on_hand=0'))
    before = await stock_world.snapshot()
    with localcontext() as context:
        context.prec = 2
        await stock_world.adjust(Decimal('9999999999.9900'))
        assert await stock_world.stock() == (Decimal('9999999999.99'), Decimal('0'))
        await stock_world.adjust(Decimal('-9999999999.99'))
    after = await stock_world.snapshot()
    assert await stock_world.stock() == (Decimal('0'), Decimal('0'))
    assert len(after['inventory_movements']) == len(before['inventory_movements']) + 2
    assert_non_stock_unchanged(before, after)


async def test_raw_snapshot_does_not_hide_duplicate_rows(stock_world):
    await stock_world.adjust(Decimal('1'))
    first = await stock_world.snapshot()
    async with stock_world.session() as db:
        db.add(InventoryMovement(sku_id=stock_world.sku, movement_type='adjustment', quantity=Decimal('1'),
                                quantity_before=Decimal('100'), quantity_after=Decimal('101'),
                                reason='inventory safety control', reference_type='manual'))
    second = await stock_world.snapshot()
    assert len(second['inventory_movements']) == len(first['inventory_movements']) + 1
    assert second['inventory_movements'] != first['inventory_movements']
