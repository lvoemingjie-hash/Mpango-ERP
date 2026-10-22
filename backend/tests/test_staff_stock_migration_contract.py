"""Offline schema-source checks; these do not replace PG migration/parity tests."""
import ast
from pathlib import Path
import re
import pytest
from sqlalchemy import text
from tests.staff_approval_support import staff_world

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT/'alembic/versions/043_staff_authority_and_credentials.py'
BOOTSTRAP = ROOT/'scripts/bootstrap_tenant_schema.py'


def literal_assignment(tree, name):
    return next(ast.literal_eval(node.value) for node in ast.walk(tree)
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets))


def test_migration_and_independent_bootstrap_declare_identical_tenant_ddl():
    migration = ast.parse(MIGRATION.read_text())
    bootstrap = ast.parse(BOOTSTRAP.read_text())
    function = next(node for node in bootstrap.body if isinstance(node, ast.AsyncFunctionDef)
                    and node.name == '_reconcile_staff_authority')
    normalize = lambda statements: tuple(re.sub(r'\s+', ' ', value).strip() for value in statements)
    current=list(literal_assignment(function, 'statements'))
    # 043 is frozen. Current bootstrap additionally includes the two 044 columns.
    current[0]=current[0].replace('policy_version BIGINT NOT NULL DEFAULT 1 CHECK (policy_version>0),','').replace('owner_direct_enabled BOOLEAN NOT NULL DEFAULT true,','')
    assert normalize(literal_assignment(migration, 'TENANT_DDL')) == normalize(current)


def test_migration_revision_is_exact_successor_and_has_no_runtime_service_import():
    tree = ast.parse(MIGRATION.read_text())
    assert literal_assignment(tree, 'revision') == '043_staff_authority_and_credentials'
    assert literal_assignment(tree, 'down_revision') == '042_order_negotiation_proposals'
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or '').startswith(('models', 'services', 'scripts'))


def test_migration_does_not_claim_or_activate_historical_owner():
    source = MIGRATION.read_text()
    assert 'INSERT INTO {q}.staff_authority (tenant_id,registration_id)' in source
    assert 'owner_email' not in source
    assert "SET is_active" not in source
    assert 'owner_user_id=:u' not in source
    assert 'staff_memberships' in source
    assert 'adjustment_requests' not in source
    assert 'stock_revision' not in source


def test_m1_authority_does_not_require_runtime_public_references():
    for path in (MIGRATION, BOOTSTRAP):
        source = path.read_text()
        assert 'registration_id UUID REFERENCES public.tenant_registrations' not in source
    migration = ast.parse(MIGRATION.read_text())
    assert 'REFERENCES {q}.users(id) ON DELETE RESTRICT' in literal_assignment(migration, 'TENANT_DDL')[0]


def test_audit_ddl_is_append_only_and_has_no_soft_delete():
    migration = ast.parse(MIGRATION.read_text())
    public = literal_assignment(migration, 'PUBLIC_DDL')
    audit_ddl = next(sql for sql in public if sql.startswith('CREATE TABLE public.staff_stock_audit_events'))
    assert 'is_deleted' not in audit_ddl and 'deleted_at' not in audit_ddl
    assert any('BEFORE UPDATE OR DELETE ON public.staff_stock_audit_events' in sql for sql in public)
    assert any('REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER' in sql for sql in public)


def test_repeated_grants_and_audit_revocation_share_one_transaction():
    tree = ast.parse((ROOT/'scripts/provision_runtime_db_roles.py').read_text())
    function = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
                    and n.name == 'apply_minimum_grants')
    protected = next(n for n in ast.walk(function) if isinstance(n, ast.AsyncWith)
                     and 'migrate.transaction()' in ast.unparse(n.items[0].context_expr))
    source = ast.unparse(protected)
    assert 'for sql in statements' in source
    assert 'REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER' in source
    assert 'staff_stock_audit_events' in source


def test_verified_owner_is_immutable_and_downgrade_refuses():
    migration = ast.parse(MIGRATION.read_text())
    tenant = literal_assignment(migration, 'TENANT_DDL')
    assert any("OLD.state='verified'" in sql and "RAISE EXCEPTION 'OWNER_PROTECTED'" in sql for sql in tenant)
    function = next(n for n in migration.body if isinstance(n, ast.FunctionDef) and n.name == 'downgrade')
    assert isinstance(function.body[0], ast.Raise)


