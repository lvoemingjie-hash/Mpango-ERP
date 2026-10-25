"""Current, quote-backed test data. No command, auth, or runtime bypasses."""
from decimal import Decimal
from contextlib import asynccontextmanager
import os
import uuid

import pytest_asyncio
from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


class TenantFixtureScope:
    """Exact created-ID scope for serial fixtures; immutable audit is retained.

    Complete audited tenants remain usable until the enclosing task DB is
    destroyed. Unrelated pre-existing rows, schemas and audit bytes are checked,
    never treated as cleanup targets. Deliberately broken, unaudited fixtures
    are removed only after their negative assertions have run.
    """

    def __init__(self, factory, before):
        self.factory = factory
        self.before = before
        self.owned = {key: set() for key in ('wholesalers', 'registrations', 'schemas', 'reset_tokens')}
        self.registration_emails = {}
        self.tenant_schemas = {}

    def expect_wholesaler(self, wholesaler_id, *, schema_created):
        """Declare a fixture-generated ID before writing, never adopt a diff."""
        raw = str(uuid.UUID(str(wholesaler_id)))
        assert raw not in self.before['wholesalers'], 'FIXTURE_ID_PREEXISTS'
        schema = 't_' + uuid.UUID(raw).hex if schema_created else None
        assert raw not in self.tenant_schemas or self.tenant_schemas[raw] == schema, 'FIXTURE_INTENT_CONFLICT'
        self.tenant_schemas[raw] = schema
        self.owned['wholesalers'].add(raw)
        if schema:
            assert schema not in self.before['schemas'], 'FIXTURE_SCHEMA_PREEXISTS'
            self.owned['schemas'].add(schema)

    def expect_registration(self, registration_id, email):
        raw = str(uuid.UUID(str(registration_id)))
        assert raw not in self.before['registrations'], 'FIXTURE_REGISTRATION_PREEXISTS'
        assert raw not in self.registration_emails or self.registration_emails[raw] == email, 'FIXTURE_REQUEST_CONFLICT'
        self.registration_emails[raw] = email
        self.owned['registrations'].add(raw)

    def expect_reset_token(self, token_id):
        raw = str(uuid.UUID(str(token_id)))
        assert raw not in self.before['reset_tokens'], 'FIXTURE_RESET_TOKEN_PREEXISTS'
        self.owned['reset_tokens'].add(raw)

    async def request_started(self, request):
        """Bind mailbox evidence to this concrete HTTP reset request."""
        if request.method == 'POST' and request.url.path == '/api/v1/auth/forgot-password':
            import json
            from services.email_delivery import get_dev_reset_email_deliveries
            email = json.loads(request.content)['email']
            request.extensions['fixture_reset_before'] = {
                delivery.token for delivery in get_dev_reset_email_deliveries(email)
            }

    async def response_received(self, response):
        import json
        request = response.request
        if request.method != 'POST':
            return
        if request.url.path == '/api/v1/auth/signup' and response.status_code == 202:
            email = json.loads(request.content)['email']
            async with self.factory() as db:
                rows = (await db.execute(text(
                    'SELECT id::text FROM public.tenant_registrations WHERE owner_email=:email'
                ), {'email': email})).scalars().all()
            assert len(rows) == 1, 'FIXTURE_SIGNUP_REQUEST_CARDINALITY'
            self.expect_registration(rows[0], email)
        if request.url.path == '/api/v1/auth/forgot-password' and response.status_code == 200:
            from services.email_delivery import get_dev_reset_email_deliveries
            from services.onboarding_service import hash_token
            from services.password_reset_service import _email_hash
            email = json.loads(request.content)['email']
            before = request.extensions['fixture_reset_before']
            deliveries = [d for d in get_dev_reset_email_deliveries(email) if d.token not in before]
            assert len(deliveries) <= 1, 'FIXTURE_RESET_REQUEST_CARDINALITY'
            async with self.factory() as db:
                for delivery in deliveries:
                    rows = (await db.execute(text(
                        'SELECT id::text FROM public.password_reset_tokens '
                        'WHERE token_hash=:token_hash AND user_email_hash=:email_hash '
                        "AND purpose='password_reset'"
                    ), {'token_hash': hash_token(delivery.token), 'email_hash': _email_hash(email)})).scalars().all()
                    assert len(rows) == 1 and rows[0] not in self.before['reset_tokens'], 'FIXTURE_RESET_LINK_MISMATCH'
                    self.expect_reset_token(rows[0])

    def http_hooks(self):
        return {'request': [self.request_started], 'response': [self.response_received]}

    async def _resolve_registration_links(self, db):
        for registration_id, email in self.registration_emails.items():
            rows = (await db.execute(text(
                'SELECT owner_email,wholesaler_id,tenant_schema FROM public.tenant_registrations WHERE id=:r'
            ), {'r': uuid.UUID(registration_id)})).all()
            assert len(rows) == 1 and rows[0].owner_email == email, 'FIXTURE_REGISTRATION_LINK_MISMATCH'
            row = rows[0]
            if row.wholesaler_id is None:
                assert row.tenant_schema is None, 'FIXTURE_REGISTRATION_SCHEMA_WITHOUT_OWNER'
                continue
            wid = str(row.wholesaler_id)
            assert row.tenant_schema == 't_' + uuid.UUID(wid).hex, 'FIXTURE_REGISTRATION_SCHEMA_MISMATCH'
            if wid not in self.owned['wholesalers']:
                # Exactly one tenant linked to the independently registered
                # signup, not all rows observed since the fixture began.
                self.expect_wholesaler(wid, schema_created=True)

    def _check_ownership(self, current):
        for key in self.owned:
            assert self.before[key] <= current[key], f'PREEXISTING_FIXTURE_LOST:{key}'
            added = current[key] - self.before[key]
            assert not (added - self.owned[key]), f'UNKNOWN_FIXTURE_ADDITION:{key}'
            assert added == self.owned[key], f'REGISTERED_FIXTURE_MISSING:{key}'
        assert self.before['audit'].items() <= current['audit'].items(), 'AUDIT_HISTORY_CHANGED'

    @staticmethod
    async def snapshot(factory):
        async with factory() as db:
            result = {}
            for key, table in (
                ('wholesalers', 'wholesalers'),
                ('registrations', 'tenant_registrations'),
                ('reset_tokens', 'password_reset_tokens'),
            ):
                result[key] = set((await db.execute(text(
                    f'SELECT id::text FROM public.{table}'
                ))).scalars())
            result['schemas'] = set((await db.execute(text(
                "SELECT nspname FROM pg_namespace WHERE nspname ~ '^t_[0-9a-f]{32}$'"
            ))).scalars())
            result['audit'] = dict((await db.execute(text(
                'SELECT id::text, to_jsonb(a)::text FROM public.staff_stock_audit_events a'
            ))).all())
            return result

    @classmethod
    async def begin(cls, factory):
        return cls(factory, await cls.snapshot(factory))

    async def retire(self):
        current = await self.snapshot(self.factory)
        retained = {'wholesalers': set(), 'registrations': set(), 'schemas': set()}
        async with self.factory() as db:
            await self._resolve_registration_links(db)
            self._check_ownership(current)
            new_wids = self.owned['wholesalers']
            new_regs = self.owned['registrations']
            new_tokens = self.owned['reset_tokens']
            for raw in sorted(new_wids):
                wid = uuid.UUID(raw)
                schema = 't_' + wid.hex
                audited = await db.scalar(text(
                    'SELECT EXISTS (SELECT 1 FROM public.staff_stock_audit_events WHERE tenant_id=:w)'
                ), {'w': wid})
                if audited:
                    regs = (await db.execute(text(
                        'SELECT id::text FROM public.tenant_registrations '
                        'WHERE wholesaler_id=:w AND tenant_schema=:s '
                        "AND status IN ('active','completed','provisioned')"
                    ), {'w': wid, 's': schema})).scalars().all()
                    assert len(regs) == 1 and regs[0] in new_regs, 'AUDITED_FIXTURE_ANCHOR_MISSING'
                    assert await db.scalar(text('SELECT to_regclass(:t)'),
                                           {'t': schema + '.inventory_adjustment_approvers'}), 'AUDITED_FIXTURE_044_MISSING'
                    retained['wholesalers'].add(raw)
                    retained['registrations'].update(regs)
                    retained['schemas'].add(schema)
            # All ownership and audit-retention checks above finish before
            # the first destructive statement, including for later tenants.
            for schema in sorted(self.owned['schemas'] - retained['schemas']):
                await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            removable_regs = new_regs - retained['registrations']
            if new_tokens:
                await db.execute(text('DELETE FROM public.password_reset_tokens WHERE id=ANY(:ids)'),
                                 {'ids': [uuid.UUID(v) for v in new_tokens]})
            if removable_regs:
                await db.execute(text('DELETE FROM public.owner_credential_setup_tokens WHERE registration_id=ANY(:ids)'),
                                 {'ids': [uuid.UUID(v) for v in removable_regs]})
                await db.execute(text('DELETE FROM public.tenant_registrations WHERE id=ANY(:ids)'),
                                 {'ids': [uuid.UUID(v) for v in removable_regs]})
            removable_wids = new_wids - retained['wholesalers']
            if removable_wids:
                await db.execute(text('DELETE FROM public.wholesalers WHERE id=ANY(:ids)'),
                                 {'ids': [uuid.UUID(v) for v in removable_wids]})
            await db.commit()
        after = await self.snapshot(self.factory)
        for key in ('wholesalers', 'registrations', 'schemas'):
            assert after[key] == self.before[key] | retained[key], f'UNEXPECTED_FIXTURE_RESIDUE:{key}'
        assert after['reset_tokens'] == self.before['reset_tokens'], 'RESET_TOKEN_RESIDUE'
        assert after['audit'] == current['audit'], 'AUDIT_HISTORY_CHANGED_DURING_RETIREMENT'
        return retained


