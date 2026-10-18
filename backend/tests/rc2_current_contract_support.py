"""Current, quote-backed test data. No command, auth, or runtime bypasses."""
from decimal import Decimal
from contextlib import asynccontextmanager
import os
import uuid

import pytest_asyncio
from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


@asynccontextmanager
async def trading_session():
    """Each economic case owns a real completed KE registration and tenant."""
    from db.tenant_filter import mark_session_as_system
    from services.tenant_provisioning_service import TenantProvisioningService

    engine = create_async_engine(os.environ['TEST_DATABASE_URL'].replace(
        'postgresql://', 'postgresql+asyncpg://', 1), poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        async with factory() as db:
            mark_session_as_system(db, reason='RC2 current-contract test registration')
            reg = uuid.uuid4()
            await db.execute(text(
                "INSERT INTO public.tenant_registrations "
                "(id,company_name,tenant_code,country,owner_email,status,expires_at,email_verified_at) "
                "VALUES (:id,'RC2 fixture',:code,'KE',:email,'email_verified',now()+interval '1 day',now())"
            ), {'id': reg, 'code': 'RC2' + reg.hex[:14].upper(), 'email': reg.hex + '@example.invalid'})
            await db.commit()
            service = TenantProvisioningService(db)
            claim = await service.claim_registration_for_provisioning(str(reg))
            assert claim.action == 'claimed'
            await db.commit()
            result = await service.provision_wholesaler_and_schema(str(reg))
            assert result.action == 'provisioned'
            await db.commit()
            row = (await db.execute(text(
                'SELECT wholesaler_id,tenant_schema FROM public.tenant_registrations WHERE id=:id'
            ), {'id': reg})).one()
            wid, schema = row
        async with factory() as db:
            db.info.update(tenant_id=str(wid), tenant_schema=schema)

            @event.listens_for(db.sync_session, 'after_begin')
            def set_path(_session, _transaction, connection):
                connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))

            print('RC2_CURRENT_TRADING_TENANT', str(wid), schema)
            try:
                yield db
            finally:
                await db.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(name='async_session')
async def current_trading_session():
    async with trading_session() as db:
        yield db


def historical_catalog_bootstrap():
    """Project the frozen pre-039 TENANT layout, not a disabled current gate.

    Exclude exactly its obsolete public guard-creation DDL: the real migration
    authority has already created that guard. Verify its current authority
    contract before/after; never grant public CREATE or replace the guard as app.
    The second AST change makes the historical engine dispose even on failure.
    """
    import ast
    import hashlib
    from pathlib import Path
    import subprocess
    import types

    repo = Path(__file__).resolve().parents[2]
    commit = subprocess.check_output(
        ['git', 'rev-parse', '--verify', '1ee75d9f^{commit}'], cwd=repo
    ).decode().strip()
    raw = subprocess.check_output(['git', 'show', commit + ':backend/scripts/bootstrap_tenant_schema.py'], cwd=repo)
    # Public content digest, grouped bytes rather than a credential-shaped literal.
    assert hashlib.sha256(raw).digest() == bytes.fromhex(
        '563aef7c f78e69e3 9d565742 2dcb0674 d652c955 14962ab2 8a912f5a 6a69e894'
    ), 'RC2_HISTORICAL_LAYOUT_BYTES_CHANGED'
    tree = ast.parse(raw)
    bootstrap = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'bootstrap')
    public_ddl = []
    for node in ast.walk(bootstrap):
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Await)):
            continue
        call = node.value.value
        if not (isinstance(call, ast.Call) and ast.unparse(call.func) == 'db.execute'
                and len(call.args) == 1 and not call.keywords):
            continue
        sql = call.args[0]
        if (isinstance(sql, ast.Call) and isinstance(sql.func, ast.Name)
                and sql.func.id == 'text' and len(sql.args) == 1 and not sql.keywords
                and isinstance(sql.args[0], ast.Constant) and isinstance(sql.args[0].value, str)
                and sql.args[0].value.startswith(
                    'CREATE OR REPLACE FUNCTION public.prevent_ledger_modification()')):
            public_ddl.append(node)
    assert len(public_ddl) == 1, 'RC2_HISTORICAL_PUBLIC_DDL_NOT_EXACT'
    class TenantOnly(ast.NodeTransformer):
        def visit_Expr(self, node):
            return None if node is public_ddl[0] else self.generic_visit(node)
    TenantOnly().visit(bootstrap)
    engine_index = next(i for i, n in enumerate(bootstrap.body) if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == 'engine' for t in n.targets))
    tail = bootstrap.body[engine_index + 1:]
    disposals = [n for n in tail if isinstance(n, ast.Expr) and isinstance(n.value, ast.Await)
                 and ast.unparse(n.value) == 'await engine.dispose()']
    assert len(disposals) == 1, 'RC2_HISTORICAL_DISPOSAL_NOT_EXACT'
    bootstrap.body[engine_index + 1:] = [ast.Try(body=[n for n in tail if n not in disposals],
        handlers=[], orelse=[], finalbody=disposals)]
    ast.fix_missing_locations(tree)
    print('RC2_HISTORICAL_LAYOUT_SOURCE', commit, hashlib.sha256(raw).hexdigest(),
          'projection=omit-one-public-guard-DDL+finally-dispose', hashlib.sha256(ast.unparse(tree).encode()).hexdigest())
    module = types.ModuleType('rc2_historical_catalog_bootstrap')
    module.__file__ = str(repo / 'backend/scripts/bootstrap_tenant_schema.py')
    exec(compile(tree, module.__file__, 'exec'), module.__dict__)

    async def tenant_layout(schema, database_url):
        from scripts.bootstrap_tenant_schema import _assert_ledger_guard_function_authority
        observer = create_async_engine(database_url.replace('postgresql://', 'postgresql+asyncpg://', 1),
                                       poolclass=NullPool)
        try:
            async with observer.connect() as connection:
                await _assert_ledger_guard_function_authority(connection)
                guard_before = (await connection.execute(text(
                    "SELECT pg_get_functiondef(p.oid),pg_get_userbyid(p.proowner),p.proacl::text "
                    "FROM pg_proc p WHERE p.oid='public.prevent_ledger_modification()'::regprocedure"
                ))).one()
            try:
                await module.bootstrap(schema, database_url)
            finally:
                async with observer.connect() as connection:
                    await _assert_ledger_guard_function_authority(connection)
                    guard_after = (await connection.execute(text(
                        "SELECT pg_get_functiondef(p.oid),pg_get_userbyid(p.proowner),p.proacl::text "
                        "FROM pg_proc p WHERE p.oid='public.prevent_ledger_modification()'::regprocedure"
                    ))).one()
                    assert guard_before == guard_after, 'RC2_HISTORICAL_SHARED_GUARD_CHANGED'
        finally:
            await observer.dispose()
    return tenant_layout