def test_verified_shape_explicitly_rejects_unknown_null_branches():
    migration = ast.parse(MIGRATION.read_text())
    ddl = literal_assignment(migration, 'TENANT_DDL')[0]
    assert 'source IS NOT NULL AND evidence_digest IS NOT NULL' in ddl
    from models.staff_approval import StaffAuthority
    shape = next(c for c in StaffAuthority.__table__.constraints if c.name == 'ck_staff_authority_shape')
    assert 'source IS NOT NULL AND evidence_digest IS NOT NULL' in str(shape.sqltext)


def test_check_normalization_keeps_boolean_grouping_and_null_gates():
    from scripts.bootstrap_tenant_schema import _staff_check_tree
    assert _staff_check_tree("(source IS NOT NULL AND state='verified') OR state='unmapped'") != _staff_check_tree(
        "source IS NOT NULL AND (state='verified' OR state='unmapped')")
    assert _staff_check_tree("source IN ('owner_setup','approved_mapping')") == _staff_check_tree(
        "((source)::text = ANY ((ARRAY['owner_setup'::character varying,'approved_mapping'::character varying])::text[]))")
    assert _staff_check_tree("email=lower(btrim(email)) AND email NOT LIKE '% %'") == _staff_check_tree(
        "(((email)::text = lower(btrim((email)::text))) AND ((email)::text !~~ '% %'::text))")


def test_orm_active_staff_token_uniqueness_matches_migration():
    from models.staff_approval import StaffCredentialSetupToken
    index = next(i for i in StaffCredentialSetupToken.__table__.indexes if i.name == 'ux_staff_token_active')
    assert index.unique
    assert [c.name for c in index.columns] == ['tenant_id','user_id']
    assert str(index.dialect_options['postgresql']['where']) == 'used_at IS NULL AND revoked_at IS NULL'


@pytest.mark.asyncio
async def test_native_owner_setup_binds_exact_current_user_and_unregistered_stays_unmapped(staff_world):
    from services.staff_management_service import StaffManagementService
    async with staff_world.session() as db:
        row=(await db.execute(text('SELECT * FROM staff_authority'))).mappings().one()
        assert row['state']=='verified' and row['owner_user_id']==staff_world.actor
        assert row['tenant_id']==staff_world.wid and row['registration_id']==staff_world.registration
        assert row['source']=='owner_setup' and len(row['evidence_digest'])==64
        await StaffManagementService(db,staff_world.wid,staff_world.schema).require_owner(staff_world.actor)
        row=(await db.execute(text('SELECT state,owner_user_id FROM t_test.staff_authority'))).one()
        assert tuple(row)==('unmapped',None)


@pytest.mark.asyncio
@pytest.mark.parametrize('column',['source','evidence_digest'])
async def test_verified_owner_pg_null_is_rejected_and_unmapped_is_legal(staff_world,column):
    from sqlalchemy.exc import IntegrityError
    async with staff_world.session() as db:
        # Owner immutable trigger would mask the CHECK. A task-owned empty
        # history row provides a real unmapped -> invalid-verified transition.
        q='"'+staff_world.schema+'"'
        before=(await db.execute(text('SELECT state,owner_user_id FROM t_test.staff_authority'))).one()
        with pytest.raises(IntegrityError) as caught:
            async with db.begin_nested():
                await db.execute(text(
                    'UPDATE t_test.staff_authority SET tenant_id=:t,registration_id=:r,owner_user_id=:u,'
                    "state='verified',source=:s,evidence_digest=:d"),
                    {'t':staff_world.wid,'r':staff_world.registration,'u':staff_world.actor,
                     's':None if column=='source' else 'approved_mapping','d':None if column=='evidence_digest' else 'a'*64})
        assert 'ck_staff_authority_shape' in str(caught.value)
        assert tuple((await db.execute(text('SELECT state,owner_user_id FROM t_test.staff_authority'))).one())==tuple(before)