async def assert_current_owner_roles(db, schema):
    """Verify seeded roles and exact staff template grants, not a new hard count."""
    from core.permission_registry import STAFF_DEFAULT_PERMISSION_CODES

    rows = (await db.execute(text(
        f'SELECT template_key,role_id FROM "{schema}".staff_role_templates'
    ))).all()
    assert {r.template_key for r in rows} == set(STAFF_DEFAULT_PERMISSION_CODES)
    role_names = set((await db.execute(text(f'SELECT name FROM "{schema}".roles'))).scalars())
    template_names = set()
    for code, role_id in rows:
        name = await db.scalar(text(f'SELECT name FROM "{schema}".roles WHERE id=:r'), {'r': role_id})
        template_names.add(name)
        actual = set((await db.execute(text(
            f'SELECT p.code FROM "{schema}".permissions p JOIN "{schema}".role_permissions rp '
            'ON rp.permission_id=p.id WHERE rp.role_id=:r'
        ), {'r': role_id})).scalars())
        assert actual == set(STAFF_DEFAULT_PERMISSION_CODES[code])
        assert 'owner:manage' not in actual
    assert role_names - template_names == {'admin', 'retailer_operator'}
    assert await db.scalar(text(f'SELECT state FROM "{schema}".staff_authority')) == 'verified'