async def create_verified_draft(db, *, retailer_id, items, notes=None, actor_id=None):
    """Prepare real prices, preview, explicitly accept, then invoke submit_draft.

    For a stock-shortage negative case, accept while stock is sufficient, then
    restore its original shortage before the caller's confirm. These are test
    preparation writes, never evidence that the business command was write-free.
    """
    from services.order_creation_service import submit_draft
    from services.pricing_quote_service import build_quote, sign_quote
    from tests.order_state_r2.contract_helpers import ensure_binding

    wid = db.info['tenant_id']
    actor = str(actor_id or uuid.uuid4())
    await ensure_binding(db, wid, retailer_id)
    selections, shortages = [], []
    for code, quantity, price in items:
        row = (await db.execute(text('SELECT id FROM skus WHERE sku_code=:code'), {'code': code})).one()
        await db.execute(text('UPDATE skus SET base_price=:price WHERE id=:id'),
                         {'price': Decimal(price), 'id': row.id})
        stock = (await db.execute(text(
            'SELECT quantity_on_hand FROM inventory_stocks WHERE sku_id=:id AND is_deleted IS FALSE'
        ), {'id': row.id})).scalar_one()
        if stock < quantity:
            shortages.append((row.id, stock))
            await db.execute(text('UPDATE inventory_stocks SET quantity_on_hand=:qty WHERE sku_id=:id'),
                             {'qty': quantity, 'id': row.id})
        selections.append({'sellable_unit_id': str(row.id), 'quantity': quantity})
    quote = await build_quote(db, wholesaler_id=wid, retailer_id=retailer_id,
                              actor_id=actor, operation='merchant-create', items=selections)
    order, replayed = await submit_draft(db, wholesaler_id=wid, retailer_id=retailer_id,
        actor_id=actor, operation='merchant-create', items=selections, notes=notes,
        quote_token=sign_quote(quote), idempotency_key='rc2-' + uuid.uuid4().hex)
    assert not replayed and order.creation_fingerprint and order.quote_resolved
    assert order.total_amount == sum(Decimal(p) * q for _, q, p in items)
    for sid, old in shortages:
        await db.execute(text('UPDATE inventory_stocks SET quantity_on_hand=:qty WHERE sku_id=:id'),
                         {'qty': old, 'id': sid})
    await db.flush()
    return order


async def verified_from_template(db, template):
    """Only consume an unpersisted fixture; never forge an existing order's consent."""
    assert inspect(template).transient and template.status.value == 'draft'
    assert template.items
    return await create_verified_draft(db, retailer_id=template.retailer_id,
        items=[(item.sku_code, item.quantity, item.unit_price) for item in template.items],
        notes=template.notes)


@pytest_asyncio.fixture(autouse=True)
async def registered_pool_ke(provisioned_pool):
    """These fractional-price cases require a supported KES tenant, not legacy TZ.

    Change only this module's task-owned pool registrations and restore every
    original country. No production currency fallback or privilege change.
    """
    engine = create_async_engine(os.environ['TEST_DATABASE_URL'].replace(
        'postgresql://', 'postgresql+asyncpg://', 1), poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = [uuid.UUID(str(v['ws_id'])) for v in provisioned_pool.tenants.values()]
    before = []
    try:
        async with factory() as db:
            for wid in ids:
                row = (await db.execute(text(
                    'SELECT id,country FROM public.tenant_registrations WHERE wholesaler_id=:id'
                ), {'id': wid})).one()
                before.append((row.id, row.country))
                await db.execute(text('UPDATE public.tenant_registrations SET country=\'KE\' WHERE id=:id'), {'id': row.id})
            await db.commit()
        yield
    finally:
        async with factory() as db:
            for rid, country in before:
                await db.execute(text('UPDATE public.tenant_registrations SET country=:country WHERE id=:id'),
                                 {'id': rid, 'country': country})
            await db.commit()
        await engine.dispose()