@pytest.mark.asyncio
@pytest.mark.parametrize('damage',['check','index','trigger'])
async def test_native_bootstrap_rejects_catalog_damage_without_resetting_history(staff_world,damage):
    from scripts.bootstrap_tenant_schema import _reconcile_staff_authority
    if damage=='index':
        # The public partial index is migration-owned. DDL is deliberately not
        # executed as app; the rejecting bootstrap below still runs as app.
        import os
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool
        url=os.environ['MPANGO_INVARIANTS_R0_MIGRATION_DATABASE_URL'].replace('postgresql://','postgresql+asyncpg://',1)
        engine=create_async_engine(url,poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text('DROP INDEX public.ux_staff_token_active'))
            try:
                async with staff_world.session() as db:
                    with pytest.raises(RuntimeError,match='STAFF_BOOTSTRAP_INDEX_MISMATCH'):
                        await _reconcile_staff_authority(db,staff_world.schema)
            finally:
                async with engine.begin() as connection:
                    await connection.execute(text('CREATE UNIQUE INDEX ux_staff_token_active ON public.staff_credential_setup_tokens(tenant_id,user_id) WHERE used_at IS NULL AND revoked_at IS NULL'))
        finally:
            await engine.dispose()
        return
    async with staff_world.session() as db:
        before=(await db.execute(text('SELECT row_to_json(a)::text FROM staff_authority a'))).scalar_one()
        async with db.begin_nested() as rollback:
            if damage=='check':
                await db.execute(text('ALTER TABLE staff_authority DROP CONSTRAINT ck_staff_authority_shape'))
            else:
                await db.execute(text('DROP TRIGGER staff_owner_immutable ON staff_authority'))
            with pytest.raises(RuntimeError,match='STAFF_BOOTSTRAP_(CONSTRAINT|INDEX|TRIGGER)_MISMATCH'):
                await _reconcile_staff_authority(db,staff_world.schema)
            assert (await db.execute(text('SELECT row_to_json(a)::text FROM staff_authority a'))).scalar_one()==before
            await rollback.rollback()


@pytest.mark.asyncio
async def test_native_bootstrap_repeat_preserves_owner_and_versions(staff_world):
    from scripts.bootstrap_tenant_schema import _reconcile_staff_authority
    async with staff_world.session() as db:
        before=(await db.execute(text('SELECT row_to_json(a)::text FROM staff_authority a'))).scalar_one()
        await _reconcile_staff_authority(db,staff_world.schema)
        await _reconcile_staff_authority(db,staff_world.schema)
        assert (await db.execute(text('SELECT row_to_json(a)::text FROM staff_authority a'))).scalar_one()==before