class SQLReadResult:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def mappings(self):
        return self

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def __iter__(self):
        return iter(self.rows)

    def one_or_none(self):
        assert len(self.rows) <= 1
        return self.rows[0] if self.rows else None

    def first(self):
        return self.rows[0] if self.rows else None


def current_rbac_sql(statement, params, *, schema, user_id, permissions, roles):
    """Concrete current-authority SQL fixture, not an authorization override."""
    from types import SimpleNamespace
    sql = str(statement)
    if not schema or f'"{schema}".' not in sql:
        return None
    if sql.startswith(f'SELECT * FROM "{schema}".staff_authority WHERE singleton=1'):
        return SQLReadResult([{'state': 'unmapped', 'owner_user_id': None, 'authz_revision': 1}])
    if sql.startswith(f'SELECT email,full_name,is_active,is_deleted FROM "{schema}".users WHERE id=:u'):
        assert str(params['u']) == str(user_id)
        return SQLReadResult([SimpleNamespace(email='fixture@example.com', full_name='Fixture',
                                              is_active=True, is_deleted=False)])
    if sql.startswith(f'SELECT * FROM "{schema}".staff_memberships WHERE user_id=:u'):
        assert str(params['u']) == str(user_id)
        return SQLReadResult()
    if sql.startswith(f'SELECT r.id,r.name FROM "{schema}".roles r JOIN'):
        assert str(params['u']) == str(user_id)
        return SQLReadResult([SimpleNamespace(id=uuid.uuid5(uuid.NAMESPACE_URL, r), name=r) for r in roles])
    if sql.startswith(f'SELECT p.code FROM "{schema}".permissions p JOIN'):
        assert str(params['u']) == str(user_id)
        return SQLReadResult(sorted(permissions))
    return None


class BoundIdentitySQL:
    """Only the two live-binding reads consumed by current_identity."""
    def __init__(self, tenant_id, user_id, roles):
        self.tenant_id, self.user_id, self.roles = tenant_id, user_id, roles

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    def begin_nested(self):
        return self

    async def execute(self, statement, params):
        from types import SimpleNamespace
        sql = str(statement)
        if sql.startswith('SELECT id FROM public.wholesalers WHERE id=:tid '):
            assert str(params['tid']) == self.tenant_id
            return SQLReadResult([SimpleNamespace(id=uuid.UUID(self.tenant_id))])
        expected = f'SELECT u.id, r.name FROM "t_{uuid.UUID(self.tenant_id).hex}".users u '
        assert sql.startswith(expected), 'UNMODELED_IDENTITY_SQL'
        assert str(params['uid']) == self.user_id
        return SQLReadResult([SimpleNamespace(id=uuid.UUID(self.user_id), name=r) for r in self.roles])


async def current_order_ledger(db, order_id):
    """Retain legacy order references AND each persisted payment's references."""
    from sqlalchemy import select
    from models.ledger import LedgerEntry

    result = await db.execute(select(LedgerEntry).where(text(
        "(reference_type='order' AND reference_id=:oid) OR "
        "(reference_type='payment' AND reference_id IN "
        "(SELECT id FROM payments WHERE order_id=:oid AND is_deleted IS FALSE))"
    )).params(oid=order_id).order_by(LedgerEntry.created_at, LedgerEntry.id))
    return list(result.scalars())


async def canonical_cash(db, order):
    from services.canonical_payment_service import CanonicalPaymentService

    result = await CanonicalPaymentService().confirm_payment(
        db=db, order_id=str(order.id), amount=order.total_amount, method='cash',
        idempotency_key='fixture-cash-' + uuid.uuid4().hex, created_by=str(uuid.uuid4()), transaction_id=None,
    )
    assert not result.replayed
    assert uuid.UUID(str(result.payment_record['id']))
    return result.order


async def assert_payment_ledger(db, order_id, *, expected_receipts=0):
    """Every real receipt owns exactly its nonzero balanced pair, even partials."""
    rows = (await db.execute(text(
        "SELECT p.id,p.amount,p.method,p.receipt_number,count(le.id) AS legs,"
        "COALESCE(sum(le.amount) FILTER(WHERE le.account_type='cash'),0) AS cash,"
        "COALESCE(sum(le.amount) FILTER(WHERE le.account_type='receivable'),0) AS receivable "
        "FROM payments p LEFT JOIN ledger_entries le ON le.reference_type='payment' AND le.reference_id=p.id "
        "WHERE p.order_id=:o AND p.is_deleted IS FALSE GROUP BY p.id ORDER BY p.id"
    ), {'o': order_id})).all()
    assert rows, 'PAYMENT_RECEIPT_MISSING'
    # Direct /orders/pay does not allocate a printed receipt; cashier
    # declaration confirmation opts in explicitly. Do not invent that option.
    assert sum(row.receipt_number is not None for row in rows) == expected_receipts
    for row in rows:
        assert row.amount > 0
        expected = (0, Decimal(0), Decimal(0)) if row.method == 'credit' else (2, row.amount, -row.amount)
        assert (row.legs, row.cash, row.receivable) == expected, 'PAYMENT_UUID_LEDGER_PAIR_MISSING_OR_DUPLICATED'