@pytest.mark.asyncio
async def test_actual_042_history_upgrade_and_repeated_grants_preserve_native_authority(tmp_path):
    """One explicitly owned temporary DB on the same verified task cluster."""
    import os
    import json
    import subprocess
    import sys
    from uuid import uuid4
    import psycopg2
    from psycopg2 import sql
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from tests.mpango_invariants_r0_support import verify_task_database_ownership_sync
    verify_task_database_ownership_sync()
    base='1d31a6bb9c02036b04827d168d9c7b720e9945b7'
    admin=os.environ['MPANGO_INVARIANTS_R0_ADMIN_DATABASE_URL']
    migrate=make_url(os.environ['MPANGO_INVARIANTS_R0_MIGRATION_DATABASE_URL'])
    runtime=make_url(os.environ['TEST_DATABASE_URL'])
    name='test_m1_upgrade_'+uuid4().hex
    root=Path(os.environ['STAFF_M1_PRIVATE_DIR'])
    receipt=root/(name+'.json')
    record={'database':name,'source_base':base,'same_cluster_as_verified_task':True,'calls':[]}
    def save():
        receipt.write_text(json.dumps(record,indent=2)+'\n')
        os.chmod(receipt,0o600)
    def call(label,argv,env):
        import time
        start=time.monotonic()
        result=subprocess.run(argv,cwd=ROOT,env=env,capture_output=True,timeout=90)
        for stream,data in (('stdout',result.stdout),('stderr',result.stderr)):
            path=root/(name+'-'+label+'.'+stream)
            path.write_bytes(data)
            os.chmod(path,0o600)
        record['calls'].append({'label':label,'argv':argv,'rc':result.returncode,'seconds':time.monotonic()-start})
        save()
        assert result.returncode==0, 'M1_UPGRADE_STAGE_FAILED:'+label
    save()
    connection=psycopg2.connect(admin)
    connection.autocommit=True
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(name),sql.Identifier(migrate.username)))
    record['created']=True
    save()
    app_engine=None
    try:
        migrate_url=migrate.set(database=name).render_as_string(hide_password=False)
        app_url=runtime.set(database=name).render_as_string(hide_password=False)
        env={**os.environ,'DATABASE_URL':migrate_url,
            'MPANGO_DB_ADMIN_URL':admin,'MPANGO_DB_MIGRATE_URL':migrate_url,'MPANGO_DB_APP_URL':app_url}
        call('alembic042',[sys.executable,'-B','-m','alembic','upgrade','042_order_negotiation_proposals'],env)
        provisioner=str(ROOT/'scripts/provision_runtime_db_roles.py')
        call('grants042',[sys.executable,'-B',provisioner,'--apply-grants'],env)
        predecessor=subprocess.check_output(['git','show',base+':backend/scripts/bootstrap_tenant_schema.py'],cwd=ROOT)
        predecessor_path=tmp_path/'bootstrap042.py'
        predecessor_path.write_bytes(predecessor)
        app_engine=create_async_engine(app_url.replace('postgresql://','postgresql+asyncpg://',1),poolclass=NullPool)
        schemas=[]
        snapshots={}
        for soft_deleted in (False,True):
            wid,registration=uuid4(),uuid4()
            schema='t_'+wid.hex
            schemas.append((schema,wid,registration))
            code='M1UP'+uuid4().hex[:12].upper()
            async with app_engine.begin() as db:
                await db.execute(text("INSERT INTO public.wholesalers (id,code,name) VALUES (:w,:c,'M1 actual042')"),{'w':wid,'c':code})
                await db.execute(text("INSERT INTO public.tenant_registrations "
                    "(id,company_name,tenant_code,country,owner_email,status,expires_at,wholesaler_id,tenant_schema,password_hash_cleared_at) "
                    "VALUES (:r,'M1 actual042',:c,'KE',:e,'active',now()+interval '1 day',:w,:s,now())"),
                    {'r':registration,'c':code,'w':wid,'s':schema,'e':uuid4().hex+'@example.com'})
            call('bootstrap042-'+wid.hex,[sys.executable,'-B',str(predecessor_path),schema],{**env,'DATABASE_URL':app_url})
            async with app_engine.begin() as db:
                await db.execute(text(f'SET LOCAL search_path TO "{schema}",public'))
                await db.execute(text("INSERT INTO users (email,password_hash,is_active) VALUES (:e,'unusable-before-proof',TRUE)"),{'e':uuid4().hex+'@example.com'})
                await db.execute(text("INSERT INTO roles (name,is_deleted) VALUES ('legacy-live',FALSE),('legacy-deleted',TRUE)"))
                await db.execute(text("INSERT INTO permissions (code,description,is_deleted) VALUES ('orders:update','Legacy update',:d) ON CONFLICT(code) DO UPDATE SET is_deleted=:d"),{'d':soft_deleted})
                await db.execute(text("INSERT INTO role_permissions (role_id,permission_id) SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.name LIKE 'legacy-%' AND p.code='orders:update'"))
                snapshots[schema]=list((await db.execute(text('SELECT row_to_json(u)::text FROM users u ORDER BY id'))).scalars())
        call('alembic043',[sys.executable,'-B','-m','alembic','upgrade','043_staff_authority_and_credentials'],env)
        call('grants043a',[sys.executable,'-B',provisioner,'--apply-grants'],env)
        call('grants043b',[sys.executable,'-B',provisioner,'--apply-grants'],env)
        call('verify043',[sys.executable,'-B',provisioner,'--verify'],env)
        from scripts.bootstrap_tenant_schema import _reconcile_staff_authority
        for index,(schema,wid,registration) in enumerate(schemas):
            async with app_engine.begin() as db:
                await db.execute(text(f'SET LOCAL search_path TO "{schema}",public'))
                assert list((await db.execute(text('SELECT row_to_json(u)::text FROM users u ORDER BY id'))).scalars())==snapshots[schema]
                authority=(await db.execute(text('SELECT state,owner_user_id,authz_revision FROM staff_authority'))).one()
                assert tuple(authority)==('unmapped',None,1),'M1_UPGRADE_MUST_NOT_CLAIM_OWNER'
                await _reconcile_staff_authority(db,schema)
                await _reconcile_staff_authority(db,schema)
                actions=list((await db.execute(text("SELECT p.code FROM permissions p JOIN role_permissions rp ON rp.permission_id=p.id JOIN roles r ON r.id=rp.role_id WHERE r.name='legacy-live' AND p.code IN ('orders:confirm','orders:ship','orders:cancel','orders:return') ORDER BY p.code"))).scalars())
                assert len(actions)==(4 if index==0 else 0),'M1_UPGRADE_SOFT_DELETE_RESTORED'
                assert await db.scalar(text("SELECT count(*) FROM role_permissions rp JOIN roles r ON r.id=rp.role_id JOIN permissions p ON p.id=rp.permission_id WHERE r.name='legacy-deleted' AND p.code IN ('orders:confirm','orders:ship','orders:cancel','orders:return')"))==0
                assert not await db.scalar(text("SELECT has_schema_privilege(current_user,'public','CREATE')"))
                uid=await db.scalar(text('SELECT id FROM users LIMIT 1'))
                await db.execute(text("INSERT INTO public.staff_stock_audit_events (tenant_id,actor_id,event_type,subject_id,details) VALUES (:t,:u,'upgrade_probe',:u,'{}')"),{'t':wid,'u':uid})
                from sqlalchemy.exc import DBAPIError
                for statement in ('UPDATE public.staff_stock_audit_events SET event_type=event_type','DELETE FROM public.staff_stock_audit_events'):
                    with pytest.raises(DBAPIError):
                        async with db.begin_nested(): await db.execute(text(statement))
        # Preserve the real nonempty 043 stage above, then upgrade its exact
        # users, Owner evidence and manual stock history to 044.
        history={}
        for schema,wid,registration in schemas:
            async with app_engine.begin() as db:
                await db.execute(text(f'SET LOCAL search_path TO "{schema}",public'))
                uid=await db.scalar(text('SELECT id FROM users LIMIT 1'))
                await db.execute(text("UPDATE staff_authority SET owner_user_id=:u,state='verified',source='approved_mapping',evidence_digest=:d,authz_revision=7 WHERE singleton=1"),
                    {'u':uid,'d':__import__('hashlib').sha256(str(registration).encode()).hexdigest()})
                product=await db.scalar(text("INSERT INTO catalog_products(name,is_active) VALUES ('Retained 043 stock',true) RETURNING id"))
                sku=await db.scalar(text("INSERT INTO skus(catalog_product_id,sku_code,name,unit,package_quantity,is_active,base_price) VALUES (:p,'UPGRADE-BOX','Retained 043 stock','box',1,true,1) RETURNING id"),{'p':product})
                await db.execute(text('INSERT INTO inventory_stocks(sku_id,quantity_on_hand,quantity_reserved) VALUES (:s,100,0)'),{'s':sku})
                await db.execute(text("INSERT INTO inventory_movements(sku_id,movement_type,quantity,quantity_before,quantity_after,reference_type) VALUES (:s,'adjustment',100,0,100,'manual')"),{'s':sku})
                history[schema]={table:list((await db.execute(text(f'SELECT to_jsonb(t)::text FROM {table} t ORDER BY id'))).scalars())
                                 for table in ('users','inventory_stocks','inventory_movements')}
        call('alembic044',[sys.executable,'-B','-m','alembic','upgrade','044_inventory_adjustment_approval'],env)
        call('grants044',[sys.executable,'-B',provisioner,'--apply-grants'],env)
        call('verify044',[sys.executable,'-B',provisioner,'--verify'],env)
        from scripts.bootstrap_tenant_schema import _reconcile_stock_approval
        for schema,wid,registration in schemas:
            async with app_engine.begin() as db:
                await db.execute(text(f'SET LOCAL search_path TO "{schema}",public'))
                await _reconcile_staff_authority(db,schema)
                await _reconcile_stock_approval(db,schema)
                assert await db.scalar(text('SELECT authz_revision FROM staff_authority'))==7
                assert await db.scalar(text('SELECT policy_version FROM staff_authority'))==1
                assert await db.scalar(text('SELECT owner_direct_enabled FROM staff_authority')) is True
                assert await db.scalar(text('SELECT count(*) FROM inventory_adjustment_approvers'))==1
                assert await db.scalar(text('SELECT count(*) FROM inventory_adjustment_requests'))==0
                for table,added in [('users',None),('inventory_stocks','stock_revision'),('inventory_movements','manual_adjustment_id')]:
                    expression='to_jsonb(t)' if added is None else "to_jsonb(t)-'"+added+"'"
                    assert list((await db.execute(text(f'SELECT ({expression})::text FROM {table} t ORDER BY id'))).scalars())==history[schema][table]
                assert await db.scalar(text('SELECT stock_revision FROM inventory_stocks'))==1
        record['result']='PASS'
        record['044_nonempty_history_preserved']=True
    finally:
        if app_engine is not None: await app_engine.dispose()
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s",(name,))
            assert cursor.fetchone()==(migrate.username,),'M1_UPGRADE_CLEANUP_OWNER_MISMATCH'
            cursor.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
        connection.close()
        record['dropped_exact_owned_database']=True
        save()


@pytest.mark.asyncio
async def test_approved_historical_binding_tool_exact_identity_dry_run_and_negative_matrix():
    from argparse import Namespace
    from uuid import uuid4
    from fastapi import HTTPException
    from services.staff_management_service import StaffManagementService
    from scripts.bind_staff_owner import bind
    from tests.staff_approval_support import StaffWorld
    world=StaffWorld()
    try:
        await world.initialize(bind_owner=False)
        uid,_email=await world.add_user()
        args=Namespace(tenant_id=world.wid,registration_id=world.registration,schema=world.schema,
            user_id=uid,approval_sha256='b'*64,apply=False)
        async with world.session() as db:
            before=await db.scalar(text('SELECT row_to_json(a)::text FROM staff_authority a'))
            with pytest.raises(HTTPException,match='OWNER_MAPPING_REQUIRED'):
                await StaffManagementService(db,world.wid,world.schema).require_owner(uid)
        assert (await bind(args))['action']=='would_bind'
        async with world.session() as db:
            assert await db.scalar(text('SELECT row_to_json(a)::text FROM staff_authority a'))==before,'M1_DRY_RUN_WROTE_OWNER'
        invalids=(
            {'registration_id':uuid4()}, {'tenant_id':uuid4()}, {'user_id':uuid4()},
            {'approval_sha256':''},
        )
        for changes in invalids:
            with pytest.raises((HTTPException,RuntimeError)):
                await bind(Namespace(**{**vars(args),**changes}))
        async with world.session() as db:
            async with db.begin_nested() as checkpoint:
                await db.execute(text('UPDATE public.tenant_registrations SET is_deleted=TRUE WHERE id=:r'),{'r':world.registration})
                with pytest.raises(HTTPException):
                    await StaffManagementService(db,world.wid,world.schema).bind_owner(registration_id=world.registration,
                        user_id=uid,source='approved_mapping',evidence_digest='b'*64,dry_run=False)
                await checkpoint.rollback()
            for bad_state in ('disabled','customer'):
                async with db.begin_nested() as checkpoint:
                    if bad_state=='disabled':
                        await db.execute(text('UPDATE users SET is_active=FALSE WHERE id=:u'),{'u':uid})
                    else:
                        await db.execute(text('UPDATE public.wholesaler_retailer_bindings SET tenant_user_id=:u WHERE wholesaler_id=:t'),{'u':uid,'t':world.wid})
                    with pytest.raises(HTTPException):
                        await StaffManagementService(db,world.wid,world.schema).bind_owner(registration_id=world.registration,
                            user_id=uid,source='approved_mapping',evidence_digest='b'*64,dry_run=False)
                    await checkpoint.rollback()
        args.apply=True
        assert (await bind(args))['action']=='bound'
        async with world.session() as db:
            row=(await db.execute(text('SELECT owner_user_id,source FROM staff_authority'))).one()
            assert tuple(row)==(uid,'approved_mapping'),'M1_HISTORICAL_TOOL_WRONG_OWNER'
            assert await db.scalar(text("SELECT count(*) FROM public.staff_stock_audit_events WHERE tenant_id=:t AND event_type='owner_bound'"),{'t':world.wid})==1
    finally:
        if hasattr(world,'engine'): await world.engine.dispose()