async def prepare_adjustment_owner(db, actor_id=None):
    """One explicitly mapped synthetic Owner, through the product binding API."""
    import hashlib
    import secrets
    from core.security import hash_password
    from services.staff_management_service import StaffManagementService
    from services.inventory_adjustment_service import InventoryAdjustmentService

    wid, schema = uuid.UUID(str(db.info['tenant_id'])), db.info['tenant_schema']
    assert schema == 't_' + wid.hex
    row = (await db.execute(text(f'SELECT state,owner_user_id FROM "{schema}".staff_authority'))).one()
    if row.state == 'verified':
        actor = row.owner_user_id
    else:
        assert row.state == 'unmapped'
        reg = await db.scalar(text(
            "SELECT id FROM public.tenant_registrations WHERE wholesaler_id=:w AND tenant_schema=:s AND status='active'"
        ), {'w': wid, 's': schema})
        assert reg is not None
        actor = actor_id
        if actor is None:
            actor = await db.scalar(text(
                f'INSERT INTO "{schema}".users (email,password_hash,is_active) VALUES (:e,:p,true) RETURNING id'
            ), {'e': uuid.uuid4().hex + '@example.invalid', 'p': hash_password(secrets.token_urlsafe(32))})
        await StaffManagementService(db, wid, schema).bind_owner(
            registration_id=reg, user_id=actor, source='approved_mapping',
            evidence_digest=hashlib.sha256(('RC4 synthetic fixture ' + str(actor)).encode()).hexdigest(), dry_run=False)
    db.info['_staff_stock_actor'] = str(actor)
    service = InventoryAdjustmentService(db, wid, schema)
    policy = await service.policy(actor)
    if not policy['owner_direct_enabled']:
        await service.set_policy(actor, approver_ids=[actor], owner_direct_enabled=True,
                                 expected_policy_version=policy['policy_version'])
    return actor


async def current_adjustment(db, *, sku_code, quantity, reason, repository=None):
    """Real audited Owner-direct command; optional repository only parks a read.

    The timing hook executes inside the actual stock snapshot call, before the
    normal locked-fresh kernel. It never substitutes a stock value or approval.
    """
    from services.inventory_adjustment_service import InventoryAdjustmentService
    from sqlalchemy import select
    from models.inventory_stock import InventoryStock
    from models.inventory_movement import InventoryMovement

    schema = db.info['tenant_schema']
    actor = await db.scalar(text(f'SELECT owner_user_id FROM "{schema}".staff_authority'))
    assert actor is not None, 'CURRENT_ADJUSTMENT_OWNER_NOT_PREPARED'
    db.info['_staff_stock_actor'] = str(actor)
    sku_id = await db.scalar(text('SELECT id FROM skus WHERE sku_code=:c'), {'c': sku_code})
    service = InventoryAdjustmentService(db, db.info['tenant_id'], schema)
    if repository is not None:
        original = service._stock
        first = True
        async def observed(sid):
            nonlocal first
            if first:
                first = False
                await repository.get_stock_by_sku_code(db, sku_code=sku_code)
            return await original(sid)
        service._stock = observed
    snapshot = await service.snapshot(actor, sku_id)
    request = await service.submit(actor, key=uuid.uuid4().hex, sellable_unit_id=sku_id,
        quantity_delta=quantity, reason_kind='correction', reason=reason, direct=True,
        expected_policy_version=snapshot['policy_version'], expected_stock_revision=snapshot['stock_revision'])
    assert request['status'] == 'applied_direct' and request['decision_actor_id'] == str(actor)
    movement = (await db.execute(select(InventoryMovement).where(
        InventoryMovement.manual_adjustment_id == uuid.UUID(request['id'])))).scalar_one()
    stock = (await db.execute(select(InventoryStock).where(InventoryStock.sku_id == sku_id)
                             .execution_options(populate_existing=True))).scalar_one()
    assert movement.reference_id == movement.manual_adjustment_id == uuid.UUID(request['id'])
    return stock, movement


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


@pytest_asyncio.fixture
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
